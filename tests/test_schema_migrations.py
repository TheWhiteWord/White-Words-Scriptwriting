"""Schema versioning: PRAGMA user_version + an ordered list of migration steps.

A database file records how many steps it has run. Opening one that is behind
runs the missing steps once, in a transaction; opening a current one costs a
single pragma. Covers story.db (core.db) and chat.db (chat.store).
"""
import sqlite3
import threading
import time

import pytest

from story_architect.core import db as core_db
from story_architect.core.db import (SCHEMA_MIGRATIONS, SchemaTooNewError,
                                     apply_migrations, create_schema, get_db)
from story_architect.core.writes import create_project

LATEST = len(SCHEMA_MIGRATIONS)


def _version(path_to_db):
    c = sqlite3.connect(str(path_to_db))
    try:
        return c.execute("PRAGMA user_version").fetchone()[0]
    finally:
        c.close()


def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _db_file(project):
    return project / ".story" / "story.db"


def _legacy_project(tmp_path, name="legacy"):
    """A project from before soft delete and before drafts.status: unstamped."""
    proj = tmp_path / name
    _db_file(proj).parent.mkdir(parents=True)
    c = sqlite3.connect(str(_db_file(proj)))
    c.executescript("""
        CREATE TABLE entities (id TEXT PRIMARY KEY, type TEXT NOT NULL, name TEXT);
        INSERT INTO entities VALUES ('a1', 'character', 'Old Hero');
        CREATE TABLE drafts (id TEXT PRIMARY KEY, ops TEXT NOT NULL, prev_ops TEXT,
                             summary TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
    """)
    c.close()
    return proj


# ─── story.db ───

def test_a_new_project_is_stamped_current(tmp_path):
    root = tmp_path / "v"
    (root / "projects").mkdir(parents=True)
    create_project("stc", {"name": "STC", "logline": "L"}, root)
    assert _version(_db_file(root / "projects" / "stc")) == LATEST


def test_a_file_without_tables_is_left_alone_until_the_schema_is_created(tmp_path):
    conn = get_db(tmp_path / "p")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    create_schema(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST
    conn.close()


def test_an_unstamped_legacy_database_is_upgraded_and_stamped(tmp_path):
    proj = _legacy_project(tmp_path)
    assert _version(_db_file(proj)) == 0
    conn = get_db(proj)
    try:
        assert {"is_deleted", "deleted_at"} <= _cols(conn, "entities")
        assert "status" in _cols(conn, "drafts")
        assert conn.execute("SELECT name FROM entities WHERE is_deleted=0").fetchall() \
            == [("Old Hero",)]
        assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST
    finally:
        conn.close()


def test_an_unstamped_database_that_is_already_current_in_shape_just_gets_stamped(tmp_path):
    """Every real database made before this change looks like this."""
    root = tmp_path / "v"
    (root / "projects").mkdir(parents=True)
    create_project("stc", {"name": "STC", "logline": "L"}, root)
    proj = root / "projects" / "stc"
    c = sqlite3.connect(str(_db_file(proj)))
    c.execute("PRAGMA user_version = 0")
    before = c.execute("SELECT count(*) FROM entities").fetchone()[0]
    c.close()

    conn = get_db(proj)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST
        assert conn.execute("SELECT count(*) FROM entities").fetchone()[0] == before
    finally:
        conn.close()


def test_only_the_missing_steps_run(tmp_path):
    """A file stamped 1 has had step 1: step 2 runs, step 1 does not."""
    calls = []
    steps = [lambda c: calls.append(1), lambda c: calls.append(2),
             lambda c: calls.append(3)]
    conn = sqlite3.connect(str(tmp_path / "x.db"), isolation_level=None)
    conn.execute("PRAGMA user_version = 1")
    apply_migrations(conn, steps)
    assert calls == [2, 3]
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    apply_migrations(conn, steps)  # current: nothing more
    assert calls == [2, 3]
    conn.close()


def test_a_current_database_runs_no_steps_on_open(tmp_path, monkeypatch):
    root = tmp_path / "v"
    (root / "projects").mkdir(parents=True)
    create_project("stc", {"name": "STC", "logline": "L"}, root)

    def boom(conn):
        raise AssertionError("a migration ran on a current database")
    monkeypatch.setattr(core_db, "SCHEMA_MIGRATIONS", [boom] * LATEST)
    get_db(root / "projects" / "stc").close()


def test_a_failing_step_changes_nothing(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "x.db"), isolation_level=None)

    def make_table(c):
        c.execute("CREATE TABLE made_by_step_1 (x)")

    def fail(c):
        raise RuntimeError("step 2 broke")

    with pytest.raises(RuntimeError, match="step 2 broke"):
        apply_migrations(conn, [make_table, fail])
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='made_by_step_1'").fetchone() is None
    conn.close()


