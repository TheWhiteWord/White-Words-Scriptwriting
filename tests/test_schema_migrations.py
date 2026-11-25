"""Schema versioning: the baseline + an append-only list of migration steps.

A database file records how far it has come (PRAGMA user_version). New files
are stamped LATEST_VERSION; a file one step behind is upgraded on open, in one
transaction; a file below the baseline or above the latest is refused. The
steps are exercised with a test-only migration monkeypatched onto the (empty)
real list — the mechanism, not history. Covers story.db (core.db) and chat.db
(chat.store).
"""

import sqlite3
import threading
import time

import pytest

from white_words.scriptwriting.core import db as core_db
from white_words.scriptwriting.core.db import (
    BASELINE_VERSION,
    LATEST_VERSION,
    SchemaTooNewError,
    SchemaTooOldError,
    apply_migrations,
    get_db,
)
from white_words.scriptwriting.core.writes import create_project


def _version(path_to_db):
    c = sqlite3.connect(str(path_to_db))
    try:
        return c.execute("PRAGMA user_version").fetchone()[0]
    finally:
        c.close()


def _db_file(project):
    return project / ".story" / "story.db"


def _stamp(project, version):
    """Make a built project pretend it was written at an earlier version."""
    c = sqlite3.connect(str(_db_file(project)))
    c.execute(f"PRAGMA user_version = {version}")
    c.close()


def _new_project(tmp_path):
    root = tmp_path / "v"
    (root / "projects").mkdir(parents=True)
    create_project("stc", {"name": "STC", "logline": "L"}, root)
    return root / "projects" / "stc"


@pytest.fixture
def one_step(monkeypatch):
    """A test-only migration after the baseline. LATEST_VERSION is derived at
    import, so it is patched alongside the list; tests stamp a built project
    BASELINE_VERSION to make it one step behind."""
    calls = []

    def step(conn):
        calls.append(1)
        conn.execute("CREATE TABLE test_only_step (x)")

    monkeypatch.setattr(core_db, "SCHEMA_MIGRATIONS", [step])
    monkeypatch.setattr(core_db, "LATEST_VERSION", BASELINE_VERSION + 1)
    return calls


# ─── story.db ───


def test_a_new_project_is_stamped_current(tmp_path):
    proj = _new_project(tmp_path)
    assert _version(_db_file(proj)) == LATEST_VERSION


def test_get_db_creates_the_schema_on_a_file_with_no_tables(tmp_path):
    conn = get_db(tmp_path / "p")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_VERSION
    assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='entities'").fetchone()
    conn.close()


def test_a_database_one_step_behind_is_upgraded_on_open_and_keeps_its_rows(tmp_path, one_step):
    proj = _new_project(tmp_path)
    _stamp(proj, BASELINE_VERSION)  # one behind the patched LATEST
    conn = get_db(proj)
    try:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='test_only_step'").fetchone()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == BASELINE_VERSION + 1
        assert conn.execute("SELECT count(*) FROM entities").fetchone()[0] >= 1
    finally:
        conn.close()
    assert one_step == [1]


def test_upgrading_twice_changes_nothing(tmp_path, one_step):
    proj = _new_project(tmp_path)
    _stamp(proj, BASELINE_VERSION)
    get_db(proj).close()
    get_db(proj).close()
    assert one_step == [1]
    assert _version(_db_file(proj)) == BASELINE_VERSION + 1


def test_only_the_missing_steps_run(tmp_path):
    """A file stamped baseline+1 has had step 1: step 2 runs, step 1 does not."""
    calls = []
    steps = [lambda c: calls.append(1), lambda c: calls.append(2), lambda c: calls.append(3)]
    conn = sqlite3.connect(str(tmp_path / "x.db"), isolation_level=None)
    conn.execute("PRAGMA user_version = 1")
    apply_migrations(conn, steps, baseline=0)
    assert calls == [2, 3]
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    apply_migrations(conn, steps, baseline=0)  # current: nothing more
    assert calls == [2, 3]
    conn.close()


def test_a_current_database_runs_no_steps_on_open(tmp_path, monkeypatch):
    proj = _new_project(tmp_path)
    c = sqlite3.connect(str(_db_file(proj)))
    c.execute(f"PRAGMA user_version = {BASELINE_VERSION + 1}")
    c.close()

    def boom(conn):
        raise AssertionError("a migration ran on a current database")

    monkeypatch.setattr(core_db, "SCHEMA_MIGRATIONS", [boom])
    monkeypatch.setattr(core_db, "LATEST_VERSION", BASELINE_VERSION + 1)
    get_db(proj).close()


def test_a_failing_step_changes_nothing(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "x.db"), isolation_level=None)
    conn.execute(f"PRAGMA user_version = {BASELINE_VERSION}")

    def make_table(c):
        c.execute("CREATE TABLE made_by_step_1 (x)")

    def fail(c):
        raise RuntimeError("step 2 broke")

    with pytest.raises(RuntimeError, match="step 2 broke"):
        apply_migrations(conn, [make_table, fail], baseline=BASELINE_VERSION)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == BASELINE_VERSION
    assert (
        conn.execute("SELECT 1 FROM sqlite_master WHERE name='made_by_step_1'").fetchone() is None
    )
    conn.close()


