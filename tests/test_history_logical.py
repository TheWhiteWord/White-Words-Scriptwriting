"""The logical entity: the form an author writes, not the rows it is stored as.

An entity is columns + `extra` + `sections` + relations, and some facts are
stored twice or from the other end. The logical shape is what the diff, the
planner and the executor all read, so it has to be exact: materialize → create →
materialize returns the same shape (§5.1's gate).
"""

import pytest

from white_words.scriptwriting.core.db import get_db, set_project_memory
from white_words.scriptwriting.core.entity import standard_sections
from white_words.scriptwriting.core.history import logical
from white_words.scriptwriting.core.writes import create_entity, edit_entity


@pytest.fixture
def project(fixture_path):
    return fixture_path


def _conn(project):
    return get_db(project)


def _materialize(project):
    conn = _conn(project)
    try:
        return logical.materialize(conn)
    finally:
        conn.close()


def _order(project):
    conn = _conn(project)
    try:
        return logical.order_of(conn)
    finally:
        conn.close()


def _empty(tmp_path, name="rebuilt"):
    dest = tmp_path / name
    dest.mkdir()
    conn = get_db(dest)
    conn.close()
    return dest


def _round_trip(project, dest):
    logical.rebuild_copy(_materialize(project), _order(project), dest)
    return _materialize(dest)


# ─── the gate ───


def test_every_entity_type_round_trips_exactly(project, tmp_path):
    """§5.1's gate: materialize → create → materialize is the same shape."""
    original = _materialize(project)
    assert {e["type"] for e in original.values()} == set(logical.CREATE_ORDER)
    assert _round_trip(project, _empty(tmp_path)) == original


def test_the_round_trip_preserves_child_order(project, tmp_path):
    original = _order(project)
    dest = _empty(tmp_path)
    _round_trip(project, dest)
    assert _order(dest) == original


def test_a_round_trip_is_a_working_project(project, tmp_path):
    """The rebuilt state is not just equal on paper: it validates and reads."""
    dest = _empty(tmp_path)
    _round_trip(project, dest)
    with _conn(dest) as conn:
        assert conn.execute("SELECT count(*) FROM entities WHERE is_deleted=0").fetchone()[0] == 26
    edit_entity(dest, "character", "kael", {"name": "Still Writable"}, "edit")
    assert _materialize(dest)["kael"]["fields"]["name"] == "Still Writable"


# ─── the shape ───


def test_computed_fields_are_not_in_the_shape(project):
    shapes = _materialize(project)
    assert "value_focus" not in shapes["save-the-children"]["fields"]
    assert "turning_point" not in shapes["central-room-day"]["fields"]
    assert "scene_beats" not in shapes["central-room-day"]["fields"]
    assert "places" not in shapes["the-central-room"]["fields"]


def test_a_scene_carries_no_order_field(project):
    """Order is the per-parent id list, not a field — a second copy would drift."""
    assert "order" not in _materialize(project)["central-room-day"]["fields"]


def test_an_act_keeps_its_order_field(project):
    """Acts are not auto-numbered by the write path, so theirs is a real field."""
    assert "order" in _materialize(project)["act-1"]["fields"]


def test_relation_backed_fields_are_assembled(project):
    shapes = _materialize(project)
    assert shapes["kael-mira"]["fields"]["characters"] == ["kael", "mira"]
    roles = {(r["plot"], r["role"]) for r in shapes["central-room-day"]["fields"]["plot_roles"]}
    assert roles == {
        ("the-resistance", "inciting_incident"),
        ("the-scientists-last-stand", "setup"),
    }
    assert shapes["the-resistance"]["fields"]["climax"] == [
        {
            "scene_id": "central-room-night",
            "description": "The Administrator makes its final offer. Kael refuses.",
        }
    ]


def test_a_scenes_location_appears_once(project):
    """`location` is a column and a reverse-index relation: one authored field."""
    assert _materialize(project)["central-room-day"]["fields"]["location"] == "the-central-room"


def test_sections_are_the_standard_set(project):
    shape = _materialize(project)["kael"]
    assert sorted(shape["sections"]) == sorted(standard_sections("character"))


def test_an_empty_section_reads_as_empty_not_absent(project):
    """A pruned section row normalizes to '', which is what create_entity writes."""
    conn = _conn(project)
    try:
        conn.execute("DELETE FROM sections WHERE entity_id='kael' AND heading='Voice'")
        conn.commit()
        shapes = logical.materialize(conn)
    finally:
        conn.close()
    assert shapes["kael"]["sections"]["Voice"] == ""
    assert sorted(shapes["kael"]["sections"]) == sorted(standard_sections("character"))


def test_project_memory_is_part_of_the_logical_entity(project):
    """It is content: `story_memory` writes it and it moves the fingerprint."""
    set_project_memory(
        project,
        {
            "decisions": ["Kael leaves"],
            "directions": [],
            "open_questions": [],
            "continuity_warnings": [],
        },
    )
    assert _materialize(project)["save-the-children"]["fields"]["memory"]["decisions"] == [
        "Kael leaves"
    ]


