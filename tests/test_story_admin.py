"""story_admin: the five operations that are not entity authoring.

Two things are worth guarding here, and they pull in opposite directions.

The confirmations must hold: `delete_project` destroys every entity in a
project, and nothing in the database can undo it. A test that only checked the
happy path would pass whether or not the guard worked.

And the list must stay a *listing*. `resolve_project` opens a database per
candidate to recover a display name, which is fine when there is one project to
resolve — copying that into an enumeration would mean a connection per project
on every call, on a root that may hold hundreds.
"""
import json
import shutil
import sqlite3
from pathlib import Path

import pytest


from white_words.scriptwriting.tools import story_admin


def _run(args, root):
    """Call the handler the way Hermes does, and parse what it returns."""
    return json.loads(story_admin.handler(args, root_path=str(root)))


@pytest.fixture
def root(tmp_path, fixture_path):
    """A story root holding one real project, copied from the fixture.

    Tests that need to touch the project database itself use
    `root / "projects" / "save-the-children"` — the same tree the tool reaches,
    so a delete staged through core.writes and undone through the tool are
    talking about one database.
    """
    projects = tmp_path / "projects"
    projects.mkdir()
    shutil.copytree(fixture_path, projects / "save-the-children")
    return tmp_path


# ─── list_projects ───

class TestListProjects:
    def test_finds_the_project(self, root):
        result = _run({"action": "list_projects"}, root)
        assert result["success"] is True
        assert result["count"] == 1
        assert result["projects"][0]["slug"] == "save-the-children"
        assert result["projects"][0]["has_database"] is True

    def test_opens_no_database(self, root, monkeypatch):
        """A listing must not connect. One connection per project is a trap
        on a large root, and it would happen on every single call."""
        opened = []
        real_connect = sqlite3.connect

        def spy(*args, **kwargs):
            opened.append(args[0] if args else kwargs.get("database"))
            return real_connect(*args, **kwargs)

        monkeypatch.setattr(sqlite3, "connect", spy)
        result = _run({"action": "list_projects"}, root)
        assert result["count"] == 1, "the listing still has to work"
        assert not opened, f"list_projects opened {len(opened)} database(s)"

    def test_reports_a_folder_with_no_database_rather_than_hiding_it(self, root):
        (root / "projects" / "half-made").mkdir()
        result = _run({"action": "list_projects"}, root)
        slugs = {p["slug"]: p for p in result["projects"]}
        assert slugs["half-made"]["has_database"] is False

    def test_empty_root_is_not_an_error(self, tmp_path):
        result = _run({"action": "list_projects"}, tmp_path)
        assert result["success"] is True and result["count"] == 0


# ─── create_project ───

class TestCreateProject:
    def test_creates_folder_and_database(self, root):
        result = _run({"action": "create_project", "project": "new-film",
                       "frontmatter": {"name": "New Film"}}, root)
        assert result["success"] is True
        assert (root / "projects" / "new-film" / ".story" / "story.db").exists()

    def test_appears_in_the_listing(self, root):
        _run({"action": "create_project", "project": "new-film",
              "frontmatter": {"name": "New Film"}}, root)
        assert _run({"action": "list_projects"}, root)["count"] == 2

    def test_missing_required_field_reports_and_creates_nothing(self, root):
        result = _run({"action": "create_project", "project": "thin"}, root)
        assert "error" in result
        assert not (root / "projects" / "thin").exists()

    def test_traversal_slug_refused(self, root):
        result = _run({"action": "create_project", "project": "../escape",
                       "frontmatter": {"name": "X"}}, root)
        assert "error" in result
        assert not (root.parent / "escape").exists()


def _exists(project, entity_id):
    from white_words.scriptwriting.core.db import get_db
    conn = get_db(project)
    try:
        return bool(conn.execute("SELECT 1 FROM entities WHERE id=?", (entity_id,)).fetchone())
    finally:
        conn.close()


# ─── delete_project ───

class TestDeleteProject:
    def test_no_confirmation_is_asked_for(self, root):
        """Nothing is lost by it: the folder goes to the trash whole. The old typed
        string was printed in its own refusal, so it stopped nobody."""
        project = root / "projects" / "save-the-children"
        result = _run({"action": "delete_project", "project": "save-the-children"}, root)
        assert result["success"] is True
        assert "action_required" not in result and "error" not in result
        assert not project.exists()
        assert "restore_project" in result["note"]

    def test_a_stray_delete_confirm_changes_nothing(self, root):
        """An old client may still send it. It is not a parameter any more."""
        result = _run({"action": "delete_project", "project": "save-the-children",
                       "delete_confirm": "DELETE some-other-film"}, root)
        assert result["success"] is True

    def test_it_can_be_undone(self, root):
        project = root / "projects" / "save-the-children"
        trashed = _run({"action": "delete_project", "project": "save-the-children"}, root)
        back = _run({"action": "restore_project", "trash_id": trashed["trash_id"]}, root)
        assert back["success"] is True
        assert (project / ".story" / "story.db").exists()

    def test_the_project_survives_the_delete_outside_the_deleted_tree(self, root):
        """Deleting moves the folder to the trash instead of removing it, so
        everything in it — not only the database — is still there, in a usable
        form, somewhere the delete did not touch."""
        result = _run({"action": "delete_project", "project": "save-the-children"}, root)
        trashed = Path(result["trashed_to"])
        assert trashed.is_dir(), f"trashed project missing: {trashed}"
        assert (root / "projects") not in trashed.parents, \
            "the trashed copy must be outside projects/"
        conn = sqlite3.connect(str(trashed / ".story" / "story.db"))
        try:
            n = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        finally:
            conn.close()
        assert n > 0, "the trashed project must contain its data"

    def test_a_folder_that_is_not_a_project_is_refused(self, root):
        (root / "projects" / "just-a-folder").mkdir()
        result = _run({"action": "delete_project", "project": "just-a-folder"}, root)
        assert "error" in result
        assert (root / "projects" / "just-a-folder").exists(), \
            "rmtree must not run on something that is not a project"

    def test_unknown_project_reports_rather_than_deleting(self, root):
        result = _run({"action": "delete_project", "project": "no-such-film"}, root)
        assert "error" in result
        assert (root / "projects" / "save-the-children").exists()


