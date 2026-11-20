"""delete_project moves the project to a trash folder; restore_project brings it back."""
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from story_architect.tools import story_admin
from story_architect.tools.story_admin import TRASH_DIR, handler

SLUG = "stc"


@pytest.fixture
def root(tmp_path, fixture_path):
    """A root holding one project, 'stc', with the extras a real one has."""
    r = tmp_path / "vault"
    proj = r / "projects" / SLUG
    proj.parent.mkdir(parents=True)
    shutil.copytree(str(fixture_path), str(proj))
    (proj / "notes.md").write_text("hand-written notes, not in the database")
    (proj / ".story" / "chat.db").write_bytes(b"pretend chat history")
    return r


def _admin(root, **args):
    return json.loads(handler(args, root_path=str(root)))


def _delete(root, slug=SLUG):
    return _admin(root, action="delete_project", project=slug)


def _tree_hashes(folder: Path) -> dict:
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


def _entities(folder: Path) -> int:
    c = sqlite3.connect(str(folder / ".story" / "story.db"))
    try:
        return c.execute("SELECT count(*) FROM entities").fetchone()[0]
    finally:
        c.close()


# ─── delete ───

def test_the_whole_folder_moves_and_nothing_is_left_behind(root):
    proj = root / "projects" / SLUG
    before = _tree_hashes(proj)
    out = _delete(root)

    assert out["success"] is True
    assert not proj.exists()
    trashed = Path(out["trashed_to"])
    assert trashed.name == SLUG and trashed.parent.parent == root / TRASH_DIR
    assert _tree_hashes(trashed) == before          # every file, byte for byte
    assert (trashed / "notes.md").read_text().startswith("hand-written")
    assert (trashed / ".story" / "chat.db").exists()
    meta = json.loads((trashed.parent / "deleted.json").read_text())
    assert meta["slug"] == SLUG and meta["original_path"] == str(proj)


def test_the_trash_is_hidden_and_not_listed_as_a_project(root):
    _delete(root)
    assert TRASH_DIR.startswith(".") and TRASH_DIR != ".trash"
    assert _admin(root, action="list_projects")["projects"] == []


def test_deleting_asks_for_no_confirmation_and_moves_the_whole_folder(root):
    """It used to refuse without a typed "DELETE <slug>" that its own refusal printed."""
    before = _tree_hashes(root / "projects" / SLUG)
    out = _admin(root, action="delete_project", project=SLUG)
    assert out["success"] is True and "action_required" not in out
    assert not (root / "projects" / SLUG).exists()
    assert _tree_hashes(Path(out["trashed_to"])) == before, "every byte is in the trash"


def test_a_failed_move_leaves_the_project_where_it_was(root, monkeypatch):
    def broken(src, dst):
        raise OSError("disk exploded")
    monkeypatch.setattr(story_admin.shutil, "move", broken)
    before = _tree_hashes(root / "projects" / SLUG)
    with pytest.raises(OSError, match="exploded"):
        _delete(root)
    assert _tree_hashes(root / "projects" / SLUG) == before
    assert list((root / TRASH_DIR).iterdir()) == []      # no half-made slot


def test_unflushed_writes_in_the_wal_travel_with_the_database(root):
    """A write that is only in story.db-wal must survive the move and the restore."""
    db = root / "projects" / SLUG / ".story" / "story.db"
    live = sqlite3.connect(str(db), isolation_level=None)
    live.execute("PRAGMA journal_mode=WAL")
    live.execute("UPDATE entities SET name='Only in the WAL' WHERE id='kael'")
    assert (db.parent / "story.db-wal").stat().st_size > 0

    out = _delete(root)
    restored = _admin(root, action="restore_project", trash_id=out["trash_id"])
    assert restored["success"] is True
    live.close()
    c = sqlite3.connect(str(db))
    try:
        assert c.execute("SELECT name FROM entities WHERE id='kael'").fetchone()[0] == "Only in the WAL"
    finally:
        c.close()


