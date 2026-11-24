"""Purge: the one irreversible operation, and what it removes.

A soft delete means nothing is ever truly lost, which quietly removes the need
for a safety net — and then quietly makes permanent deletion necessary, because
the database otherwise grows without bound. Purge closes that loop, so it has to
be harder to trigger than any other action:

  1. The person approves it. The agent's `story_admin(action="purge")` only
     STAGES a draft; approving the draft in the app runs `purge_deleted`
     (tests/test_purge_approval.py). This file tests `purge_deleted` itself, the
     function the approved draft runs.
  2. An age floor (default 30 days). Anything deleted in this session stays
     restorable, so tidying up can never destroy a fresh mistake.
"""

import json
import shutil
import sqlite3
from pathlib import Path

import pytest


FIXTURE = Path(__file__).parent / "fixtures" / "save-the-children"


@pytest.fixture
def vault(tmp_path, monkeypatch):
    v = tmp_path / "v"
    dest = v / "projects" / "stc"
    dest.parent.mkdir(parents=True)
    shutil.copytree(str(FIXTURE), str(dest))
    import white_words.scriptwriting.core.config
    monkeypatch.setattr(white_words.scriptwriting.core.config, "load_plugin_config",
                        lambda: {"root_path": str(v)})
    from white_words.scriptwriting.tools.story_import import handler
    handler({"project": "stc", "confirm": True}, root_path=str(v))
    return v


TARGET = {"entity_type": "character", "id": "kael"}


def _edit(vault, action, **args):
    """The two admin-only trash actions: purge (everything past the age floor,
    unless a `target` is passed) and restore (one entity, so it gets the target).

    A `target` on purge means "just this one entity" and skips the age floor, so
    these bulk-purge tests must not send one; test_purge_one.py covers that form.
    """
    from white_words.scriptwriting.tools.story_admin import handler
    base = {"action": action, "project": "stc", "summary": "test"}
    if action == "restore":
        base["target"] = TARGET
    return json.loads(handler({**base, **args}, root_path=str(vault)))


def _purge(vault, **kw):
    """What the approved draft runs: purge_deleted, with no confirmation inside."""
    from white_words.scriptwriting.core.trash import purge_deleted
    return purge_deleted(vault / "projects" / "stc", kw.get("target"),
                         kw.get("older_than_days", 30))


def _exists(vault, entity_id):
    conn = sqlite3.connect(
        str(vault / "projects" / "stc" / ".story" / "story.db"))
    try:
        return bool(conn.execute(
            "SELECT 1 FROM entities WHERE id=?", (entity_id,)).fetchone())
    finally:
        conn.close()


def _delete(vault):
    from white_words.scriptwriting.core.writes import delete_entity
    return delete_entity(vault / "projects" / "stc",
                         "character", "kael", "test", True)


class TestPurgeRemovesWhatItIsGiven:
    def test_lowering_the_floor_allows_the_purge(self, vault):
        _delete(vault)
        _purge(vault, older_than_days=0)
        assert not _exists(vault, "kael")

    def test_purged_entities_can_no_longer_be_restored(self, vault):
        _delete(vault)
        _purge(vault, older_than_days=0)
        assert "error" in _edit(vault, "restore")


class TestWhatPurgeRemoves:
    @pytest.fixture
    def purged(self, vault):
        _delete(vault)
        r = _purge(vault, older_than_days=0)
        return vault, r

    def test_it_reports_everything_it_destroyed(self, purged):
        _, r = purged
        ids = {p["id"] for p in r["purged"]}
        assert "kael" in ids

    def test_cascade_children_go_too(self, purged):
        vault, _ = purged
        assert not _exists(vault, "kael-1")

    def test_prose_goes_with_it(self, purged):
        vault, _ = purged
        conn = sqlite3.connect(
            str(vault / "projects" / "stc" / ".story" / "story.db"))
        try:
            n = conn.execute(
                "SELECT count(*) FROM sections WHERE entity_id='kael'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert n == 0

    def test_a_backup_is_taken_first(self, purged):
        _, r = purged
        assert Path(r["backup"]).exists()

    def test_the_backup_actually_contains_the_purged_rows(self, purged):
        """Otherwise the safety net is decorative."""
        _, r = purged
        conn = sqlite3.connect(r["backup"])
        try:
            n = conn.execute(
                "SELECT count(*) FROM entities WHERE id='kael'").fetchone()[0]
        finally:
            conn.close()
        assert n == 1

    def test_live_entities_are_untouched(self, purged):
        vault, _ = purged
        assert _exists(vault, "mira")
        assert _exists(vault, "the-resistance")


class TestPurgeLeavesNoMarkdownToResurrect:
    """Purged rows must not come back through the Markdown either."""

    def test_the_note_is_swept_and_the_entity_stays_gone(self, vault):
        from white_words.scriptwriting.tools.story_export import handler as export_handler
        from white_words.scriptwriting.tools.story_import import handler as import_handler
        from white_words.scriptwriting.tools.story_retrieve import handler as retrieve_handler
        from test_round_trip import note_for, note_rel

        # The sweep only touches files a previous export wrote, so the entity
        # has to be exported once while it still exists. The filename is the
        # title, so the path is only knowable after that first export.
        export_handler({"project": "stc", "confirm": True},
                       root_path=str(vault))
        proj = vault / "projects" / "stc"
        note = note_for(proj, "characters", "kael")
        assert note.exists()

        _delete(vault)
        _purge(vault, older_than_days=0)

        export_handler({"project": "stc", "confirm": True},
                       root_path=str(vault))
        assert not note.exists(), "purged entity's note survived"

        import_handler({"project": "stc", "confirm": True},
                       root_path=str(vault))
        r = json.loads(retrieve_handler({
            "project": "stc", "entity_type": "character", "id": ["kael"],
            "fields": ["one_sentence"]}, root_path=str(vault)))
        assert not r.get("entities"), "purged entity came back"


class TestSoftDeleteSurvivesAnExportImportRoundTrip:
    """A delete must not be undone by an ordinary export → import cycle."""

    def test_deleted_entity_is_not_resurrected(self, vault):
        from white_words.scriptwriting.tools.story_export import handler as export_handler
        from white_words.scriptwriting.tools.story_import import handler as import_handler
        from white_words.scriptwriting.tools.story_retrieve import handler as retrieve_handler
        from test_round_trip import note_for, note_rel
        # Export first, so the manifest knows the file exists. The filename is
        # the title, so the path is captured while the note still exists.
        export_handler({"project": "stc", "confirm": True},
                       root_path=str(vault))
        proj = vault / "projects" / "stc"
        note = note_for(proj, "characters", "kael")
        _delete(vault)
        export_handler({"project": "stc", "confirm": True},
                       root_path=str(vault))
        assert not note.exists()
        import_handler({"project": "stc", "confirm": True},
                       root_path=str(vault))
        r = json.loads(retrieve_handler({
            "project": "stc", "entity_type": "character", "id": ["kael"],
            "fields": ["one_sentence"]}, root_path=str(vault)))
        assert not r.get("entities"), "story_import resurrected a deleted entity"
