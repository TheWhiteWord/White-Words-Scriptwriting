"""A project DB created by an earlier build must still be readable.

Regression: story_load failed with "no such column: is_deleted" on a project
whose story.db predates the soft-delete commit. The migration lived only in
create_schema(), which read-only tools never call.

The repairs are now numbered migration steps (`core.db.SCHEMA_MIGRATIONS`) that
`get_db` runs once, on the first open of a database that has no up-to-date
version stamp. These tests build databases in the *old shapes* and check they
open and read correctly; the versioning mechanism itself is in
test_schema_migrations.py.

The `drafts` *table* needs no repair: create_schema makes it, and
create_project is the only way a real database comes into being, so no project
predates draft staging. Only its `status` column (added when a commit began to
mark its row instead of deleting it) is missing from older tables.
"""
import sqlite3


from story_architect.core.db import _m1_soft_delete_columns, get_db


def test_get_db_migrates_a_legacy_database(tmp_path):
    """A DB with the pre-soft-delete entities table is repaired on open."""
    proj = tmp_path / "legacy"
    db = proj / ".story" / "story.db"
    db.parent.mkdir(parents=True)

    legacy = sqlite3.connect(str(db))
    legacy.executescript(
        """
        CREATE TABLE entities (
            id TEXT PRIMARY KEY, type TEXT, name TEXT,
            one_sentence TEXT, order_key REAL, status TEXT,
            parent_id TEXT, location_id TEXT, extra TEXT
        );
        INSERT INTO entities (id, type, name) VALUES ('a1', 'character', 'Old Hero');
        """
    )
    legacy.commit()
    legacy.close()

    conn = get_db(proj)
    try:
        assert conn.execute("SELECT name FROM entities WHERE is_deleted=0").fetchall() == [
            ("Old Hero",)
        ]
    finally:
        conn.close()


def test_get_db_on_a_fresh_project_does_not_fail(tmp_path):
    """No entities table yet — get_db must not try to migrate nothing."""
    conn = get_db(tmp_path / "brand-new")
    try:
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone() is not None
    finally:
        conn.close()


def test_migrations_are_idempotent(tmp_path):
    """The first two steps are guarded ("only if missing") because they also run
    on unstamped databases of unknown shape, so running one twice — or on a
    database that is already in the new shape — must be a no-op, not an error.
    """
    from story_architect.core.writes import create_project
    root = tmp_path / "v"
    (root / "projects").mkdir(parents=True)
    create_project("stc", {"name": "STC", "logline": "L"}, root)

    conn = get_db(root / "projects" / "stc")
    try:
        _m1_soft_delete_columns(conn)
        _m1_soft_delete_columns(conn)
    finally:
        conn.close()


def test_a_drafts_table_without_status_gains_it(tmp_path):
    """A drafts table predating the `status` column gains it on open.

    The table itself is assumed present — create_schema makes it — so this
    builds one in the old shape and checks the column is added.
    """
    proj = tmp_path / "old-drafts"
    db = proj / ".story" / "story.db"
    db.parent.mkdir(parents=True)
    legacy = sqlite3.connect(str(db))
    legacy.executescript(
        """
        CREATE TABLE drafts (
            id TEXT PRIMARY KEY,
            ops TEXT NOT NULL,
            prev_ops TEXT,
            summary TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        """
    )
    legacy.commit()
    legacy.close()

    conn = get_db(proj)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(drafts)")}
        assert "status" in cols
    finally:
        conn.close()
