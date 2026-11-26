"""``history.db`` — the manifest of a project's drafts and branches.

The manifest is its own file because ``story.db`` is overwritten when the user
switches branch: the record of what the drafts WERE cannot live in the thing that
gets replaced. It follows ``chat.db``: its own baseline, migration list and
version stamp, created on first touch.

The live ``story.db`` is the working copy of the CURRENT branch's head. Every
other branch's head is parked at ``history/heads/<branch_id>.db``, and every
draft is frozen at ``history/snapshots/<snapshot_id>.db``.

What a branch records is its latest frozen draft (``base_snapshot_id``): the head
is "that draft plus whatever has been done since". A draft's parents are in
``snapshot_parents`` — its base, plus any branch pending a complete merge (§7.9),
which the next save turns into a second parent.

The lock: every operation takes ``BEGIN IMMEDIATE`` on the manifest, which
serialises history operations against each other and across processes, and holds
it over the file moves so no second caller can see half a switch.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .. import clock
from ..backups import check_source, load_database_in_place
from ..db import apply_migrations, get_db, transaction
from . import fingerprint

SCHEMA = """
CREATE TABLE IF NOT EXISTS branches (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL UNIQUE,
    base_snapshot_id      TEXT NOT NULL,
    is_current            INTEGER NOT NULL DEFAULT 0,
    created_at            TEXT NOT NULL,
    pending_merge_parents JSON
);
-- Exactly one current branch. The head is the live story.db, so two would mean
-- two answers to where the user is working.
CREATE UNIQUE INDEX IF NOT EXISTS idx_branches_current ON branches(is_current) WHERE is_current=1;

CREATE TABLE IF NOT EXISTS snapshots (
    id             TEXT PRIMARY KEY,
    branch_id      TEXT NOT NULL,
    seq            INTEGER NOT NULL,
    label          TEXT NOT NULL DEFAULT '',
    note           TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    fingerprint    TEXT NOT NULL,
    counts         JSON
);

CREATE TABLE IF NOT EXISTS snapshot_parents (
    snapshot_id TEXT NOT NULL,
    parent_id   TEXT NOT NULL,
    ord         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (snapshot_id, parent_id)
);

