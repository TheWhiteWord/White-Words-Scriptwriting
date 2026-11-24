"""T7 — the one-off that rewrites stored stamps from naive local time to UTC.

`tasks/task_40/upgrade_live_db.py` is not part of the app; these tests load it
by path. It must: read each naive stamp as local time and write it as aware UTC
(`clock.py`'s format), leave aware stamps alone, never change a row count, keep
"deleted together" groups together, take a safety backup before `--apply`, change
nothing without it, and refuse (changing nothing) on a stamp it cannot read.
"""
import importlib.util
import json
import os
import shutil
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from white_words.scriptwriting.core import clock
from white_words.scriptwriting.core.writes import delete_entity, edit_entity
from white_words.scriptwriting.core import drafts

pytestmark = pytest.mark.skipif(not hasattr(time, "tzset"), reason="needs time.tzset")

SCRIPT = Path(__file__).resolve().parent.parent / "tasks" / "task_40" / "upgrade_live_db.py"
ROME = ZoneInfo("Europe/Rome")
SCENE = "central-room-day"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("upgrade_live_db", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@contextmanager
def machine_timezone(name):
    old = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()


def _dump(project):
    """Every row of every table — what 'nothing changed' means."""
    conn = sqlite3.connect(str(project / ".story" / "story.db"))
    try:
        tables = sorted(r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
        return {t: sorted(map(repr, conn.execute(f"SELECT * FROM {t}"))) for t in tables}
    finally:
        conn.close()


def _sql(project, sql, *args):
    conn = sqlite3.connect(str(project / ".story" / "story.db"))
    try:
        rows = conn.execute(sql, args).fetchall()
        conn.commit()
        return rows
    finally:
        conn.close()


def _counts(project):
    return {t: len(rows) for t, rows in _dump(project).items()}


WINTER, SUMMER = "2026-11-20T09:15:00", "2026-07-20T09:15:00"     # Rome: UTC+1 / UTC+2


@pytest.fixture
def naive(fixture_path):
    """A project the way it was before T7: every stored stamp naive local time."""
    delete_entity(fixture_path, "scene", SCENE, "t", True)          # a scene + its beats
    delete_entity(fixture_path, "character", "kael", "t", True)
    edit_entity(fixture_path, "scene", "central-room-night", {"Content": "A new version."}, "e")
    op = [{"op": "create", "type": "character", "id": "newchar",
           "frontmatter": {"name": "New"}, "sections": {}, "summary": "n"}]
    draft_id = drafts.stage(fixture_path, op, "a")["draft_id"]
    _sql(fixture_path, "UPDATE entities SET deleted_at=? WHERE is_deleted=1 AND id != 'kael' "
                       "AND deleted_at IS NOT NULL", WINTER)
    _sql(fixture_path, "UPDATE entities SET deleted_at=? WHERE id='kael'", SUMMER)
    _sql(fixture_path, "UPDATE revisions SET replaced_at=?", WINTER)
    _sql(fixture_path, "UPDATE drafts SET created_at=? WHERE id=?", WINTER, draft_id)
    return fixture_path


# ─── one stamp ───

@pytest.mark.parametrize("naive_stamp,expected", [
    ("2026-11-20T09:15:00", "2026-11-20T08:15:00+00:00"),            # winter: UTC+1
    ("2026-07-20T09:15:00", "2026-07-20T07:15:00+00:00"),            # summer (DST): UTC+2
    ("2026-03-29T03:30:00", "2026-03-29T01:30:00+00:00"),            # just after the spring jump
    ("2026-10-25T02:30:00", "2026-10-25T00:30:00+00:00"),            # ambiguous hour: the FIRST one
    ("2026-11-20", "2026-11-19T23:00:00+00:00"),                     # a bare date is local midnight
])
def test_a_naive_stamp_is_read_as_local_time_and_written_as_utc(script, naive_stamp, expected):
    assert script.convert_stamp(naive_stamp, ROME) == expected
    assert clock.parse(expected)                                     # and it is a valid aware stamp


def test_an_aware_stamp_is_left_alone(script):
    assert script.convert_stamp("2026-11-20T08:15:00+00:00", ROME) is None
    assert script.convert_stamp("2026-11-20T09:15:00+01:00", ROME) is None


def test_a_microsecond_stamp_keeps_a_fixed_width(script):
    """A deleted project's stamp: whole-second and fractional stamps must still sort."""
    assert script.convert_stamp("2026-11-20T09:15:00.123456", ROME, "microseconds") \
        == "2026-11-20T08:15:00.123456+00:00"
    # `isoformat()` drops a zero fraction, so the old stamp may have none.
    assert script.convert_stamp("2026-11-20T09:15:00", ROME, "microseconds") \
        == "2026-11-20T08:15:00.000000+00:00"


@pytest.mark.parametrize("junk", ["yesterday", "", "2026-13-45T00:00:00", "12:00"])
def test_a_stamp_it_cannot_read_is_an_error_not_a_guess(script, junk):
    with pytest.raises(ValueError):
        script.convert_stamp(junk, ROME)


def test_without_a_zone_the_machines_own_zone_is_used_with_its_history(script):
    """Summer and winter differ: the machine's zone is applied as it was on THAT
    date, not as it is today."""
    with machine_timezone("Europe/Rome"):
        assert script.convert_stamp(WINTER, None) == "2026-11-20T08:15:00+00:00"
        assert script.convert_stamp(SUMMER, None) == "2026-07-20T07:15:00+00:00"
    with machine_timezone("America/New_York"):
        assert script.convert_stamp(WINTER, None) == "2026-11-20T14:15:00+00:00"


# ─── a project ───

def test_a_report_run_changes_nothing_and_says_what_it_would_do(script, naive, capsys):
    before = _dump(naive)

    code = script.main([str(naive), "--tz", "Europe/Rome"])

    out = capsys.readouterr().out
    assert code == 0
    assert _dump(naive) == before                                    # the real database, untouched
    assert "report mode" in out
    assert WINTER + " -> 2026-11-20T08:15:00+00:00" in out           # a sample to eyeball
    assert "Europe/Rome" in out                                      # which zone it assumed


def test_apply_converts_every_stamp_and_changes_no_row_count(script, naive, capsys):
    before_counts = _counts(naive)
    scene_group = {r[0] for r in _sql(naive,
        "SELECT deleted_at FROM entities WHERE is_deleted=1 AND id != 'kael'")}
    assert scene_group == {WINTER}                                   # one delete, one stamp

    code = script.main([str(naive), "--apply", "--tz", "Europe/Rome"])

    assert code == 0, capsys.readouterr().out
    assert _counts(naive) == before_counts
    after_group = {r[0] for r in _sql(naive,
        "SELECT deleted_at FROM entities WHERE is_deleted=1 AND id != 'kael'")}
    assert after_group == {"2026-11-20T08:15:00+00:00"}              # still ONE stamp: still "together"
    assert _sql(naive, "SELECT deleted_at FROM entities WHERE id='kael'") == \
        [("2026-07-20T07:15:00+00:00",)]                             # the summer one, with DST
    assert _sql(naive, "SELECT replaced_at FROM revisions") == [("2026-11-20T08:15:00+00:00",)]
    assert _sql(naive, "SELECT created_at FROM drafts") == [("2026-11-20T08:15:00+00:00",)]
    for table, column in clock.STORED_STAMPS:                        # nothing naive is left
        for (value,) in _sql(naive, f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL"):
            clock.parse(value)


def test_apply_takes_a_safety_backup_first_and_prints_where(script, naive, capsys):
    before = _dump(naive)

    script.main([str(naive), "--apply", "--tz", "Europe/Rome"])

    out = capsys.readouterr().out
    [backup] = list((naive / ".story").glob("pre-t7-utc-*.db"))
    assert f"safety backup: {backup}" in out
    copy = naive / "backup-copy"
    (copy / ".story").mkdir(parents=True)
    shutil.copy(backup, copy / ".story" / "story.db")
    assert _dump(copy) == before                                     # the backup is the OLD data


def test_a_second_run_changes_nothing(script, naive, capsys):
    script.main([str(naive), "--apply", "--tz", "Europe/Rome"])
    once = _dump(naive)

    code = script.main([str(naive), "--apply", "--tz", "Europe/Rome"])

    assert code == 0
    assert _dump(naive) == once
    # Two runs inside one second still leave two safety backups: the second must
    # not overwrite the first, which is the only copy of the old data.
    assert len(list((naive / ".story").glob("pre-t7-utc-*.db"))) == 2
    assert "0 stamp(s) converted" in capsys.readouterr().out.split("safety backup")[-1]


def test_aware_stamps_in_a_mixed_database_are_not_touched(script, naive):
    aware = "2026-05-05T05:05:05+00:00"
    _sql(naive, "UPDATE revisions SET replaced_at=?", aware)

    script.main([str(naive), "--apply", "--tz", "Europe/Rome"])

    assert _sql(naive, "SELECT replaced_at FROM revisions") == [(aware,)]
    assert _sql(naive, "SELECT created_at FROM drafts")[0][0].endswith("+00:00")


def test_a_stamp_it_cannot_read_stops_everything_and_changes_nothing(script, naive, capsys):
    _sql(naive, "UPDATE revisions SET replaced_at='last tuesday'")
    before = _dump(naive)

    code = script.main([str(naive), "--apply", "--tz", "Europe/Rome"])

    out = capsys.readouterr().out
    assert code == 1
    assert "STOP" in out and "last tuesday" in out
    assert _dump(naive) == before                                    # not even the readable ones


def test_a_deleted_row_with_no_stamp_gets_the_current_utc_time(script, fixture_path):
    """A database from a build that predates deleted_at (T2b's data fix). It is
    stamped NOW, in UTC — not as local time that the conversion then misreads."""
    _sql(fixture_path, "UPDATE entities SET is_deleted=1 WHERE id='kael'")
    with machine_timezone("Pacific/Kiritimati"):                     # far from the zone given below
        script.main([str(fixture_path), "--apply", "--tz", "Europe/Rome"])
    [(stamp,)] = _sql(fixture_path, "SELECT deleted_at FROM entities WHERE id='kael'")
    assert stamp.endswith("+00:00")
    assert abs(clock.parse(stamp) - datetime.now(timezone.utc)) < timedelta(seconds=30)


def test_the_check_after_the_conversion_rolls_everything_back(script, naive, capsys):
    """The last line of defence: if a stamp is somehow still not timezone-aware
    after the rewrite (here a trigger writes a naive one back), nothing is kept."""
    _sql(naive, "CREATE TRIGGER sneaky AFTER UPDATE OF replaced_at ON revisions "
                "BEGIN UPDATE revisions SET replaced_at='2026-01-01T00:00:00' WHERE id=NEW.id; END")
    before = _dump(naive)

    code = script.main([str(naive), "--apply", "--tz", "Europe/Rome"])

    out = capsys.readouterr().out
    assert code == 1
    assert "STOP" in out and "still not timezone-aware" in out
    assert _dump(naive) == before                                    # the other columns rolled back too


def test_a_folder_with_no_database_is_refused(script, tmp_path, capsys):
    assert script.main([str(tmp_path)]) == 2
    assert "No database" in capsys.readouterr().out


# ─── a whole root: every project, the trashed ones, the trash records ───

@pytest.fixture
def root(naive, tmp_path):
    """root/projects/{a,b}, and a trashed project with its record, all naive."""
    root = tmp_path / "root"
    for slug in ("a", "b"):
        shutil.copytree(naive, root / "projects" / slug)
    slot = root / ".story-trash" / "gone_20260101_000000_x"
    shutil.copytree(naive, slot / "gone")
    (slot / "deleted.json").write_text(json.dumps({
        "slug": "gone", "original_path": "/x/gone", "deleted_at": "2026-11-20T09:15:00.123456"}))
    other = root / ".story-trash" / "gone_20260101_000001_y"
    other.mkdir(parents=True)
    (other / "deleted.json").write_text(json.dumps({      # an incomplete slot: no folder
        "slug": "half", "original_path": "/x/half", "deleted_at": "2026-11-20T09:15:00"}))
    return root


def _every_project_db(root):
    return [root / "projects" / "a", root / "projects" / "b",
            root / ".story-trash" / "gone_20260101_000000_x" / "gone"]


def test_all_converts_every_project_and_every_trash_record(script, root, capsys):
    code = script.main([str(root), "--all", "--apply", "--tz", "Europe/Rome"])

    assert code == 0, capsys.readouterr().out
    for project in _every_project_db(root):
        assert _sql(project, "SELECT created_at FROM drafts") == [("2026-11-20T08:15:00+00:00",)]
        assert list((project / ".story").glob("pre-t7-utc-*.db")), project
    record = json.loads((root / ".story-trash" / "gone_20260101_000000_x" / "deleted.json").read_text())
    assert record["deleted_at"] == "2026-11-20T08:15:00.123456+00:00"
    assert record["slug"] == "gone"                                  # nothing else in the record changed
    assert (root / ".story-trash" / "gone_20260101_000000_x" / "deleted.json.pre-t7").exists()
    half = json.loads((root / ".story-trash" / "gone_20260101_000001_y" / "deleted.json").read_text())
    assert half["deleted_at"] == "2026-11-20T08:15:00.000000+00:00"  # a record is converted even without its folder


def test_all_in_report_mode_changes_nothing_anywhere(script, root, capsys):
    before = {p: _dump(p) for p in _every_project_db(root)}
    records = {p: p.read_text() for p in (root / ".story-trash").glob("*/deleted.json")}

    code = script.main([str(root), "--all", "--tz", "Europe/Rome"])

    assert code == 0
    assert {p: _dump(p) for p in _every_project_db(root)} == before
    assert {p: p.read_text() for p in (root / ".story-trash").glob("*/deleted.json")} == records
    assert not list(root.rglob("pre-t7-utc-*.db"))


def test_all_stops_before_changing_anything_if_one_project_is_unreadable(script, root, capsys):
    _sql(root / "projects" / "b", "UPDATE revisions SET replaced_at='nope'")
    before = {p: _dump(p) for p in _every_project_db(root)}

    code = script.main([str(root), "--all", "--apply", "--tz", "Europe/Rome"])

    assert code == 1
    assert {p: _dump(p) for p in _every_project_db(root)} == before   # project "a" was NOT converted either
    assert "projects/b" in capsys.readouterr().out.replace("\\", "/")
