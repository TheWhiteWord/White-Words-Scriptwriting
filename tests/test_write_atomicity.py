"""Multi-statement writes are all-or-nothing.

Each test makes the *last* step of an operation fail, using a SQLite trigger
that raises, and then checks that nothing the earlier steps did survived.
Before these writes ran in a transaction, a failure part-way left the database
half-changed: an entity flagged deleted but its relations already gone, a purge
that removed sections and relations but not the entity.
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
    import story_architect.core.config
    monkeypatch.setattr(story_architect.core.config, "load_plugin_config",
                        lambda: {"root_path": str(v)})
    from story_architect.tools.story_import import handler
    handler({"project": "stc", "confirm": True}, root_path=str(v))
    return v


def _project(vault):
    return vault / "projects" / "stc"


def _db(vault):
    return sqlite3.connect(str(_project(vault) / ".story" / "story.db"),
                           isolation_level=None)


def _snapshot(vault):
    """Everything an operation could touch, in a comparable form."""
    c = _db(vault)
    try:
        return {
            "entities": c.execute("SELECT * FROM entities ORDER BY id").fetchall(),
            "relations": c.execute("SELECT * FROM relations ORDER BY 1, 2, 3").fetchall(),
            "sections": c.execute("SELECT * FROM sections ORDER BY 1, 2").fetchall(),
        }
    finally:
        c.close()


def _break(vault, trigger_sql):
    c = _db(vault)
    c.execute(trigger_sql)
    c.close()


def _unbreak(vault, name):
    c = _db(vault)
    c.execute(f"DROP TRIGGER {name}")
    c.close()


def _call_admin(vault, **args):
    from story_architect.tools.story_admin import handler
    return json.loads(handler({"project": "stc", "summary": "t", **args},
                              root_path=str(vault)))


# ─── delete ───

def test_failed_delete_changes_nothing(vault):
    """The reference scrub is the delete's last step. If it fails, the entity
    flag, the child flags and the inbound-relation deletes before it must all
    be undone — not left as a half-deleted character."""
    from story_architect.core.writes import delete_entity

    before = _snapshot(vault)
    # The scrub rewrites `extra` on relationships that name the character.
    _break(vault, "CREATE TRIGGER boom BEFORE UPDATE OF extra ON entities "
                  "BEGIN SELECT RAISE(ABORT, 'boom'); END")

    with pytest.raises(sqlite3.Error, match="boom"):
        delete_entity(_project(vault), "character", "kael", "t", True)

    assert _snapshot(vault) == before

    # Same call succeeds once the fault is gone: the failure left no residue.
    _unbreak(vault, "boom")
    result = delete_entity(_project(vault), "character", "kael", "t", True)
    assert result["success"] is True
    c = _db(vault)
    assert c.execute("SELECT is_deleted FROM entities WHERE id='kael'").fetchone()[0] == 1


def test_delete_refusals_leave_database_untouched(vault):
    """The two payload-returning paths (no confirm, structural child) sit
    inside the transaction; they must commit nothing and leave no lock."""
    from story_architect.core.writes import delete_entity

    before = _snapshot(vault)
    refused = delete_entity(_project(vault), "character", "kael", "t", None)
    assert "error" in refused
    parent_of_scenes = next(
        r[0] for r in _db(vault).execute(
            "SELECT parent_id FROM entities WHERE type='scene' LIMIT 1"))
    blocked = delete_entity(_project(vault), "sequence", parent_of_scenes, "t", True)
    assert "error" in blocked
    assert _snapshot(vault) == before
    # and the write lock was released: another connection can write straight away
    c = _db(vault)
    c.execute("PRAGMA busy_timeout=0")
    c.execute("UPDATE entities SET name=name WHERE id='kael'")


# ─── purge ───

def test_failed_purge_removes_nothing(vault):
    from story_architect.core.writes import delete_entity

    delete_entity(_project(vault), "character", "kael", "t", True)
    c = _db(vault)
    c.execute("UPDATE entities SET deleted_at='2000-01-01T00:00:00' WHERE id='kael'")
    c.close()
    before = _snapshot(vault)

    # sections and relations are deleted first, the entity row last
    _break(vault, "CREATE TRIGGER boom BEFORE DELETE ON entities "
                  "BEGIN SELECT RAISE(ABORT, 'boom'); END")
    with pytest.raises(sqlite3.Error, match="boom"):
        _call_admin(vault, action="purge", target={"entity_type": "character", "id": "kael"},
                    purge_confirm="DELETE stc")

    assert _snapshot(vault) == before


# ─── restore ───

def test_failed_restore_leaves_parent_deleted(vault):
    """Restore flips the parent, then its children. If the children step fails,
    the parent must not come back alone."""
    from story_architect.core.writes import delete_entity

    c = _db(vault)
    scene = c.execute("SELECT parent_id FROM entities "
                      "WHERE type='scene_beats' LIMIT 1").fetchone()[0]
    child = c.execute("SELECT id FROM entities WHERE parent_id=? AND type='scene_beats'",
                      (scene,)).fetchone()[0]
    c.close()
    assert delete_entity(_project(vault), "scene", scene, "t", True)["success"]
    before = _snapshot(vault)

    _break(vault, f"CREATE TRIGGER boom BEFORE UPDATE ON entities WHEN OLD.id='{child}' "
                  f"BEGIN SELECT RAISE(ABORT, 'boom'); END")
    with pytest.raises(sqlite3.Error, match="boom"):
        _call_admin(vault, action="restore", target={"entity_type": "scene", "id": scene})

    assert _snapshot(vault) == before


# ─── import ───

def test_import_failure_before_the_transaction_is_reported_not_raised(vault, monkeypatch):
    """A failure before the import's BEGIN (here: the safety backup) used to be
    followed by an unguarded ROLLBACK, which itself raised 'cannot rollback - no
    transaction is active' and replaced the real error with a crash."""
    from story_architect.tools import story_import

    def no_backup(project_path):
        raise OSError("disk full")
    monkeypatch.setattr(story_import, "_backup", no_backup)

    out = json.loads(story_import.handler({"project": "stc", "confirm": True},
                                          root_path=str(vault)))
    assert "disk full" in out["error"]


def test_failed_import_keeps_existing_data(vault):
    """The import wipes every table then rebuilds. If the rebuild fails, the
    wipe must be undone."""
    from story_architect.tools.story_import import handler

    before = _snapshot(vault)
    # entities are inserted before sections; fail on the first section row
    _break(vault, "CREATE TRIGGER boom BEFORE INSERT ON sections "
                  "BEGIN SELECT RAISE(ABORT, 'boom'); END")
    out = json.loads(handler({"project": "stc", "confirm": True}, root_path=str(vault)))
    assert "boom" in out["error"]
    assert _snapshot(vault) == before