CREATE TABLE IF NOT EXISTS merge_sessions (
    id                 TEXT PRIMARY KEY,
    target_branch_id   TEXT NOT NULL,
    source_ref         JSON NOT NULL,
    base_snapshot_id   TEXT,
    target_fingerprint TEXT,
    selection          JSON,
    decisions          JSON,
    status             TEXT NOT NULL DEFAULT 'open',
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
"""

BASELINE = 1
MIGRATIONS: list = []
LATEST = BASELINE + len(MIGRATIONS)

# A draft's file is frozen: a write attempt fails loudly instead of silently
# rewriting a draft someone is reading. The directory still allows deleting it.
FROZEN_MODE = 0o444

FIRST_BRANCH_NAME = "main"
FIRST_SNAPSHOT_LABEL = "Draft 1"

_BRANCH_COLUMNS = "id, name, base_snapshot_id, is_current, created_at, pending_merge_parents"
_SNAPSHOT_COLUMNS = (
    "id, branch_id, seq, label, note, created_at, schema_version, fingerprint, counts"
)


def _now() -> str:
    return clock.now_iso()


# ─── layout ───


def history_path(project_path: Path) -> Path:
    return project_path / ".story" / "history.db"


def snapshots_dir(project_path: Path) -> Path:
    return project_path / ".story" / "history" / "snapshots"


def heads_dir(project_path: Path) -> Path:
    return project_path / ".story" / "history" / "heads"


def snapshot_file(project_path: Path, snapshot_id: str) -> Path:
    return snapshots_dir(project_path) / f"{snapshot_id}.db"


def head_file(project_path: Path, branch_id: str) -> Path:
    return heads_dir(project_path) / f"{branch_id}.db"


def connect(project_path: Path) -> sqlite3.Connection:
    """Open the manifest, creating it current-shaped on first touch."""
    p = history_path(project_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    conn.execute("PRAGMA foreign_keys=ON")
    if conn.execute("PRAGMA user_version").fetchone()[0] != LATEST:
        try:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone():
                apply_migrations(conn, MIGRATIONS, baseline=BASELINE, name="history.db")
            else:
                conn.executescript(SCHEMA)
                conn.execute(f"PRAGMA user_version = {LATEST}")
        except Exception:
            conn.close()
            raise
    return conn


@contextmanager
def locked(project_path: Path):
    """Yield a manifest connection holding the write lock for the whole block.

    ``BEGIN IMMEDIATE`` up front, not at the first write: these operations read,
    then move files, then write, and a lock taken at the first write would let a
    second caller pass its checks against a state the first is about to change.
    Held over the file moves too, so no caller sees a switch half done.
    """
    conn = connect(project_path)
    try:
        with transaction(conn):
            yield conn
    finally:
        conn.close()


# ─── ids and names ───


def _slugify(name: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def _branch_id(conn: sqlite3.Connection, name: str) -> str:
    """A branch id slugged from its name, unused. The id survives a rename."""
    slug = _slugify(name) or "branch"
    candidate, n = slug, 1
    while conn.execute("SELECT 1 FROM branches WHERE id=?", (candidate,)).fetchone():
        n += 1
        candidate = f"{slug}-{n}"
    return candidate


def _branch_name(conn: sqlite3.Connection, name: str, *, skip_id: str | None = None) -> str:
    """Check a branch name is usable. Names are unique; the id is not the name."""
    clean = (name or "").strip()
    if not clean:
        raise ValueError("A branch needs a name.")
    row = conn.execute("SELECT id FROM branches WHERE name=?", (clean,)).fetchone()
    if row and row[0] != skip_id:
        raise ValueError(f"There is already a branch called {clean!r}. Pick another name.")
    return clean


def _new_snapshot_id(conn: sqlite3.Connection) -> str:
    """An unused snapshot id: its timestamp, plus a counter within that second.

    Two saves in one second would otherwise collide, and the second would
    overwrite the first's file.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate, n = f"s-{stamp}", 1
    while conn.execute("SELECT 1 FROM snapshots WHERE id=?", (candidate,)).fetchone():
        n += 1
        candidate = f"s-{stamp}-{n}"
    return candidate


# ─── reading ───


def _branch_row(row) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "base_snapshot_id": row[2],
        "is_current": bool(row[3]),
        "created_at": row[4],
        "pending_merge_parents": json.loads(row[5] or "[]"),
    }


def _snapshot_row(row) -> dict:
    return {
        "id": row[0],
        "branch_id": row[1],
        "seq": row[2],
        "label": row[3],
        "note": row[4],
        "created_at": row[5],
        "schema_version": row[6],
        "fingerprint": row[7],
        "counts": json.loads(row[8] or "{}"),
    }


