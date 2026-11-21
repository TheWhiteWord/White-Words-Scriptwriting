"""One-off: bring the live story.db up to the current schema (T2b, Part 1).

Not part of the app — nothing imports this. Without --apply it works on a
temporary copy and only reports; with --apply it takes a safety backup first
(prints the path), then upgrades the real project.

usage: python tasks/task_40/upgrade_live_db.py PROJECT_DIR [--apply]

Run with the project venv: .venv/bin/python tasks/task_40/upgrade_live_db.py ...
"""
import argparse
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from story_architect.core.db import get_db
from story_architect.core.integrity import find_orphans

TABLES = ("entities", "relations", "sections", "revisions", "drafts")
# These four hold story data: the upgrade may create a missing table (0 rows)
# but must never add or remove a row.
UNTOUCHABLE = ("entities", "relations", "sections", "revisions")


def _counts(conn):
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {t: (conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] if t in have else None)
            for t in TABLES}


def _print_state(conn, label):
    print(f"--- {label} ---")
    print("user_version:", conn.execute("PRAGMA user_version").fetchone()[0])
    for t, n in _counts(conn).items():
        print(f"  {t}: {'missing' if n is None else n}")


def _backup_into(db_path: Path, dest: Path):
    """SQLite backup API, never shutil.copy: the source may be in WAL mode."""
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def upgrade(project: Path) -> int:
    """Migrate + data-fix + verify one project directory. Returns an exit code."""
    db_path = project / ".story" / "story.db"
    raw = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    _print_state(raw, "before")
    before = _counts(raw)
    raw.close()

    # get_db runs every pending migration and stamps PRAGMA user_version.
    conn = get_db(project)
    try:
        # Rows deleted by a build that predates deleted_at: one shared stamp
        # keeps a parent and its children "deleted together"; the 30-day purge
        # floor protects them.
        unstamped = conn.execute(
            "SELECT count(*) FROM entities WHERE is_deleted=1 AND deleted_at IS NULL"
        ).fetchone()[0]
        if unstamped:
            stamp = datetime.now().isoformat(timespec="seconds")
            conn.execute(
                "UPDATE entities SET deleted_at=? WHERE is_deleted=1 AND deleted_at IS NULL",
                (stamp,))
            print(f"stamped {unstamped} unstamped deleted row(s) with {stamp}")

        _print_state(conn, "after")
        after = _counts(conn)
        for t in TABLES:
            b = before[t] or 0
            a = after[t] or 0
            print(f"  diff {t}: {b} -> {a} ({a - b:+d})")

        orphans = find_orphans(conn)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        print("find_orphans:", orphans if orphans else "{} (clean)")
        print("integrity_check:", integrity)
    finally:
        conn.close()

    changed = [t for t in UNTOUCHABLE if (before[t] or 0) != (after[t] or 0)]
    if changed:
        print(f"STOP: row counts changed for {changed} — do not --apply; tell the human.")
        return 1
    if orphans or integrity != "ok":
        print("STOP: orphans or a failed integrity check — do not --apply; tell the human.")
        return 1
    print("OK: version current, zero orphans, integrity ok, row counts unchanged.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("project_dir", type=Path)
    ap.add_argument("--apply", action="store_true",
                    help="upgrade the real project (after a safety backup); "
                         "without it, report on a temporary copy")
    args = ap.parse_args()
    project = args.project_dir.resolve()
    db_path = project / ".story" / "story.db"
    if not db_path.exists():
        print(f"No database at {db_path}")
        return 2

    if not args.apply:
        tmp = Path(tempfile.mkdtemp(prefix="t2b-report-"))
        try:
            copy = tmp / "project"
            (copy / ".story").mkdir(parents=True)
            _backup_into(db_path, copy / ".story" / "story.db")
            print(f"report mode: working on a copy of {db_path}")
            return upgrade(copy)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    backup = project / ".story" / f"pre-t2b-upgrade-{datetime.now():%Y%m%d_%H%M%S}.db"
    _backup_into(db_path, backup)
    print(f"safety backup: {backup}")
    print("Keep it until the whole of Phase E is done.")
    return upgrade(project)


if __name__ == "__main__":
    raise SystemExit(main())
