"""The Trash tab's API: list, preview, restore, purge.

The rules these call are the agent's own (`core/trash.py`, shared with
`story_admin`), so what is asserted here is mostly the contract between the two:
a bundle is the parent plus what it took with it, restore is exact, and a purge
is one transaction behind one backup.
"""
import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from white_words.scriptwriting.app.config import Config
from white_words.scriptwriting.app.server import create_app
from white_words.scriptwriting.core.backups import list_backups
from white_words.scriptwriting.core.writes import delete_entity

SLUG = "save-the-children"
HDR = {"X-White-Words": "1", "Origin": "http://127.0.0.1:8731"}


def _sql(p, sql, *args):
    conn = sqlite3.connect(str(p / ".story" / "story.db"))
    try:
        rows = conn.execute(sql, args).fetchall()
        conn.commit()          # a write has to land, or the next connection can't see it
        return rows
    finally:
        conn.close()


def _first_scene_with_beats(p):
    return _sql(p, "SELECT parent_id FROM entities WHERE type='scene_beats' LIMIT 1")[0][0]


def _beats_of(p, scene):
    return [r[0] for r in _sql(
        p, "SELECT id FROM entities WHERE type='scene_beats' AND parent_id=?", scene)]


def _earlier(p, entity_id, stamp="2026-01-01T09:00:00+00:00"):
    """Push one deletion's stamp into the past.

    `deleted_at` has whole-second resolution, so two deletes inside one second
    are indistinguishable and the bundle rule (same stamp, same parent) merges
    them — correct for one person doing two things in one second, and the reason
    a test about a *separate* deletion has to give it a stamp it cannot share.
    """
    _sql(p, "UPDATE entities SET deleted_at=? WHERE id=?", stamp, entity_id)


@pytest.fixture
def client(fixture_path, tmp_path):
    """A configured app on a private copy of the fixture project."""
    root = tmp_path / "root"
    (root / "projects").mkdir(parents=True)
    project = root / "projects" / SLUG
    shutil.copytree(str(fixture_path), str(project))
    cfg = Config(root=root, port=8731)
    app = create_app(cfg)
    return TestClient(app, base_url="http://127.0.0.1:8731"), project


def _trash(tc):
    r = tc.get(f"/api/projects/{SLUG}/trash")
    assert r.status_code == 200, r.text
    return r.json()


def _ids(payload):
    return {item["id"] for item in payload["items"]}


# ─── the list ────────────────────────────────────────────────────────────────

def test_empty_trash(client):
    tc, project = client
    body = _trash(tc)
    assert body["count"] == 0 and body["items"] == []
    assert body["entities"] == 0 and body["counts_by_type"] == {}


def test_a_deletion_is_one_row_with_its_children_nested(client):
    """The bundle rule, seen from the UI: the beats are never their own row."""
    tc, project = client
    scene = _first_scene_with_beats(project)
    beats = _beats_of(project, scene)
    assert beats
    assert delete_entity(project, "scene", scene, "t", True)["success"]

    body = _trash(tc)
    assert body["count"] == 1
    item = body["items"][0]
    assert item["id"] == scene and item["type"] == "scene"
    assert {inc["id"] for inc in item["includes"]} == set(beats)
    assert item["label"] == "Scene" and item["includes"][0]["label"] == "Scene Beats"
    assert item["preview"]                      # the composed heading, not the id
    assert item["has_script"] in (True, False)
    assert item["restore"]["blockers"] == []
    # The badge counts every entity, not just the rows.
    assert body["entities"] == 1 + len(beats)
    assert body["counts_by_type"]["scene_beats"] == len(beats)


