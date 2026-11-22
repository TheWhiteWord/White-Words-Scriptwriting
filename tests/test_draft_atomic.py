"""T5 — atomic draft commit: a draft lands all its ops or none.

Before T5 every op was its own transaction and the "committed" mark was a third
one, so a stop part-way left a mixture and a crash between the last op and the
mark left the ops landed with the draft still open. Now `drafts.commit` runs
every op and the mark on ONE connection in ONE transaction. These tests hold:

  * the ops see each other's uncommitted rows (DB-3, which only T3 made possible),
  * a failure of any kind — a raised error, a returned error dict, a crash while
    marking — leaves the database exactly as it was and the draft open,
  * a repeated commit replays instead of writing twice,
  * a purge draft still takes the one-op-at-a-time path (a purge opens its own
    connection and takes a backup, which cannot happen inside the shared one),
  * the approve route's contract is unchanged.
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

import twin_helpers as twin
from story_architect.app.config import Config
from story_architect.app.server import create_app
from story_architect.core import db, drafts
from story_architect.core.backups import list_backups
from story_architect.core.writes import create_entity, delete_entity

from test_purge_approval import _age

H = {"X-Story-Architect": "1"}


# ─── ops ───

def _create(etype, slug, **fm):
    return {"op": "create", "type": etype, "id": slug, "frontmatter": fm,
            "sections": {}, "summary": f"new {etype} {slug}"}


def _scene(slug, **fm):
    fm = {"title": slug, "sequence_id": "seq-discovery", "act_id": "act-1", **fm}
    return _create("scene", slug, **fm)


def _edit_unknown():
    """Raises inside the write function: there is no such character."""
    return {"op": "edit", "entity_type": "character", "entity_id": "nobody-at-all",
            "data": {"one_sentence": "x"}, "summary": "edit a ghost"}


def _delete_a_sequence_with_scenes():
    """RETURNS an error dict instead of raising (Gotcha 4): structural children."""
    return {"op": "delete", "entity_type": "sequence", "entity_id": "seq-discovery",
            "summary": "delete a sequence that still has scenes"}


FAILING_THIRD_OPS = [
    pytest.param(_edit_unknown, "edit character/nobody-at-all", id="raises"),
    pytest.param(_delete_a_sequence_with_scenes, "delete sequence/seq-discovery",
                 id="returns-an-error-dict"),
]


def _two_creates_and_a_bad_third(bad):
    return [_create("character", "newchar", name="New Char"),
            _scene("new-scene", characters=["kael"]),
            bad()]


def _stage(project, ops, summary="a batch"):
    return drafts.stage(project, ops, summary)["draft_id"]


def _open_ids(project):
    return [d["id"] for d in drafts.list_drafts(project)["drafts"]]


def _exists(project, entity_id):
    return bool(twin.sql(project, "SELECT 1 FROM entities WHERE id=?", entity_id))


# ─── 1. a later op sees an earlier op's uncommitted row ───

# Each pair is one the second op's validator genuinely reads from the database.
# (A relationship's characters are not validated at all — that gap is T3's
# finding — so the relationship pair passes with or without the shared
# connection; it is kept because it is the briefed example.)
SELF_REFERENCING_BATCHES = [
    pytest.param(
        [_create("location", "newloc", name="New Loc"),
         _scene("new-scene", location="newloc")],
        id="location-then-scene"),
    pytest.param(
        [_create("character", "newchar", name="New Char"),
         _create("plot", "new-plot", name="New Plot", characters=["newchar"])],
        id="character-then-plot"),
    pytest.param(
        [_create("character", "newchar", name="New Char"),
         _create("relationship", "mira-newchar", name="Mira and New",
                 characters=["mira", "newchar"])],
        id="character-then-relationship"),
]


@pytest.mark.parametrize("ops", SELF_REFERENCING_BATCHES)
def test_creates_that_reference_each_other_commit_together(fixture_path, ops):
    staged = drafts.stage(fixture_path, ops, "a pair")
    # The dry run replays commit on a COPY of the database (a different path and
    # connection): it must reach the same verdict.
    assert staged["dry_run"] == {"status": "clean"}

    result = drafts.commit(fixture_path, staged["draft_id"])

    # `success` and the exact list — `committed` alone is truthy on a partial
    # failure too (T1 finding).
    assert result["success"] is True
    assert result["committed"] is True
    assert result["applied"] == [drafts._describe(op) for op in ops]
    for op in ops:
        assert _exists(fixture_path, op["id"])
    assert _open_ids(fixture_path) == []
    twin.assert_no_orphans(fixture_path)


# ─── 2. nothing lands when op K fails ───

@pytest.mark.parametrize("bad,bad_label", FAILING_THIRD_OPS)
def test_nothing_lands_when_the_third_op_fails(fixture_path, bad, bad_label):
    before = twin.snapshot(fixture_path)
    ops = _two_creates_and_a_bad_third(bad)
    staged = drafts.stage(fixture_path, ops, "two good, one bad")
    # The stage-time verdict is the same refusal.
    assert staged["dry_run"]["status"] == "refused"
    assert staged["dry_run"]["failed_op"] == bad_label

    result = drafts.commit(fixture_path, staged["draft_id"])

    assert result["success"] is False
    assert result["committed"] == []                 # always [] now, never "what landed"
    assert result["failed"]["op"] == bad_label
    assert result["failed"]["error"]
    assert result["draft_kept"] is True
    assert twin.snapshot(fixture_path) == before     # byte-for-byte as before
    assert not _exists(fixture_path, "newchar") and not _exists(fixture_path, "new-scene")
    assert _open_ids(fixture_path) == [staged["draft_id"]]
    twin.assert_no_orphans(fixture_path)


@pytest.mark.parametrize("bad,bad_label", FAILING_THIRD_OPS)
def test_the_failure_says_nothing_was_changed(fixture_path, bad, bad_label):
    staged = drafts.stage(fixture_path, _two_creates_and_a_bad_third(bad), "x")
    result = drafts.commit(fixture_path, staged["draft_id"])

    msg = result["message"]
    assert "Nothing was changed" in msg
    assert "Change 3 of 3 failed" in msg and bad_label in msg
    assert staged["draft_id"] in msg and "kept" in msg and "re-stage" in msg
    # The old partial-landing wording is gone.
    assert "then it stopped" not in msg and "remainder" not in msg

    md = result["preview_md"]
    assert "Nothing was changed" in md and bad_label in md
    assert "Partly saved" not in md
    # No op is shown as saved: none was.
    assert "✅" not in md


def test_a_write_that_returns_success_false_is_a_failure_too(fixture_path, monkeypatch):
    """No write function returns this today, but the contract is "an error key OR
    success False" (Gotcha 4) and a refusal must never be read as a landed op."""
    from story_architect.core import writes
    real = writes.create_entity

    def refusing(project_path, etype, slug, *args, **kwargs):
        if slug == "new-scene":
            return {"success": False, "message": "refused by the write"}
        return real(project_path, etype, slug, *args, **kwargs)

    monkeypatch.setattr(writes, "create_entity", refusing)
    before = twin.snapshot(fixture_path)
    draft_id = _stage(fixture_path, [_create("character", "newchar", name="New Char"),
                                     _scene("new-scene")])

    result = drafts.commit(fixture_path, draft_id)

    assert result["success"] is False and result["committed"] == []
    assert result["failed"] == {"op": "create scene/new-scene",
                                "error": "refused by the write"}
    assert twin.snapshot(fixture_path) == before
    assert _open_ids(fixture_path) == [draft_id]


