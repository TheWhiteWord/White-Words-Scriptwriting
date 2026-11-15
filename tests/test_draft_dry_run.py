"""The dry run: staging reports whether the batch would commit, and touches nothing.

The replay runs `commit` against a throwaway copy of the project database, so
the verdict is the real one — op ordering, within-batch effects and every
validator included — while the project itself is untouched.
"""
import tempfile
from pathlib import Path

import pytest

from story_architect.core import drafts

from test_drafts import _counts


def _file_set(root):
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob("*")
                  if p.is_file())


def _take_climax():
    """Give `the-core-day` the climax `central-room-night` already holds."""
    return [{
        "op": "edit", "entity_type": "scene", "entity_id": "the-core-day",
        "data": {"plot_roles": [
            {"plot": "the-resistance", "role": "climax",
             "description": "The children refuse the system's final offer."}]},
        "summary": "The Core takes the climax",
    }]


def _free_climax():
    """Clear the climax on one scene, then give it to another — in one batch."""
    return [
        {"op": "edit", "entity_type": "scene", "entity_id": "central-room-night",
         "data": {"plot_roles": []}, "summary": "Night releases the climax"},
        {"op": "edit", "entity_type": "scene", "entity_id": "the-core-day",
         "data": {"plot_roles": [
             {"plot": "the-resistance", "role": "resolution",
              "description": "The children emerge into the real world."},
             {"plot": "the-resistance", "role": "climax",
              "description": "The children refuse the system's final offer."}]},
         "summary": "The Core takes the climax"},
    ]


class _TempDirRecorder:
    """Wrap TemporaryDirectory to record each dir's file set before cleanup."""

    def __init__(self, monkeypatch):
        real = tempfile.TemporaryDirectory
        self.record = []
        record = self.record

        class _CM:
            def __init__(self, cm, path):
                self._cm = cm
                self.path = path

            def __enter__(self):
                self._cm.__enter__()
                return self.path

            def __exit__(self, *exc):
                record.append((self.path, _file_set(self.path)))
                return self._cm.__exit__(*exc)

        def factory(*args, **kwargs):
            cm = real(*args, **kwargs)
            return _CM(cm, Path(cm.name))

        monkeypatch.setattr(tempfile, "TemporaryDirectory", factory)


@pytest.fixture
def temp_dirs(monkeypatch):
    return _TempDirRecorder(monkeypatch).record


# ─── the verdict ───

def test_a_conflict_is_caught_at_stage_time(fixture_path):
    result = drafts.stage(fixture_path, _take_climax(), "move the climax")
    dry = result["dry_run"]
    assert dry["status"] == "refused"
    assert dry["failed_op"] == "edit scene/the-core-day"
    # The error names the plot, the role and the scene that already holds it.
    assert "the-resistance" in dry["error"]
    assert "climax" in dry["error"]
    assert "central-room-night" in dry["error"]


def test_a_freeing_batch_is_clean(fixture_path):
    """The false-positive case: a committed-state check would refuse this."""
    result = drafts.stage(fixture_path, _free_climax(), "hand the climax over")
    assert result["dry_run"] == {"status": "clean"}


def test_a_clean_batch_is_clean(fixture_path):
    result = drafts.stage(fixture_path, [{
        "op": "edit", "entity_type": "location", "entity_id": "the-central-room",
        "data": {"mood": "colder"}, "summary": "the room cools"}], "a mood")
    assert result["dry_run"] == {"status": "clean"}


# ─── isolation ───

def test_the_real_project_is_untouched(fixture_path):
    before_counts = _counts(fixture_path)
    before_files = _file_set(fixture_path)
    drafts.stage(fixture_path, _take_climax(), "move the climax")
    assert _counts(fixture_path) == before_counts
    assert _file_set(fixture_path) == before_files


def test_the_copy_is_untouched_apart_from_the_database(fixture_path, temp_dirs):
    """The loud break: a future file-writing write path lands in the copy, not
    the real project — so the copy's file set is what must stay DB-only."""
    drafts.stage(fixture_path, _free_climax(), "hand the climax over")
    assert len(temp_dirs) == 1
    _, files = temp_dirs[0]
    assert files, "the replay made no copy"
    assert set(files) <= {".story/story.db", ".story/story.db-wal",
                          ".story/story.db-shm"}, files


def test_the_temp_dir_is_removed_on_every_path(fixture_path, temp_dirs,
                                               monkeypatch):
    drafts.stage(fixture_path, _free_climax(), "clean")
    drafts.stage(fixture_path, _take_climax(), "refused")

    def boom(*args, **kwargs):
        raise RuntimeError("sandbox exploded")

    monkeypatch.setattr(drafts, "commit", boom)
    result = drafts.stage(fixture_path, _free_climax(), "unavailable")
    assert result["dry_run"]["status"] == "unavailable"
    assert "sandbox exploded" in result["dry_run"]["error"]

    assert len(temp_dirs) == 3
    assert not any(path.exists() for path, _ in temp_dirs)


# ─── the backstop ───

def test_commit_still_refuses_the_draft_the_dry_run_refused(fixture_path):
    staged = drafts.stage(fixture_path, _take_climax(), "move the climax")
    result = drafts.commit(fixture_path, staged["draft_id"])
    assert result["success"] is False
    assert result["failed"]["error"] == staged["dry_run"]["error"]
