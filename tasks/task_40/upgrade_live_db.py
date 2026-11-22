"""One-off: bring live project data up to date (T2b schema, T7 UTC timestamps).

Not part of the app — nothing imports this. Without --apply it only REPORTS (it
works on temporary copies and changes nothing). With --apply it takes a safety
backup of each database first (prints the path), then upgrades the real one.

What it does, per project database:
  1. T2b: run any pending schema migration; stamp rows deleted by a build that
     predates `deleted_at`.
  2. T7: every stored stamp that is naive local time (entities.deleted_at,
     drafts.created_at, revisions.replaced_at — the list is
     `clock.STORED_STAMPS`) is read as LOCAL TIME and rewritten as UTC with an
     explicit offset, e.g. 2026-11-20T09:15:00 -> 2026-11-20T08:15:00+00:00.
     Stamps that already have an offset are left alone, so running it twice is
     safe. A stamp it cannot read stops everything and changes nothing.
  3. Verify: every stamp parses as timezone-aware, no row count changed, no
     orphans, integrity ok. Conversion and verification are ONE transaction:
     if the check fails, nothing is written.

usage:
  python tasks/task_40/upgrade_live_db.py PROJECT_DIR [--apply] [--tz ZONE]
  python tasks/task_40/upgrade_live_db.py ROOT --all [--apply] [--tz ZONE]

--all treats the folder as the story ROOT and covers every project under
projects/, every trashed project under .story-trash/ (its database comes back
with it on restore) and every .story-trash/*/deleted.json record. With --apply
it first reports on EVERYTHING and writes nothing unless all of it is readable.

--tz ZONE names the zone the naive stamps were written in (e.g. Europe/Rome).
Default: this machine's own zone, applied as it was on each stamp's date (so
summer time is handled). The run prints the zone it assumed and a few sample
conversions — check them before --apply. A stamp from the one repeated hour when
the clocks go back is read as the first of the two.

Run with the project venv: .venv/bin/python tasks/task_40/upgrade_live_db.py ...
"""
import argparse
import json
import os
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from story_architect.core import clock
from story_architect.core.db import get_db, transaction
from story_architect.core.integrity import find_orphans

TABLES = ("entities", "relations", "sections", "revisions", "drafts")
# These four hold story data: the upgrade may create a missing table (0 rows)
# but must never add or remove a row.
UNTOUCHABLE = ("entities", "relations", "sections", "revisions")
TRASH_DIR = ".story-trash"
SAMPLES = 3


class _Stop(Exception):
    """Something the human must look at before anything is written."""


# ─── one stamp ───

def convert_stamp(value, tz=None, timespec="seconds"):
    """A naive stamp as local time -> aware UTC text; None if it already has an offset.

    Raises ValueError for anything that is not a date/time at all: a guess here
    would be a wrong date in the database.
    """
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is not None:
        return None
    if tz is not None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(timezone.utc).isoformat(timespec=timespec)


def _zone_label(tz):
    if tz is not None:
        return str(tz)
    return f"this machine's local zone ({'/'.join(dict.fromkeys(time.tzname))})"


# ─── one database ───

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


