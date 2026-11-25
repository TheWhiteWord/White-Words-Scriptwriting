"""Backups of a project's database: make, list, restore, prune.

Files live in ``<project>/.story/`` and are named
``story[_auto]_<date>_<time>[_<label>]_<id>.db``:

* ``story_auto_…`` — **automatic**: taken by the app before something
  destructive (a Markdown import, a purge) and before every restore. Only these
  are ever pruned, to the newest AUTO_BACKUPS_KEPT.
* ``story_…`` — **manual**: taken on request, optionally with a label that
  names it (a milestone to come back to). Never pruned. Backups made before this
  naming existed (``story_<date>_<time>.db``) count as manual, so nothing old is
  ever deleted on a guess.

``*.partial`` files (a backup still being written, or one that failed) never
match, so a listing only ever shows complete backups.
"""

import re
import sqlite3
import threading
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

# Standard desktop practice is "the last handful"; automatic backups here are
# taken before destructive operations and before restores, so 20 spans weeks of
# normal use without growing without bound.
AUTO_BACKUPS_KEPT = 20

# The periodic backup (maybe_periodic_backup): at most one a day, and only when
# the project changed since the last one.
PERIODIC_BACKUP_INTERVAL = timedelta(hours=24)

# SQLite checkpoints the write-ahead log into story.db when the last connection
# closes, which can touch the file a moment *after* a backup was taken. Changes
# within this many seconds of a backup are not counted as new.
_CHECKPOINT_SLACK_SECONDS = 5

_periodic_lock = threading.Lock()

_NAME = re.compile(r"^story(?P<auto>_auto)?_(?P<date>\d{8})_(?P<time>\d{6})(?P<rest>.*)\.db$")


def slugify_label(label: str) -> str | None:
    """A label as it appears in a file name: ASCII, lowercase, hyphens.

    "Bozza finale — dopo la lettura" -> "bozza-finale-dopo-la-lettura".
    """
    ascii_text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:40].strip("-")
    return slug or None


def create_backup(project_path: Path, *, label: str | None = None, automatic: bool = False) -> str:
    """Snapshot the project database. Returns the backup's path.

    Automatic backups prune older automatic ones afterwards; manual ones are kept.
    """
    from .db import backup_database

    slug = None
    if label:
        slug = slugify_label(label)
        if slug is None:
            raise ValueError("The label needs at least one letter or digit.")
    path = backup_database(project_path, prefix="story_auto" if automatic else "story", label=slug)
    if automatic:
        prune_automatic_backups(project_path)
    return path


def maybe_periodic_backup(project_path: Path, *, now: datetime | None = None) -> str | None:
    """Take an automatic backup if one is due; return its path, or None.

    Due means: the newest *automatic* backup is older than PERIODIC_BACKUP_INTERVAL
    (or there is none) **and** the project database changed after it. The second
    condition keeps a project that is only ever opened from filling every
    automatic slot with identical copies, which would push out the older states
    the cap is there to keep.

    Meant to be called whenever a project is opened. Safe to call from several
    threads at once: only one of them backs up.
    """
    now = now or datetime.now()
    db = project_path / ".story" / "story.db"
    if not db.exists():
        return None
    with _periodic_lock:
        newest = next((b for b in list_backups(project_path) if b["kind"] == "automatic"), None)
        if newest is not None:
            taken = datetime.fromisoformat(newest["created_at"])
            if now - taken < PERIODIC_BACKUP_INTERVAL:
                return None
            # story.db changes only at checkpoints; the -wal file on every write
            changed = max(
                (f.stat().st_mtime for f in (db, db.with_name("story.db-wal")) if f.exists()),
                default=0,
            )
            if changed <= taken.timestamp() + _CHECKPOINT_SLACK_SECONDS:
                return None
        return create_backup(project_path, automatic=True)


def list_backups(project_path: Path) -> list[dict]:
    """Every complete backup, newest first.

    Each: name, kind ("automatic" | "manual"), label (or None), created_at
    (local time, from the name), size_bytes.
    """
    found = []
    folder = project_path / ".story"
    for f in folder.glob("story_*.db"):
        m = _NAME.match(f.name)
        if not m or not f.is_file():
            continue
        st = f.stat()
        try:
            created = datetime.strptime(m["date"] + m["time"], "%Y%m%d%H%M%S")
        except ValueError:
            created = datetime.fromtimestamp(st.st_mtime)
        rest = m["rest"]
        label = (
            rest[1:-9] or None
            if rest.startswith("_") and len(rest) > 9 and rest[-9] == "_"
            else None
        )
        found.append(
            (
                created,
                st.st_mtime_ns,
                {
                    "name": f.name,
                    "kind": "automatic" if m["auto"] else "manual",
                    "label": label,
                    "created_at": created.isoformat(timespec="seconds"),
                    "size_bytes": st.st_size,
                },
            )
        )
    found.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [t[2] for t in found]


def prune_automatic_backups(project_path: Path, keep: int | None = None) -> list[str]:
    """Delete automatic backups beyond the newest `keep`. Returns the names removed.

    Manual backups are never touched. `keep` is at least 1, so the backup that
    has just been taken always survives.
    """
    keep = max(1, AUTO_BACKUPS_KEPT if keep is None else keep)
    automatic = [b for b in list_backups(project_path) if b["kind"] == "automatic"]
    removed = []
    for b in automatic[keep:]:
        (project_path / ".story" / b["name"]).unlink(missing_ok=True)
        removed.append(b["name"])
    return removed


