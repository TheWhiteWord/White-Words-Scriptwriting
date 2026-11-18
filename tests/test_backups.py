"""Backups: make, list, restore, prune."""
import json
import os
import sqlite3
import time
from pathlib import Path

import pytest

from story_architect.core import backups
from story_architect.core.backups import (create_backup, list_backups,
                                          prune_automatic_backups, restore_backup)
from story_architect.core.writes import edit_entity
from story_architect.tools.story_backup import handler


@pytest.fixture
def fixture_path(fixture_path):
    """The shared fixture project, minus the backups that building it left behind,
    so every test here starts from an empty backup list."""
    for f in (fixture_path / ".story").glob("story_*.db"):
        f.unlink()
    return fixture_path


def _tool(project: Path, **args):
    return json.loads(handler({"project": str(project), **args},
                              root_path=str(project.parent)))


def _sql(project, sql, params=()):
    c = sqlite3.connect(str(project / ".story" / "story.db"), isolation_level=None)
    try:
        return c.execute(sql, params).fetchall()
    finally:
        c.close()


def _name(project, sql_value=None):
    return _sql(project, "SELECT name FROM entities WHERE id='kael'")[0][0]


def _rename(project, new):
    edit_entity(project, "character", "kael", {"name": new}, "rename")


def _stray_files(project):
    """Anything in .story/ that is not a story*.db backup or the live database."""
    live = {"story.db", "story.db-wal", "story.db-shm", "chat.db", "chat.db-wal", "chat.db-shm", "memory.md"}
    return sorted(f for f in os.listdir(project / ".story")
                  if f not in live and not (f.startswith("story_") and f.endswith(".db")))


# ─── naming and listing ───

def test_a_manual_backup_with_a_label(fixture_path):
    path = Path(create_backup(fixture_path, label="After the table read"))
    assert path.name.startswith("story_") and not path.name.startswith("story_auto_")
    [b] = list_backups(fixture_path)
    assert b["name"] == path.name
    assert b["kind"] == "manual"
    assert b["label"] == "after-the-table-read"
    assert b["size_bytes"] > 0
    assert b["created_at"][:10] == time.strftime("%Y-%m-%d")


def test_an_automatic_backup_is_marked_automatic(fixture_path):
    create_backup(fixture_path, automatic=True)
    [b] = list_backups(fixture_path)
    assert b["kind"] == "automatic" and b["label"] is None and b["name"].startswith("story_auto_")


def test_labels_are_made_safe_for_a_file_name(fixture_path):
    assert backups.slugify_label("Bozza finale — dopo la lettura") == "bozza-finale-dopo-la-lettura"
    assert backups.slugify_label("Così è meglio!") == "cosi-e-meglio"
    assert backups.slugify_label("../../etc/passwd") == "etc-passwd"
    assert backups.slugify_label("***") is None
    with pytest.raises(ValueError, match="letter or digit"):
        create_backup(fixture_path, label="***")
    path = create_backup(fixture_path, label="x" * 200)
    assert len(list_backups(fixture_path)[0]["label"]) <= 40
    assert Path(path).parent == fixture_path / ".story"


def test_newest_first(fixture_path):
    a = Path(create_backup(fixture_path, label="first"))
    b = Path(create_backup(fixture_path, label="second"))
    os.utime(a, (1, 1))                    # same-second names: mtime breaks the tie
    assert [x["label"] for x in list_backups(fixture_path)] == ["second", "first"]


def test_only_complete_backups_are_listed(fixture_path):
    folder = fixture_path / ".story"
    (folder / "story_20260101_101010_abcd1234.partial").write_bytes(b"half")
    (folder / "story_20260101_101010_abcd1234.db-wal").write_bytes(b"")
    (folder / "notes.db").write_bytes(b"")
    (folder / "story_garbage.db").write_bytes(b"")
    assert list_backups(fixture_path) == []


def test_old_style_names_count_as_manual_and_keep_their_date(fixture_path):
    folder = fixture_path / ".story"
    for n in ("story_20250102_030405.db", "story_20250102_030405_1.db"):
        (folder / n).write_bytes(b"x")
    found = list_backups(fixture_path)
    assert {b["kind"] for b in found} == {"manual"}
    assert {b["created_at"] for b in found} == {"2025-01-02T03:04:05"}
    assert all(b["label"] is None for b in found)


