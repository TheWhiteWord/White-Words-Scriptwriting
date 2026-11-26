"""The branch graph's "picked from" edges: cherry-picks only.

A complete merge is an applied session too, but the draft the branch saves next carries
its source as a parent, and the graph draws that as a solid edge. Listing it as a pick as
well drew every merge twice.
"""

import pytest

from white_words.scriptwriting.core.history import graph, session, store
from white_words.scriptwriting.core.writes import edit_entity

NAME = "field:character:kael:name"


@pytest.fixture
def project(fixture_path):
    store.adopt(fixture_path)
    root = store.head_state(fixture_path)["branch"]["base_snapshot_id"]
    store.branch_from(fixture_path, root, "side")
    store.switch(fixture_path, "side")
    edit_entity(fixture_path, "character", "kael", {"name": "Kael On Side"}, "side")
    store.save_snapshot(fixture_path, "Side 1")
    store.switch(fixture_path, "main")
    return fixture_path


def _apply(project, *, complete):
    side = next(
        s["id"] for s in store.list_branches(project)["snapshots"] if s["label"] == "Side 1"
    )
    started = session.start(project, "main", {"kind": "snapshot", "id": side}, selection=[NAME])
    session.apply(project, started["id"], complete=complete)
    return side


def test_a_cherry_pick_is_a_pick(project):
    side = _apply(project, complete=False)

    picks = graph.summary(project)["picked_from"]

    assert [(p["branch"], p["source"]["id"]) for p in picks] == [("main", side)]


def test_a_complete_merge_is_a_pick_only_until_its_parent_is_saved(project):
    side = _apply(project, complete=True)

    assert [p["source"]["id"] for p in graph.summary(project)["picked_from"]] == [side]
    assert graph.summary(project)["branches"][0]["pending_merge_parents"] == [side]

    merged = store.save_snapshot(project, "Merged")

    assert side in merged["parents"]
    assert graph.summary(project)["picked_from"] == []