def _branch(conn: sqlite3.Connection, branch_id: str) -> dict:
    row = conn.execute(
        f"SELECT {_BRANCH_COLUMNS} FROM branches WHERE id=?", (branch_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"No such branch: {branch_id}.")
    return _branch_row(row)


def _snapshot(conn: sqlite3.Connection, snapshot_id: str) -> dict | None:
    row = conn.execute(
        f"SELECT {_SNAPSHOT_COLUMNS} FROM snapshots WHERE id=?", (snapshot_id,)
    ).fetchone()
    return _snapshot_row(row) if row else None


def _current(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(f"SELECT {_BRANCH_COLUMNS} FROM branches WHERE is_current=1").fetchone()
    return _branch_row(row) if row else None


def list_branches(project_path: Path) -> dict:
    """Every branch and every draft, with parents — what the graph draws."""
    conn = connect(project_path)
    try:
        branches = [
            _branch_row(r)
            for r in conn.execute(f"SELECT {_BRANCH_COLUMNS} FROM branches ORDER BY created_at, id")
        ]
        parents: dict[str, list] = {}
        for snapshot_id, parent_id in conn.execute(
            "SELECT snapshot_id, parent_id FROM snapshot_parents ORDER BY snapshot_id, ord"
        ):
            parents.setdefault(snapshot_id, []).append(parent_id)
        snapshots = []
        for r in conn.execute(f"SELECT {_SNAPSHOT_COLUMNS} FROM snapshots ORDER BY created_at, id"):
            snap = _snapshot_row(r)
            snap["parents"] = parents.get(snap["id"], [])
            snapshots.append(snap)
        return {"branches": branches, "snapshots": snapshots}
    finally:
        conn.close()


def head_state(project_path: Path) -> dict:
    """What the live database holds now, and what the current branch last saved."""
    conn = connect(project_path)
    try:
        branch = _current(conn)
        base = _snapshot(conn, branch["base_snapshot_id"]) if branch else None
    finally:
        conn.close()
    live = fingerprint.of_project(project_path)
    return {
        "branch": branch,
        "base": base,
        "fingerprint": live,
        "changed": bool(base) and live != base["fingerprint"],
    }


def merge_base(project_path: Path, target_snapshot_id: str, source_snapshot_id: str) -> dict:
    """The most recent draft both sides descend from — a merge's base (§7.1).

    Walks `snapshot_parents` from each side. The candidates are the source's reachable
    ancestors that the target also reaches; the base is the one whose longest distance
    from its own side is smallest, so a cherry-picked source can never beat a real
    shared ancestor. Several candidates at the same distance means a criss-cross
    history: one is taken and `imprecise` says so, rather than a recursive merge
    (§14-F).

    A missing ancestor is not an error: every project descends from its first draft, so
    two drafts of one project always meet. `base is None` means only that a caller
    passed a draft from another project, which the caller refuses.
    """
    conn = connect(project_path)
    try:
        known = {r[0] for r in conn.execute("SELECT id FROM snapshots")}
        if target_snapshot_id not in known or source_snapshot_id not in known:
            missing = [s for s in (target_snapshot_id, source_snapshot_id) if s not in known]
            raise ValueError(f"No such draft: {', '.join(missing)}.")
        distance = _ancestor_distances(conn)
    finally:
        conn.close()

    def nearest(snapshot_id: str) -> dict:
        found, frontier, depth = {}, [snapshot_id], 0
        while frontier:
            for sid in frontier:
                found.setdefault(sid, depth)
            frontier = [p for sid in frontier for p in distance.get(sid, ()) if p not in found]
            depth += 1
        return found

    ours, theirs = nearest(target_snapshot_id), nearest(source_snapshot_id)
    shared = set(ours) & set(theirs)
    if not shared:
        return {"base": None, "imprecise": False}
    scored = sorted(shared, key=lambda s: (max(ours[s], theirs[s]), ours[s], s))
    best = max(ours[scored[0]], theirs[scored[0]])
    tied = [s for s in scored if max(ours[s], theirs[s]) == best]
    return {"base": scored[0], "imprecise": len(tied) > 1}


def _ancestor_distances(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Every draft's direct parents, for the ancestor walk."""
    out: dict[str, list[str]] = {}
    for snapshot_id, parent_id in conn.execute(
        "SELECT snapshot_id, parent_id FROM snapshot_parents"
    ):
        out.setdefault(snapshot_id, []).append(parent_id)
    return out


# ─── files ───


def _open_source(source: Path, *, frozen: bool) -> sqlite3.Connection:
    """Open a database to copy FROM, seeing every committed write.

    A live database keeps its latest commits in ``-wal`` until a checkpoint, and an
    ``immutable`` open ignores that file: it would copy the database as it was at the
    last checkpoint and silently drop the rest. So a live source is opened ``mode=ro``,
    which reads the ``-wal``.

    A frozen draft is the opposite case: it has no ``-wal`` (see `_write_atomic`), and a
    ``mode=ro`` open would create one beside a file nothing may touch. It is opened
    ``immutable``, which leaves no sidecar.
    """
    if frozen:
        return sqlite3.connect(f"file:{source}?mode=ro&immutable=1", uri=True)
    return sqlite3.connect(f"file:{source}?mode=ro", uri=True)


def _write_atomic(src: sqlite3.Connection, dest: Path, *, compact: bool) -> None:
    """Copy `src` to `dest` through SQLite, atomically.

    The copy goes under a `.partial` name and is renamed only when complete, so a
    crash or a full disk leaves no file that looks like a draft but is not. WAL is
    the reason it is `Connection.backup()` and not a file copy: committed writes
    can still be in `story.db-wal`, and a plain copy would silently produce a
    stale draft. `compact` drops the staged proposals (they belong to the head
    they were made on) and vacuums.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, partial = tempfile.mkstemp(prefix=".partial-", suffix=".db", dir=str(dest.parent))
    os.close(fd)
    try:
        out = sqlite3.connect(partial, isolation_level=None)
        try:
            src.backup(out)
            if compact:
                out.execute("DELETE FROM drafts")
                out.execute("VACUUM")
        finally:
            out.close()
        os.replace(partial, dest)
    except BaseException:
        Path(partial).unlink(missing_ok=True)
        raise


def _freeze(project_path: Path, snapshot_id: str, *, source: Path | None = None) -> Path:
    """Write a draft's frozen file.

    From the live database by default (a save), or from an existing frozen file (a
    branch's head: the branch starts as an exact copy of the draft it grew from).
    """
    dest = snapshot_file(project_path, snapshot_id)
    src = get_db(project_path) if source is None else _open_source(source, frozen=True)
    try:
        _write_atomic(src, dest, compact=source is None)
    finally:
        src.close()
    _drop_sidecars(dest)
    os.chmod(dest, FROZEN_MODE)
    return dest


def _drop_sidecars(path: Path) -> None:
    """Remove `-wal`/`-shm` debris beside a draft.

    SQLite creates them in read-write mode *before* it discovers the file is
    read-only, so a bug that opens a draft for writing leaves two empty files
    behind. Nothing reads a draft read-write (that is what `ProjectView` copies
    for), so this only ever sweeps debris — but debris beside a frozen draft is
    exactly what would make a later reader open a stale view of it.
    """
    for sidecar in path.parent.glob("*-wal"):
        sidecar.unlink(missing_ok=True)
    for sidecar in path.parent.glob("*-shm"):
        sidecar.unlink(missing_ok=True)


def _park(project_path: Path, src: Path, dest: Path, *, frozen: bool = False) -> None:
    """Copy a database to a parked-head path, atomically.

    `frozen` says whether `src` is a file written and closed by `_write_atomic` (a
    draft) or a database still being written (the live head). See `_open_source`.
    """
    handle = _open_source(src, frozen=frozen)
    try:
        _write_atomic(handle, dest, compact=False)
    finally:
        handle.close()
    _drop_sidecars(dest)


# ─── adoption ───


def _counts(conn: sqlite3.Connection) -> dict:
    """What a draft holds, for the landing page, without opening its file."""
    return {
        t: n
        for t, n in conn.execute(
            "SELECT type, count(*) FROM entities WHERE is_deleted=0 GROUP BY type"
        )
    }


def _adopt(project_path: Path, conn: sqlite3.Connection) -> dict:
    """Give a project with no manifest its first branch and draft.

    Lazy: the first call that touches history writes down the state it found.
    A project that predates this feature needs no migration — it has exactly the
    state it has, and that state becomes Draft 1.
    """
    existing = _current(conn)
    if existing:
        return existing
    if conn.execute("SELECT 1 FROM branches LIMIT 1").fetchone():
        raise ValueError("history.db has branches but none is current. Pick one to switch to.")

    branch_id = _branch_id(conn, FIRST_BRANCH_NAME)
    snapshot_id = _new_snapshot_id(conn)
    _freeze(project_path, snapshot_id)

    project = get_db(project_path)
    try:
        version = project.execute("PRAGMA user_version").fetchone()[0]
        counts = _counts(project)
    finally:
        project.close()

    conn.execute(
        f"INSERT INTO snapshots ({_SNAPSHOT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            snapshot_id,
            branch_id,
            1,
            FIRST_SNAPSHOT_LABEL,
            "",
            _now(),
            version,
            fingerprint.of_project(project_path),
            json.dumps(counts),
        ),
    )
    conn.execute(
        f"INSERT INTO branches ({_BRANCH_COLUMNS}) VALUES (?,?,?,1,?,?)",
        (branch_id, FIRST_BRANCH_NAME, snapshot_id, _now(), json.dumps([])),
    )
    return _branch(conn, branch_id)


def adopt(project_path: Path) -> dict:
    """Ensure the project has a manifest with a current branch; return that branch."""
    with locked(project_path) as conn:
        return _adopt(project_path, conn)


# ─── operations ───


def _save(project_path: Path, conn: sqlite3.Connection, label: str | None, note: str) -> dict:
    """Freeze the head as a draft, on a manifest connection that already holds the lock."""
    branch = _adopt(project_path, conn)
    base = _snapshot(conn, branch["base_snapshot_id"])
    assert base is not None, "a branch's saved draft is never deleted"
    live = fingerprint.of_project(project_path)
    if live == base["fingerprint"]:
        raise ValueError(
            f"Nothing has changed since {base['label']}. A draft has to be a different "
            "state from the one before it."
        )

    snapshot_id = _new_snapshot_id(conn)
    _freeze(project_path, snapshot_id)

    project = get_db(project_path)
    try:
        version = project.execute("PRAGMA user_version").fetchone()[0]
        counts = _counts(project)
    finally:
        project.close()

    seq = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) + 1 FROM snapshots WHERE branch_id=?", (branch["id"],)
    ).fetchone()[0]
    conn.execute(
        f"INSERT INTO snapshots ({_SNAPSHOT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            snapshot_id,
            branch["id"],
            seq,
            (label or f"Draft {seq}").strip(),
            note,
            _now(),
            version,
            live,
            json.dumps(counts),
        ),
    )
    # Its parents: the draft it grew from, then any branch whose complete merge this
    # save is the first draft after (§7.9).
    parents = [base["id"]] + [p for p in branch["pending_merge_parents"] if p != base["id"]]
    for order, parent in enumerate(parents):
        conn.execute(
            "INSERT OR IGNORE INTO snapshot_parents (snapshot_id, parent_id, ord) VALUES (?,?,?)",
            (snapshot_id, parent, order),
        )
    conn.execute(
        "UPDATE branches SET base_snapshot_id=?, pending_merge_parents=? WHERE id=?",
        (snapshot_id, json.dumps([]), branch["id"]),
    )
    saved = _snapshot(conn, snapshot_id)
    assert saved is not None
    saved["parents"] = parents
    return saved


def save_snapshot(project_path: Path, label: str | None = None, note: str = "") -> dict:
    """Freeze the current head as a draft. Refuses when nothing has changed.

    The head is unchanged by a save — a draft is a copy of it — so nothing is
    copied back.
    """
    with locked(project_path) as conn:
        return _save(project_path, conn, label, note)


def restore_point(project_path: Path, conn: sqlite3.Connection, label: str) -> dict:
    """The draft a merge can be undone to, on a manifest lock the caller already holds.

    A head identical to its own saved draft has nothing to save — that draft IS this
    state — so it is returned rather than duplicated, with ``created`` saying which
    happened. A project this feature has never touched is adopted first: without a
    branch there is no draft to be the restore point.
    """
    branch = _adopt(project_path, conn)
    base = _snapshot(conn, branch["base_snapshot_id"])
    assert base is not None, "a branch's saved draft is never deleted"
    if fingerprint.of_project(project_path) == base["fingerprint"]:
        return {**base, "created": False}
    return {**_save(project_path, conn, label, ""), "created": True}


def record_pending_parent(
    project_path: Path, snapshot_id: str, *, conn: sqlite3.Connection | None = None
) -> dict:
    """Declare that a complete merge has accounted for `snapshot_id` (§7.9).

    Only a complete merge calls this: a recorded parent means "everything in it is
    already accounted for", so the next *Save draft* writes it as a second
    `snapshot_parents` row and clears the column. A cherry-pick records nothing and
    its unselected changes are offered again next time.

    Writes to `branches` only — no parent row here, or `save_snapshot` would write the
    same parent twice. `conn` is a manifest connection whose caller already holds the
    lock; the executor applies a plan under that lock, so this has to run inside it
    rather than take the manifest lock a second time and deadlock.
    """
    if conn is None:
        with locked(project_path) as held:
            return record_pending_parent(project_path, snapshot_id, conn=held)
    branch = _adopt(project_path, conn)
    if not _snapshot(conn, snapshot_id):
        raise ValueError(f"No such draft: {snapshot_id}.")
    pending = list(branch["pending_merge_parents"])
    if snapshot_id not in pending:
        pending.append(snapshot_id)
        conn.execute(
            "UPDATE branches SET pending_merge_parents=? WHERE id=?",
            (json.dumps(pending), branch["id"]),
        )
    return _branch(conn, branch["id"])


def branch_from(project_path: Path, snapshot_id: str, name: str) -> dict:
    """Start a branch at a draft; its head is parked, ready to switch to."""
    with locked(project_path) as conn:
        _adopt(project_path, conn)
        if not _snapshot(conn, snapshot_id):
            raise ValueError(f"No such draft: {snapshot_id}.")
        clean = _branch_name(conn, name)
        branch_id = _branch_id(conn, clean)
        source = snapshot_file(project_path, snapshot_id)
        if not source.exists():
            raise ValueError(f"Draft {snapshot_id} has no file on disk.")
        _park(project_path, source, head_file(project_path, branch_id), frozen=True)
        conn.execute(
            f"INSERT INTO branches ({_BRANCH_COLUMNS}) VALUES (?,?,?,0,?,?)",
            (branch_id, clean, snapshot_id, _now(), json.dumps([])),
        )
        return _branch(conn, branch_id)


def switch(project_path: Path, branch_id: str) -> dict:
    """Make a branch current, loading its head into the live database.

    The live database is parked as the outgoing branch's head first: that copy IS
    the pre-switch state and is addressable by branch name, so no separate safety
    backup is taken (it would evict a daily one from the 20-slot cap).

    Refused while the head has open staged drafts: those exist only in story.db
    and are deliberately not part of a draft, so the copy would destroy them.
    """
    with locked(project_path) as conn:
        current = _adopt(project_path, conn)
        target = _branch(conn, branch_id)
        if target["is_current"]:
            raise ValueError(f"Already on {target['name']}.")

        live = get_db(project_path)
        try:
            open_drafts = [
                r[0] for r in live.execute("SELECT id FROM drafts WHERE status='open' ORDER BY id")
            ]
        finally:
            live.close()
        if open_drafts:
            raise ValueError(
                f"This branch has open drafts ({', '.join(open_drafts)}). Commit or discard them "
                "before switching, or the proposals would be lost."
            )

        target_head = head_file(project_path, target["id"])
        if not target_head.exists():
            raise ValueError(f"Branch {target['name']!r} has no parked head to load.")
        check_source(target_head, f"branch {target['name']!r}")

        _park(
            project_path,
            project_path / ".story" / "story.db",
            head_file(project_path, current["id"]),
        )
        load_database_in_place(project_path, target_head, safety_label=None)
        conn.execute("UPDATE branches SET is_current=0 WHERE id=?", (current["id"],))
        conn.execute("UPDATE branches SET is_current=1 WHERE id=?", (target["id"],))
        # Its head is live now; a parked copy left behind would be a stale
        # duplicate for a later switch to load.
        target_head.unlink(missing_ok=True)
        return _branch(conn, target["id"])


def rename_branch(project_path: Path, branch_id: str, name: str) -> dict:
    """Change a branch's display name. Its id, files and history do not move."""
    with locked(project_path) as conn:
        _adopt(project_path, conn)
        branch = _branch(conn, branch_id)
        clean = _branch_name(conn, name, skip_id=branch["id"])
        conn.execute("UPDATE branches SET name=? WHERE id=?", (clean, branch["id"]))
        return _branch(conn, branch["id"])


def delete_branch(project_path: Path, branch_id: str) -> dict:
    """Delete a branch, its parked head, and every draft nothing else reaches."""
    with locked(project_path) as conn:
        _adopt(project_path, conn)
        branch = _branch(conn, branch_id)
        if branch["is_current"]:
            raise ValueError(
                f"{branch['name']!r} is the branch you are working on. Switch to another "
                "branch before deleting it."
            )
        conn.execute("DELETE FROM branches WHERE id=?", (branch["id"],))
        head_file(project_path, branch["id"]).unlink(missing_ok=True)
        return {
            "deleted": branch["id"],
            "snapshots_removed": _prune_unreachable(conn, project_path),
        }


def delete_snapshot(project_path: Path, snapshot_id: str) -> dict:
    """Delete one draft, re-attaching its children to its own parents."""
    with locked(project_path) as conn:
        _adopt(project_path, conn)
        snapshot = _snapshot(conn, snapshot_id)
        if not snapshot:
            raise ValueError(f"No such draft: {snapshot_id}.")
        holder = conn.execute(
            "SELECT name FROM branches WHERE base_snapshot_id=?", (snapshot_id,)
        ).fetchone()
        if holder:
            raise ValueError(
                f"{snapshot['label']} is what branch {holder[0]!r} has saved. A branch's latest "
                "draft cannot be deleted; delete the branch instead."
            )

        parents = [
            r[0]
            for r in conn.execute(
                "SELECT parent_id FROM snapshot_parents WHERE snapshot_id=? ORDER BY ord",
                (snapshot_id,),
            )
        ]
        children = [
            r[0]
            for r in conn.execute(
                "SELECT snapshot_id FROM snapshot_parents WHERE parent_id=? ORDER BY snapshot_id",
                (snapshot_id,),
            )
        ]
        # Children take this draft's parents, keeping their order. The graph stays
        # connected, and a later merge finds an older common ancestor — which shows
        # more conflicts, never a wrong result.
        conn.execute("DELETE FROM snapshot_parents WHERE snapshot_id=?", (snapshot_id,))
        for child in children:
            conn.execute(
                "DELETE FROM snapshot_parents WHERE snapshot_id=? AND parent_id=?",
                (child, snapshot_id),
            )
            for order, parent in enumerate(parents):
                conn.execute(
                    "INSERT OR IGNORE INTO snapshot_parents (snapshot_id, parent_id, ord) "
                    "VALUES (?,?,?)",
                    (child, parent, order),
                )
        conn.execute("DELETE FROM snapshots WHERE id=?", (snapshot_id,))
        snapshot_file(project_path, snapshot_id).unlink(missing_ok=True)
        return {"deleted": snapshot_id, "reparented": children}


def _reachable(conn: sqlite3.Connection) -> set:
    """Every draft reachable from a branch's saved state by following parents."""
    keep: set = set()
    stack = [r[0] for r in conn.execute("SELECT base_snapshot_id FROM branches")]
    while stack:
        current = stack.pop()
        if current in keep:
            continue
        keep.add(current)
        stack.extend(
            r[0]
            for r in conn.execute(
                "SELECT parent_id FROM snapshot_parents WHERE snapshot_id=?", (current,)
            )
        )
    return keep


def _prune_unreachable(conn: sqlite3.Connection, project_path: Path) -> list:
    """Remove every draft no branch can reach any more, and its file."""
    reachable = _reachable(conn)
    doomed = [r[0] for r in conn.execute("SELECT id FROM snapshots") if r[0] not in reachable]
    for snapshot_id in doomed:
        conn.execute("DELETE FROM snapshot_parents WHERE snapshot_id=?", (snapshot_id,))
        conn.execute("DELETE FROM snapshot_parents WHERE parent_id=?", (snapshot_id,))
        conn.execute("DELETE FROM snapshots WHERE id=?", (snapshot_id,))
        snapshot_file(project_path, snapshot_id).unlink(missing_ok=True)
    return doomed