# ─── retention ───

def test_only_the_newest_automatic_backups_are_kept(fixture_path, monkeypatch):
    monkeypatch.setattr(backups, "AUTO_BACKUPS_KEPT", 3)
    made = []
    for i in range(6):
        p = Path(create_backup(fixture_path, automatic=True))
        os.utime(p, (1000 + i, 1000 + i))   # strictly ordered, whatever the clock says
        made.append(p.name)
    kept = [b["name"] for b in list_backups(fixture_path)]
    assert len(kept) == 3
    assert set(kept) <= set(made)
    # the one just taken always survives
    assert Path(create_backup(fixture_path, automatic=True)).exists()


def test_manual_and_legacy_backups_are_never_pruned(fixture_path, monkeypatch):
    monkeypatch.setattr(backups, "AUTO_BACKUPS_KEPT", 1)
    legacy = fixture_path / ".story" / "story_20240101_000000.db"
    legacy.write_bytes(b"x")
    mine = Path(create_backup(fixture_path, label="milestone"))
    for _ in range(5):
        create_backup(fixture_path, automatic=True)
    names = {b["name"] for b in list_backups(fixture_path)}
    assert legacy.name in names and mine.name in names
    assert len([b for b in list_backups(fixture_path) if b["kind"] == "automatic"]) == 1


def test_prune_returns_what_it_removed_and_always_keeps_one(fixture_path):
    for _ in range(3):
        create_backup(fixture_path, automatic=True)
    removed = prune_automatic_backups(fixture_path, keep=0)    # asking for none still keeps one
    assert len(removed) == 2
    assert len(list_backups(fixture_path)) == 1


def test_import_and_purge_take_automatic_backups(fixture_path):
    from story_architect.core.writes import delete_entity
    from story_architect.tools.story_admin import handler as admin
    from story_architect.tools.story_import import handler as imp

    imp({"project": str(fixture_path), "confirm": True}, root_path=str(fixture_path.parent))
    delete_entity(fixture_path, "character", "kael", "t", True)
    json.loads(admin({"action": "purge", "project": str(fixture_path),
                      "purge_confirm": "DELETE save-the-children",
                      "target": {"entity_type": "character", "id": "kael"}},
                     root_path=str(fixture_path.parent)))
    kinds = [b["kind"] for b in list_backups(fixture_path)]
    assert kinds.count("automatic") == 2 and kinds.count("manual") == 0


# ─── restore ───

def test_restore_brings_back_the_project_as_it_was(fixture_path):
    original = _name(fixture_path)
    snap = Path(create_backup(fixture_path, label="milestone")).name
    _rename(fixture_path, "Kael, Later")
    assert _name(fixture_path) == "Kael, Later"

    out = restore_backup(fixture_path, snap)
    assert out["success"] is True and out["restored"] == snap
    assert _name(fixture_path) == original


def test_a_restore_is_undone_by_restoring_its_safety_backup(fixture_path):
    snap = Path(create_backup(fixture_path, label="milestone")).name
    _rename(fixture_path, "Work done after the milestone")
    out = restore_backup(fixture_path, snap)
    safety = out["safety_backup"]
    assert out["hint"].endswith(safety + ".")
    entry = next(b for b in list_backups(fixture_path) if b["name"] == safety)
    assert entry["kind"] == "automatic" and entry["label"] == "before-restore"

    restore_backup(fixture_path, safety)
    assert _name(fixture_path) == "Work done after the milestone"


def test_restore_covers_every_table(fixture_path):
    from story_architect.core.writes import delete_entity
    snap = Path(create_backup(fixture_path)).name
    edit_entity(fixture_path, "scene", "central-room-day", {"Content": "REWRITTEN"}, "x")
    delete_entity(fixture_path, "character", "mira", "t", True)
    restore_backup(fixture_path, snap)
    assert _sql(fixture_path, "SELECT is_deleted FROM entities WHERE id='mira'") == [(0,)]
    assert _sql(fixture_path, "SELECT count(*) FROM revisions")[0][0] == 0
    assert "REWRITTEN" not in _sql(fixture_path, "SELECT body FROM sections WHERE "
                                   "entity_id='central-room-day' AND heading='Content'")[0][0]


