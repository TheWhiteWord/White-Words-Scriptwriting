"""Version history of section text.

Every overwrite of a section body keeps the text it replaced, so a scene can be
taken back to an earlier state. One hook (edit_entity) covers the agent's draft
commits and the script editor's Save.
"""
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from story_architect.core import revisions
from story_architect.core.writes import delete_entity, edit_entity
from story_architect.tools.story_admin import handler

SCENE = "central-room-day"
OTHER = "central-room-night"


def _admin(project: Path, **args):
    return json.loads(handler({"project": str(project), **args},
                              root_path=str(project.parent)))


def _sql(project, sql, params=()):
    c = sqlite3.connect(str(project / ".story" / "story.db"), isolation_level=None)
    try:
        return c.execute(sql, params).fetchall()
    finally:
        c.close()


def _content(project, scene=SCENE):
    return _sql(project, "SELECT body FROM sections WHERE entity_id=? AND heading='Content'",
                (scene,))[0][0]


def _write(project, text, scene=SCENE, summary="edit"):
    return edit_entity(project, "scene", scene, {"Content": text}, summary)


def _revs(project, scene=SCENE, heading="Content"):
    return revisions.list_revisions(project, scene, heading)


# ─── what gets kept ───

def test_an_overwrite_keeps_the_text_it_replaced(fixture_path):
    original = _content(fixture_path)
    _write(fixture_path, "A new version of the scene.", summary="Tightened the opening")

    revs = _revs(fixture_path)
    assert len(revs) == 1
    assert revs[0]["heading"] == "Content"
    assert revs[0]["summary"] == "Tightened the opening"
    assert revs[0]["chars"] == len(original)
    full = revisions.get_revision(fixture_path, SCENE, revs[0]["id"])
    assert full["body"] == original
    assert _content(fixture_path) == "A new version of the scene."


def test_an_identical_write_keeps_nothing(fixture_path):
    _write(fixture_path, _content(fixture_path))
    assert _revs(fixture_path) == []


def test_an_empty_previous_body_keeps_nothing(fixture_path):
    """The fixture's placeholder sections are empty: nothing would be lost."""
    assert _sql(fixture_path, "SELECT body FROM sections WHERE entity_id=? AND heading='Beats'",
                (SCENE,))[0][0] == ""
    edit_entity(fixture_path, "scene", SCENE, {"Beats": "First beat."}, "fill in")
    assert _revs(fixture_path, heading="Beats") == []


def test_only_changed_sections_are_kept(fixture_path):
    edit_entity(fixture_path, "scene", SCENE,
                {"Content": "New text.", "Notes": _sql(
                    fixture_path, "SELECT body FROM sections WHERE entity_id=? AND heading='Notes'",
                    (SCENE,))[0][0]}, "edit")
    assert [r["heading"] for r in _revs(fixture_path, heading=None)] == ["Content"]


def test_newest_first_with_a_preview(fixture_path):
    _write(fixture_path, "\n\nFIRST EDIT\nmore", summary="one")
    _write(fixture_path, "second edit", summary="two")
    _write(fixture_path, "third edit", summary="three")
    revs = _revs(fixture_path)
    # each revision carries the summary of the edit that replaced it
    assert [r["summary"] for r in revs] == ["three", "two", "one"]
    assert revs[1]["preview"] == "FIRST EDIT"   # first non-empty line, trimmed


# ─── retention ───

def test_only_the_last_n_are_kept_per_section(fixture_path, monkeypatch):
    monkeypatch.setattr(revisions, "REVISIONS_KEPT", 3)
    for i in range(6):
        _write(fixture_path, f"version {i}")
    revs = _revs(fixture_path)
    assert len(revs) == 3
    bodies = [revisions.get_revision(fixture_path, SCENE, r["id"])["body"] for r in revs]
    assert bodies == ["version 4", "version 3", "version 2"]


