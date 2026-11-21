"""T4 — atomic version checks: the token compare and the write are one transaction.

The old race (check on one connection, write on another) cannot be produced
reliably with threads, so these tests hold the guarantee that removes it:
while a save is between its check and its write, nobody else can commit.
A competitor connection that tries to write mid-save must be locked out.
"""
import sqlite3

import pytest

import twin_helpers as twin
from story_architect.core import manual_edits, manual_entities, manual_structure, writes


def _competitor(db_path):
    """Try to commit from ANOTHER connection; report what happened."""
    other = sqlite3.connect(str(db_path), isolation_level=None)
    other.execute("PRAGMA busy_timeout=50")
    try:
        other.execute("UPDATE entities SET one_sentence='sneaky' WHERE id='kael'")
        return "committed"
    except sqlite3.OperationalError as e:
        return str(e)
    finally:
        other.close()


def _patch_edit_with_competitor(monkeypatch, p, seen):
    # All three save paths late-import edit_entity from writes, so patching
    # writes.edit_entity patches the name where it is looked up.
    real = writes.edit_entity

    def edit_with_a_competitor(*a, **kw):
        seen["outcome"] = _competitor(p / ".story" / "story.db")
        return real(*a, **kw)

    monkeypatch.setattr(writes, "edit_entity", edit_with_a_competitor)


def test_form_save_nobody_commits_between_check_and_write(fixture_path, monkeypatch):
    p = fixture_path
    seen = {}
    _patch_edit_with_competitor(monkeypatch, p, seen)
    cur = manual_entities.load_entity(p, "character", "kael")
    out = manual_entities.edit_form_entity(p, "character", "kael", {
        "base_version": cur["version"],
        "values": {**cur["values"], "one_sentence": "mine"}})
    assert "locked" in seen["outcome"]
    assert out["values"]["one_sentence"] == "mine"
    twin.assert_no_orphans(p)


def test_structure_apply_nobody_commits_between_check_and_write(fixture_path, monkeypatch):
    p = fixture_path
    act_id = twin.sql(p, "SELECT id FROM entities WHERE type='act' AND is_deleted=0 LIMIT 1")[0][0]
    seq_id = twin.sql(p, "SELECT id FROM entities WHERE type='sequence' AND is_deleted=0 LIMIT 1")[0][0]
    # A second sequence, so the target can move a scene ACROSS sequences —
    # that move goes through edit_entity, the seam the competitor watches.
    assert writes.create_entity(p, "sequence", "t4-seq",
                                {"title": "T4 Seq", "act_id": act_id, "order": 2})["success"]
    tree = manual_structure.load_tree(p)
    shape = {"base_version": tree["version"],
             "acts": [{"id": a["id"], "sequences": [
                 {"id": q["id"], "scenes": [s["id"] for s in q["scenes"]]}
                 for q in a["sequences"]]} for a in tree["acts"]]}
    moved = next(q for a in shape["acts"] for q in a["sequences"]
                 if q["id"] == seq_id)["scenes"].pop(0)
    next(q for a in shape["acts"] for q in a["sequences"]
         if q["id"] == "t4-seq")["scenes"].append(moved)
    seen = {}
    _patch_edit_with_competitor(monkeypatch, p, seen)
    out = manual_structure.apply(p, shape)
    assert "locked" in seen["outcome"]
    assert out["applied"] >= 1
    assert [s["id"] for s in next(q for a in out["tree"]["acts"] for q in a["sequences"]
                                  if q["id"] == "t4-seq")["scenes"]] == [moved]
    twin.assert_no_orphans(p)


def test_script_save_nobody_commits_between_check_and_write(fixture_path, monkeypatch):
    p = fixture_path
    sid = twin.sql(p, "SELECT s.entity_id FROM sections s JOIN entities e ON e.id=s.entity_id "
                      "WHERE s.heading='Content' AND s.body!='' AND e.is_deleted=0 LIMIT 1")[0][0]
    s = manual_edits.load_scene_script(p, sid)
    blocks = [dict(b) for b in s["blocks"]]
    blocks[0]["text"] += " Still."
    payload = {"base_hash": s["hash"], "blocks": blocks,
               "heading": {k: s["scene"][k] for k in
                           ("int_ext", "place", "location", "time_of_day", "forced_heading")},
               "extra_cast": []}
    seen = {}
    _patch_edit_with_competitor(monkeypatch, p, seen)
    out = manual_edits.save_scene_script(p, sid, payload)
    assert "locked" in seen["outcome"]
    assert "Still." in out["content"]
    twin.assert_no_orphans(p)


def test_structure_failure_lands_nothing(fixture_path, monkeypatch):
    """Two scenes move across sequences; the second move fails. The first move
    must not survive it — the whole apply is one transaction now."""
    p = fixture_path
    act_id = twin.sql(p, "SELECT id FROM entities WHERE type='act' AND is_deleted=0 LIMIT 1")[0][0]
    seq_id = twin.sql(p, "SELECT id FROM entities WHERE type='sequence' AND is_deleted=0 LIMIT 1")[0][0]
    assert writes.create_entity(p, "sequence", "t4-seq",
                                {"title": "T4 Seq", "act_id": act_id, "order": 2})["success"]
    tree = manual_structure.load_tree(p)
    shape = {"base_version": tree["version"],
             "acts": [{"id": a["id"], "sequences": [
                 {"id": q["id"], "scenes": [s["id"] for s in q["scenes"]]}
                 for q in a["sequences"]]} for a in tree["acts"]]}
    src = next(q for a in shape["acts"] for q in a["sequences"] if q["id"] == seq_id)["scenes"]
    dst = next(q for a in shape["acts"] for q in a["sequences"] if q["id"] == "t4-seq")["scenes"]
    dst.append(src.pop(0))
    dst.append(src.pop(0))
    before = twin.snapshot(p)
    real = writes.edit_entity
    calls = []

    def boom(*a, **kw):
        calls.append(1)
        if len(calls) == 2:
            raise ValueError("move exploded")
        return real(*a, **kw)

    monkeypatch.setattr(writes, "edit_entity", boom)
    with pytest.raises(manual_structure.StructureError) as e:
        manual_structure.apply(p, shape)
    assert "Nothing was changed" in str(e.value) and "move exploded" in str(e.value)
    assert twin.snapshot(p) == before
    twin.assert_no_orphans(p)
