"""The story_draft tool: the four actions, end to end.

The core is covered in test_drafts.py. This file is about the seam — that the
tool routes to the right core function, that a caller can only reach the
project it named, and that a staged draft does not wake the dashboard for a
change the user has not accepted.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


from white_words.scriptwriting.tools.story_draft import handler
from white_words.scriptwriting.tools.story_draft import SCHEMA

OPS = [{
    "op": "create", "type": "scene", "id": "mira-tells-kael",
    "frontmatter": {"title": "The Telling", "sequence_id": "seq-discovery",
                    "act_id": "act-1", "characters": ["mira", "kael"]},
    "sections": {"Objective": "Mira confesses the reservoir is failing."},
    "summary": "New scene: The Telling",
}]


def call(args, project_path):
    return json.loads(handler(dict(args, project=str(project_path))))


# ─── stage ───

def test_stage_returns_a_draft_id_and_writes_nothing(fixture_path):
    before = _entity_count(fixture_path)
    result = call({"action": "stage", "ops": OPS, "summary": "The Telling"}, fixture_path)

    assert result["success"] is True
    assert result["draft_id"].startswith("d-")
    assert result["op_count"] == 1
    assert _entity_count(fixture_path) == before


def test_stage_rejects_a_malformed_op_with_a_readable_error(fixture_path):
    result = call({"action": "stage", "ops": [{"op": "create", "type": "scene"}]},
                  fixture_path)
    assert "error" in result
    assert "missing: id, frontmatter" in result["error"]


def test_stage_rejects_a_project_op(fixture_path):
    result = call({"action": "stage", "ops": [{
        "op": "create", "type": "project", "id": "new-film",
        "frontmatter": {}, "summary": "a new film"}]}, fixture_path)
    assert "projects cannot be drafted" in result["error"]


def test_restaging_the_same_draft_id_replaces_and_diffs(fixture_path):
    first = call({"action": "stage", "ops": OPS, "summary": "The Telling"}, fixture_path)
    again = call({"action": "stage", "ops": OPS[:0] + [
        dict(OPS[0], summary="The Telling, rewritten")],
        "summary": "The Telling", "draft_id": first["draft_id"]}, fixture_path)

    assert again["restaged"] is True
    assert again["changes"]["changed"][0]["fields"] == ["summary"]
    assert again["changes"]["dropped"] == []


# ─── commit ───

def test_commit_writes_and_clears_the_draft(fixture_path):
    staged = call({"action": "stage", "ops": OPS, "summary": "The Telling"}, fixture_path)
    result = call({"action": "commit", "draft_id": staged["draft_id"]}, fixture_path)

    assert result["success"] is True
    assert result["committed"] is True
    assert call({"action": "list"}, fixture_path)["count"] == 0
    assert _entity_count(fixture_path) > 0


def test_commit_reports_the_failure_and_keeps_the_draft(fixture_path):
    # T5 rewrote this (it was "...partial_failure..."): the create that came
    # first used to land and be named in `committed`; now nothing lands.
    before = _entity_count(fixture_path)
    ops = OPS + [{
        "op": "reorder", "entity_type": "sequence", "entity_id": "act-two",
        "ordered_ids": ["a", "b"], "summary": "Resequence act two"}]
    staged = call({"action": "stage", "ops": ops, "summary": "two changes"}, fixture_path)
    result = call({"action": "commit", "draft_id": staged["draft_id"]}, fixture_path)

    assert result["success"] is False
    assert result["draft_kept"] is True
    assert result["committed"] == []
    assert result["failed"]["op"].startswith("reorder")
    assert "Nothing was changed" in result["message"]
    assert _entity_count(fixture_path) == before
    assert call({"action": "list"}, fixture_path)["count"] == 1


# ─── discard ───

def test_discard_removes_the_draft(fixture_path):
    staged = call({"action": "stage", "ops": OPS, "summary": "x"}, fixture_path)
    result = call({"action": "discard", "draft_id": staged["draft_id"]}, fixture_path)
    assert result["discarded"] == staged["draft_id"]
    assert call({"action": "list"}, fixture_path)["count"] == 0


def test_discard_of_an_unknown_draft_is_an_error_not_a_crash(fixture_path):
    result = call({"action": "discard", "draft_id": "d-nope"}, fixture_path)
    assert "No open draft" in result["error"]


# ─── list ───

def test_list_on_a_clean_project_is_empty_not_an_error(fixture_path):
    assert call({"action": "list"}, fixture_path) == {
        "success": True, "drafts": [], "count": 0}


def test_list_reports_every_open_draft(fixture_path):
    call({"action": "stage", "ops": OPS, "summary": "first"}, fixture_path)
    call({"action": "stage", "ops": OPS, "summary": "second"}, fixture_path)
    result = call({"action": "list"}, fixture_path)
    assert result["count"] == 2
    assert {d["summary"] for d in result["drafts"]} == {"first", "second"}


# ─── argument errors ───

@pytest.mark.parametrize("action", ["stage", "commit", "discard", "list"])
def test_an_unknown_project_is_refused_before_anything_runs(action, tmp_path):
    result = call({"action": action, "draft_id": "d-x", "ops": OPS}, tmp_path / "ghost")
    assert "error" in result


def test_an_unknown_action_is_refused(fixture_path):
    assert "Unknown action" in call({"action": "explode"}, fixture_path)["error"]


def test_commit_without_a_draft_id_does_not_crash(fixture_path):
    assert "error" in call({"action": "commit"}, fixture_path)


# ─── the dashboard hook gate ───

def _hook():
    """The real post_tool_call hook, with a ctx that records dispatches."""
    plugin = sys.modules.get("hermes_story_architect")
    if plugin is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "hermes_story_architect", REPO / "__init__.py",
            submodule_search_locations=[str(REPO)])
        plugin = importlib.util.module_from_spec(spec)
        sys.modules["hermes_story_architect"] = plugin
        spec.loader.exec_module(plugin)

    dispatched = []
    hooks = {}

    class FakeCtx:
        def register_tool(self, *a, **kw):
            pass

        def register_skill(self, *a, **kw):
            pass

        def register_hook(self, name, fn):
            hooks[name] = fn

        def dispatch_tool(self, name, args):
            dispatched.append((name, args))

        def get_config(self, key, default=None):
            return default

    plugin.register(FakeCtx())
    return hooks["post_tool_call"], dispatched


# ─── schema ───

def test_the_schema_documents_every_action():
    assert SCHEMA["properties"]["action"]["enum"] == \
        ["stage", "commit", "discard", "list"]


def test_the_schema_says_relations_ride_in_frontmatter():
    """The relations-inside-frontmatter trap: an op built to the schema rather
    than to this sentence would lose every relation."""
    assert "INSIDE frontmatter" in SCHEMA["properties"]["ops"]["description"]


def test_the_schema_reports_the_dry_run_verdict():
    """The agent must be told what `dry_run` means before it can act on it."""
    desc = SCHEMA["description"]
    assert "dry_run" in desc
    assert "'refused'" in desc
    assert "'unavailable'" in desc
    assert "re-stage" in desc


def _entity_count(project_path):
    import sqlite3
    conn = sqlite3.connect(str(project_path / ".story" / "story.db"))
    try:
        return conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    finally:
        conn.close()


# ─── the card gate ───

def _call_tool(monkeypatch, fixture_path, args):
    """Drive `on_call_tool` directly and collect what it publishes.

    The handler is what decides whether an approval card reaches the bus; the
    surrounding MCP transport is not part of that decision.
    """
    import asyncio
    from mcp import types as mcp_types
    from white_words.scriptwriting.app import mcp_server

    published = []

    async def recorder(ev):
        published.append(ev)

    monkeypatch.setattr(mcp_server, "_publish_bus", recorder)
    server = mcp_server.create_mcp_server(
        mcp_server.Config(root=fixture_path.parent, port=8731))
    entry = server.get_request_handler("tools/call")
    assert entry is not None
    handler = entry.handler
    params = mcp_types.CallToolRequestParams(name="draft", arguments=args)

    async def run():
        return await handler(None, params)

    # Never close the loop this runs on: `asyncio.run` closes its own, and every
    # other chat test then calls get_event_loop() — a closed loop leaves none.
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(run())
    return [ev for ev in published if ev.get("type") == "draft"]


def test_a_clean_stage_publishes_the_card(monkeypatch, fixture_path):
    published = _call_tool(monkeypatch, fixture_path, {
        "action": "stage", "project": str(fixture_path), "ops": OPS,
        "summary": "The Telling"})

    assert len(published) == 1
    assert published[0]["draft"]["id"].startswith("d-")
    assert published[0]["draft"]["status"] == "open"


def test_a_refused_stage_publishes_nothing(monkeypatch, fixture_path):
    ops = [{"op": "edit", "entity_type": "scene", "entity_id": "the-core-day",
            "data": {"plot_roles": [
                {"plot": "the-resistance", "role": "climax",
                 "description": "The children refuse the system's final offer."}]},
            "summary": "The Core takes the climax"}]
    assert _call_tool(monkeypatch, fixture_path, {
        "action": "stage", "project": str(fixture_path), "ops": ops,
        "summary": "take the climax"}) == []


def test_an_unavailable_stage_publishes_nothing(monkeypatch, fixture_path):
    from white_words.scriptwriting.core import drafts

    monkeypatch.setattr(drafts, "dry_run",
                        lambda project_path, draft_id: {
                            "status": "unavailable",
                            "error": "OperationalError: no such table: drafts"})
    assert _call_tool(monkeypatch, fixture_path, {
        "action": "stage", "project": str(fixture_path), "ops": OPS,
        "summary": "no replay"}) == []


def test_a_commit_does_not_publish_an_empty_card(monkeypatch, fixture_path):
    """A commit carries `draft_id` too; only a clean stage may publish."""
    staged = call({"action": "stage", "ops": OPS, "summary": "The Telling"}, fixture_path)
    assert _call_tool(monkeypatch, fixture_path, {
        "action": "commit", "project": str(fixture_path),
        "draft_id": staged["draft_id"]}) == []
