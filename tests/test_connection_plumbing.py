"""T3 — connection plumbing: writes and validators run on the caller's connection.

DB-3: inside one outer transaction every step must read and write through the
ONE connection. A second connection in WAL mode sees only what was committed
before the outer transaction began, so a validator that opens its own cannot
see rows an earlier step wrote but has not committed. These tests hold that
guarantee, the ownership rule (a supplied connection is never closed, committed
or rolled back by the callee), and the no-hidden-connection rule.
"""
import sqlite3

import pytest

import twin_helpers as twin
from white_words.scriptwriting.core import db, entity, manual_edits, manual_entities, manual_structure, writes
from white_words.scriptwriting.core.db import get_db, transaction

WORDS = {"p": "loyalty", "c": "complicity", "cd": "betrayal", "nn": "fanatic love"}


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "v"
    (root / "projects").mkdir(parents=True)
    assert writes.create_project("stc", {"name": "STC"}, root)["success"]
    return root / "projects" / "stc"


def _turn():
    return {"plot": "main-plot", "value": "trust", "from": "loyalty", "to": "betrayal",
            "effects": [{"character": "kael",
                         "levels": [{"conflict_level": "personal",
                                     "effect": "Kael feels betrayed."}]}]}


# ── 1. A later step sees an earlier step's uncommitted row ──────────────────

def _location_steps(project, conn):
    assert writes.create_entity(project, "location", "newloc", {"name": "New Loc"},
                                conn=conn)["success"]
    assert writes.create_entity(project, "scene", "s1",
                                {"title": "S1", "location": "newloc"}, conn=conn)["success"]
    return [("location", "newloc"), ("scene", "s1")]


def _plot_steps(project, conn):
    assert writes.create_entity(project, "character", "newchar", {"name": "New Char"},
                                conn=conn)["success"]
    assert writes.create_entity(project, "plot", "pl1",
                                {"name": "P1", "characters": ["newchar"]}, conn=conn)["success"]
    return [("character", "newchar"), ("plot", "pl1")]


def _value_turn_setup(project):
    # Committed before the outer transaction: the plot and its protagonist.
    assert writes.create_entity(project, "character", "kael", {"name": "Kael"})["success"]
    assert writes.create_entity(project, "plot", "main-plot",
                                {"name": "Main", "characters": ["kael"]})["success"]


def _value_turn_steps(project, conn):
    # The value the turn names is written but NOT committed when the scene is created.
    assert writes.create_entity(project, "value", "trust",
                                {"name": "Trust", **WORDS}, conn=conn)["success"]
    assert writes.create_entity(project, "scene", "s1",
                                {"title": "S1", "value_turns": [_turn()]}, conn=conn)["success"]
    return [("value", "trust"), ("scene", "s1")]


@pytest.mark.parametrize("setup,steps", [
    pytest.param(None, _location_steps, id="location"),
    pytest.param(None, _plot_steps, id="plot"),
    pytest.param(_value_turn_setup, _value_turn_steps, id="value-turns"),
])
def test_a_later_step_sees_an_earlier_steps_uncommitted_row(project, setup, steps):
    if setup is not None:
        setup(project)
    conn = get_db(project)
    try:
        with transaction(conn):
            created = steps(project, conn)
        fresh = get_db(project)
        try:
            for etype, eid in created:
                assert fresh.execute(
                    "SELECT 1 FROM entities WHERE id=? AND type=?", (eid, etype)).fetchone()
        finally:
            fresh.close()
    finally:
        conn.close()
    twin.assert_no_orphans(project)


# ── 2. Nothing opens a hidden connection ────────────────────────────────────

