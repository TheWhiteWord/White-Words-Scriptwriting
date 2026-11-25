"""Deleting flags; reading hides: names in `extra` and `location_id`.

The second half of the soft-delete change (relation rows were the first, see
test_live_relations.py). A delete used to scrub the deleted id out of the other
entities' `extra` (`characters`, `scenes`, the keys of `perspectives`) and empty
`location_id`. Anything it scrubbed was gone for good: delete + restore lost
Kael's perspectives, his place in the relationships, a scene's location.

Now nothing is touched. The references stay as written; every reader hides the
ones that name a deleted entity (core/references.py). The tests hold that to the
old behaviour with twin projects, and to the new promise with an exact round trip.
"""

import json
import shutil
import sqlite3

import pytest

import twin_helpers as twin
from white_words.scriptwriting.core import db as core_db
from white_words.scriptwriting.core.manual_entities import load_entity
from white_words.scriptwriting.core.references import (
    REFERENCE_COLUMNS,
    REFERENCE_LISTS,
    REFERENCE_MAPS,
    dead_ids,
    live_column,
    live_extra,
    live_extra_json,
    references_to,
)
from white_words.scriptwriting.core.writes import create_entity, delete_entity, edit_entity
from white_words.scriptwriting.tools.story_admin import handler as admin

SLUG = twin.SLUG

SCENARIOS = [
    [("character", "kael")],
    [("character", "mira")],
    [("scene", "central-room-day")],
    [("scene", "the-core-day")],
    [("plot", "the-resistance")],
    [("relationship", "kael-mira")],
    [("location", "the-central-room")],
    [("location", "the-garden")],
    [("world", "the-i")],
    # More than one, so the references of two deleted entities are hidden together
    [("character", "kael"), ("character", "mira")],
    [("character", "kael"), ("scene", "central-room-day"), ("location", "the-garden")],
]


def _ids(scenario):
    return "+".join(f"{t}-{i}" for t, i in scenario)


def _restore(vault, etype, eid):
    return json.loads(
        admin(
            {
                "action": "restore",
                "project": SLUG,
                "target": {"entity_type": etype, "id": eid},
                "summary": "t",
            },
            root_path=str(vault),
        )
    )


# ─── the helper itself ───


class TestTheHelper:
    DEAD = frozenset({"kael"})
    EXTRA = {
        "characters": ["kael", "mira"],
        "scenes": ["s1"],
        "perspectives": {"kael": {"x": 1}, "mira": {"y": 2}},
        "other": ["kael"],
    }

    def test_dead_ids_come_out_of_lists_and_perspective_keys(self):
        out = live_extra(self.EXTRA, self.DEAD)
        assert out["characters"] == ["mira"]
        assert out["perspectives"] == {"mira": {"y": 2}}

    def test_a_list_keeps_its_key_when_it_empties(self):
        assert live_extra({"characters": ["kael"]}, self.DEAD) == {"characters": []}

    def test_only_the_reference_fields_are_touched(self):
        assert live_extra(self.EXTRA, self.DEAD)["other"] == ["kael"]

    def test_the_stored_dict_is_never_changed(self):
        before = json.dumps(self.EXTRA)
        live_extra(self.EXTRA, self.DEAD)
        assert json.dumps(self.EXTRA) == before

    def test_nothing_dead_returns_the_same_object(self):
        assert live_extra(self.EXTRA, frozenset()) is self.EXTRA
        assert live_extra(self.EXTRA, frozenset({"nobody"})) is self.EXTRA

    def test_a_column_reads_empty_not_none(self):
        assert live_column("kael", self.DEAD) == ""
        assert live_column("mira", self.DEAD) == "mira"
        assert live_column(None, self.DEAD) is None

    def test_the_json_form_returns_the_same_text_when_nothing_is_dead(self):
        text = json.dumps(self.EXTRA)
        assert live_extra_json(text, frozenset({"nobody"})) is text
        assert json.loads(live_extra_json(text, self.DEAD))["characters"] == ["mira"]
        assert live_extra_json(None, self.DEAD) is None

    def test_what_is_hidden_is_declared_in_one_place(self):
        assert REFERENCE_LISTS == ("characters", "scenes")
        assert REFERENCE_MAPS == ("perspectives",)
        assert REFERENCE_COLUMNS == ("location_id", "parent_id")


