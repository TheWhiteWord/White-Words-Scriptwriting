"""The restore guard: a deleted scene's singular plot role, and its position.

A soft delete hides a scene's `plot_<role>` rows and keeps its `order_key`, but
nothing counts the row while it is in the trash: another scene may take the
singular role, and `_get_next_order_db` hands the next scene the deleted key.
`restore` used to clear the flag and leave both states behind. These are the
two rules that stop it, asserted against the real write path.
"""

import sqlite3

import pytest

from white_words.scriptwriting.core import trash
from white_words.scriptwriting.core.db import get_db
from white_words.scriptwriting.core.writes import delete_entity, edit_entity


def _sql(p, sql, *args):
    conn = sqlite3.connect(str(p / ".story" / "story.db"))
    try:
        rows = conn.execute(sql, args).fetchall()
        conn.commit()
        return rows
    finally:
        conn.close()


def _holders(p, plot="the-resistance", role="inciting_incident"):
    """Live scenes holding a singular role, read the way both rules read it."""
    return [
        r[0]
        for r in _sql(
            p,
            "SELECT e.id FROM live_relations r JOIN entities e ON e.id = r.to_id "
            "WHERE r.from_id=? AND r.kind=? AND e.is_deleted=0 ORDER BY e.id",
            plot,
            f"plot_{role}",
        )
    ]


def _siblings(p, sequence="seq-discovery"):
    return _sql(
        p,
        "SELECT id, order_key FROM entities WHERE type='scene' AND parent_id=? "
        "AND is_deleted=0 ORDER BY order_key, id",
        sequence,
    )


def _check(p, entity_id, **kw):
    conn = get_db(p)
    try:
        return trash.restore_check(conn, entity_id, **kw)
    finally:
        conn.close()


@pytest.fixture
def scene_with_role(fixture_path):
    """`central-room-day` deleted, its inciting-incident slot given to another scene.

    That is what the app allows today: the deleted scene's row is hidden, so the
    validator (which counts live scenes) lets a second scene take the role.
    """
    delete_entity(fixture_path, "scene", "central-room-day", "t", confirm=True)
    edit_entity(
        fixture_path,
        "scene",
        "the-core-day",
        {
            "plot_roles": [
                {"plot": "the-resistance", "role": "inciting_incident", "description": "x"}
            ]
        },
        "take the freed role",
    )
    return fixture_path


# ─── the role collision ──────────────────────────────────────────────────────


class TestRoleCollision:
    def test_the_check_reports_it_and_names_the_holder(self, scene_with_role):
        check = _check(scene_with_role, "central-room-day")
        assert len(check["collisions"]) == 1
        c = check["collisions"][0]
        assert (c["plot"], c["role"]) == ("the-resistance", "inciting_incident")
        assert c["holder"] == {"id": "the-core-day", "name": "The Core - Day"}
        assert c["choices"] == ["drop", "take"]
        assert "The Resistance" in c["message"] and "inciting incident" in c["message"]

    def test_a_scene_whose_role_is_free_reports_nothing(self, fixture_path):
        delete_entity(fixture_path, "scene", "central-room-day", "t", confirm=True)
        assert _check(fixture_path, "central-room-day")["collisions"] == []

    def test_a_non_singular_role_is_not_a_collision(self, fixture_path):
        """`setup` spans many scenes, so a second holder is the ordinary case.

        `central-room-day` holds `setup` on The Scientists' Last Stand, and once
        a second scene holds it too, that pair is shared — legal. Only its
        `inciting_incident` shares a holder, so only that one is reported.
        """
        edit_entity(
            fixture_path,
            "scene",
            "the-core-day",
            {
                "plot_roles": [
                    {"plot": "the-scientists-last-stand", "role": "setup", "description": "y"}
                ]
            },
            "share a spanning role",
        )
        delete_entity(fixture_path, "scene", "central-room-day", "t", confirm=True)
        check = _check(fixture_path, "central-room-day")
        assert check["collisions"] == [], "two live setups is legal; nothing to decide"

    def test_restore_refuses_and_writes_nothing(self, scene_with_role):
        result = trash.restore(scene_with_role, "scene", "central-room-day", "t")
        assert result["code"] == "restore_needs_decision"
        assert result["collisions"][0]["holder"]["id"] == "the-core-day"
        # Nothing landed: still deleted, still one holder, no duplicate row.
        assert (
            _sql(scene_with_role, "SELECT is_deleted FROM entities WHERE id='central-room-day'")[0][
                0
            ]
            == 1
        )
        assert _holders(scene_with_role) == ["the-core-day"]

    def test_drop_restores_without_the_role(self, scene_with_role):
        result = trash.restore(
            scene_with_role,
            "scene",
            "central-room-day",
            "t",
            resolutions=[{"plot": "the-resistance", "role": "inciting_incident", "choice": "drop"}],
        )
        assert result["success"] is True
        assert result["resolved_roles"] == [
            {"plot": "the-resistance", "role": "inciting_incident", "choice": "drop"}
        ]
        assert _holders(scene_with_role) == ["the-core-day"]
        # The scene still holds its other role row: only the collided one went.
        assert _sql(
            scene_with_role,
            "SELECT kind FROM relations WHERE to_id='central-room-day' AND kind LIKE 'plot_%'",
        ) == [("plot_setup",)]

    def test_take_moves_the_role_to_the_restored_scene(self, scene_with_role):
        trash.restore(
            scene_with_role,
            "scene",
            "central-room-day",
            "t",
            resolutions=[{"plot": "the-resistance", "role": "inciting_incident", "choice": "take"}],
        )
        assert _holders(scene_with_role) == ["central-room-day"]

    def test_a_missing_resolution_refuses_and_names_the_choices(self, scene_with_role):
        result = trash.restore(scene_with_role, "scene", "central-room-day", "t", resolutions=[])
        assert result["code"] == "restore_needs_decision"
        assert "Choose one: drop / take" in result["error"]

    def test_an_unknown_choice_is_refused(self, scene_with_role):
        result = trash.restore(
            scene_with_role,
            "scene",
            "central-room-day",
            "t",
            resolutions=[
                {"plot": "the-resistance", "role": "inciting_incident", "choice": "theirs"}
            ],
        )
        assert result["code"] == "restore_needs_decision"
        assert "One of: drop, take" in result["error"]

    def test_a_resolution_for_another_role_does_not_satisfy_it(self, scene_with_role):
        result = trash.restore(
            scene_with_role,
            "scene",
            "central-room-day",
            "t",
            resolutions=[{"plot": "the-resistance", "role": "climax", "choice": "take"}],
        )
        assert result["code"] == "restore_needs_decision"