def test_a_memory_only_change_round_trips(project, tmp_path):
    """Without the field declared, a memory write would be lost by the copy."""
    set_project_memory(
        project,
        {
            "decisions": ["Kael leaves"],
            "directions": [],
            "open_questions": [],
            "continuity_warnings": [],
        },
    )
    dest = _empty(tmp_path)
    _round_trip(project, dest)
    assert _materialize(dest)["save-the-children"]["fields"]["memory"]["decisions"] == [
        "Kael leaves"
    ]


# ─── the rules the round trip depends on ───


def test_children_are_created_in_their_parents_order(tmp_path):
    """`create_entity` numbers from the live siblings, so id order is not enough.

    Ids that sort against the story order are the case that catches it: created
    `zulu` then `alpha`, a rebuild in id order would give `alpha, zulu`.
    """
    src = _empty(tmp_path, "src")
    create_entity(src, "project", "p", {"name": "P"})
    create_entity(src, "act", "act-1", {"title": "One"})
    create_entity(src, "sequence", "seq-1", {"title": "S", "act_id": "act-1"})
    create_entity(src, "scene", "zulu", {"title": "Z", "sequence_id": "seq-1"})
    create_entity(src, "scene", "alpha", {"title": "A", "sequence_id": "seq-1"})

    dest = _empty(tmp_path, "dest")
    _round_trip(src, dest)

    with _conn(dest) as conn:
        got = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM entities WHERE type='scene' ORDER BY order_key, id"
            )
        ]
    assert got == ["zulu", "alpha"]
    assert _order(dest) == _order(src)


def test_a_shared_order_key_still_round_trips(tmp_path):
    """Two live siblings can share a key; the id list is what carries the order."""
    src = _empty(tmp_path, "src")
    create_entity(src, "project", "p", {"name": "P"})
    create_entity(src, "act", "act-1", {"title": "One"})
    create_entity(src, "sequence", "seq-1", {"title": "S", "act_id": "act-1"})
    create_entity(src, "scene", "zulu", {"title": "Z", "sequence_id": "seq-1"})
    create_entity(src, "scene", "alpha", {"title": "A", "sequence_id": "seq-1"})
    with _conn(src) as conn:
        conn.execute("UPDATE entities SET order_key=1 WHERE id='alpha'")
        conn.commit()

    dest = _empty(tmp_path, "dest")
    _round_trip(src, dest)
    assert _order(dest) == _order(src)
    assert _materialize(dest) == _materialize(src)


def test_acts_keep_their_story_order_through_a_round_trip(tmp_path):
    """Acts are not renumbered by `create_entity`; the field has to carry it."""
    src = _empty(tmp_path, "src")
    create_entity(src, "project", "p", {"name": "P"})
    create_entity(src, "act", "act-a", {"title": "A", "order": 1})
    create_entity(src, "act", "act-b", {"title": "B", "order": 2})
    with _conn(src) as conn:
        conn.execute("UPDATE entities SET order_key=1 WHERE id='act-b'")
        conn.execute("UPDATE entities SET order_key=9 WHERE id='act-a'")
        conn.commit()

    dest = _empty(tmp_path, "dest")
    _round_trip(src, dest)
    assert _order(dest)["act:"] == ["act-b", "act-a"]


# ─── what the shape is for ───


def test_a_field_edit_shows_as_one_changed_field(project):
    """The point of the shape: one authored change, one difference."""
    before = _materialize(project)["kael"]
    edit_entity(project, "character", "kael", {"name": "Renamed"}, "edit")
    after = _materialize(project)["kael"]
    assert [k for k in before["fields"] if before["fields"][k] != after["fields"][k]] == ["name"]


def test_a_trashed_entity_is_not_in_the_shape(project):
    from white_words.scriptwriting.core.writes import delete_entity

    delete_entity(project, "character", "the-outsider", "removed", confirm=True)
    assert "the-outsider" not in _materialize(project)


def test_a_reference_to_a_trashed_entity_is_hidden(project):
    """A reader hides a dead id (`live_extra` / `live_column`); so does the shape.
    `relationship.characters` is `extra`-backed, where the relation view cannot
    help — before this, the id survived in a shape the entity was absent from."""
    from white_words.scriptwriting.core.writes import delete_entity

    delete_entity(project, "character", "kael", "removed", confirm=True)
    shapes = _materialize(project)
    assert shapes["kael-mira"]["fields"]["characters"] == ["mira"]
    assert shapes["central-room-day"]["fields"]["characters"] == ["mira"]


def test_a_reference_column_to_a_trashed_entity_reads_empty(project):
    from white_words.scriptwriting.core.writes import delete_entity

    delete_entity(project, "location", "the-central-room", "removed", confirm=True)
    assert _materialize(project)["central-room-day"]["fields"]["location"] == ""


def test_a_rename_inside_the_trash_does_not_change_the_shape(project):
    from white_words.scriptwriting.core.writes import delete_entity

    delete_entity(project, "character", "the-outsider", "removed", confirm=True)
    before = _materialize(project)
    with _conn(project) as conn:
        conn.execute("UPDATE entities SET name='Renamed In The Bin' WHERE id='the-outsider'")
        conn.commit()
    assert _materialize(project) == before