# ─── the old behaviour, as a reference ───


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_ids)
def test_hiding_references_reads_the_same_as_scrubbing_them(fixture_path, tmp_path, scenario):
    """No reader may be able to tell a hidden reference from a scrubbed one.

    Twin projects, the same deletes in both. In one the references stay (hidden
    by the readers); in the other they are scrubbed on top, as the old delete
    did. A reader that does not call core/references.py shows the ghost in the
    first twin only, and the lists below name it.
    """
    hidden, vh = twin.build(fixture_path, tmp_path, "hidden")
    scrubbed, vs = twin.build(fixture_path, tmp_path, "scrubbed")
    for p in (hidden, scrubbed):
        for etype, eid in scenario:
            assert delete_entity(p, etype, eid, "t", True)["success"]
    twin.scrub_references(scrubbed)

    a = twin.everything_a_reader_can_say(hidden, vh)
    b = twin.everything_a_reader_can_say(scrubbed, vs)
    assert twin.differing(a, b) == [], "readers that show a reference to a deleted entity"


# ─── a grandchild: the one place a live row can outlive its parent ───


def _nested(fixture_path, tmp_path, name):
    """A location put under a location, which sits under the world. The tools
    allow it; the fixture has none."""
    p, vault = twin.build(fixture_path, tmp_path, name)
    assert create_entity(p, "location", "nook", {"name": "Nook", "world": "the-central-room"})
    return p, vault


def test_a_grandchild_of_a_deleted_entity_reads_as_having_no_parent(fixture_path, tmp_path):
    """Deleting the world flags its locations, not THEIR locations. The orphan
    stays live, and its stored `parent_id` names a deleted entity: readers must
    show what the old delete's scrub left, a location with no world."""
    hidden, vh = _nested(fixture_path, tmp_path, "hidden")
    scrubbed, vs = _nested(fixture_path, tmp_path, "scrubbed")
    for p in (hidden, scrubbed):
        res = delete_entity(p, "world", "the-i", "t", True)
        assert sorted(res["cascade_deleted"]) == ["the-central-room", "the-garden"]
    twin.scrub_references(scrubbed)
    assert twin.sql(hidden, "SELECT is_deleted FROM entities WHERE id='nook'") == [(0,)]
    assert load_entity(hidden, "location", "nook")["values"]["world"] == ""
    a = twin.everything_a_reader_can_say(hidden, vh)
    b = twin.everything_a_reader_can_say(scrubbed, vs)
    assert twin.differing(a, b) == []


def test_restoring_the_world_gives_the_grandchild_its_parent_back(fixture_path, tmp_path):
    p, vault = _nested(fixture_path, tmp_path, "rt")
    before = twin.snapshot(p)
    delete_entity(p, "world", "the-i", "t", True)
    assert _restore(vault, "world", "the-i")["success"]
    assert twin.snapshot(p) == before
    assert load_entity(p, "location", "nook")["values"]["world"] == "the-central-room"


# ─── restore gives back everything ───


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_ids)
def test_delete_then_restore_leaves_every_stored_byte_as_it_was(fixture_path, tmp_path, scenario):
    """The promise: restore is an exact inverse. Every row of every table."""
    p, vault = twin.build(fixture_path, tmp_path, "rt")
    before = twin.snapshot(p)
    for etype, eid in scenario:
        assert delete_entity(p, etype, eid, "t", True)["success"]
    assert twin.snapshot(p) != before or all(t == "relationship" for t, _ in scenario)
    for etype, eid in reversed(scenario):  # the other order from the deletes
        assert _restore(vault, etype, eid)["success"]
    assert twin.snapshot(p) == before


def test_kaels_perspectives_come_back(fixture_path, tmp_path):
    """The loss that motivated this: prose the writer wrote, gone on restore."""
    p, vault = twin.build(fixture_path, tmp_path, "persp")
    before = load_entity(p, "relationship", "kael-mira")["values"]
    assert "kael" in before["perspectives"]
    delete_entity(p, "character", "kael", "t", True)
    assert "kael" not in load_entity(p, "relationship", "kael-mira")["values"]["perspectives"]
    _restore(vault, "character", "kael")
    assert load_entity(p, "relationship", "kael-mira")["values"] == before


