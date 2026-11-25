"""`ProjectView`: reading a frozen draft without touching it.

A draft is `0444` and must never be opened read-write: SQLite leaves `-wal`/`-shm`
beside a file before it discovers the file is read-only, and a migration would
rewrite a frozen file. The view copies the draft out instead, and these pin that
the draft is untouched and the copy is a working project.
"""

import sqlite3
import stat

import pytest

from white_words.scriptwriting.core.history import logical, store, view
from white_words.scriptwriting.core.writes import edit_entity


@pytest.fixture
def project(fixture_path):
    """The fixture with a manifest and one frozen draft of a changed state."""
    store.adopt(fixture_path)
    edit_entity(fixture_path, "character", "kael", {"name": "Kael Renamed"}, "rename")
    store.save_snapshot(fixture_path, label="second")
    return fixture_path


def _latest_draft(project):
    drafts = store.list_branches(project)["snapshots"]
    return max(drafts, key=lambda d: d["seq"])


def _untouched(path):
    return path.read_bytes(), path.stat().st_mode


def test_a_view_reads_the_draft_and_leaves_it_untouched(project):
    snapshot = _latest_draft(project)
    path = store.snapshot_file(project, snapshot["id"])
    before = _untouched(path)

    with view.project_view(project, snapshot["id"]) as tmp:
        live = logical.of_project(tmp)

    assert len(live) == 26
    assert _untouched(path) == before


def test_a_view_leaves_no_wal_beside_the_draft(project):
    """A read-write open would leave the sidecars; the view never makes one."""
    snapshot = _latest_draft(project)
    beside_before = sorted(p.name for p in store.snapshots_dir(project).iterdir())
    with view.project_view(project, snapshot["id"]) as tmp:
        logical.of_project(tmp)
    assert sorted(p.name for p in store.snapshots_dir(project).iterdir()) == beside_before


def test_a_view_shows_the_state_the_draft_holds(project):
    """The draft carries the head as it was; a later edit is not in it."""
    snapshot = _latest_draft(project)
    edit_entity(project, "character", "kael", {"name": "Changed After Saving"}, "rename")

    with view.project_view(project, snapshot["id"]) as tmp:
        assert logical.of_project(tmp)["kael"]["fields"]["name"] == "Kael Renamed"
    assert logical.of_project(project)["kael"]["fields"]["name"] == "Changed After Saving"


def test_the_copy_is_gone_after_the_block(project):
    snapshot = _latest_draft(project)
    with view.project_view(project, snapshot["id"]) as tmp:
        assert (tmp / ".story" / "story.db").exists()
    assert not tmp.exists()


def test_the_copy_is_gone_when_the_block_raises(project):
    snapshot = _latest_draft(project)
    with pytest.raises(RuntimeError):
        with view.project_view(project, snapshot["id"]) as tmp:
            raise RuntimeError("boom")
    assert not tmp.exists()


def test_a_missing_draft_is_refused(project):
    with pytest.raises(ValueError, match="no file on disk"):
        with view.project_view(project, "s-not-a-draft"):
            pass


def test_a_draft_from_a_newer_build_is_refused(project, tmp_path):
    """A newer schema is refused by the same check a backup goes through."""
    src = store.snapshot_file(project, _latest_draft(project)["id"])
    newer = tmp_path / "newer.db"
    conn = sqlite3.connect(f"file:{src}?mode=ro&immutable=1", uri=True)
    try:
        conn.backup(sqlite3.connect(str(newer)))
    finally:
        conn.close()
    conn = sqlite3.connect(str(newer))
    conn.execute("PRAGMA user_version = 99")
    conn.close()
    newer.chmod(stat.S_IRUSR)

    store.snapshot_file(project, "s-newer").write_bytes(newer.read_bytes())
    with pytest.raises(ValueError, match="newer version"):
        with view.project_view(project, "s-newer"):
            pass


def test_two_views_of_one_draft_do_not_share_a_directory(project):
    snapshot = _latest_draft(project)
    with view.project_view(project, snapshot["id"]) as first:
        with view.project_view(project, snapshot["id"]) as second:
            assert first != second
            edit_entity(first, "character", "kael", {"name": "Only In First"}, "edit")
            assert logical.of_project(second)["kael"]["fields"]["name"] == "Kael Renamed"
