"""A delete flags only what it deletes, and restore brings back only that.

The cascade used to look at every child by `parent_id`, trashed or not. So
deleting a parent re-stamped children that were already in the trash (their own
deletion time was overwritten), listed them in the preview as if this action
would delete them, let a trashed scene block its sequence from being deleted,
and a later restore of the parent brought them all back.

The rule now: a child belongs to a delete when it was live at that moment, and
to a restore when it carries the parent's own deletion stamp.
"""

import json
import shutil
import sqlite3

import pytest

from white_words.scriptwriting.core.writes import delete_entity
from white_words.scriptwriting.tools.story_admin import handler as admin
from white_words.scriptwriting.tools.story_import import handler as import_handler

EARLIER = "2026-01-01T09:00:00"


@pytest.fixture
def proj(fixture_path, tmp_path):
    vault = tmp_path / "v"
    p = vault / "projects" / "save-the-children"
    p.parent.mkdir(parents=True)
    shutil.copytree(str(fixture_path), str(p))
    import_handler({"project": "save-the-children", "confirm": True}, root_path=str(vault))
    return p, vault


def _sql(p, sql, *args):
    conn = sqlite3.connect(str(p / ".story" / "story.db"))
    try:
        rows = conn.execute(sql, args).fetchall()
        conn.commit()
        return rows
    finally:
        conn.close()


def _row(p, eid):
    return _sql(p, "SELECT is_deleted, deleted_at FROM entities WHERE id=?", eid)[0]


def _restore(proj, etype, eid):
    p, vault = proj
    return json.loads(
        admin(
            {
                "action": "restore",
                "project": "save-the-children",
                "target": {"entity_type": etype, "id": eid},
                "summary": "t",
            },
            root_path=str(vault),
        )
    )


SCENE, BEATS = "central-room-day", "central-room-day-beats"


def _trash_beats_earlier(p):
    """The scene's beats were deleted on their own at an earlier time."""
    res = delete_entity(p, "scene_beats", BEATS, "t", True)
    assert res.get("success"), res
    _sql(p, "UPDATE entities SET deleted_at=? WHERE id=?", EARLIER, BEATS)


class TestDeleteLeavesTrashedChildrenAlone:
    def test_their_own_deletion_time_is_kept(self, proj):
        p, _ = proj
        _trash_beats_earlier(p)
        assert delete_entity(p, "scene", SCENE, "t", True)["success"]
        assert _row(p, BEATS) == (1, EARLIER)
        assert _row(p, SCENE)[0] == 1 and _row(p, SCENE)[1] != EARLIER

    def test_the_preview_does_not_list_them(self, proj):
        p, _ = proj
        _trash_beats_earlier(p)
        preview = delete_entity(p, "scene", SCENE, "t")  # no confirm
        assert preview["would_delete"] == [SCENE]
        assert preview["cascade_children"] == []

    def test_the_result_does_not_claim_them(self, proj):
        p, _ = proj
        _trash_beats_earlier(p)
        assert delete_entity(p, "scene", SCENE, "t", True)["cascade_deleted"] == []

    def test_a_live_child_is_still_deleted_with_its_parent(self, proj):
        p, _ = proj
        res = delete_entity(p, "scene", SCENE, "t", True)
        assert res["cascade_deleted"] == [BEATS]
        assert _row(p, BEATS)[1] == _row(p, SCENE)[1] is not None

    def test_a_trashed_scene_does_not_block_deleting_its_sequence(self, proj):
        p, _ = proj
        scenes = [
            r[0]
            for r in _sql(
                p,
                "SELECT id FROM entities WHERE parent_id='seq-discovery' "
                "AND type='scene' AND is_deleted=0",
            )
        ]
        assert scenes
        for sid in scenes:
            assert delete_entity(p, "scene", sid, "t", True)["success"]
        res = delete_entity(p, "sequence", "seq-discovery", "t", True)
        assert res.get("success"), res
        assert res["cascade_deleted"] == []

    def test_a_live_scene_still_blocks_its_sequence(self, proj):
        p, _ = proj
        res = delete_entity(p, "sequence", "seq-discovery", "t", True)
        assert "blocking_children" in res
        assert _row(p, "seq-discovery")[0] == 0


class TestRestoreBringsBackOnlyWhatThatDeleteFlagged:
    def test_a_child_trashed_earlier_stays_in_the_trash(self, proj):
        p, _ = proj
        _trash_beats_earlier(p)
        delete_entity(p, "scene", SCENE, "t", True)
        res = _restore(proj, "scene", SCENE)
        assert res["success"]
        assert res["restored_cascade_children"] == []
        assert _row(p, SCENE) == (0, None)
        assert _row(p, BEATS) == (1, EARLIER)

    def test_a_child_trashed_on_its_own_afterwards_stays_in_the_trash(self, proj):
        p, _ = proj
        delete_entity(p, "scene", SCENE, "t", True)
        # Same child, deleted again later by hand: a different stamp from the parent's.
        _sql(p, "UPDATE entities SET deleted_at=? WHERE id=?", "2099-01-01T00:00:00", BEATS)
        assert _restore(proj, "scene", SCENE)["restored_cascade_children"] == []
        assert _row(p, BEATS)[0] == 1

    def test_children_deleted_together_come_back_together(self, proj):
        p, _ = proj
        delete_entity(p, "scene", SCENE, "t", True)
        res = _restore(proj, "scene", SCENE)
        assert res["restored_cascade_children"] == [BEATS]
        assert _row(p, BEATS) == (0, None)

    def test_the_trashed_child_can_still_be_restored_on_its_own(self, proj):
        p, _ = proj
        _trash_beats_earlier(p)
        delete_entity(p, "scene", SCENE, "t", True)
        _restore(proj, "scene", SCENE)
        assert _restore(proj, "scene_beats", BEATS)["success"]
        assert _row(p, BEATS) == (0, None)

    def test_restore_and_targeted_purge_agree_on_what_was_deleted_together(self, proj):
        """One rule, two users: what restore would bring back, purge removes, and
        a child trashed earlier is left alone by both."""
        p, vault = proj
        _trash_beats_earlier(p)
        delete_entity(p, "scene", SCENE, "t", True)
        from white_words.scriptwriting.core.trash import purge_deleted

        res = purge_deleted(p, {"entity_type": "scene", "id": SCENE})
        assert res.get("success"), res
        assert [x["id"] for x in res["purged"]] == [SCENE]
        assert _sql(p, "SELECT 1 FROM entities WHERE id=?", SCENE) == []
        # Still in the trash, and no longer pointing at a scene that is gone.
        assert _row(p, BEATS) == (1, EARLIER)
        assert _sql(p, "SELECT parent_id FROM entities WHERE id=?", BEATS) == [("",)]