# ─── the batch ───────────────────────────────────────────────────────────────


class TestBatch:
    def test_one_unresolved_target_refuses_the_whole_batch(self, scene_with_role):
        delete_entity(scene_with_role, "character", "kael", "t", confirm=True)
        with pytest.raises(trash.RestoreRefused) as raised:
            trash.restore_many(
                scene_with_role,
                [
                    {"entity_type": "character", "id": "kael"},
                    {"entity_type": "scene", "id": "central-room-day"},
                ],
            )
        refused = raised.value.refused
        assert [r["id"] for r in refused] == ["central-room-day"]
        assert refused[0]["collisions"][0]["plot"] == "the-resistance"
        assert _sql(scene_with_role, "SELECT is_deleted FROM entities WHERE id='kael'")[0][0] == 1

    def test_a_per_target_resolution_restores_both(self, scene_with_role):
        delete_entity(scene_with_role, "character", "kael", "t", confirm=True)
        result = trash.restore_many(
            scene_with_role,
            [
                {"entity_type": "character", "id": "kael"},
                {"entity_type": "scene", "id": "central-room-day"},
            ],
            resolutions={
                "central-room-day": [
                    {"plot": "the-resistance", "role": "inciting_incident", "choice": "take"}
                ]
            },
        )
        assert result["success"] is True
        assert {r["id"] for r in result["restored"]} == {"kael", "central-room-day"}
        assert _holders(scene_with_role) == ["central-room-day"]

    def test_take_in_a_batch_moves_the_role_to_the_restored_scene(self, fixture_path):
        """`take` from a live holder that is not in the batch.

        `the-core-day` holds the role the trashed `central-room-day` used to
        have. Restoring the trashed scene with `take` moves the role onto it and
        leaves exactly one live holder.
        """
        delete_entity(fixture_path, "scene", "central-room-day", "t", confirm=True)
        edit_entity(
            fixture_path,
            "scene",
            "the-core-day",
            {
                "plot_roles": [
                    {"plot": "the-resistance", "role": "inciting_incident", "description": "x"}
                ]
            },
            "take the freed role",
        )
        result = trash.restore_many(
            fixture_path,
            [{"entity_type": "scene", "id": "central-room-day"}],
            resolutions={
                "central-room-day": [
                    {"plot": "the-resistance", "role": "inciting_incident", "choice": "take"}
                ]
            },
        )
        assert result["success"] is True
        assert _holders(fixture_path) == ["central-room-day"]

    def test_two_trashed_holders_offer_only_drop(self, fixture_path):
        """Two scenes in one batch, each holding the role: neither can keep it.

        Reachable in the app: delete the first (freeing the slot), give the role
        to a second scene, delete that one too. Both rows still hold it, so a
        batch restore would put two live climaxes on one plot. `take` would move
        the role onto a scene arriving in the same call, so it is not offered.
        """
        delete_entity(fixture_path, "scene", "central-room-day", "t", confirm=True)
        edit_entity(
            fixture_path,
            "scene",
            "the-core-day",
            {
                "plot_roles": [
                    {"plot": "the-resistance", "role": "inciting_incident", "description": "x"}
                ]
            },
            "take the freed role",
        )
        delete_entity(fixture_path, "scene", "the-core-day", "t", confirm=True)

        conn = get_db(fixture_path)
        try:
            check = trash.restore_check(
                conn, "the-core-day", also_restoring=["central-room-day", "the-core-day"]
            )
        finally:
            conn.close()
        [collision] = check["collisions"]
        assert collision["choices"] == ["drop"]

        # `take` is not on offer, and asking for it anyway is refused.
        with pytest.raises(trash.RestoreRefused) as raised:
            trash.restore_many(
                fixture_path,
                [
                    {"entity_type": "scene", "id": "central-room-day"},
                    {"entity_type": "scene", "id": "the-core-day"},
                ],
                resolutions={
                    eid: [{"plot": "the-resistance", "role": "inciting_incident", "choice": "take"}]
                    for eid in ("central-room-day", "the-core-day")
                },
            )
        assert "only be dropped" in raised.value.refused[0]["error"]
        assert raised.value.refused[0]["collisions"][0]["choices"] == ["drop"]

        # Both drop it: the batch lands, and neither scene claims the role.
        result = trash.restore_many(
            fixture_path,
            [
                {"entity_type": "scene", "id": "central-room-day"},
                {"entity_type": "scene", "id": "the-core-day"},
            ],
            resolutions={
                eid: [{"plot": "the-resistance", "role": "inciting_incident", "choice": "drop"}]
                for eid in ("central-room-day", "the-core-day")
            },
        )
        assert result["success"] is True
        assert _holders(fixture_path) == []

    def test_a_drop_in_a_batch_leaves_the_live_holder_alone(self, fixture_path):
        delete_entity(fixture_path, "scene", "central-room-day", "t", confirm=True)
        edit_entity(
            fixture_path,
            "scene",
            "the-core-day",
            {
                "plot_roles": [
                    {"plot": "the-resistance", "role": "inciting_incident", "description": "x"}
                ]
            },
            "take the freed role",
        )
        result = trash.restore_many(
            fixture_path,
            [{"entity_type": "scene", "id": "central-room-day"}],
            resolutions={
                "central-room-day": [
                    {"plot": "the-resistance", "role": "inciting_incident", "choice": "drop"}
                ]
            },
        )
        assert result["success"] is True
        assert _holders(fixture_path) == ["the-core-day"]


