"""Purging one trashed item forever: `purge_deleted` with a `target`.

The approved draft runs `purge_deleted` (see test_purge_approval.py for the approval
itself); these tests call it directly."""

import json
import sqlite3
from pathlib import Path

import pytest

from white_words.scriptwriting.core.writes import delete_entity
from white_words.scriptwriting.core.trash import purge_deleted
from white_words.scriptwriting.tools.story_admin import handler


def _admin(project: Path, **args):
    out = handler({"project": str(project), **args}, root_path=str(project.parent))
    return json.loads(out)


def _purge(project, target=None, older_than_days=30):
    return purge_deleted(project, target, older_than_days)


def _purge_one(project, entity_id, entity_type, **extra):
    return _purge(project, target={"entity_type": entity_type, "id": entity_id}, **extra)


def _sql(project, sql, params=()):
    c = sqlite3.connect(str(project / ".story" / "story.db"), isolation_level=None)
    try:
        return c.execute(sql, params).fetchall()
    finally:
        c.close()


def _exists(project, entity_id):
    return bool(_sql(project, "SELECT 1 FROM entities WHERE id=?", (entity_id,)))


def _scene_with_beat(project):
    (scene,) = _sql(project, "SELECT parent_id FROM entities WHERE type='scene_beats' LIMIT 1")[0]
    (beat,) = _sql(
        project, "SELECT id FROM entities WHERE type='scene_beats' AND parent_id=?", (scene,)
    )[0]
    return scene, beat


def _snapshot(project):
    return {
        t: _sql(project, f"SELECT * FROM {t} ORDER BY 1, 2")
        for t in ("entities", "relations", "sections")
    }


def test_removes_that_entity_and_everything_attached_to_it(fixture_path):
    delete_entity(fixture_path, "character", "kael", "t", True)
    assert _sql(fixture_path, "SELECT count(*) FROM sections WHERE entity_id='kael'")[0][0] > 0

    out = _purge_one(fixture_path, "kael", "character")
    assert out["success"] is True
    assert [p["id"] for p in out["purged"]] == ["kael"]
    assert not _exists(fixture_path, "kael")
    assert _sql(fixture_path, "SELECT count(*) FROM sections WHERE entity_id='kael'")[0][0] == 0
    assert (
        _sql(fixture_path, "SELECT count(*) FROM relations WHERE from_id='kael' OR to_id='kael'")[
            0
        ][0]
        == 0
    )


def test_other_trashed_items_stay_even_when_they_are_old_enough_to_purge(fixture_path):
    delete_entity(fixture_path, "character", "kael", "t", True)
    delete_entity(fixture_path, "character", "mira", "t", True)
    _sql(fixture_path, "UPDATE entities SET deleted_at='2020-01-01T00:00:00' WHERE id='mira'")

    _purge_one(fixture_path, "kael", "character")
    assert not _exists(fixture_path, "kael")
    assert _exists(fixture_path, "mira")
    assert [d["id"] for d in _admin(fixture_path, action="list_deleted")["deleted"]] == ["mira"]


def test_a_fresh_deletion_can_be_purged_by_name(fixture_path):
    """The age floor guards the bulk sweep; naming one item is not a sweep."""
    delete_entity(fixture_path, "character", "kael", "t", True)
    assert _purge_one(fixture_path, "kael", "character")["success"] is True


def test_older_than_days_is_ignored_for_a_named_item(fixture_path):
    delete_entity(fixture_path, "character", "kael", "t", True)
    out = _purge_one(fixture_path, "kael", "character", older_than_days=100000)
    assert [p["id"] for p in out["purged"]] == ["kael"]


def test_takes_a_backup_first_and_it_still_has_the_entity(fixture_path):
    delete_entity(fixture_path, "character", "kael", "t", True)
    out = _purge_one(fixture_path, "kael", "character")
    snap = Path(out["backup"])
    assert snap.exists()
    c = sqlite3.connect(str(snap))
    try:
        assert c.execute("SELECT is_deleted FROM entities WHERE id='kael'").fetchone() == (1,)
    finally:
        c.close()


# ─── refusals: nothing may change ───


