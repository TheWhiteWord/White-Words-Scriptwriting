"""T7 — every stored timestamp is timezone-aware UTC, from one helper.

Stored stamps used to be naive local time (`datetime.now()`). They are compared
as TEXT — the purge age floor (`deleted_at <= cutoff`), the 30-day receipt
pruning, and "deleted together" by equality — so they only mean something if
every stamp has one format and one zone. A machine whose timezone or DST changes
between two writes, or a vault shared across zones, silently shifted the
comparison by hours. `core/clock.py` now produces every stored stamp as
`2026-11-20T09:15:00+00:00` (UTC, whole seconds, explicit offset).

The conversion of stamps already on disk is tested in test_utc_conversion.py.
"""

import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from white_words.scriptwriting.core import clock, db, drafts, revisions
from white_words.scriptwriting.core.trash import preview_purge
from white_words.scriptwriting.core.writes import delete_entity, edit_entity
from white_words.scriptwriting.tools.story_admin import handler as admin

pytestmark = pytest.mark.skipif(not hasattr(time, "tzset"), reason="needs time.tzset")

STAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$")
STAMP_US = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00$")
SRC = Path(__file__).resolve().parent.parent / "src" / "white_words" / "scriptwriting"

SCENE = "central-room-day"  # has a beats child


@contextmanager
def machine_timezone(name):
    """Pretend the machine is in another timezone for the duration."""
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


def _rows(project, sql, *args):
    conn = sqlite3.connect(str(project / ".story" / "story.db"))
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


# ─── the helper ───


def test_now_iso_is_one_fixed_shape(monkeypatch):
    assert STAMP.match(clock.now_iso())
    assert STAMP_US.match(clock.now_iso("microseconds"))

    # Fixed width even when the microseconds happen to be zero: `isoformat()`
    # alone drops them, and two stamps of different lengths do not sort as text.
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 20, 9, 15, 0, 0, tzinfo=tz)

    monkeypatch.setattr(clock, "datetime", Frozen)
    assert clock.now_iso() == "2026-11-20T09:15:00+00:00"
    assert clock.now_iso("microseconds") == "2026-11-20T09:15:00.000000+00:00"


@pytest.mark.parametrize("zone", ["Pacific/Kiritimati", "Pacific/Pago_Pago", "Europe/Rome"])
def test_now_iso_does_not_depend_on_the_machines_timezone(zone):
    with machine_timezone(zone):
        stamp = clock.now_iso()
    assert STAMP.match(stamp)
    assert abs(clock.parse(stamp) - datetime.now(timezone.utc)) < timedelta(seconds=10)


def test_ago_iso_is_a_stamp_in_the_same_format():
    now, ago = clock.now_iso(), clock.ago_iso(30)
    assert STAMP.match(ago)
    assert ago < now  # as text, so as time
    gap = clock.parse(now) - clock.parse(ago)
    assert abs(gap - timedelta(days=30)) < timedelta(seconds=10)


def test_parse_reads_an_aware_stamp():
    assert clock.parse("2026-11-20T09:15:00+00:00") == datetime(
        2026, 11, 20, 9, 15, tzinfo=timezone.utc
    )
    assert clock.parse("2026-11-20T09:15:00+02:00").utcoffset() == timedelta(hours=2)
    assert clock.parse("2026-11-20T09:15:00Z").utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "bad,why",
    [
        ("2026-11-20T09:15:00", "naive"),  # unconverted data, not a format to tolerate
        ("2026-11-20", "naive"),
        ("not a time", "Invalid isoformat"),
        ("", "Invalid isoformat"),
    ],
)
def test_parse_refuses_what_is_not_an_aware_stamp(bad, why):
    with pytest.raises(ValueError, match=why):
        clock.parse(bad)


# ─── every stored stamp comes from it ───


