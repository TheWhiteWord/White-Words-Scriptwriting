"""The four lookup indexes (migration 5).

On a populated database the plans for the lookups every reader runs —
relations by `to_id`, entities by `parent_id` and by `type` — are full scans,
and so is the deleted-id set the hiding layer reads constantly. These tests
pin the indexes on both schema paths (fresh create and migration from a
file stamped 4), the guard for a file with no `relations`, and that SQLite
actually uses each index.
"""
import sqlite3

import pytest

from story_architect.core.db import (SCHEMA_MIGRATIONS, create_schema, get_db,
                                     transaction)
from story_architect.core.writes import create_project

INDEXES = {"idx_relations_to", "idx_entities_type", "idx_entities_parent",
           "idx_entities_deleted"}


def _db_file(project):
    return project / ".story" / "story.db"


def _index_names(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}


def _new_project(tmp_path):
    root = tmp_path / "v"
    (root / "projects").mkdir(parents=True)
    create_project("stc", {"name": "STC", "logline": "L"}, root)
    return root / "projects" / "stc"


# ─── presence on both schema paths ───

def test_a_new_project_has_all_four_indexes(tmp_path):
    proj = _new_project(tmp_path)
    conn = sqlite3.connect(str(_db_file(proj)))
    try:
        assert INDEXES <= _index_names(conn)
    finally:
        conn.close()


def test_a_database_stamped_4_gains_the_indexes_on_open_and_keeps_its_rows(tmp_path):
    proj = _new_project(tmp_path)
    c = sqlite3.connect(str(_db_file(proj)))
    c.execute("INSERT INTO entities (id, type, name) VALUES ('kael', 'character', 'Kael')")
    c.execute("INSERT INTO entities (id, type, name) VALUES ('s1', 'scene', 'One')")
    c.execute("INSERT INTO relations (from_id, to_id, kind) VALUES ('kael', 's1', 'character_scene')")
    before = {t: c.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
              for t in ("entities", "relations")}
    for name in INDEXES:
        c.execute(f"DROP INDEX IF EXISTS {name}")
    c.execute("PRAGMA user_version = 4")  # as written before migration 5 existed
    c.commit()
    c.close()

    conn = get_db(proj)
    try:
        assert INDEXES <= _index_names(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(SCHEMA_MIGRATIONS)
        for table, count in before.items():
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == count
    finally:
        conn.close()


def test_a_legacy_database_without_relations_still_migrates(tmp_path):
    """The legacy shape (full pre-soft-delete columns, no relations table):
    the guard skips the relations index instead of erroring on a missing table."""
    proj = tmp_path / "legacy"
    _db_file(proj).parent.mkdir(parents=True)
    c = sqlite3.connect(str(_db_file(proj)))
    c.executescript("""
        CREATE TABLE entities (id TEXT PRIMARY KEY, type TEXT, name TEXT,
                               one_sentence TEXT, order_key REAL, status TEXT,
                               parent_id TEXT, location_id TEXT, extra TEXT);
        INSERT INTO entities (id, type, name) VALUES ('a1', 'character', 'Old Hero');
        CREATE TABLE drafts (id TEXT PRIMARY KEY, ops TEXT NOT NULL, prev_ops TEXT,
                             summary TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
    """)
    c.close()
    conn = get_db(proj)
    try:
        names = _index_names(conn)
        assert INDEXES - {"idx_relations_to"} <= names
        assert "idx_relations_to" not in names
        assert conn.execute("SELECT name FROM entities WHERE is_deleted=0").fetchall() \
            == [("Old Hero",)]
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(SCHEMA_MIGRATIONS)
    finally:
        conn.close()


# ─── the plans use them ───

def _populated_db(tmp_path):
    """A few thousand rows: on a tiny table SQLite can prefer a scan even
    with an index present, which would make the plan assertions flaky."""
    proj = tmp_path / "big"
    _db_file(proj).parent.mkdir(parents=True)
    conn = sqlite3.connect(str(_db_file(proj)), isolation_level=None)
    create_schema(conn)
    with transaction(conn):
        for i in range(3000):
            conn.execute(
                "INSERT INTO entities (id, type, name, parent_id, is_deleted) VALUES (?,?,?,?,?)",
                (f"sc{i:05d}", "scene", f"Scene {i}", f"sq{i % 40:05d}", 1 if i % 100 == 99 else 0))
        for i in range(40):
            conn.execute("INSERT INTO entities (id, type, name) VALUES (?,?,?)",
                         (f"sq{i:05d}", "sequence", f"Seq {i}"))
        for i in range(1000):
            conn.execute("INSERT INTO entities (id, type, name) VALUES (?,?,?)",
                         (f"ch{i:05d}", "character", f"Char {i}"))
        for c in range(1000):
            for k in range(9):  # 9 consecutive scenes per character: 9000 unique pairs
                conn.execute("INSERT INTO relations (from_id, to_id, kind) VALUES (?,?,?)",
                             (f"ch{c:05d}", f"sc{(c * 9 + k) % 3000:05d}", "character_scene"))
    return conn


def _plan(conn, query):
    # Plan wording varies between SQLite versions; assert on the index name only.
    return " ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + query))


@pytest.mark.parametrize("query,index", [
    ("SELECT from_id FROM relations WHERE to_id='sc00001' AND kind='character_scene'",
     "idx_relations_to"),
    ("SELECT id FROM entities WHERE parent_id='sq00001' AND is_deleted=0",
     "idx_entities_parent"),
    ("SELECT id FROM entities WHERE type='scene' AND is_deleted=0",
     "idx_entities_type"),
    # The partial index serves the literal only — a parameterised is_deleted=?
    # cannot use it. dead_ids() and live_relations both use the literal.
    ("SELECT id FROM entities WHERE is_deleted=1", "idx_entities_deleted"),
])
def test_the_query_plan_uses_the_index(tmp_path, query, index):
    conn = _populated_db(tmp_path)
    try:
        assert index in _plan(conn, query)
    finally:
        conn.close()