def test_a_child_deleted_separately_keeps_its_own_row(client):
    """Deleted on its own, earlier: its own stamp, so its own row.

    The stamp is forced into the past because `deleted_at` has whole-second
    resolution: two deletes inside one second are indistinguishable, and the
    bundle rule (same stamp, same parent) then merges them — which is right for
    one person doing two things in one second, and why a *separate* deletion is
    tested with a stamp it cannot share.
    """
    tc, project = client
    scene = _first_scene_with_beats(project)
    beats = _beats_of(project, scene)[0]
    assert delete_entity(project, "scene_beats", beats, "t", True)["success"]
    _earlier(project, beats)
    assert delete_entity(project, "scene", scene, "t", True)["success"]

    body = _trash(tc)
    assert _ids(body) == {scene, beats}
    scene_row = next(i for i in body["items"] if i["id"] == scene)
    assert scene_row["includes"] == []           # did not take the beats with it


# ─── the preview ─────────────────────────────────────────────────────────────

def test_preview_shows_the_prose_and_the_hidden_links(client):
    tc, project = client
    assert delete_entity(project, "character", "kael", "t", True)["success"]

    r = tc.get(f"/api/projects/{SLUG}/trash/character/kael")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["entity"]["label"] == "Character"
    assert body["entity"]["deleted_at"]
    assert body["sections"], "the prose survives a delete; the preview must show it"
    # Its relations still exist, and the panel is told which ends are still live.
    kinds = {link["kind"] for link in body["relations"]["all"]}
    assert kinds
    assert all("live" in link for link in body["relations"]["all"])
    assert body["restore"]["returned"]["sections"] == len(body["sections"])
    assert body["purge"]["items"][0]["id"] == "kael"

    # The panel names what a link points at, never the raw id: a cast entry read
    # "central-room-day" until the relation ends were added to the lookup, and a
    # person deciding whether to restore cannot check a slug.
    names = {link["id"]: link["name"] for link in body["relations"]["all"]}
    assert names.get("central-room-day") == "Central Room - Day"
    assert all(name and name != eid for eid, name in names.items()), names


def test_preview_of_a_live_entity_is_a_conflict(client):
    tc, project = client
    r = tc.get(f"/api/projects/{SLUG}/trash/character/kael")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "not_in_trash"


def test_preview_of_an_unknown_entity_is_404(client):
    tc, project = client
    r = tc.get(f"/api/projects/{SLUG}/trash/character/nobody")
    assert r.status_code == 404


# ─── restore ─────────────────────────────────────────────────────────────────

def test_the_bundle_is_not_reported_as_staying_behind(client):
    """A child of the bundle comes back with the parent — so it is never "stranded".

    The only stranded child is one deleted on its own, carrying another stamp;
    reporting the bundle as stranded made the panel say "also deleted with it"
    and "stays behind" about the same row.
    """
    tc, project = client
    scene = _first_scene_with_beats(project)
    beats = _beats_of(project, scene)[0]
    delete_entity(project, "scene_beats", beats, "t", True)
    _earlier(project, beats)
    delete_entity(project, "scene", scene, "t", True)

    body = tc.get(f"/api/projects/{SLUG}/trash/scene/{scene}").json()
    stranded = body["restore"]["warnings"].get("stranded_children", [])
    assert [s["id"] for s in stranded] == [beats], "the separately-deleted child stays behind"
    assert body["includes"] == []

    # The scene's own panel must not contradict itself: nothing is both in the
    # bundle and left behind.
    night = tc.get(f"/api/projects/{SLUG}/trash/scene/central-room-night")
    if night.status_code == 200:
        payload = night.json()
        assert not payload["restore"]["warnings"].get("stranded_children")
        assert payload["includes"], "its beats are in the bundle, so they come back"


def test_a_link_named_twice_is_one_line(client):
    """A scene's location is written twice — the column *and* a relation row.

    The preview names entities, not storage: two lines for one location read as
    two links the user must bring back, and the panel offers each of them a tick
    box. So a ref is keyed by (type, id) and the second sighting is dropped.
    """
    tc, project = client
    assert delete_entity(project, "location", "the-central-room", "t", True)["success"]
    assert delete_entity(project, "scene", "central-room-day", "t", True)["success"]

    body = tc.get(f"/api/projects/{SLUG}/trash/scene/central-room-day").json()
    refs = body["restore"]["warnings"].get("reference_in_trash", [])
    keys = [(r["entity_type"], r["id"]) for r in refs]
    assert len(keys) == len(set(keys)), f"the same entity twice: {keys}"
    # The column's label wins over the relation kind: one link, named plainly.
    assert keys == [("location", "the-central-room")]
    assert refs[0]["field"] == "location"