def test_restoring_an_older_snapshot_upgrades_it(fixture_path):
    """The version number travels with the backup; a snapshot from before the
    last schema step is brought forward after it is restored."""
    from story_architect.core.db import SCHEMA_MIGRATIONS
    snap = Path(create_backup(fixture_path)).name
    c = sqlite3.connect(str(fixture_path / ".story" / snap))
    c.execute("DROP TABLE revisions")
    c.execute("PRAGMA user_version = 2")
    c.commit()
    c.close()
    restore_backup(fixture_path, snap)
    assert _sql(fixture_path, "PRAGMA user_version")[0][0] == len(SCHEMA_MIGRATIONS)
    assert _sql(fixture_path, "SELECT 1 FROM sqlite_master WHERE name='revisions'")


def test_other_open_connections_see_the_restore_and_the_watcher_fires(fixture_path):
    from story_architect.app.routes.projects import DbChangeWatcher

    snap = Path(create_backup(fixture_path)).name
    _rename(fixture_path, "Changed")
    other = sqlite3.connect(str(fixture_path / ".story" / "story.db"), isolation_level=None)
    other.execute("SELECT count(*) FROM entities").fetchone()       # open and warm
    watcher = DbChangeWatcher(fixture_path / ".story" / "story.db")
    watcher.changed()                                                # baseline

    restore_backup(fixture_path, snap)
    assert other.execute("SELECT name FROM entities WHERE id='kael'").fetchone()[0] != "Changed"
    assert watcher.changed() is True
    other.execute("UPDATE entities SET name='still writable' WHERE id='kael'")   # no lock left
    other.close()
    watcher.close()


def test_listing_and_restoring_leave_nothing_behind(fixture_path):
    snap = Path(create_backup(fixture_path, label="m")).name
    list_backups(fixture_path)
    restore_backup(fixture_path, snap)
    assert _stray_files(fixture_path) == []      # no -wal/-shm beside the backups


# ─── restore refusals: nothing may change ───

@pytest.mark.parametrize("bad", ["nope.db", "../story.db", "/etc/passwd", "story_20250101_000000.db"])
def test_an_unknown_or_path_like_name_is_refused(fixture_path, bad):
    before = _name(fixture_path)
    with pytest.raises(ValueError, match="No such backup"):
        restore_backup(fixture_path, bad)
    assert _name(fixture_path) == before
    assert [b for b in list_backups(fixture_path) if b["label"] == "before-restore"] == []


def _plant(project, name, data: bytes):
    (project / ".story" / name).write_bytes(data)
    return name


def test_a_corrupt_file_is_refused(fixture_path):
    name = _plant(fixture_path, "story_20250101_000000_abcdefgh.db", b"this is not sqlite" * 100)
    before = _name(fixture_path)
    with pytest.raises(ValueError, match="not a readable project database|cannot be opened|damaged"):
        restore_backup(fixture_path, name)
    assert _name(fixture_path) == before


def _corrupt_an_indexed_value(path: Path, needle: bytes, broken: bytes) -> None:
    """Rewrite one copy of `needle` in the file, leaving a row and its index disagreeing.

    The value also appears in prose, where a change is invisible to SQLite, so
    try each copy until the file's own integrity check objects to it.
    """
    original = path.read_bytes()
    at = original.find(needle)
    while at != -1:
        path.write_bytes(original[:at] + broken + original[at + len(needle):])
        conn = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return
        finally:
            conn.close()
        at = original.find(needle, at + 1)
    path.write_bytes(original)
    raise AssertionError(f"no copy of {needle!r} is in an index")


def test_a_readable_but_damaged_backup_is_refused(fixture_path):
    """The file opens and queries fine, but a table row disagrees with its index."""
    snap = Path(create_backup(fixture_path)).name
    path = fixture_path / ".story" / snap
    _corrupt_an_indexed_value(path, b"the-administrator", b"the-adm1n1strator")
    before = _name(fixture_path)
    with pytest.raises(ValueError, match="damaged"):
        restore_backup(fixture_path, snap)
    assert _name(fixture_path) == before


def test_a_database_that_is_not_a_project_is_refused(fixture_path, tmp_path):
    other = tmp_path / "other.db"
    c = sqlite3.connect(str(other))
    c.execute("CREATE TABLE unrelated (x)")
    c.commit()
    c.close()
    name = _plant(fixture_path, "story_20250101_000000_abcdefgh.db", other.read_bytes())
    with pytest.raises(ValueError, match="not a project database"):
        restore_backup(fixture_path, name)