def test_the_report_shapes(fixture_path):
    """The keys the approve route and the agent read (Part 2.4) stay put."""
    ok_ops = [_create("character", "newchar", name="New Char")]
    ok = drafts.commit(fixture_path, _stage(fixture_path, ok_ops))
    assert set(ok) == {"success", "committed", "draft_id", "applied", "preview_md", "message"}
    assert ok["committed"] is True

    bad = drafts.commit(fixture_path, _stage(fixture_path, [_edit_unknown()]))
    assert set(bad) == {"success", "committed", "failed", "draft_id", "draft_kept",
                        "preview_md", "message"}
    assert set(bad["failed"]) == {"op", "error"}


def test_a_fixed_draft_lands_after_a_failed_commit(fixture_path):
    ops = _two_creates_and_a_bad_third(_edit_unknown)
    draft_id = _stage(fixture_path, ops)
    assert drafts.commit(fixture_path, draft_id)["success"] is False

    fixed = ops[:2] + [{"op": "edit", "entity_type": "character", "entity_id": "kael",
                        "data": {"one_sentence": "Kael, steadier."}, "summary": "fix Kael"}]
    drafts.stage(fixture_path, fixed, "fixed", draft_id=draft_id)    # same id: a re-stage
    result = drafts.commit(fixture_path, draft_id)

    assert result["success"] is True
    assert "already_committed" not in result
    assert result["applied"] == [drafts._describe(op) for op in fixed]
    assert _exists(fixture_path, "newchar") and _exists(fixture_path, "new-scene")
    assert _open_ids(fixture_path) == []
    twin.assert_no_orphans(fixture_path)