def test_a_delete_stamps_the_whole_delete_with_one_utc_stamp(fixture_path):
    delete_entity(fixture_path, "scene", SCENE, "t", True)
    stamps = {
        r[0] for r in _rows(fixture_path, "SELECT deleted_at FROM entities WHERE is_deleted=1")
    }
    assert len(stamps) == 1  # parent and children: "deleted together"
    assert STAMP.match(stamps.pop())
    assert len(_rows(fixture_path, "SELECT 1 FROM entities WHERE is_deleted=1")) > 1


def test_an_overwritten_section_is_kept_with_a_utc_stamp(fixture_path):
    edit_entity(fixture_path, "scene", SCENE, {"Content": "A new version."}, "edit")
    [rev] = revisions.list_revisions(fixture_path, SCENE, "Content")
    assert STAMP.match(rev["replaced_at"])
    assert STAMP.match(_rows(fixture_path, "SELECT replaced_at FROM revisions")[0][0])


def test_a_staged_draft_is_stamped_utc_and_a_restage_keeps_it(fixture_path):
    op = [
        {
            "op": "create",
            "type": "character",
            "id": "newchar",
            "frontmatter": {"name": "New"},
            "sections": {},
            "summary": "n",
        }
    ]
    draft_id = drafts.stage(fixture_path, op, "a")["draft_id"]
    first = _rows(fixture_path, "SELECT created_at FROM drafts WHERE id=?", draft_id)[0][0]
    assert STAMP.match(first)
    drafts.stage(fixture_path, op, "b", draft_id=draft_id)
    assert _rows(fixture_path, "SELECT created_at FROM drafts WHERE id=?", draft_id)[0][0] == first


def test_a_deleted_project_is_stamped_utc_with_full_precision(tmp_path):
    root = tmp_path / "root"
    (root / "projects" / "demo" / ".story").mkdir(parents=True)
    db.get_db(root / "projects" / "demo").close()  # a project has a database
    out = json.loads(admin({"action": "delete_project", "project": "demo"}, root_path=str(root)))
    meta = (root / ".story-trash" / out["trash_id"] / "deleted.json").read_text()
    stamp = json.loads(meta)["deleted_at"]
    # Microseconds on purpose: two deletes in one second must still sort newest-first.
    assert STAMP_US.match(stamp)


# ─── the point of T7: the machine's zone no longer matters ───


def test_a_zone_change_cannot_make_a_fresh_delete_look_too_old(fixture_path):
    """Deleted on a machine at UTC+14, then the machine moves to UTC-11. As naive
    local time the stamp was 25 hours AHEAD of the new cutoff, so a purge asking
    for "everything deleted up to now" skipped it."""
    with machine_timezone("Pacific/Kiritimati"):
        delete_entity(fixture_path, "character", "kael", "t", True)
    with machine_timezone("Pacific/Pago_Pago"):
        items = preview_purge(fixture_path, None, older_than_days=0)["items"]
    assert [i["id"] for i in items] == ["kael"]


def test_a_zone_change_cannot_make_a_fresh_delete_look_old_enough(fixture_path):
    """The other direction, and the dangerous one: deleted at UTC-11, purged from
    a machine at UTC+14 with a one-day floor. As naive local time the stamp was
    25 hours BEHIND the cutoff, so a delete from seconds ago was purgeable."""
    with machine_timezone("Pacific/Pago_Pago"):
        delete_entity(fixture_path, "character", "kael", "t", True)
    with machine_timezone("Pacific/Kiritimati"):
        items = preview_purge(fixture_path, None, older_than_days=1)["items"]
    assert items == []