# ─── restore ───

class TestRestore:
    def test_undoes_a_soft_delete_exactly(self, root):
        from white_words.scriptwriting.core.db import get_db
        from white_words.scriptwriting.core.writes import delete_entity

        project = root / "projects" / "save-the-children"
        conn = get_db(project)
        try:
            sections_before = conn.execute(
                "SELECT COUNT(*) FROM sections WHERE entity_id='the-garden'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert sections_before > 0, "the fixture must have prose to lose"

        delete_entity(project, "location", "the-garden", "s", confirm=True)

        result = _run({"action": "restore", "project": "save-the-children",
                       "target": {"entity_type": "location", "id": "the-garden"},
                       "summary": "the garden"}, root)
        assert result["success"] is True
        assert result["entity_id"] == "the-garden"

        conn = get_db(project)
        try:
            assert conn.execute(
                "SELECT is_deleted FROM entities WHERE id='the-garden'"
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM sections WHERE entity_id='the-garden'"
            ).fetchone()[0] == sections_before, "prose must come back intact"
        finally:
            conn.close()

    def test_restoring_a_live_entity_reports_rather_than_pretending(self, root):
        result = _run({"action": "restore", "project": "save-the-children",
                       "target": {"entity_type": "location",
                                  "id": "the-central-room"}}, root)
        assert "error" in result
        assert "not deleted" in result["error"]

    def test_unknown_entity_reports(self, root):
        result = _run({"action": "restore", "project": "save-the-children",
                       "target": {"entity_type": "location", "id": "nowhere"}}, root)
        assert "error" in result


# ─── purge ───

class TestPurge:
    def test_it_only_proposes(self, root):
        """No string to type and nothing to echo back: the answer to a purge request
        is a draft for the person, and it says so."""
        result = _run({"action": "purge", "project": "save-the-children"}, root)
        assert result["success"] is True and result["purged"] is False
        assert "draft_id" in result and "preview_md" in result
        assert "action_required" not in result
        assert "purge_confirm" not in json.dumps(result)

    def test_age_floor_keeps_recent_deletes_restorable(self, root):
        """A delete from this session must never be purgeable, even once the
        person has approved a purge."""
        from white_words.scriptwriting.core import drafts
        from white_words.scriptwriting.core.writes import delete_entity
        project = root / "projects" / "save-the-children"
        delete_entity(project, "location", "the-garden", "s", confirm=True)

        staged = _run({"action": "purge", "project": "save-the-children"}, root)
        assert staged["success"] is True and staged["purged"] is False
        assert drafts.commit(project, staged["draft_id"])["committed"]
        assert _exists(project, "the-garden"), "nothing is old enough yet"

    def test_purges_once_past_the_floor(self, root):
        from white_words.scriptwriting.core.db import get_db
        from white_words.scriptwriting.core.writes import delete_entity

        project = root / "projects" / "save-the-children"
        delete_entity(project, "location", "the-garden", "s", confirm=True)
        # Backdate past the floor.
        conn = get_db(project)
        try:
            conn.execute("UPDATE entities SET deleted_at='2000-01-01T00:00:00' "
                         "WHERE is_deleted=1")
        finally:
            conn.close()

        from white_words.scriptwriting.core import drafts
        from white_words.scriptwriting.core.backups import list_backups
        staged = _run({"action": "purge", "project": "save-the-children"}, root)
        assert staged["purged"] is False and _exists(project, "the-garden")
        assert "the-garden" in staged["preview_md"], "the card names what will go"

        before = len(list_backups(project))
        assert drafts.commit(project, staged["draft_id"])["committed"]   # the person approves
        assert len(list_backups(project)) == before + 1, "purge takes a backup first"

        conn = get_db(project)
        try:
            assert conn.execute(
                "SELECT COUNT(*) FROM entities WHERE id='the-garden'"
            ).fetchone()[0] == 0
        finally:
            conn.close()


# ─── the tool boundary ───

def test_unknown_action_reports_rather_than_crashing(root):
    result = _run({"action": "delete_everything"}, root)
    assert "error" in result


def test_authoring_is_not_reachable_here():
    """story_admin must not become a back door around story_draft.

    The whole point of the tool split is that entity content cannot be written
    without the user seeing a preview. A create/edit action appearing here
    would quietly reopen the path this design closed.
    """
    actions = set(story_admin.SCHEMA["properties"]["action"]["enum"])
    assert not actions & {"create", "edit", "edit_note", "delete_entity", "reorder"}