def test_the_agents_request_removes_nothing(fixture_path):
    """The admin action only stages it; the person approves in the app."""
    delete_entity(fixture_path, "character", "kael", "t", True)
    out = _admin(fixture_path, action="purge", target={"entity_type": "character", "id": "kael"})
    assert out["purged"] is False and out["success"] is True
    assert _exists(fixture_path, "kael")


def test_refuses_an_entity_that_is_not_in_the_trash(fixture_path):
    before = _snapshot(fixture_path)
    out = _purge_one(fixture_path, "kael", "character")  # live
    assert "not in the trash" in out["error"]
    assert _snapshot(fixture_path) == before


def test_refuses_an_unknown_id(fixture_path):
    before = _snapshot(fixture_path)
    out = _purge_one(fixture_path, "no-such-thing", "character")
    assert "not found" in out["error"].lower()
    assert _snapshot(fixture_path) == before


def test_refuses_a_wrong_type_rather_than_deleting_the_wrong_thing(fixture_path):
    delete_entity(fixture_path, "character", "kael", "t", True)
    before = _snapshot(fixture_path)
    out = _purge_one(fixture_path, "kael", "location")
    assert "is a character" in out["error"]
    assert _snapshot(fixture_path) == before


# ─── what goes with it ───


def test_things_deleted_in_the_same_operation_go_too(fixture_path):
    scene, beat = _scene_with_beat(fixture_path)
    delete_entity(fixture_path, "scene", scene, "t", True)
    out = _purge_one(fixture_path, scene, "scene")
    assert sorted(p["id"] for p in out["purged"]) == sorted([scene, beat])
    assert not _exists(fixture_path, scene) and not _exists(fixture_path, beat)
    assert _sql(fixture_path, "SELECT count(*) FROM sections WHERE entity_id=?", (beat,))[0][0] == 0


def test_a_child_deleted_separately_stays_in_the_trash_and_loses_its_dead_link(fixture_path):
    scene, beat = _scene_with_beat(fixture_path)
    delete_entity(fixture_path, "scene", scene, "t", True)
    _sql(fixture_path, "UPDATE entities SET deleted_at='2020-01-01T00:00:00' WHERE id=?", (beat,))

    out = _purge_one(fixture_path, scene, "scene")
    assert [p["id"] for p in out["purged"]] == [scene]
    assert _exists(fixture_path, beat)
    assert _sql(fixture_path, "SELECT parent_id FROM entities WHERE id=?", (beat,)) == [("",)]
    # still in the trash, and restorable on its own
    assert beat in [d["id"] for d in _admin(fixture_path, action="list_deleted")["deleted"]]
    restored = _admin(
        fixture_path,
        action="restore",
        target={"entity_type": "scene_beats", "id": beat},
        summary="back",
    )
    assert restored["success"] is True


def test_the_bulk_purge_also_clears_dead_links_on_what_it_leaves_behind(fixture_path):
    scene, beat = _scene_with_beat(fixture_path)
    delete_entity(fixture_path, "scene", scene, "t", True)
    _sql(fixture_path, "UPDATE entities SET deleted_at='2020-01-01T00:00:00' WHERE id=?", (scene,))
    # the beat keeps the newer stamp, so the sweep takes the scene and leaves the beat
    out = _purge(fixture_path)
    assert [p["id"] for p in out["purged"]] == [scene]
    assert _exists(fixture_path, beat)
    assert _sql(fixture_path, "SELECT parent_id FROM entities WHERE id=?", (beat,)) == [("",)]


def test_a_failure_part_way_removes_nothing(fixture_path):
    delete_entity(fixture_path, "character", "kael", "t", True)
    before = _snapshot(fixture_path)
    _sql(
        fixture_path,
        "CREATE TRIGGER boom BEFORE DELETE ON entities BEGIN SELECT RAISE(ABORT, 'boom'); END",
    )
    with pytest.raises(sqlite3.Error, match="boom"):
        _purge_one(fixture_path, "kael", "character")
    _sql(fixture_path, "DROP TRIGGER boom")
    assert _snapshot(fixture_path) == before


def test_restore_after_purge_says_it_is_gone(fixture_path):
    delete_entity(fixture_path, "character", "kael", "t", True)
    _purge_one(fixture_path, "kael", "character")
    out = _admin(
        fixture_path,
        action="restore",
        target={"entity_type": "character", "id": "kael"},
        summary="x",
    )
    assert "not found" in out["error"].lower()