def _plan(conn, tz):
    """What would change: ({(table, column): [(old, new), ...]}, [unreadable])."""
    changes, bad = {}, []
    for table, column in clock.STORED_STAMPS:
        for (old,) in conn.execute(
                f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL").fetchall():
            try:
                new = convert_stamp(old, tz)
            except (ValueError, TypeError) as e:
                bad.append((table, column, old, str(e)))
                continue
            if new is not None:
                changes.setdefault((table, column), []).append((old, new))
    return changes, bad


def _unreadable_after(conn):
    """Stamps that do not parse as aware — what `clock.parse` would refuse."""
    bad = []
    for table, column in clock.STORED_STAMPS:
        for (value,) in conn.execute(
                f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL").fetchall():
            try:
                clock.parse(value)
            except (ValueError, TypeError) as e:
                bad.append((table, column, value, str(e)))
    return bad


def _print_bad(bad):
    for table, column, value, why in bad:
        print(f"  {table}.{column}: {value!r} ({why})")


def upgrade(project: Path, tz=None) -> int:
    """Migrate + data-fix + convert + verify one project directory. Returns an exit code."""
    db_path = project / ".story" / "story.db"
    raw = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    _print_state(raw, "before")
    before = _counts(raw)
    raw.close()

    # get_db runs every pending migration and stamps PRAGMA user_version.
    conn = get_db(project)
    try:
        converted = 0
        try:
            with transaction(conn):
                # Rows deleted by a build that predates deleted_at: one shared stamp
                # keeps a parent and its children "deleted together"; the 30-day
                # purge floor protects them.
                unstamped = conn.execute(
                    "SELECT count(*) FROM entities WHERE is_deleted=1 AND deleted_at IS NULL"
                ).fetchone()[0]
                if unstamped:
                    stamp = clock.now_iso()
                    conn.execute(
                        "UPDATE entities SET deleted_at=? WHERE is_deleted=1 AND deleted_at IS NULL",
                        (stamp,))
                    print(f"stamped {unstamped} unstamped deleted row(s) with {stamp}")

                changes, bad = _plan(conn, tz)
                if bad:
                    print("STOP: stamps that are not a date and time — nothing was written. "
                          "Fix or remove them by hand, then run again:")
                    _print_bad(bad)
                    raise _Stop
                print(f"naive stamps are read as local time in {_zone_label(tz)}")
                shown = 0
                for (table, column), pairs in changes.items():
                    for old, new in pairs:
                        converted += conn.execute(
                            f"UPDATE {table} SET {column}=? WHERE {column}=?", (new, old)).rowcount
                        if shown < SAMPLES:
                            print(f"  {table}.{column}: {old} -> {new}")
                            shown += 1

                bad = _unreadable_after(conn)
                if bad:
                    print("STOP: stamps are still not timezone-aware after the conversion — "
                          "nothing was written:")
                    _print_bad(bad)
                    raise _Stop
        except _Stop:
            return 1
        print(f"{converted} stamp(s) converted")

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
    print("OK: version current, every stamp timezone-aware, zero orphans, integrity ok, "
          "row counts unchanged.")
    return 0


def _report(project: Path, tz) -> int:
    """`upgrade` on a temporary copy: says everything, changes nothing."""
    db_path = project / ".story" / "story.db"
    tmp = Path(tempfile.mkdtemp(prefix="t7-report-"))
    try:
        copy = tmp / "project"
        (copy / ".story").mkdir(parents=True)
        _backup_into(db_path, copy / ".story" / "story.db")
        print(f"report mode: working on a copy of {db_path}")
        return upgrade(copy, tz)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _apply(project: Path, tz) -> int:
    """Safety backup, then `upgrade` on the real project."""
    db_path = project / ".story" / "story.db"
    stem = project / ".story" / f"pre-t7-utc-{datetime.now():%Y%m%d_%H%M%S}"
    backup, n = stem.with_suffix(".db"), 1
    while backup.exists():          # never overwrite an earlier safety backup
        n += 1
        backup = Path(f"{stem}-{n}.db")
    _backup_into(db_path, backup)
    print(f"safety backup: {backup}")
    print("Keep it until you are sure everything works.")
    return upgrade(project, tz)


# ─── the project trash records (root/.story-trash/*/deleted.json) ───

def _convert_record(record: Path, tz, apply: bool):
    """The record's `deleted_at` -> UTC with full precision. Returns (old, new) or None."""
    data = json.loads(record.read_text(encoding="utf-8"))
    old = data.get("deleted_at")
    if not old:
        return None
    new = convert_stamp(old, tz, "microseconds")      # full precision: they must sort newest-first
    if new is None:
        return None
    if apply:
        shutil.copy2(record, record.with_name(record.name + ".pre-t7"))
        data["deleted_at"] = new
        tmp = record.with_name(record.name + ".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, record)
    return old, new


def _targets(root: Path):
    """(project folders with a database, trash records) under a story root."""
    projects, records = [], []
    for d in sorted((root / "projects").glob("*")) if (root / "projects").is_dir() else []:
        if (d / ".story" / "story.db").exists():
            projects.append(d)
    trash = root / TRASH_DIR
    for slot in sorted(trash.iterdir()) if trash.is_dir() else []:
        record = slot / "deleted.json"
        if not record.is_file():
            continue
        records.append(record)
        try:
            folder = slot / json.loads(record.read_text(encoding="utf-8"))["slug"]
        except (OSError, ValueError, KeyError):
            continue
        if (folder / ".story" / "story.db").exists():
            projects.append(folder)
    return projects, records


def sweep(root: Path, apply: bool, tz) -> int:
    projects, records = _targets(root)
    if not projects and not records:
        print(f"Nothing to convert under {root} (no projects/ or {TRASH_DIR}/).")
        return 2
    print(f"found {len(projects)} project database(s) and {len(records)} trash record(s) under {root}")

    failed = []
    for project in projects:                           # pass 1: report on everything
        print(f"\n===== {project} =====")
        if _report(project, tz) != 0:
            failed.append(project)
    for record in records:
        try:
            result = _convert_record(record, tz, apply=False)
        except (ValueError, TypeError, OSError) as e:
            print(f"\n===== {record} =====\n  unreadable: {e}")
            failed.append(record)
            continue
        if result:
            print(f"\n===== {record} =====\n  deleted_at: {result[0]} -> {result[1]}")
    if failed:
        print("\nSTOP: nothing was changed anywhere. Needs attention first:")
        for f in failed:
            print(f"  {f}")
        return 1
    if not apply:
        print("\nreport mode: nothing was changed. Run again with --apply to convert.")
        return 0

    code = 0                                           # pass 2: everything was readable
    for project in projects:
        print(f"\n===== applying: {project} =====")
        code = max(code, _apply(project, tz))
    for record in records:
        result = _convert_record(record, tz, apply=True)
        if result:
            print(f"converted {record}: {result[0]} -> {result[1]}")
    return code


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path, help="a project folder, or with --all the story root")
    ap.add_argument("--apply", action="store_true",
                    help="change the real data (after a safety backup); "
                         "without it, only report")
    ap.add_argument("--all", action="store_true",
                    help="PATH is the story root: every project, trashed project and trash record")
    ap.add_argument("--tz", help="zone the naive stamps were written in, e.g. Europe/Rome "
                                 "(default: this machine's zone)")
    args = ap.parse_args(argv)
    try:
        tz = ZoneInfo(args.tz) if args.tz else None
    except (ZoneInfoNotFoundError, ValueError):
        print(f"Unknown timezone: {args.tz!r} (use a name like Europe/Rome)")
        return 2
    path = args.path.resolve()

    if args.all:
        return sweep(path, args.apply, tz)

    db_path = path / ".story" / "story.db"
    if not db_path.exists():
        print(f"No database at {db_path}")
        return 2
    return _apply(path, tz) if args.apply else _report(path, tz)


if __name__ == "__main__":
    raise SystemExit(main())