def test_a_backup_from_a_newer_build_is_refused(fixture_path):
    snap = Path(create_backup(fixture_path)).name
    c = sqlite3.connect(str(fixture_path / ".story" / snap))
    c.execute("PRAGMA user_version = 99")
    c.commit()
    c.close()
    before = _name(fixture_path)
    with pytest.raises(ValueError, match="newer version"):
        restore_backup(fixture_path, snap)
    assert _name(fixture_path) == before


def test_a_different_page_size_is_refused(fixture_path):
    snap = Path(create_backup(fixture_path)).name
    path = fixture_path / ".story" / snap
    c = sqlite3.connect(str(path))
    c.execute("PRAGMA journal_mode=DELETE")
    c.execute("PRAGMA page_size = 8192")
    c.execute("VACUUM")
    c.close()
    before = _name(fixture_path)
    with pytest.raises(ValueError, match="page size"):
        restore_backup(fixture_path, snap)
    assert _name(fixture_path) == before


# ─── the tool ───

def test_the_tool_defaults_to_creating_a_backup(fixture_path):
    out = _tool(fixture_path)
    assert out["success"] and Path(out["backup"]).exists()
    assert list_backups(fixture_path)[0]["kind"] == "manual"


def test_the_tool_lists_creates_with_a_label_and_restores(fixture_path):
    assert "no backups" in _tool(fixture_path, action="list")["message"].lower()
    made = _tool(fixture_path, action="create", label="Draft two")
    listed = _tool(fixture_path, action="list")
    assert listed["count"] == 1 and listed["backups"][0]["label"] == "draft-two"
    assert listed["automatic_kept"] == backups.AUTO_BACKUPS_KEPT

    _rename(fixture_path, "Changed")
    out = _tool(fixture_path, action="restore", backup=Path(made["backup"]).name)
    assert out["success"] and _name(fixture_path) != "Changed"


@pytest.mark.parametrize("args, fragment", [
    ({"action": "restore"}, "needs backup"),
    ({"action": "restore", "backup": "nope.db"}, "No such backup"),
    ({"action": "create", "label": "***"}, "letter or digit"),
    ({"action": "explode"}, "Unknown action"),
])
def test_the_tool_reports_bad_requests(fixture_path, args, fragment):
    assert fragment in _tool(fixture_path, **args)["error"]


# ─── committed draft receipts ───

_RENAME_OP = {"op": "edit", "entity_type": "character", "entity_id": "kael",
              "data": {"name": "Kael Prime"}, "summary": "rename"}


def test_old_committed_draft_rows_are_pruned_but_recent_and_open_ones_stay(fixture_path):
    from story_architect.core import drafts

    def row(id_, status, created):
        _sql(fixture_path, "INSERT INTO drafts (id, ops, summary, created_at, status) "
                           "VALUES (?, '[]', '', ?, ?)", (id_, created, status))
    row("old-committed", "committed", "2020-01-01T00:00:00")
    row("recent-committed", "committed", time.strftime("%Y-%m-%dT%H:%M:%S"))
    row("old-open", "open", "2020-01-01T00:00:00")

    staged = drafts.stage(fixture_path, [_RENAME_OP], "rename")
    drafts.commit(fixture_path, staged["draft_id"])
    ids = {r[0] for r in _sql(fixture_path, "SELECT id FROM drafts")}
    assert "old-committed" not in ids
    assert {"recent-committed", "old-open", staged["draft_id"]} <= ids


def test_the_draft_just_committed_keeps_its_receipt_even_if_it_was_staged_long_ago(fixture_path):
    from story_architect.core import drafts
    staged = drafts.stage(fixture_path, [_RENAME_OP], "rename")
    _sql(fixture_path, "UPDATE drafts SET created_at='2020-01-01T00:00:00' WHERE id=?",
         (staged["draft_id"],))
    drafts.commit(fixture_path, staged["draft_id"])
    assert _sql(fixture_path, "SELECT status FROM drafts WHERE id=?",
                (staged["draft_id"],)) == [("committed",)]
    again = drafts.commit(fixture_path, staged["draft_id"])      # a repeated commit replays
    assert again.get("committed") is True