def test_nothing_opens_a_hidden_connection(fixture_path, monkeypatch):
    p = fixture_path
    conn = get_db(p)          # opened BEFORE the patch: the caller's own connection

    def forbidden(*a, **k):
        raise AssertionError("opened a hidden connection inside the caller's transaction")

    monkeypatch.setattr(db, "get_db", forbidden)
    # Late imports resolve through db.get_db; module-level imports are separate names.
    for mod in (manual_entities, manual_edits, manual_structure):
        monkeypatch.setattr(mod, "get_db", forbidden)
    try:
        with transaction(conn):
            assert writes.create_entity(p, "character", "newchar", {"name": "New Char"},
                                        conn=conn)["success"]
            assert writes.create_entity(p, "location", "newloc", {"name": "New Loc"},
                                        conn=conn)["success"]
            assert writes.create_entity(p, "value", "t3-value", {"name": "T3 Value", **WORDS},
                                        conn=conn)["success"]
            assert writes.create_entity(p, "scene", "newscene",
                                        {"title": "New", "location": "newloc",
                                         "characters": ["newchar"]}, conn=conn)["success"]
            assert writes.edit_entity(p, "character", "newchar",
                                      {"one_sentence": "x"}, "s", conn=conn)["success"]
            writes.current_values(p, "character", "newchar", {"one_sentence": "y"}, conn=conn)
            plot_id = conn.execute(
                "SELECT id FROM entities WHERE type='plot' AND is_deleted=0 LIMIT 1").fetchone()[0]
            assert writes.edit_entity(p, "scene", "newscene",
                                      {"plot_roles": [{"plot": plot_id, "role": "setup"}]},
                                      "s", conn=conn)["success"]
            assert writes.create_entity(p, "scene_beats", "newscene-beats",
                                        {"scene": "newscene", "driver": "newchar",
                                         "beats": [{"action": {"by": "newchar", "surface": "x"}}]},
                                        conn=conn)["success"]
            assert "error" in writes.delete_entity(p, "value", "t3-value", "s", conn=conn)  # preview
            assert writes.delete_entity(p, "value", "t3-value", "s", confirm=True,
                                        conn=conn)["success"]
            assert writes.create_entity(p, "sequence", "seqx", {"title": "Seq X"},
                                        conn=conn)["success"]
            for sid in ("rs1", "rs2"):
                assert writes.create_entity(p, "scene", sid, {"title": sid, "sequence_id": "seqx"},
                                            conn=conn)["success"]
            assert writes.reorder(p, "scene", ["rs2", "rs1"], "s", conn=conn)["success"]
            manual_entities.load_entity(p, "character", "newchar", conn=conn)
            manual_entities.delete_preview(p, "character", "newchar", conn=conn)
            manual_structure.load_tree(p, conn=conn)
            manual_edits.load_scene_script(p, "newscene", conn=conn)
            manual_edits.check_scene_script(p, "newscene", {"blocks": [], "heading": {}}, conn=conn)
        assert conn.execute(
            "SELECT one_sentence FROM entities WHERE id='newchar'").fetchone()[0] == "x"
    finally:
        conn.close()


# ── 3. Ownership: a supplied connection stays open; no connection leaks ─────

def test_connection_ownership(fixture_path, monkeypatch):
    p = fixture_path
    opened = []
    real = db.get_db

    def counting(path):
        c = real(path)
        opened.append(c)
        return c

    monkeypatch.setattr(db, "get_db", counting)
    for mod in (manual_entities, manual_edits, manual_structure):
        monkeypatch.setattr(mod, "get_db", counting)
    conn = real(p)
    try:
        with transaction(conn):
            writes.create_entity(p, "character", "ownchar", {"name": "Own"}, conn=conn)
            writes.edit_entity(p, "character", "ownchar", {"one_sentence": "x"}, "s", conn=conn)
            writes.current_values(p, "character", "ownchar", {"one_sentence": "y"}, conn=conn)
            writes.delete_entity(p, "character", "ownchar", "s", conn=conn)   # preview
            loc_id = conn.execute(
                "SELECT id FROM entities WHERE type='location' AND is_deleted=0 LIMIT 1").fetchone()[0]
            entity.validate_scene_location(p, loc_id, conn=conn)
            manual_entities.load_entity(p, "character", "ownchar", conn=conn)
            manual_structure.load_tree(p, conn=conn)
            assert conn.in_transaction          # no callee committed or rolled back
        assert opened == []                     # supplied conn: nothing opened its own
        assert conn.execute("SELECT 1").fetchone() == (1,)   # still open: caller owns it

        # Without a connection every call opens its own — and closes it.
        writes.create_entity(p, "character", "leakchar", {"name": "Leak"})
        writes.edit_entity(p, "character", "leakchar", {"one_sentence": "x"}, "s")
        writes.current_values(p, "character", "leakchar", {"one_sentence": "y"})
        writes.delete_entity(p, "character", "leakchar", "s")                 # preview
        loc_id = conn.execute(
            "SELECT id FROM entities WHERE type='location' AND is_deleted=0 LIMIT 1").fetchone()[0]
        entity.validate_scene_location(p, loc_id)
        manual_entities.load_entity(p, "character", "leakchar")
        manual_structure.load_tree(p)
        scene_id = conn.execute(
            "SELECT id FROM entities WHERE type='scene' AND is_deleted=0 LIMIT 1").fetchone()[0]
        manual_edits.load_scene_script(p, scene_id)
        assert opened, "the no-conn calls should have opened connections"
        for c in opened:
            with pytest.raises(sqlite3.ProgrammingError):
                c.execute("SELECT 1")           # every connection handed out was closed
    finally:
        conn.close()


# ── 4. Rollback reaches everything ──────────────────────────────────────────

def test_rollback_reaches_every_step(project):
    before = twin.snapshot(project)
    conn = get_db(project)
    try:
        with pytest.raises(ValueError, match="stop"):
            with transaction(conn):
                writes.create_entity(project, "character", "c1", {"name": "C1"}, conn=conn)
                writes.create_entity(project, "location", "l1", {"name": "L1"}, conn=conn)
                writes.edit_entity(project, "character", "c1", {"one_sentence": "x"}, "s", conn=conn)
                raise ValueError("stop")
    finally:
        conn.close()
    assert twin.snapshot(project) == before
    twin.assert_no_orphans(project)