# ─── the position collision ──────────────────────────────────────────────────


class TestPosition:
    """`_get_next_order_db` counts live rows, so a deleted key comes round again."""

    def _collide(self, p, new_id="the-roof-dawn"):
        delete_entity(p, "scene", "the-core-day", "t", confirm=True)
        trash.restore  # the delete alone is not a collision; the new scene is
        from white_words.scriptwriting.core.writes import create_entity

        create_entity(
            p,
            "scene",
            new_id,
            {
                "title": new_id,
                "sequence_id": "seq-discovery",
            },
        )
        return new_id

    def test_the_check_reports_where_it_will_go(self, fixture_path):
        self._collide(fixture_path)
        placement = _check(fixture_path, "the-core-day")["placement"]
        assert placement["order_key"] == 3
        assert placement["taken_by"]["id"] == "the-roof-dawn"
        assert placement["after"]["id"] == "central-room-night"

    def test_restore_puts_it_back_after_its_old_neighbour(self, fixture_path):
        self._collide(fixture_path)
        result = trash.restore(fixture_path, "scene", "the-core-day", "t")
        assert result["placed"] == {
            "position": 3,
            "after": "Central Room - Night",
            "was_taken_by": "the-roof-dawn",
        }
        assert [r[0] for r in _siblings(fixture_path)] == [
            "central-room-day",
            "central-room-night",
            "the-core-day",
            "the-roof-dawn",
        ]

    def test_the_keys_are_a_clean_sequence_after_the_restore(self, fixture_path):
        """Not just the order: no key is shared, which is what the export writes."""
        self._collide(fixture_path)
        trash.restore(fixture_path, "scene", "the-core-day", "t")
        keys = [r[1] for r in _siblings(fixture_path)]
        assert keys == [1, 2, 3, 4]

    def test_an_id_that_sorts_early_is_not_promoted(self, fixture_path):
        """The tie used to break on the id, so an early-sorting id came out third."""
        self._collide(fixture_path, new_id="a-roof-dawn")
        result = trash.restore(fixture_path, "scene", "the-core-day", "t")
        assert result["placed"]["position"] == 3
        assert [r[0] for r in _siblings(fixture_path)] == [
            "central-room-day",
            "central-room-night",
            "the-core-day",
            "a-roof-dawn",
        ]

    def test_no_collision_leaves_the_sequence_alone(self, fixture_path):
        delete_entity(fixture_path, "scene", "the-core-day", "t", confirm=True)
        result = trash.restore(fixture_path, "scene", "the-core-day", "t")
        assert "placed" not in result
        assert [r[1] for r in _siblings(fixture_path)] == [1, 2, 3]

    def test_a_batch_restore_settles_the_position_too(self, fixture_path):
        self._collide(fixture_path)
        result = trash.restore_many(fixture_path, [{"entity_type": "scene", "id": "the-core-day"}])
        assert result["placed"] == [
            {"id": "the-core-day", "position": 3, "after": "Central Room - Night"}
        ]
        assert [r[1] for r in _siblings(fixture_path)] == [1, 2, 3, 4]