def test_the_live_update_watcher_survives_the_folder_moving(root):
    from story_architect.app.routes.projects import DbChangeWatcher
    watcher = DbChangeWatcher(root / "projects" / SLUG / ".story" / "story.db")
    watcher.changed()
    _delete(root)
    assert watcher.changed() is False       # file gone: quiet, no exception
    watcher.close()


# ─── list and restore ───

def test_list_and_restore_round_trip(root):
    proj = root / "projects" / SLUG
    before = _tree_hashes(proj)
    out = _delete(root)

    listed = _admin(root, action="list_trashed_projects")
    assert listed["count"] == 1
    [entry] = listed["trashed"]
    assert entry["slug"] == SLUG and entry["trash_id"] == out["trash_id"]
    assert entry["has_database"] is True and entry["deleted_at"]

    back = _admin(root, action="restore_project", trash_id=out["trash_id"])
    assert back["success"] is True and Path(back["project"]) == proj
    assert _tree_hashes(proj) == before
    assert _entities(proj) > 0
    assert _admin(root, action="list_trashed_projects")["count"] == 0
    assert list((root / TRASH_DIR).iterdir()) == []         # the slot is gone too


def test_an_empty_trash_says_so(root):
    out = _admin(root, action="list_trashed_projects")
    assert out["count"] == 0 and "No projects" in out["message"]


def test_deleting_the_same_slug_twice_keeps_both(root):
    first = _delete(root)
    shutil.copytree(first["trashed_to"], root / "projects" / SLUG)   # same slug is back
    (root / "projects" / SLUG / "notes.md").write_text("second incarnation")
    second = _delete(root)

    assert first["trash_id"] != second["trash_id"]
    listed = _admin(root, action="list_trashed_projects")
    assert [e["trash_id"] for e in listed["trashed"]][0] == second["trash_id"]   # newest first
    assert listed["count"] == 2
    _admin(root, action="restore_project", trash_id=first["trash_id"])
    assert (root / "projects" / SLUG / "notes.md").read_text().startswith("hand-written")


def test_restore_never_overwrites_an_existing_project(root):
    out = _delete(root)
    (root / "projects" / SLUG / ".story").mkdir(parents=True)
    (root / "projects" / SLUG / ".story" / "story.db").write_bytes(b"a newer project")
    res = _admin(root, action="restore_project", trash_id=out["trash_id"])
    assert "already exists" in res["error"]
    assert (root / "projects" / SLUG / ".story" / "story.db").read_bytes() == b"a newer project"
    assert _admin(root, action="list_trashed_projects")["count"] == 1     # still in the trash


@pytest.mark.parametrize("args, fragment", [
    ({}, "needs trash_id"),
    ({"trash_id": "nope"}, "No such project in the trash"),
    ({"trash_id": "../projects"}, "No such project in the trash"),
    ({"trash_id": "/etc"}, "No such project in the trash"),
])
def test_restore_refusals(root, args, fragment):
    _delete(root)
    out = _admin(root, action="restore_project", **args)
    assert fragment in out["error"]
    assert _admin(root, action="list_trashed_projects")["count"] == 1


def test_a_half_made_slot_is_not_listed_or_restorable(root):
    (root / TRASH_DIR / "stc_20260101_000000_abcd1234").mkdir(parents=True)         # no deleted.json
    broken = root / TRASH_DIR / "stc_20260101_000001_abcd1234"
    broken.mkdir()
    (broken / "deleted.json").write_text(json.dumps({"slug": "stc"}))               # no folder
    assert _admin(root, action="list_trashed_projects")["count"] == 0
    assert "No such project" in _admin(root, action="restore_project",
                                       trash_id=broken.name)["error"]


def test_the_actions_are_in_the_tool_schema():
    enum = story_admin.SCHEMA["properties"]["action"]["enum"]
    assert {"list_trashed_projects", "restore_project"} <= set(enum)
    assert "trash_id" in story_admin.SCHEMA["properties"]