def test_a_database_below_the_baseline_is_refused_and_untouched(tmp_path):
    proj = _new_project(tmp_path)
    c = sqlite3.connect(str(_db_file(proj)))
    c.execute(f"PRAGMA user_version = {BASELINE_VERSION - 1}")
    c.close()
    with pytest.raises(SchemaTooOldError, match="older than this build supports"):
        get_db(proj)
    assert _version(_db_file(proj)) == BASELINE_VERSION - 1


def test_a_file_with_tables_but_no_version_is_refused(tmp_path):
    proj = _new_project(tmp_path)
    c = sqlite3.connect(str(_db_file(proj)))
    c.execute("PRAGMA user_version = 0")
    c.close()
    with pytest.raises(SchemaTooOldError, match="older than this build supports"):
        get_db(proj)
    assert _version(_db_file(proj)) == 0


def test_a_database_from_a_newer_build_is_refused_and_untouched(tmp_path):
    proj = _new_project(tmp_path)
    c = sqlite3.connect(str(_db_file(proj)))
    c.execute(f"PRAGMA user_version = {LATEST_VERSION + 5}")
    c.close()
    with pytest.raises(SchemaTooNewError, match="newer version"):
        get_db(proj)
    assert _version(_db_file(proj)) == LATEST_VERSION + 5


def test_two_connections_opening_a_behind_database_upgrade_it_once(tmp_path):
    """The second one in must find the work done, not repeat it."""
    runs = []
    gate = threading.Barrier(4)

    def step(c):
        runs.append(1)
        c.execute("CREATE TABLE IF NOT EXISTS t (x)")
        # Slow enough that every other thread has already read the old version
        # and is queued for the write lock when this one finishes.
        time.sleep(0.3)

    path = tmp_path / "x.db"
    sqlite3.connect(str(path)).close()
    errors = []

    def worker():
        c = sqlite3.connect(str(path), isolation_level=None, timeout=10)
        try:
            gate.wait()
            apply_migrations(c, [step], baseline=0)
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


def test_a_backup_one_step_behind_is_upgraded_when_opened(tmp_path, one_step):
    from white_words.scriptwriting.core.db import backup_database

    proj = _new_project(tmp_path)
    snap = backup_database(proj)
    # backup_database opens through get_db, which may have upgraded the file
    # under the patched LATEST: stamp the snapshot itself one step behind.
    c = sqlite3.connect(str(snap))
    c.execute(f"PRAGMA user_version = {BASELINE_VERSION}")
    c.close()
    assert _version(snap) == BASELINE_VERSION
    before = sqlite3.connect(str(snap)).execute("SELECT count(*) FROM entities").fetchone()[0]

    # The snapshot travels with its version; under the patched LATEST it is one
    # step behind, and opening the project it is restored into brings it forward.
    _db_file(proj).write_bytes(open(snap, "rb").read())
    for ext in ("-wal", "-shm"):
        f = _db_file(proj).with_name("story.db" + ext)
        if f.exists():
            f.unlink()
    conn = get_db(proj)
    try:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='test_only_step'").fetchone()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == BASELINE_VERSION + 1
        assert conn.execute("SELECT count(*) FROM entities").fetchone()[0] == before
    finally:
        conn.close()


# ─── chat.db ───


def test_a_new_chat_db_is_stamped(tmp_path):
    from white_words.scriptwriting.chat import store

    store.connect(tmp_path).close()
    assert _version(tmp_path / ".story" / "chat.db") == store.CHAT_LATEST


def test_a_chat_db_one_step_behind_is_upgraded_on_open(tmp_path, monkeypatch):
    from white_words.scriptwriting.chat import store

    store.connect(tmp_path).close()  # stamped CHAT_BASELINE
    p = tmp_path / ".story" / "chat.db"
    c = sqlite3.connect(str(p))
    c.execute("INSERT INTO conversations (id, created_at, updated_at) VALUES ('c1', 't', 't')")
    c.execute(
        "INSERT INTO messages (conversation_id, role, text, timestamp) "
        "VALUES ('c1', 'user', 'hello', 't')"
    )
    c.commit()
    c.close()

    calls = []

    def step(conn):
        calls.append(1)
        conn.execute("CREATE TABLE chat_test_only (x)")

    monkeypatch.setattr(store, "MIGRATIONS", [step])
    monkeypatch.setattr(store, "CHAT_LATEST", store.CHAT_BASELINE + 1)
    conn = store.connect(tmp_path)
    try:
        assert conn.execute("SELECT text FROM messages").fetchall() == [("hello",)]
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='chat_test_only'").fetchone()
    finally:
        conn.close()
    assert calls == [1]
    assert _version(p) == store.CHAT_BASELINE + 1


def test_a_chat_db_below_the_baseline_is_refused(tmp_path):
    from white_words.scriptwriting.chat import store

    store.connect(tmp_path).close()
    p = tmp_path / ".story" / "chat.db"
    c = sqlite3.connect(str(p))
    c.execute("PRAGMA user_version = 0")
    c.close()
    with pytest.raises(SchemaTooOldError, match="older than this build supports"):
        store.connect(tmp_path)
    assert _version(p) == 0


def test_chat_db_from_a_newer_build_is_refused(tmp_path):
    from white_words.scriptwriting.chat import store

    store.connect(tmp_path).close()
    p = tmp_path / ".story" / "chat.db"
    c = sqlite3.connect(str(p))
    c.execute("PRAGMA user_version = 99")
    c.close()
    with pytest.raises(SchemaTooNewError):
        store.connect(tmp_path)
    assert _version(p) == 99