def test_restoring_the_parent_brings_the_bundle_back(client):
    tc, project = client
    scene = _first_scene_with_beats(project)
    assert delete_entity(project, "scene", scene, "t", True)["success"]

    r = tc.post(f"/api/projects/{SLUG}/trash/scene/{scene}/restore", json={}, headers=HDR)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["restored"][0] == scene
    assert body["restored_cascade_children"]

    assert _trash(tc)["count"] == 0
    assert _sql(project, "SELECT is_deleted FROM entities WHERE id=?", scene)[0][0] == 0
    live = _sql(project, "SELECT count(*) FROM live_relations WHERE from_id=? OR to_id=?",
                scene, scene)[0][0]
    assert live, "the cast comes back visible: nothing was rebuilt, only un-hidden"


def test_restore_is_blocked_while_the_parent_is_in_the_trash(client):
    """A beats record deleted on its own, under a scene that is also in the trash."""
    tc, project = client
    scene = _first_scene_with_beats(project)
    beats = _beats_of(project, scene)[0]
    assert delete_entity(project, "scene_beats", beats, "t", True)["success"]
    _earlier(project, beats)
    assert delete_entity(project, "scene", scene, "t", True)["success"]

    r = tc.post(f"/api/projects/{SLUG}/trash/scene_beats/{beats}/restore",
                json={}, headers=HDR)
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["code"] == "restore_blocked"
    blocker = error["blockers"][0]
    assert blocker["code"] == "parent_trashed"
    assert blocker["fix"]["id"] == scene

    # The fix the panel offers: the same call with the parent added.
    r = tc.post(f"/api/projects/{SLUG}/trash/restore",
                json={"targets": [{"entity_type": "scene_beats", "id": beats},
                                  {"entity_type": "scene", "id": scene}]}, headers=HDR)
    assert r.status_code == 200, r.text
    assert _sql(project, "SELECT is_deleted FROM entities WHERE id=?", beats)[0][0] == 0


def test_a_blocked_target_restores_nothing_from_the_batch(client):
    tc, project = client
    scene = _first_scene_with_beats(project)
    beats = _beats_of(project, scene)[0]
    delete_entity(project, "scene_beats", beats, "t", True)
    _earlier(project, beats)
    delete_entity(project, "scene", scene, "t", True)
    delete_entity(project, "character", "kael", "t", True)

    r = tc.post(f"/api/projects/{SLUG}/trash/restore",
                json={"targets": [{"entity_type": "character", "id": "kael"},
                                  {"entity_type": "scene_beats", "id": beats}]},
                headers=HDR)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "restore_blocked"
    # kael was restorable, and is still deleted: the batch is one action.
    assert _sql(project, "SELECT is_deleted FROM entities WHERE id='kael'")[0][0] == 1


def test_restore_refuses_an_empty_batch_and_a_live_target(client):
    tc, project = client
    r = tc.post(f"/api/projects/{SLUG}/trash/restore", json={"targets": []}, headers=HDR)
    assert r.status_code == 422

    r = tc.post(f"/api/projects/{SLUG}/trash/restore",
                json={"targets": [{"entity_type": "character", "id": "kael"}]}, headers=HDR)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "not_in_trash"


# ─── purge ───────────────────────────────────────────────────────────────────

def test_purge_preview_names_the_bundle_and_what_else_is_touched(client):
    tc, project = client
    scene = _first_scene_with_beats(project)
    beats = _beats_of(project, scene)
    delete_entity(project, "scene", scene, "t", True)

    r = tc.post(f"/api/projects/{SLUG}/trash/purge-preview",
                json={"targets": [{"entity_type": "scene", "id": scene}]}, headers=HDR)
    assert r.status_code == 200, r.text
    body = r.json()
    assert {i["id"] for i in body["items"]} == {scene} | set(beats)
    assert body["backup"] is True
    assert all("label" in i for i in body["items"])


