"""T6 — one source of truth for a draft's status.

The `drafts` table holds the truth. The chat message holds a display copy (a
"snapshot") whose `status` goes stale when the agent commits through the tool,
when a draft is discarded, or after a failed approve. So the conversation is
reconciled at READ time: `drafts.reconcile_status` is the rule (pure, one row of
the table below per case) and `drafts.reconcile_snapshots` applies it to many
snapshots with ONE lookup. The route that serves a conversation calls it; the
stored message is never rewritten by a read.

    snapshot says      table row     show
    open | failed      open          the snapshot's own value (failed keeps its error)
    open | failed      committed     committed
    open | failed      no row        discarded
    committed|discarded  anything    the snapshot's own value (terminal)
"""
import pytest
from fastapi.testclient import TestClient

from white_words.scriptwriting.app.config import Config
from white_words.scriptwriting.app.server import create_app
from white_words.scriptwriting.chat import store as chat_store
from white_words.scriptwriting.core import db, drafts
from white_words.scriptwriting.core.writes import create_entity

H = {"X-White-Words": "1"}


# ─── the rule: one case per row of the table ───

RULE = [
    # row 1 — the table agrees the draft is still open: keep the snapshot's value
    pytest.param("open", "open", "open", id="open-snapshot-open-row"),
    pytest.param("failed", "open", "failed", id="failed-snapshot-open-row-keeps-failed"),
    # row 2 — the agent (or anyone) committed it
    pytest.param("open", "committed", "committed", id="open-snapshot-committed-row"),
    pytest.param("failed", "committed", "committed", id="failed-snapshot-committed-row"),
    # row 3 — no row: discarded (a receipt would have said committed)
    pytest.param("open", None, "discarded", id="open-snapshot-no-row"),
    pytest.param("failed", None, "discarded", id="failed-snapshot-no-row"),
    # row 4 — terminal: whatever the table says, including nothing (receipts are
    # pruned after 30 days, so a missing row is normal here)
    pytest.param("committed", "open", "committed", id="committed-snapshot-open-row"),
    pytest.param("committed", "committed", "committed", id="committed-snapshot-committed-row"),
    pytest.param("committed", None, "committed", id="committed-snapshot-pruned-receipt"),
    pytest.param("discarded", "open", "discarded", id="discarded-snapshot-open-row"),
    pytest.param("discarded", "committed", "discarded", id="discarded-snapshot-committed-row"),
    pytest.param("discarded", None, "discarded", id="discarded-snapshot-no-row"),
]


@pytest.mark.parametrize("snapshot,row,shown", RULE)
def test_the_rule(snapshot, row, shown):
    assert drafts.reconcile_status(snapshot, row) == shown


def test_a_status_the_rule_does_not_know_is_left_alone():
    """The overlay corrects the two states that go stale; anything else is not
    ours to rewrite, and an unknown table value must not invent a verdict."""
    assert drafts.reconcile_status("weird", None) == "weird"
    assert drafts.reconcile_status(None, "committed") is None
    assert drafts.reconcile_status("open", "weird") == "open"


# ─── against a real database ───

def _card(draft_id, status="open", **extra):
    return {"id": draft_id, "status": status, "summary": "s", "created_at": "t",
            "changes": [], "warnings": [], **extra}


def _stage(project, slug="newchar"):
    ops = [{"op": "create", "type": "character", "id": slug,
            "frontmatter": {"name": slug.title()}, "sections": {}, "summary": "new"}]
    return drafts.stage(project, ops, "a draft")["draft_id"]


def test_an_open_draft_stays_open(fixture_path):
    draft_id = _stage(fixture_path)
    [shown] = drafts.reconcile_snapshots(fixture_path, [_card(draft_id)])
    assert shown["status"] == "open"


def test_the_agent_commits_through_the_tool_and_the_card_shows_committed(fixture_path):
    """The card was stored as "open"; the agent's own `story_draft commit` never
    touches the chat message."""
    draft_id = _stage(fixture_path)
    assert drafts.commit(fixture_path, draft_id)["success"] is True
    [shown] = drafts.reconcile_snapshots(fixture_path, [_card(draft_id)])
    assert shown["status"] == "committed"


def test_a_discarded_draft_shows_discarded(fixture_path):
    draft_id = _stage(fixture_path)
    drafts.discard(fixture_path, draft_id)
    [shown] = drafts.reconcile_snapshots(fixture_path, [_card(draft_id)])
    assert shown["status"] == "discarded"


def test_a_failed_approve_keeps_failed_and_its_error(fixture_path):
    """After a failed commit (T5) the draft is still open in the table, so the
    card the approve route stored — failed, with the reason — must survive."""
    bad = [{"op": "edit", "entity_type": "character", "entity_id": "nobody-at-all",
            "data": {"one_sentence": "x"}, "summary": "edit a ghost"}]
    draft_id = drafts.stage(fixture_path, bad, "bad")["draft_id"]
    result = drafts.commit(fixture_path, draft_id)
    assert result["success"] is False
    card = _card(draft_id, "failed", error=result["failed"]["error"])

    [shown] = drafts.reconcile_snapshots(fixture_path, [card])

    assert shown["status"] == "failed"
    assert shown["error"] == result["failed"]["error"]


def test_a_pruned_receipt_does_not_undo_a_committed_card(fixture_path):
    draft_id = _stage(fixture_path)
    drafts.commit(fixture_path, draft_id)
    conn = db.get_db(fixture_path)
    with db.transaction(conn):
        conn.execute("DELETE FROM drafts WHERE id=?", (draft_id,))
    conn.close()
    [shown] = drafts.reconcile_snapshots(fixture_path, [_card(draft_id, "committed")])
    assert shown["status"] == "committed"