# ─── 3. crash safety ───

def test_a_crash_while_marking_leaves_nothing_landed_and_the_draft_open(
        fixture_path, monkeypatch):
    before = twin.snapshot(fixture_path)
    ops = [_create("character", "newchar", name="New Char"), _scene("new-scene")]
    draft_id = _stage(fixture_path, ops)

    def crash(*args, **kwargs):
        raise RuntimeError("the disk went away")

    monkeypatch.setattr(drafts, "_mark_committed", crash)
    result = drafts.commit(fixture_path, draft_id)

    # Old behaviour: both creates stayed landed while the draft stayed open, and
    # committing again failed on "already exists".
    assert result["success"] is False and result["committed"] == []
    assert result["draft_kept"] is True
    assert "Nothing was changed" in result["message"]
    assert "the disk went away" in result["failed"]["error"]
    assert twin.snapshot(fixture_path) == before
    assert _open_ids(fixture_path) == [draft_id]

    monkeypatch.undo()                              # the disk is back
    again = drafts.commit(fixture_path, draft_id)
    assert again["success"] is True and "already_committed" not in again
    assert _exists(fixture_path, "newchar") and _exists(fixture_path, "new-scene")
    twin.assert_no_orphans(fixture_path)


# ─── 4. idempotence ───

def test_committing_twice_writes_once(fixture_path):
    ops = [_create("character", "newchar", name="New Char"), _scene("new-scene")]
    draft_id = _stage(fixture_path, ops)
    first = drafts.commit(fixture_path, draft_id)
    after_first = twin.snapshot(fixture_path)

    second = drafts.commit(fixture_path, draft_id)

    assert first["success"] is True and "already_committed" not in first
    assert second["success"] is True and second["already_committed"] is True
    assert second["applied"] == first["applied"]
    assert twin.snapshot(fixture_path) == after_first          # no second write
    twin.assert_no_orphans(fixture_path)


# ─── 5. no hidden connection inside the transaction ───

def test_no_op_opens_a_second_connection_while_the_transaction_is_open(
        fixture_path, monkeypatch):
    """DB-3 on the whole draft path: a write that opened its own connection while
    the shared transaction holds the write lock would wait 3 s and fail — or,
    for a read, see the old snapshot. The spy refuses any `get_db` made while a
    connection this commit opened is inside a transaction."""
    real = db.get_db
    opened = []

    def in_transaction(conn):
        try:
            return conn.in_transaction
        except sqlite3.ProgrammingError:                  # already closed
            return False

    def spy(project_path):
        assert not any(in_transaction(c) for c in opened), \
            "a connection was opened while the draft's transaction was open"
        conn = real(project_path)
        opened.append(conn)
        return conn

    monkeypatch.setattr(db, "get_db", spy)
    from story_architect.core import (manual_edits, manual_entities,
                                      manual_structure, track)
    for mod in (manual_edits, manual_entities, manual_structure, track):
        monkeypatch.setattr(mod, "get_db", spy)

    ops = [
        _create("location", "newloc", name="New Loc"),
        _create("character", "newchar", name="New Char"),
        _scene("new-scene", location="newloc", characters=["newchar"]),
        {"op": "edit", "entity_type": "scene", "entity_id": "new-scene",
         "data": {"status": "drafted"}, "summary": "mark it"},
        {"op": "reorder", "entity_type": "scene", "entity_id": "seq-discovery",
         "ordered_ids": ["new-scene", "central-room-day", "central-room-night"],
         "summary": "order it"},
        {"op": "delete", "entity_type": "character", "entity_id": "newchar",
         "summary": "drop it again"},
    ]
    draft_id = _stage(fixture_path, ops)
    result = drafts.commit(fixture_path, draft_id)

    assert result["success"] is True, result
    assert len(result["applied"]) == len(ops)
    twin.assert_no_orphans(fixture_path)


# ─── 6. purge drafts keep the per-op path ───

PURGE = {"op": "purge", "target": {"entity_type": "character", "id": "kael"},
         "summary": "remove Kael for good"}


@pytest.fixture
def trashed(fixture_path):
    delete_entity(fixture_path, "character", "kael", "t", True)
    _age(fixture_path)
    return fixture_path