def test_the_age_floor_cuts_at_thirty_days_whatever_the_machines_zone(fixture_path):
    """Five hours either side of the floor, asked from a machine 14 hours ahead of
    UTC: as naive local time the cutoff sat 14 hours late, so the younger one
    counted as old enough."""
    delete_entity(fixture_path, "character", "kael", "t", True)
    delete_entity(fixture_path, "character", "mira", "t", True)

    def ago(**delta):
        return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat(timespec="seconds")

    conn = sqlite3.connect(str(fixture_path / ".story" / "story.db"))
    conn.execute("UPDATE entities SET deleted_at=? WHERE id='kael'", (ago(days=30, hours=5),))
    conn.execute("UPDATE entities SET deleted_at=? WHERE id='mira'", (ago(days=30, hours=-5),))
    conn.commit()
    conn.close()
    with machine_timezone("Pacific/Kiritimati"):
        assert [i["id"] for i in preview_purge(fixture_path)["items"]] == ["kael"]


def test_receipts_are_pruned_on_utc_stamps(fixture_path):
    def row(slug, **delta):
        stamp = (datetime.now(timezone.utc) - timedelta(**delta)).isoformat(timespec="seconds")
        conn = sqlite3.connect(str(fixture_path / ".story" / "story.db"))
        conn.execute(
            "INSERT INTO drafts (id, ops, summary, created_at, status) "
            "VALUES (?, '[]', 's', ?, 'committed')",
            (slug, stamp),
        )
        conn.commit()
        conn.close()

    # Five hours either side of the 30-day line, committed from a machine 14 hours
    # ahead of UTC (see the age-floor test above for why).
    row("old-receipt", days=30, hours=5)
    row("recent-receipt", days=30, hours=-5)
    op = [
        {
            "op": "create",
            "type": "character",
            "id": "newchar",
            "frontmatter": {"name": "New"},
            "sections": {},
            "summary": "n",
        }
    ]
    draft_id = drafts.stage(fixture_path, op, "a")["draft_id"]
    with machine_timezone("Pacific/Kiritimati"):
        assert drafts.commit(fixture_path, draft_id)["success"] is True

    left = {r[0] for r in _rows(fixture_path, "SELECT id FROM drafts")}
    assert "old-receipt" not in left
    assert {"recent-receipt", draft_id} <= left


# ─── guards against drifting back ───


def test_every_timestamp_column_in_the_schema_is_a_listed_stamp(tmp_path):
    """A new `*_at` column must be added to `clock.STORED_STAMPS` — which is the
    list the one-off conversion walks — or this fails."""
    conn = db.get_db(tmp_path)
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        found = {
            (t, c[1])
            for t in tables
            for c in conn.execute(f"PRAGMA table_info({t})")
            if c[1].endswith("_at")
        }
    finally:
        conn.close()
    assert found == set(clock.STORED_STAMPS)


# Where the clock may still be read directly, and why. Everything else must go
# through core/clock.py.
LOCAL_TIME_ALLOWED = {
    "core/clock.py": "the producer",
    "chat/store.py": "the chat database's own stamps; already timezone-aware UTC",
    "core/backups.py": "backup FILE NAMES carry local time; renaming would mix old and new names",
    "core/db.py": "the name of a backup file",
    "core/drafts.py": "the label inside a draft's id (an identifier, not a stamp)",
    "tools/story_admin.py": "the name of a trash folder",
}


def test_no_stored_stamp_is_made_outside_the_clock():
    offenders = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel.startswith("web/") or rel in LOCAL_TIME_ALLOWED:
            continue
        text = path.read_text(encoding="utf-8")
        for pat in ("datetime.now(", "datetime.utcnow(", ".isoformat("):
            if pat in text:
                offenders.append(f"{rel}: {pat}")
    assert not offenders, (
        "stored stamps come from core/clock.py; if this is a file name "
        "or identifier, add the file to LOCAL_TIME_ALLOWED with the reason: "
        f"{offenders}"
    )


def test_the_allowed_files_still_need_their_exemption():
    """An exemption that no longer applies is how a rule rots."""
    for rel in LOCAL_TIME_ALLOWED:
        text = (SRC / rel).read_text(encoding="utf-8")
        assert any(p in text for p in ("datetime.now(", ".isoformat(", "timezone.utc")), rel