def test_purge_removes_the_bundle_behind_one_backup(client):
    tc, project = client
    scene = _first_scene_with_beats(project)
    beats = _beats_of(project, scene)
    delete_entity(project, "scene", scene, "t", True)
    before = len(list_backups(project))

    r = tc.post(f"/api/projects/{SLUG}/trash/purge",
                json={"targets": [{"entity_type": "scene", "id": scene}]}, headers=HDR)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["backup"] and body["purged"]
    assert len(list_backups(project)) == before + 1, "one backup for the whole call"

    gone = [r[0] for r in _sql(project, "SELECT id FROM entities WHERE id IN (%s)"
                               % ",".join("?" * (1 + len(beats))), scene, *beats)]
    assert gone == []
    assert _sql(project, "SELECT count(*) FROM sections WHERE entity_id=?", scene)[0][0] == 0
    assert _trash(tc)["count"] == 0


def test_purging_clears_a_live_entitys_reference(client):
    """The bug a purge had and a delete did not (spec §3.2).

    After a delete the id is still in `entities`, so readers hide it. After a
    purge it is gone, and only rewriting the live `extra` stops a relationship
    naming a character that no longer exists.
    """
    tc, project = client
    assert delete_entity(project, "character", "kael", "t", True)["success"]

    r = tc.post(f"/api/projects/{SLUG}/trash/purge",
                json={"targets": [{"entity_type": "character", "id": "kael"}]}, headers=HDR)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["affected"], "a live relationship named the character"
    assert body["cleared"], "and it had to be rewritten"

    for (extra_json,) in _sql(project, "SELECT extra FROM entities WHERE type='relationship'"):
        assert "kael" not in (json.loads(extra_json or "{}").get("characters") or [])
    assert not _sql(project, "SELECT 1 FROM relations WHERE from_id='kael' OR to_id='kael'")


def test_purge_refuses_a_live_target_an_unknown_one_and_an_empty_list(client):
    tc, project = client
    r = tc.post(f"/api/projects/{SLUG}/trash/purge",
                json={"targets": [{"entity_type": "character", "id": "kael"}]}, headers=HDR)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "not_in_trash"

    r = tc.post(f"/api/projects/{SLUG}/trash/purge",
                json={"targets": [{"entity_type": "character", "id": "nobody"}]}, headers=HDR)
    assert r.status_code == 404

    r = tc.post(f"/api/projects/{SLUG}/trash/purge", json={"targets": []}, headers=HDR)
    assert r.status_code == 422


def test_purge_leaves_a_live_location_link_blank_rather_than_dangling(client):
    tc, project = client
    rows = _sql(project, "SELECT id FROM entities WHERE type='location'")
    assert rows
    location = rows[0][0]
    scene = _sql(project, "SELECT id FROM entities WHERE type='scene' AND location_id=? "
                          "AND is_deleted=0 LIMIT 1", location)
    if not scene:
        pytest.skip("fixture has no scene pointing at that location")
    scene = scene[0][0]
    delete_entity(project, "location", location, "t", True)

    r = tc.post(f"/api/projects/{SLUG}/trash/purge",
                json={"targets": [{"entity_type": "location", "id": location}]}, headers=HDR)
    assert r.status_code == 200, r.text
    assert _sql(project, "SELECT location_id FROM entities WHERE id=?", scene)[0][0] == ""


# ─── the agent and the tab agree ─────────────────────────────────────────────

def test_the_tab_and_the_agent_report_the_same_bundle(client):
    from white_words.scriptwriting.tools.story_admin import handler as admin

    tc, project = client
    scene = _first_scene_with_beats(project)
    delete_entity(project, "scene", scene, "t", True)

    agent = json.loads(admin({"project": str(project), "action": "list_deleted"},
                             root_path=str(project.parent.parent)))
    ui = _trash(tc)
    assert agent["count"] == ui["count"]
    assert {i["id"] for i in agent["deleted"]} == _ids(ui)
    assert {i["id"] for i in agent["deleted"][0]["includes"]} == \
           {i["id"] for i in ui["items"][0]["includes"]}
