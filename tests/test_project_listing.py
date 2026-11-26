"""The landing-page listing: the four history keys, and that a read never writes.

`list_projects` runs on every landing-page load, over every project under the root.
So it must not create a manifest for a project this feature has never touched, and
must not adopt one — both would be a write triggered by a page refresh.
"""

import shutil

import pytest

from white_words.scriptwriting.app import services
from white_words.scriptwriting.core.history import store
from white_words.scriptwriting.core.writes import edit_entity

SLUG = "save-the-children"
EMPTY = {
    "current_draft": None,
    "branch_count": 0,
    "last_saved": None,
    "changes_since_save": 0,
}


@pytest.fixture
def root(fixture_path, tmp_path):
    (tmp_path / "projects").mkdir()
    shutil.copytree(str(fixture_path), str(tmp_path / "projects" / SLUG))
    return tmp_path


def _project(root):
    return root / "projects" / SLUG


def _listing(root, slug=SLUG):
    [row] = [p for p in services.list_projects(root) if p["slug"] == slug]
    return row


def test_a_project_with_no_history_reports_the_four_empties(root):
    row = _listing(root)

    assert {k: row[k] for k in EMPTY} == EMPTY
    assert row["has_db"] is True and row["name"]


def test_a_listing_never_creates_a_manifest(root):
    """A read that writes: the first landing-page load would leave history.db behind."""
    assert not store.history_path(_project(root)).exists()

    _listing(root)

    assert not store.history_path(_project(root)).exists()


def test_an_adopted_project_reports_its_first_draft(root):
    project = _project(root)
    store.adopt(project)

    row = _listing(root)

    assert row["branch_count"] == 1
    assert row["current_draft"] == "Draft 1"
    assert row["last_saved"]
    assert row["changes_since_save"] == 0


def test_unsaved_changes_are_counted_not_flagged(root):
    """The landing page shows "N changes since", so the key is a count."""
    project = _project(root)
    store.adopt(project)
    edit_entity(project, "character", "kael", {"name": "Kael Renamed"}, "probe")
    edit_entity(project, "character", "mira", {"name": "Mira Renamed"}, "probe")

    assert _listing(root)["changes_since_save"] == 2


def test_multiple_branches_are_counted(root):
    project = _project(root)
    store.adopt(project)
    base = store.head_state(project)["branch"]["base_snapshot_id"]
    store.branch_from(project, base, "side")

    assert _listing(root)["branch_count"] == 2


def test_the_current_draft_follows_a_save(root):
    project = _project(root)
    store.adopt(project)
    edit_entity(project, "character", "kael", {"name": "Kael Renamed"}, "probe")
    store.save_snapshot(project, "Draft 2", "a note")

    row = _listing(root)

    assert row["current_draft"] == "Draft 2"
    assert row["changes_since_save"] == 0


def test_an_unreadable_manifest_does_not_break_the_listing(root):
    """A manifest this build cannot read is not a reason to fail the page."""
    project = _project(root)
    store.adopt(project)
    store.history_path(project).write_bytes(b"not a database")

    row = _listing(root)

    assert {k: row[k] for k in EMPTY} == EMPTY
    assert row["has_db"] is True