def test_the_limit_is_per_section_and_per_entity(fixture_path, monkeypatch):
    monkeypatch.setattr(revisions, "REVISIONS_KEPT", 2)
    _write(fixture_path, "other scene v1", scene=OTHER)
    _write(fixture_path, "other scene v2", scene=OTHER)
    for i in range(5):
        _write(fixture_path, f"version {i}")
    assert len(_revs(fixture_path)) == 2
    assert len(_revs(fixture_path, scene=OTHER)) == 2   # the other scene's untouched by this one's churn


# ─── restore ───

def test_restore_puts_the_text_back_and_keeps_what_it_replaces(fixture_path):
    original = _content(fixture_path)
    _write(fixture_path, "Version B.")
    _write(fixture_path, "Version C.")
    oldest = _revs(fixture_path)[-1]            # the original text
    assert revisions.get_revision(fixture_path, SCENE, oldest["id"])["body"] == original

    out = revisions.restore_revision(fixture_path, SCENE, oldest["id"])
    assert out["success"] is True and out["heading"] == "Content"
    assert _content(fixture_path) == original
    # the text it replaced is now a revision: a restore can be undone
    newest = _revs(fixture_path)[0]
    assert revisions.get_revision(fixture_path, SCENE, newest["id"])["body"] == "Version C."
    revisions.restore_revision(fixture_path, SCENE, newest["id"])
    assert _content(fixture_path) == "Version C."


def test_restore_refuses_what_it_should_and_changes_nothing(fixture_path):
    _write(fixture_path, "Version B.")
    _write(fixture_path, "x", scene=OTHER)
    rev = _revs(fixture_path)[0]["id"]
    before = (_content(fixture_path), len(_revs(fixture_path)))

    with pytest.raises(ValueError, match="not found"):
        revisions.restore_revision(fixture_path, SCENE, 999999)
    with pytest.raises(ValueError, match="not found"):   # a revision of a different entity
        revisions.restore_revision(fixture_path, OTHER, rev)

    _sql(fixture_path, "UPDATE entities SET status='locked' WHERE id=?", (SCENE,))
    with pytest.raises(ValueError, match="locked"):
        revisions.restore_revision(fixture_path, SCENE, rev)
    assert (_content(fixture_path), len(_revs(fixture_path))) == before


# ─── one hook for both write paths ───

def test_the_script_editors_save_keeps_a_revision_too(fixture_path):
    from story_architect.core import manual_edits as me

    view = me.load_scene_script(fixture_path, SCENE)
    sc = view["scene"]
    blocks = [dict(b) for b in view["blocks"]]
    blocks[0] = {**blocks[0], "text": blocks[0]["text"] + " (edited by hand)"}
    before = _content(fixture_path)
    me.save_scene_script(fixture_path, SCENE, {
        "base_hash": view["hash"], "blocks": blocks,
        "heading": {k: sc.get(k, "") for k in
                    ("int_ext", "place", "location", "time_of_day", "forced_heading")},
        "extra_cast": []})

    revs = _revs(fixture_path)
    assert len(revs) == 1
    assert revs[0]["summary"] == "Script edited by hand in the script editor"
    assert revisions.get_revision(fixture_path, SCENE, revs[0]["id"])["body"] == before


def test_the_snapshot_and_the_overwrite_are_one_transaction(fixture_path):
    """If the overwrite fails, the revision made just before it must not survive."""
    _sql(fixture_path, "CREATE TRIGGER boom BEFORE UPDATE ON sections "
                       "BEGIN SELECT RAISE(ABORT, 'boom'); END")
    original = _content(fixture_path)
    with pytest.raises(sqlite3.Error, match="boom"):
        _write(fixture_path, "never lands")
    _sql(fixture_path, "DROP TRIGGER boom")
    assert _revs(fixture_path) == []
    assert _content(fixture_path) == original


# ─── lifecycle ───