def load_database_in_place(
    project_path: Path, source: Path, *, safety_label: str | None = "before-restore"
) -> str | None:
    """Copy a validated database file into the live project database, in place.

    ``source`` must already be a checked project database (see `check_source`):
    this function owns only what the copy itself can go wrong at — a target that
    does not exist, a page size the target cannot take, and the state after the
    copy. Returns the safety backup's path, or None when none was taken.

    The copy goes through SQLite's backup API instead of swapping the file. A
    file swap leaves other open connections (the web app, the agent's tools)
    pointing at the old file, where a write would be lost, and a stale ``-wal``
    left beside the new file corrupts it. Copying in place is one transaction on
    the real file: other connections see the new data as soon as it commits, and
    nothing is left behind.

    With a `safety_label` the current state is saved as an automatic backup
    before the copy — the page-size refusal comes first, so a refused copy
    leaves no backup behind. A caller that already holds a copy of the current
    state (a branch switch parks it as the branch's head) passes None.

    The copy is migrated forward inside the live database.
    """
    from .db import BASELINE_VERSION, SCHEMA_MIGRATIONS, apply_migrations, get_db

    name = Path(source).name
    if not (project_path / ".story" / "story.db").exists():
        raise ValueError("This project has no story.db to restore into.")

    # immutable: read it without creating -wal/-shm files beside the source
    try:
        snap = sqlite3.connect(f"file:{source}?mode=ro&immutable=1", uri=True)
    except sqlite3.Error as e:
        raise ValueError(f"{name} cannot be opened: {e}")
    try:
        try:
            page_size = snap.execute("PRAGMA page_size").fetchone()[0]
        except sqlite3.Error as e:
            raise ValueError(f"{name} is not a readable project database: {e}")
        live = get_db(project_path)
        try:
            if live.execute("PRAGMA page_size").fetchone()[0] != page_size:
                raise ValueError(
                    f"{name} uses a different database page size and cannot be copied into "
                    "this project."
                )
            safety = (
                create_backup(project_path, label=safety_label, automatic=True)
                if safety_label
                else None
            )
            snap.backup(live)
            apply_migrations(
                live,
                SCHEMA_MIGRATIONS,
                baseline=BASELINE_VERSION,
                name=f"{project_path.name}/.story/story.db",
            )
            if live.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                kept = f" The state before it is saved as {Path(safety).name}." if safety else ""
                raise RuntimeError(f"The database failed its integrity check after the copy.{kept}")
        finally:
            live.close()
    finally:
        snap.close()
    return safety


def check_source(source: Path, label: str) -> None:
    """Raise ValueError unless `source` is a project database this build opens.

    A readable SQLite file, no damage, an `entities` table, and a schema version
    between the baseline and the latest. Raises, changing nothing. `label` names
    the file in the message — a backup's file name, or a branch's.
    """
    from .db import BASELINE_VERSION, LATEST_VERSION

    # immutable: read it without creating -wal/-shm files beside the source
    try:
        snap = sqlite3.connect(f"file:{source}?mode=ro&immutable=1", uri=True)
    except sqlite3.Error as e:
        raise ValueError(f"{label} cannot be opened: {e}")
    try:
        try:
            ok = snap.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            has_entities = snap.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='entities'"
            ).fetchone()
            version = snap.execute("PRAGMA user_version").fetchone()[0]
        except sqlite3.Error as e:
            raise ValueError(f"{label} is not a readable project database: {e}")
    finally:
        snap.close()
    if not ok:
        raise ValueError(f"{label} is damaged and cannot be used.")
    if not has_entities:
        raise ValueError(f"{label} is not a project database (no entities table).")
    if version > LATEST_VERSION:
        raise ValueError(
            f"{label} was made by a newer version of White Words (schema "
            f"{version}, this build knows {LATEST_VERSION}). Update the app first."
        )
    if version < BASELINE_VERSION:
        raise ValueError(
            f"{label} is older than this build supports (schema {version}; the "
            f"baseline is {BASELINE_VERSION})."
        )


def restore_backup(project_path: Path, name: str) -> dict:
    """Replace the project database with a backup's contents.

    The backup is checked before anything changes (a readable SQLite file, no
    damage, a project database, not from a newer build nor older than the
    baseline) and then handed to `load_database_in_place`, which takes the
    safety backup and copies it in. Raises ValueError, changing nothing, if a
    check fails.
    """
    # Only names from the listing: that is what keeps a path like ../story.db out.
    if name not in {b["name"] for b in list_backups(project_path)}:
        raise ValueError(f'No such backup: {name}. Use action="list" for the names.')
    source = project_path / ".story" / name
    if not (project_path / ".story" / "story.db").exists():
        raise ValueError("This project has no story.db to restore into.")

    check_source(source, name)

    safety = load_database_in_place(project_path, source, safety_label="before-restore")
    assert safety is not None  # a restore always keeps the state it replaces

    meta = next(b for b in list_backups(project_path) if b["name"] == name)
    return {
        "success": True,
        "restored": name,
        "restored_created_at": meta["created_at"],
        "safety_backup": Path(safety).name,
        "message": (
            f"Restored the project to {meta['created_at']}. Anything done after that is not in it."
        ),
        "hint": f"To undo this restore, restore {Path(safety).name}.",
    }