def test_only_the_status_changes_and_the_input_is_not_touched(fixture_path):
    draft_id = _stage(fixture_path)
    drafts.commit(fixture_path, draft_id)
    card = _card(draft_id, changes=[{"x": 1}], warnings=["w"], extra="kept")
    before = dict(card)

    [shown] = drafts.reconcile_snapshots(fixture_path, [card])

    assert card == before                                   # not mutated
    assert {k: v for k, v in shown.items() if k != "status"} == \
           {k: v for k, v in before.items() if k != "status"}


def test_the_same_draft_on_two_cards_each_follows_its_own_snapshot(fixture_path):
    """A re-stage under one id can leave two cards for it: one open, one failed."""
    draft_id = _stage(fixture_path)
    drafts.commit(fixture_path, draft_id)
    shown = drafts.reconcile_snapshots(
        fixture_path, [_card(draft_id, "open"), _card(draft_id, "failed", error="e"),
                       _card(draft_id, "discarded")])
    assert [s["status"] for s in shown] == ["committed", "committed", "discarded"]


def test_many_cards_cost_one_lookup_and_none_when_nothing_can_be_stale(
        fixture_path, monkeypatch):
    ids = [_stage(fixture_path, f"c{i}") for i in range(4)]
    seen = []
    real = db.get_db

    def spy(project_path):
        conn = real(project_path)
        conn.set_trace_callback(lambda sql: seen.append(sql))
        return conn

    monkeypatch.setattr(db, "get_db", spy)

    drafts.reconcile_snapshots(fixture_path, [_card(i) for i in ids])
    assert len([s for s in seen if "FROM drafts" in s]) == 1

    seen.clear()                     # terminal cards need no lookup at all
    drafts.reconcile_snapshots(fixture_path, [_card("a", "committed"), _card("b", "discarded")])
    drafts.reconcile_snapshots(fixture_path, [])
    assert seen == []


# ─── the route that serves a conversation ───

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("white_words.scriptwriting.app.token.load_api_key", lambda: "k")
    root = tmp_path / "root"
    proj = root / "projects" / "demo"
    (proj / ".story").mkdir(parents=True)
    create_entity(proj, "character", "kael", {"name": "Kael"})
    tc = TestClient(create_app(Config(root=root, port=8731)), base_url="http://127.0.0.1:8731")
    return tc, proj


def _conversation_with_cards(proj, cards):
    cid = chat_store.create_conversation(proj, "t")
    chat_store.add_message(proj, cid, "user", "propose something")
    mid = chat_store.add_message(proj, cid, "assistant", "here", drafts=cards)
    return cid, mid


def _served(tc, cid):
    r = tc.get(f"/api/projects/demo/conversations/{cid}")
    assert r.status_code == 200
    return [d for m in r.json()["messages"] for d in (m["drafts"] or [])]


def test_the_served_conversation_shows_the_tables_status(client):
    tc, proj = client
    committed, discarded, still_open = (_stage(proj, s) for s in ("ca", "cb", "cc"))
    drafts.commit(proj, committed)
    drafts.discard(proj, discarded)
    cid, _ = _conversation_with_cards(
        proj, [_card(committed), _card(discarded), _card(still_open), _card("d-gone")])

    shown = {d["id"]: d["status"] for d in _served(tc, cid)}

    assert shown == {committed: "committed", discarded: "discarded",
                     still_open: "open", "d-gone": "discarded"}


def test_serving_a_conversation_does_not_rewrite_the_stored_card(client):
    """The overlay is a display fix. The approve/reject routes read the stored
    cards through the same store to rewrite them, and must see what was stored."""
    tc, proj = client
    draft_id = _stage(proj)
    drafts.commit(proj, draft_id)
    cid, _ = _conversation_with_cards(proj, [_card(draft_id)])

    assert _served(tc, cid)[0]["status"] == "committed"

    stored = chat_store.get_conversation(proj, cid)["messages"][-1]["drafts"][0]
    assert stored["status"] == "open"


def test_a_failed_approve_still_reads_failed_after_a_reload(client):
    """End to end through the real approve route: the card it stores says
    failed with the reason, the table says open, and the reload keeps both."""
    tc, proj = client
    bad = [{"op": "edit", "entity_type": "character", "entity_id": "nobody-at-all",
            "data": {"one_sentence": "x"}, "summary": "edit a ghost"}]
    draft_id = drafts.stage(proj, bad, "bad")["draft_id"]
    cid, _ = _conversation_with_cards(proj, [_card(draft_id)])

    r = tc.post(f"/api/projects/demo/drafts/{draft_id}/approve", headers=H,
                json={"conversation_id": cid})
    assert r.status_code == 200 and r.json()["status"] == "failed"

    [card] = _served(tc, cid)
    assert card["status"] == "failed"
    assert "nobody-at-all" in card["error"]


def test_approve_and_reject_still_return_what_they_returned(client):
    """Part 2.4: the routes' contract is untouched by T6."""
    tc, proj = client
    ok = _stage(proj, "okchar")
    r = tc.post(f"/api/projects/demo/drafts/{ok}/approve", headers=H, json={})
    assert r.status_code == 200 and r.json()["status"] == "committed"
    assert set(r.json()) == {"status", "draft"}

    rej = _stage(proj, "rejchar")
    r = tc.post(f"/api/projects/demo/drafts/{rej}/reject", headers=H, json={})
    assert r.status_code == 200 and r.json()["draft"]["status"] == "discarded"

    r = tc.post("/api/projects/demo/drafts/d-nope/approve", headers=H, json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "stale_draft"