def test_a_purge_draft_commits_and_takes_a_backup(trashed):
    """A purge opens its own connection and a backup connection. Inside the
    shared transaction it would wait 3 s for the lock and fail with
    "database is locked" — so purge-only drafts do not go through it."""
    draft_id = _stage(trashed, [PURGE])
    backups = len(list_backups(trashed))

    result = drafts.commit(trashed, draft_id)

    assert result["success"] is True, result
    assert result["committed"] is True
    assert not _exists(trashed, "kael")
    assert len(list_backups(trashed)) == backups + 1
    assert _open_ids(trashed) == []
    assert drafts.commit(trashed, draft_id)["already_committed"] is True
    twin.assert_no_orphans(trashed)


def test_a_failed_purge_changes_nothing_and_says_so(fixture_path):
    """Kael is alive, so the purge is refused (the first and only op)."""
    draft_id = _stage(fixture_path, [PURGE])
    before = twin.snapshot(fixture_path)

    result = drafts.commit(fixture_path, draft_id)

    assert result["success"] is False and result["committed"] == []
    assert result["failed"]["op"] == "purge character/kael"
    assert "Nothing was changed" in result["message"]
    assert twin.snapshot(fixture_path) == before
    assert _open_ids(fixture_path) == [draft_id]


def test_a_draft_with_several_purges_says_truthfully_what_was_done(trashed):
    """The one draft that can still land in part: each purge is its own
    transaction (it takes a backup), and a purge cannot be undone. So here, and
    only here, `committed` lists what was done instead of being empty."""
    second = {"op": "purge", "target": {"entity_type": "character", "id": "mira"},
              "summary": "remove Mira for good"}               # Mira is alive: refused
    draft_id = _stage(trashed, [PURGE, second])

    result = drafts.commit(trashed, draft_id)

    assert result["success"] is False
    assert result["committed"] == ["purge character/kael"]
    assert result["failed"]["op"] == "purge character/mira"
    assert "1 of 2 purge(s) were done and cannot be undone" in result["message"]
    assert "Nothing was changed" not in result["message"]
    assert "Partly done" in result["preview_md"]
    assert not _exists(trashed, "kael") and _exists(trashed, "mira")
    assert _open_ids(trashed) == [draft_id]
    twin.assert_no_orphans(trashed)


def test_a_purge_still_cannot_be_bundled_with_other_changes(fixture_path):
    """T5 relies on this: a mixed draft would send a purge into the shared
    transaction. It must stay impossible to stage."""
    for ops in ([_create("character", "newchar", name="N"), PURGE],
                [PURGE, _create("character", "newchar", name="N")]):
        with pytest.raises(drafts.DraftError, match="cannot be bundled"):
            drafts.stage(fixture_path, ops, "mixed")
    assert _open_ids(fixture_path) == []


# ─── 7. the approve route ───

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("story_architect.app.token.load_api_key", lambda: "k")
    root = tmp_path / "root"
    proj = root / "projects" / "demo"
    (proj / ".story").mkdir(parents=True)
    create_entity(proj, "character", "kael", {"name": "Kael"})
    tc = TestClient(create_app(Config(root=root, port=8731)), base_url="http://127.0.0.1:8731")
    return tc, proj


def _approve(tc, draft_id):
    return tc.post(f"/api/projects/demo/drafts/{draft_id}/approve", headers=H, json={})


def test_approving_a_good_draft_reports_committed(client):
    tc, proj = client
    draft_id = _stage(proj, [_create("character", "newchar", name="New Char")])

    r = _approve(tc, draft_id)

    assert r.status_code == 200
    assert r.json()["status"] == "committed"
    assert "error" not in r.json()["draft"]
    assert _exists(proj, "newchar")


def test_approving_a_failing_draft_reports_failed_and_changes_nothing(client):
    tc, proj = client
    before = twin.snapshot(proj)
    draft_id = _stage(proj, [_create("character", "newchar", name="New Char"),
                             _edit_unknown()])

    r = _approve(tc, draft_id)

    assert r.status_code == 200
    assert r.json()["status"] == "failed"
    assert "nobody-at-all" in r.json()["draft"]["error"]
    assert twin.snapshot(proj) == before
    assert _open_ids(proj) == [draft_id]                 # the card can be tried again


def test_approving_an_unknown_draft_is_a_stale_draft(client):
    tc, _ = client
    r = _approve(tc, "d-nope")
    assert r.status_code == 409 and r.json()["error"]["code"] == "stale_draft"
