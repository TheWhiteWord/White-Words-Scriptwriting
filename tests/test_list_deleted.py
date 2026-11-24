"""story_admin action=list_deleted: the trash, and the ids restore/purge need."""
import json
import sqlite3
from pathlib import Path

import pytest

from white_words.scriptwriting.core.writes import delete_entity
from white_words.scriptwriting.tools.story_admin import handler


def _admin(project: Path, **args):
    out = handler({"project": str(project), **args}, root_path=str(project.parent))
    return json.loads(out)


def _list(project, **args):
    return _admin(project, action="list_deleted", **args)


def _sql(project, sql, params=()):
    c = sqlite3.connect(str(project / ".story" / "story.db"), isolation_level=None)
    try:
        return c.execute(sql, params).fetchall()
    finally:
        c.close()


def _first_scene_with_beats(project):
    return _sql(project, "SELECT parent_id FROM entities WHERE type='scene_beats' LIMIT 1")[0][0]


def test_empty_trash(fixture_path):
    out = _list(fixture_path)
    assert out["success"] is True
    assert out["count"] == 0 and out["deleted"] == []
    assert out["message"] == "Nothing has been deleted."


def test_a_deleted_entity_is_listed_with_what_restore_needs(fixture_path):
    delete_entity(fixture_path, "character", "kael", "t", True)
    out = _list(fixture_path)
    assert out["count"] == 1
    item = out["deleted"][0]
    assert item["type"] == "character" and item["id"] == "kael"
    assert item["name"]
    assert item["deleted_at"]
    assert item["includes"] == []
    assert item["purge_eligible"] is False   # just deleted: under the 30-day floor


def test_listed_type_and_id_feed_straight_into_restore(fixture_path):
    delete_entity(fixture_path, "character", "kael", "t", True)
    item = _list(fixture_path)["deleted"][0]
    restored = _admin(fixture_path, action="restore",
                      target={"entity_type": item["type"], "id": item["id"]},
                      summary="restore from the list")
    assert restored.get("success") is True
    assert _list(fixture_path)["deleted"] == []


def test_live_entities_are_not_listed(fixture_path):
    delete_entity(fixture_path, "character", "kael", "t", True)
    ids = {d["id"] for d in _list(fixture_path)["deleted"]}
    assert ids == {"kael"}


def test_children_deleted_with_a_parent_fold_under_it(fixture_path):
    scene = _first_scene_with_beats(fixture_path)
    beats = [r[0] for r in _sql(
        fixture_path, "SELECT id FROM entities WHERE type='scene_beats' AND parent_id=?",
        (scene,))]
    assert beats
    assert delete_entity(fixture_path, "scene", scene, "t", True)["success"]

    out = _list(fixture_path)
    assert out["count"] == 1, "one deletion should be one entry"
    item = out["deleted"][0]
    assert item["id"] == scene and item["type"] == "scene"
    assert sorted(i["id"] for i in item["includes"]) == sorted(beats)
    assert all(i["type"] == "scene_beats" for i in item["includes"])


def test_a_child_with_its_own_deletion_time_is_its_own_entry(fixture_path):
    """Grouping goes by the shared deletion stamp, not by parentage alone: a beat
    deleted at another time is a separate item, and restoring the scene's
    deletion is not what brings it back.

    The state is set up in the database directly. delete_entity does not
    currently preserve an earlier deletion time on a child (its child query does
    not skip rows already in the trash), which is task D1's to settle.
    """
    scene = _first_scene_with_beats(fixture_path)
    beat = _sql(fixture_path, "SELECT id FROM entities WHERE type='scene_beats' "
                              "AND parent_id=?", (scene,))[0][0]
    assert delete_entity(fixture_path, "scene", scene, "t", True)["success"]
    _sql(fixture_path, "UPDATE entities SET deleted_at='2020-01-01T00:00:00' WHERE id=?", (beat,))

    items = _list(fixture_path)["deleted"]
    assert {scene, beat} <= {d["id"] for d in items}
    scene_item = next(d for d in items if d["id"] == scene)
    assert beat not in [i["id"] for i in scene_item["includes"]]


def test_newest_deletion_first(fixture_path):
    delete_entity(fixture_path, "character", "kael", "t", True)
    delete_entity(fixture_path, "character", "mira", "t", True)
    _sql(fixture_path, "UPDATE entities SET deleted_at='2020-01-01T00:00:00' WHERE id='kael'")
    items = _list(fixture_path)["deleted"]
    assert [d["id"] for d in items] == ["mira", "kael"]


def test_purge_eligible_follows_the_age_floor(fixture_path):
    delete_entity(fixture_path, "character", "kael", "t", True)
    _sql(fixture_path, "UPDATE entities SET deleted_at='2020-01-01T00:00:00' WHERE id='kael'")
    assert _list(fixture_path)["deleted"][0]["purge_eligible"] is True
    # a longer threshold than the age of the deletion: no longer eligible
    assert _list(fixture_path, older_than_days=100000)["deleted"][0]["purge_eligible"] is False


def test_unknown_project_is_an_error_not_a_crash(fixture_path):
    out = json.loads(handler({"action": "list_deleted", "project": "no-such-project"},
                             root_path=str(fixture_path.parent)))
    assert "error" in out


def test_action_is_advertised_in_the_tool_schema():
    from white_words.scriptwriting.tools.story_admin import SCHEMA
    assert "list_deleted" in SCHEMA["properties"]["action"]["enum"]
