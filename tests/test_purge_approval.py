"""Purge waits for the person.

A purge is the one irreversible thing left: a soft delete is exactly undone by
`restore`, and a deleted project sits in the trash. It used to be gated by a
typed "DELETE <slug>" that the refusal message printed for the caller to echo
back, which stopped nobody. Now the agent's `story_admin(action="purge")` only
stages a draft; the person approves it on the same card as any other change, and
approving runs `core.trash.purge_deleted`. Until then nothing is removed.
"""
import json
import sqlite3

import pytest

from story_architect.core import drafts
from story_architect.core.backups import list_backups
from story_architect.core.trash import preview_purge, purge_deleted
from story_architect.core.writes import delete_entity
from story_architect.tools.story_admin import handler as admin
from story_architect.tools.story_draft import handler as draft_tool

TARGET = {"entity_type": "character", "id": "kael"}


def _admin(project, **args):
    return json.loads(admin({"project": str(project), **args}, root_path=str(project.parent)))


def _exists(project, entity_id):
    conn = sqlite3.connect(str(project / ".story" / "story.db"))
    try:
        return bool(conn.execute("SELECT 1 FROM entities WHERE id=?", (entity_id,)).fetchone())
    finally:
        conn.close()


def _age(project, days_ago=90):
    conn = sqlite3.connect(str(project / ".story" / "story.db"))
    conn.execute("UPDATE entities SET deleted_at=? WHERE is_deleted=1",
                 (f"2020-01-01T00:00:00",))
    conn.commit()
    conn.close()


@pytest.fixture
def trashed(fixture_path):
    """A project with Kael deleted long ago, so the age floor is not in the way."""
    delete_entity(fixture_path, "character", "kael", "t", True)
    _age(fixture_path)
    return fixture_path


# ─── the agent can only propose ───

class TestTheAgentOnlyProposes:
    def test_nothing_is_removed(self, trashed):
        out = _admin(trashed, action="purge", target=TARGET)
        assert out["success"] is True and out["purged"] is False
        assert _exists(trashed, "kael")

    def test_a_bulk_request_removes_nothing_either(self, trashed):
        out = _admin(trashed, action="purge")
        assert out["purged"] is False and _exists(trashed, "kael")

    def test_the_old_typed_string_is_not_a_way_around_it(self, trashed):
        out = _admin(trashed, action="purge", target=TARGET,
                     purge_confirm="DELETE save-the-children")
        assert out["purged"] is False and _exists(trashed, "kael")

    def test_nothing_is_handed_over_to_echo_back(self, trashed):
        out = _admin(trashed, action="purge", target=TARGET)
        text = json.dumps(out)
        assert "purge_confirm" not in text and "action_required" not in text
        assert "DELETE save-the-children" not in text

    def test_the_reply_tells_the_agent_to_relay_it_and_that_it_cannot_be_undone(self, trashed):
        out = _admin(trashed, action="purge", target=TARGET)
        assert "approve" in out["message"] and "cannot be undone" in out["message"]
        assert "preview_md" in out

    def test_a_target_without_an_id_is_refused(self, trashed):
        assert "error" in _admin(trashed, action="purge", target={"entity_type": "character"})

    def test_the_draft_is_listed_for_the_app(self, trashed):
        out = _admin(trashed, action="purge", target=TARGET)
        listed = drafts.list_drafts(trashed)
        assert out["draft_id"] in json.dumps(listed, default=str)


# ─── what the person sees ───

class TestTheApprovalCard:
    def _card(self, project, **args):
        out = _admin(project, action="purge", **args)
        return drafts.describe_ops(project, [{"op": "purge", "summary": "s", **{
            k: v for k, v in args.items() if k in ("target", "older_than_days")}}])[0], out

    def test_it_is_the_existing_delete_card_marked_irreversible(self, trashed):
        card, _ = self._card(trashed, target=TARGET)
        assert card["kind"] == "delete"          # the frontend's card for removals
        assert card["reversible"] is False        # which then says "This cannot be undone."

    def test_it_names_what_will_go(self, trashed):
        card, _ = self._card(trashed, target=TARGET)
        assert card["label"] == "1 deleted item" and "Kael" in card["detail"]

    def test_the_markdown_preview_says_so_too(self, trashed):
        out = _admin(trashed, action="purge", target=TARGET)
        assert "PURGE" in out["preview_md"] and "cannot be undone" in out["preview_md"]
        assert "character/kael" in out["preview_md"]

    def test_a_long_list_is_cut_but_counted(self, fixture_path):
        for eid in ("kael", "mira", "the-administrator"):
            delete_entity(fixture_path, "character", eid, "t", True)
        _age(fixture_path)
        card = drafts.describe_ops(fixture_path, [{"op": "purge", "summary": "s"}])[0]
        assert card["label"].startswith("3 deleted items")

    def test_a_purge_that_would_be_refused_says_so_on_the_card(self, fixture_path):
        """Kael is alive: purge only takes what is already in the trash."""
        out = _admin(fixture_path, action="purge", target=TARGET)
        assert out["dry_run"]["status"] != "clean"
        card = drafts.describe_ops(fixture_path, [{"op": "purge", "summary": "s",
                                                   "target": TARGET}])[0]
        assert "refused" in card["label"]

    def test_the_card_and_the_purge_agree_on_the_set(self, fixture_path):
        """One selection serves both, so the card cannot describe another set."""
        for eid in ("kael", "mira"):
            delete_entity(fixture_path, "character", eid, "t", True)
        _age(fixture_path)
        for kwargs in ({}, {"older_than_days": 0}, {"target": TARGET}):
            shown = [i["id"] for i in preview_purge(fixture_path, **kwargs)["items"]]
            assert shown, kwargs
            ran = [p["id"] for p in purge_deleted(fixture_path, **kwargs)["purged"]]
            assert sorted(shown) == sorted(ran), kwargs
            if not kwargs.get("target"):
                break