def test_a_database_from_a_newer_build_is_refused_and_untouched(tmp_path):
    root = tmp_path / "v"
    (root / "projects").mkdir(parents=True)
    create_project("stc", {"name": "STC", "logline": "L"}, root)
    proj = root / "projects" / "stc"
    c = sqlite3.connect(str(_db_file(proj)))
    c.execute(f"PRAGMA user_version = {LATEST + 5}")
    c.close()

    with pytest.raises(SchemaTooNewError, match="newer version"):
        get_db(proj)
    assert _version(_db_file(proj)) == LATEST + 5


def test_two_connections_opening_an_old_database_upgrade_it_once(tmp_path):
    """The second one in must find the work done, not repeat it."""
    runs = []
    gate = threading.Barrier(4)

    def step(c):
        runs.append(1)
        c.execute("CREATE TABLE IF NOT EXISTS t (x)")
        # Slow enough that every other thread has already read "version 0" and
        # is queued for the write lock when this one finishes.
        time.sleep(0.3)

    path = tmp_path / "x.db"
    sqlite3.connect(str(path)).close()
    errors = []

    def worker():
        c = sqlite3.connect(str(path), isolation_level=None, timeout=10)
        try:
            gate.wait()
            apply_migrations(c, [step])
        except Exception as e:  # pragma: no cover - only on failure
            errors.append(e)
        finally:
            c.close()

    ts = [threading.Thread(target=worker) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert errors == []
    assert len(runs) == 1
    assert _version(path) == 1


def test_a_backup_keeps_its_version_so_an_old_one_is_upgraded_when_opened(tmp_path):
    from story_architect.core.db import backup_database

    proj = _legacy_project(tmp_path)
    get_db(proj).close()  # now stamped
    snap = backup_database(proj)
    assert _version(snap) == LATEST

    # An older snapshot, as if taken before the last step existed:
    c = sqlite3.connect(snap)
    c.execute("PRAGMA user_version = 1")
    c.execute("ALTER TABLE drafts RENAME TO drafts_old")
    c.execute("CREATE TABLE drafts (id TEXT PRIMARY KEY, ops TEXT NOT NULL, prev_ops TEXT, "
              "summary TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)")
    c.close()
    _db_file(proj).write_bytes(open(snap, "rb").read())
    for ext in ("-wal", "-shm"):
        f = _db_file(proj).with_name("story.db" + ext)
        if f.exists():
            f.unlink()
    conn = get_db(proj)
    try:
        assert "status" in _cols(conn, "drafts")
    finally:
        conn.close()


# ─── chat.db ───

def test_a_new_chat_db_is_stamped(tmp_path):
    from story_architect.chat import store
    store.connect(tmp_path).close()
    assert _version(tmp_path / ".story" / "chat.db") == len(store.MIGRATIONS)


def test_a_legacy_chat_db_gains_its_columns_and_keeps_its_messages(tmp_path):
    from story_architect.chat import store
    p = tmp_path / ".story" / "chat.db"
    p.parent.mkdir(parents=True)
    c = sqlite3.connect(str(p))
    c.executescript("""
        CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, backend_state TEXT,
            last_opened INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL,
            role TEXT NOT NULL, text TEXT NOT NULL DEFAULT '', timestamp TEXT NOT NULL,
            metadata TEXT, status TEXT NOT NULL DEFAULT 'complete');
        INSERT INTO conversations (id, created_at, updated_at) VALUES ('c1', 't', 't');
        INSERT INTO messages (conversation_id, role, text, timestamp) VALUES ('c1', 'user', 'hello', 't');
    """)
    c.close()
    assert _version(p) == 0

    conn = store.connect(tmp_path)
    try:
        assert {"tools", "drafts", "attachments", "hidden", "error"} <= _cols(conn, "messages")
        assert conn.execute("SELECT text, hidden FROM messages").fetchall() == [("hello", 0)]
    finally:
        conn.close()
    assert _version(p) == len(store.MIGRATIONS)


def test_chat_db_from_a_newer_build_is_refused(tmp_path):
    from story_architect.chat import store
    store.connect(tmp_path).close()
    p = tmp_path / ".story" / "chat.db"
    c = sqlite3.connect(str(p))
    c.execute("PRAGMA user_version = 99")
    c.close()
    with pytest.raises(SchemaTooNewError):
        store.connect(tmp_path)
    assert _version(p) == 99