def test_a_scenes_location_comes_back(fixture_path, tmp_path):
    p, vault = twin.build(fixture_path, tmp_path, "loc")
    before = load_entity(p, "scene", "the-core-day")["values"]["location"]
    assert before == "the-garden"
    delete_entity(p, "location", "the-garden", "t", True)
    assert load_entity(p, "scene", "the-core-day")["values"]["location"] == ""
    _restore(vault, "location", "the-garden")
    assert load_entity(p, "scene", "the-core-day")["values"]["location"] == before


# ─── writers ───

EDITS = [
    (
        "a scene whose location is in the trash: its title",
        ("location", "the-garden"),
        ("scene", "the-core-day"),
        {"title": "Renamed"},
    ),
    (
        "a scene whose location is in the trash: its place",
        ("location", "the-garden"),
        ("scene", "the-core-day"),
        {"place": "THE GARDEN"},
    ),
    (
        "a scene whose location is in the trash: its dramatic role",
        ("location", "the-garden"),
        ("scene", "the-core-day"),
        {"dramatic_role": "plot_role"},
    ),
    (
        "a relationship whose character is in the trash: its history",
        ("character", "kael"),
        ("relationship", "kael-mira"),
        {"history": "Rewritten."},
    ),
    (
        "a plot whose character is in the trash: its summary",
        ("character", "kael"),
        ("plot", "the-resistance"),
        {"one_sentence": "Rewritten."},
    ),
    (
        "a relationship whose scene is in the trash: its status",
        ("scene", "central-room-day"),
        ("relationship", "kael-mira"),
        {"history": "Again."},
    ),
]


@pytest.mark.parametrize("what,gone,target,data", EDITS, ids=[e[0] for e in EDITS])
def test_an_edit_gives_the_same_answer_as_when_the_references_were_scrubbed(
    fixture_path, tmp_path, what, gone, target, data
):
    """The agent must not meet a new refusal because a name it cannot see is
    still stored: an edit is validated against what a reader sees."""
    hidden, vh = twin.build(fixture_path, tmp_path, "hidden")
    scrubbed, vs = twin.build(fixture_path, tmp_path, "scrubbed")
    for p in (hidden, scrubbed):
        delete_entity(p, *gone, "t", True)
    twin.scrub_references(scrubbed)

    def attempt(p):
        try:
            res = edit_entity(p, target[0], target[1], dict(data), "t")
            return {"ok": bool(res.get("success")), "applied": res.get("applied_fields")}
        except ValueError as e:
            return {"error": str(e)}

    assert attempt(hidden) == attempt(scrubbed)
    a = twin.everything_a_reader_can_say(hidden, vh)
    b = twin.everything_a_reader_can_say(scrubbed, vs)
    assert twin.differing(a, b) == []


def test_an_edit_of_another_field_keeps_the_hidden_references(fixture_path, tmp_path):
    """Edits merge into the stored `extra`: what they do not touch stays, so
    restoring the character afterwards still brings Kael back."""
    p, vault = twin.build(fixture_path, tmp_path, "keep")
    before = load_entity(p, "relationship", "kael-mira")["values"]
    delete_entity(p, "character", "kael", "t", True)
    edit_entity(p, "relationship", "kael-mira", {"history": "Rewritten."}, "t")
    _restore(vault, "character", "kael")
    after = load_entity(p, "relationship", "kael-mira")["values"]
    assert after["history"] == "Rewritten."
    assert after["characters"] == before["characters"]
    assert after["perspectives"] == before["perspectives"]


def test_an_edit_that_sets_the_field_replaces_it(fixture_path, tmp_path):
    """The writer rewrote the list, so the hidden name goes with the old value.
    Pinned so it is a decision, not an accident."""
    p, vault = twin.build(fixture_path, tmp_path, "replace")
    delete_entity(p, "character", "kael", "t", True)
    edit_entity(p, "relationship", "kael-mira", {"characters": ["mira"]}, "t")
    _restore(vault, "character", "kael")
    assert "kael" not in load_entity(p, "relationship", "kael-mira")["values"]["characters"]


# ─── the delete's report ───