# ─── approving ───

class TestApproving:
    def test_approval_removes_it_for_good_and_takes_a_backup(self, trashed):
        out = _admin(trashed, action="purge", target=TARGET)
        before = len(list_backups(trashed))
        report = drafts.commit(trashed, out["draft_id"])
        assert report["committed"]
        assert not _exists(trashed, "kael")
        assert len(list_backups(trashed)) == before + 1

    def test_it_is_still_restorable_until_then(self, trashed):
        _admin(trashed, action="purge", target=TARGET)
        res = json.loads(admin({"action": "restore", "project": str(trashed),
                                "target": TARGET, "summary": "t"},
                               root_path=str(trashed.parent)))
        assert res["success"] is True

    def test_rejecting_removes_nothing(self, trashed):
        out = _admin(trashed, action="purge", target=TARGET)
        drafts.discard(trashed, out["draft_id"])
        assert _exists(trashed, "kael")

    def test_the_age_floor_holds_after_approval(self, fixture_path):
        delete_entity(fixture_path, "character", "kael", "t", True)   # just now
        out = _admin(fixture_path, action="purge")
        drafts.commit(fixture_path, out["draft_id"])
        assert _exists(fixture_path, "kael")

    def test_approving_a_refused_purge_removes_nothing_and_says_so(self, fixture_path):
        out = _admin(fixture_path, action="purge", target=TARGET)   # Kael is alive
        report = drafts.commit(fixture_path, out["draft_id"])
        assert _exists(fixture_path, "kael")
        assert report["success"] is False and report["committed"] == []
        assert report["failed"]["op"] == "purge character/kael"

    def test_approving_twice_does_not_purge_twice(self, trashed):
        out = _admin(trashed, action="purge", target=TARGET)
        drafts.commit(trashed, out["draft_id"])
        again = drafts.commit(trashed, out["draft_id"])
        assert again.get("already_committed") is True


# ─── a purge is never a side effect ───

class TestAPurgeStandsAlone:
    PURGE = {"op": "purge", "summary": "remove old items"}
    EDIT = {"op": "edit", "entity_type": "character", "entity_id": "mira",
            "data": {"status": "written"}, "summary": "e"}

    def test_it_cannot_be_bundled_with_another_change(self, trashed):
        with pytest.raises(drafts.DraftError, match="on its own"):
            drafts.validate_ops([self.EDIT, self.PURGE])

    def test_nor_with_a_delete(self, trashed):
        d = {"op": "delete", "entity_type": "character", "entity_id": "mira", "summary": "d"}
        with pytest.raises(drafts.DraftError):
            drafts.validate_ops([self.PURGE, d])

    def test_alone_it_is_fine(self):
        assert drafts.validate_ops([self.PURGE])

    @pytest.mark.parametrize("bad", [
        {"target": {"entity_type": "character"}}, {"target": "kael"},
        {"older_than_days": -1}, {"older_than_days": "30"}, {"older_than_days": True},
    ])
    def test_a_malformed_purge_is_refused_at_stage(self, bad):
        with pytest.raises(drafts.DraftError):
            drafts.validate_ops([{**self.PURGE, **bad}])

    def test_the_draft_tool_can_stage_it_too_and_it_still_waits(self, trashed):
        out = json.loads(draft_tool({"action": "stage", "project": str(trashed),
                                     "ops": [{**self.PURGE, "target": TARGET}]},
                                    root_path=str(trashed.parent)))
        assert out.get("success"), out
        assert _exists(trashed, "kael")

    def test_restaging_a_purge_draft_does_not_break_the_diff(self, trashed):
        first = _admin(trashed, action="purge", target=TARGET)
        again = drafts.stage(trashed, [{**self.PURGE, "target": TARGET}],
                             draft_id=first["draft_id"])
        assert again["restaged"] is True


# ─── the reversible deletes ask for nothing ───

def test_deleting_an_entity_through_a_draft_is_still_one_step_for_the_person(fixture_path):
    """The person's approval of the draft IS the confirmation; nothing typed."""
    out = drafts.stage(fixture_path, [{"op": "delete", "entity_type": "character",
                                       "entity_id": "kael", "summary": "d"}])
    assert drafts.commit(fixture_path, out["draft_id"])["committed"]
    assert json.loads(admin({"action": "restore", "project": str(fixture_path),
                             "target": TARGET, "summary": "t"},
                            root_path=str(fixture_path.parent)))["success"] is True