def test_history_survives_a_soft_delete_and_a_restore(fixture_path):
    _write(fixture_path, "Version B.")
    delete_entity(fixture_path, "scene", SCENE, "t", True)
    assert len(_revs(fixture_path)) == 1                # still there while in the trash
    _admin(fixture_path, action="restore", target={"entity_type": "scene", "id": SCENE},
           summary="back")
    assert len(_revs(fixture_path)) == 1


def test_purging_an_entity_removes_its_history_and_only_its_history(fixture_path):
    _write(fixture_path, "Version B.")
    _write(fixture_path, "Other B.", scene=OTHER)
    delete_entity(fixture_path, "scene", SCENE, "t", True)
    out = _admin(fixture_path, action="purge", purge_confirm="DELETE save-the-children",
                 target={"entity_type": "scene", "id": SCENE})
    assert out["success"] is True
    assert _sql(fixture_path, "SELECT count(*) FROM revisions WHERE entity_id=?", (SCENE,))[0][0] == 0
    assert len(_revs(fixture_path, scene=OTHER)) == 1


def test_a_reimport_keeps_the_history(fixture_path):
    from story_architect.tools.story_import import handler as imp
    _write(fixture_path, "Version B.")
    before = _sql(fixture_path, "SELECT id, body FROM revisions")
    out = json.loads(imp({"project": str(fixture_path), "confirm": True},
                         root_path=str(fixture_path.parent)))
    assert out.get("success") is True
    assert _sql(fixture_path, "SELECT id, body FROM revisions") == before


# ─── the story_admin actions ───

def test_the_actions_work_end_to_end(fixture_path):
    original = _content(fixture_path)
    _write(fixture_path, "Version B.", summary="rewrite")

    listed = _admin(fixture_path, action="list_revisions", target={"id": SCENE})
    assert listed["success"] and listed["count"] == 1
    assert listed["kept_per_section"] == revisions.REVISIONS_KEPT
    rev_id = listed["revisions"][0]["id"]

    out = _admin(fixture_path, action="restore_revision", target={"id": SCENE},
                 revision_id=rev_id)
    assert out["success"] is True
    assert _content(fixture_path) == original


def test_list_filters_by_heading_and_reports_an_empty_history(fixture_path):
    assert "No earlier versions" in _admin(fixture_path, action="list_revisions",
                                           target={"id": SCENE})["message"]
    _write(fixture_path, "B")
    assert _admin(fixture_path, action="list_revisions", target={"id": SCENE},
                  heading="Notes")["count"] == 0
    assert _admin(fixture_path, action="list_revisions", target={"id": SCENE},
                  heading="Content")["count"] == 1


@pytest.mark.parametrize("args, fragment", [
    ({"action": "list_revisions"}, "needs target"),
    ({"action": "restore_revision", "target": {"id": SCENE}}, "integer revision_id"),
    ({"action": "restore_revision", "target": {"id": SCENE}, "revision_id": True},
     "integer revision_id"),
    ({"action": "restore_revision", "target": {"id": SCENE}, "revision_id": 424242},
     "not found"),
])
def test_bad_requests_are_errors_not_crashes(fixture_path, args, fragment):
    out = _admin(fixture_path, **args)
    assert fragment in out["error"]


# ─── schema ───

def test_a_new_project_has_the_table_and_an_old_one_gains_it(tmp_path):
    from story_architect.core.db import SCHEMA_MIGRATIONS, get_db
    from story_architect.core.writes import create_project

    root = tmp_path / "v"
    (root / "projects").mkdir(parents=True)
    create_project("stc", {"name": "STC", "logline": "L"}, root)
    proj = root / "projects" / "stc"
    assert _sql(proj, "SELECT 1 FROM sqlite_master WHERE name='revisions'")

    # as built before this step existed: stamped 2, no revisions table
    _sql(proj, "DROP TABLE revisions")
    _sql(proj, "PRAGMA user_version = 2")
    conn = get_db(proj)
    try:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='revisions'").fetchone()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(SCHEMA_MIGRATIONS)
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='idx_revisions_section'").fetchone()
    finally:
        conn.close()