def test_the_report_names_what_now_reads_as_gone(fixture_path, tmp_path):
    p, _ = twin.build(fixture_path, tmp_path, "report")
    res = delete_entity(p, "location", "the-garden", "t", True)
    assert res["detached"] == [
        {
            "entity_id": "the-core-day",
            "entity_type": "scene",
            "field": "location",
            "was_pointing_at": "the-garden",
        }
    ]
    # The report reads what is STORED, which a delete no longer changes.
    conn = sqlite3.connect(str(p / ".story" / "story.db"))
    try:
        assert references_to(conn, {"the-garden"})[0] == ["the-core-day"]
    finally:
        conn.close()


def test_a_delete_changes_no_row_but_the_flags(fixture_path, tmp_path):
    p, _ = twin.build(fixture_path, tmp_path, "flags")
    before = {r[0]: r for r in twin.sql(p, "SELECT * FROM entities")}
    delete_entity(p, "character", "kael", "t", True)
    after = {r[0]: r for r in twin.sql(p, "SELECT * FROM entities")}
    cols = [r[1] for r in twin.sql(p, "PRAGMA table_info(entities)")]
    flag_cols = {cols.index("is_deleted"), cols.index("deleted_at")}
    for eid, row in before.items():
        changed = {i for i, (x, y) in enumerate(zip(row, after[eid])) if x != y}
        assert changed <= flag_cols, (eid, [cols[i] for i in changed - flag_cols])


# ─── a database one step behind ───


@pytest.fixture
def one_step(monkeypatch):
    """A test-only migration after the baseline. LATEST_VERSION is derived at
    import, so it is patched alongside the list; tests stamp a built project
    BASELINE_VERSION to make it one step behind."""
    calls = []

    def step(conn):
        calls.append(1)
        conn.execute("CREATE TABLE test_only_step (x)")

    monkeypatch.setattr(core_db, "SCHEMA_MIGRATIONS", [step])
    monkeypatch.setattr(core_db, "LATEST_VERSION", core_db.BASELINE_VERSION + 1)
    return calls


def test_every_reader_opens_a_database_one_step_behind(fixture_path, tmp_path, one_step):
    """The readers use the live_relations view. None of them may be the first
    thing to open a behind file without bringing it forward."""
    from white_words.scriptwriting.app import services
    from white_words.scriptwriting.core import (
        db,
        manual_edits,
        manual_entities,
        manual_structure,
        track,
    )
    from white_words.scriptwriting.tools import story_export, story_load, story_retrieve

    calls = {
        "summary": lambda p, v: db.get_project_summary(p),
        "unfilled_map": lambda p, v: db.get_unfilled_map(p),
        "dashboard": lambda p, v: db.get_dashboard_data(p),
        "app_dashboard": lambda p, v: services.get_project_dashboard(v, SLUG),
        "form": lambda p, v: manual_entities.load_entity(p, "scene", "central-room-day"),
        "script": lambda p, v: manual_edits.load_scene_script(p, "central-room-day"),
        "tree": lambda p, v: manual_structure.load_tree(p),
        "track": lambda p, v: track.for_entity(p, "mira"),
        "preview": lambda p, v: manual_entities.delete_preview(p, "character", "kael"),
        "retrieve": lambda p, v: story_retrieve.handler(
            {"project": SLUG, "entity_type": "scene", "id": "central-room-day", "fields": ["all"]},
            root_path=str(v),
        ),
        "load": lambda p, v: story_load.handler({"project": SLUG}, root_path=str(v)),
        "export": lambda p, v: story_export.handler({"project": SLUG}, root_path=str(v)),
    }
    for name, call in calls.items():
        p, v = twin.build(fixture_path, tmp_path, f"behind-{name}")
        # twin.build already opened the file under the patched LATEST: undo that
        # upgrade so the reader is the first to open a genuinely behind file.
        c = sqlite3.connect(str(p / ".story" / "story.db"))
        c.execute("DROP TABLE IF EXISTS test_only_step")
        c.execute(f"PRAGMA user_version = {core_db.BASELINE_VERSION}")
        c.close()
        result = call(p, v)
        assert "no such table" not in json.dumps(result, default=str), name
    assert one_step  # readers that open through get_db brought their file forward
