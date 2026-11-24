"""core.db.transaction: the one way to make a multi-statement write atomic."""
import sqlite3
import threading

import pytest

from white_words.scriptwriting.core.db import get_db, transaction


@pytest.fixture
def conn(tmp_path):
    c = get_db(tmp_path)
    c.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)")
    yield c
    c.close()


def _rows(c):
    return c.execute("SELECT id, v FROM t ORDER BY id").fetchall()


def test_commits_on_normal_exit(conn):
    with transaction(conn):
        conn.execute("INSERT INTO t VALUES (1, 10)")
        assert conn.in_transaction
    assert not conn.in_transaction
    assert _rows(conn) == [(1, 10)]


def test_rolls_back_and_reraises_the_original_error(conn):
    with pytest.raises(ValueError, match="mine"):
        with transaction(conn):
            conn.execute("INSERT INTO t VALUES (1, 10)")
            raise ValueError("mine")
    assert not conn.in_transaction
    assert _rows(conn) == []


def test_return_inside_the_block_commits(conn):
    def f():
        with transaction(conn):
            conn.execute("INSERT INTO t VALUES (1, 10)")
            return "early"
    assert f() == "early"
    assert not conn.in_transaction
    assert _rows(conn) == [(1, 10)]


def test_original_error_survives_when_sqlite_already_ended_the_transaction(conn):
    """The case the old hand-written cleanup had to guard against: the
    transaction is already gone when the handler runs, and a blind ROLLBACK
    would raise and hide the real error."""
    with pytest.raises(ValueError, match="mine"):
        with transaction(conn):
            conn.execute("INSERT INTO t VALUES (1, 10)")
            conn.execute("ROLLBACK")
            raise ValueError("mine")
    assert _rows(conn) == []


def test_failed_statement_rolls_back_earlier_statements(conn):
    conn.execute("INSERT INTO t VALUES (1, 10)")
    with pytest.raises(sqlite3.IntegrityError):
        with transaction(conn):
            conn.execute("INSERT INTO t VALUES (2, 20)")
            conn.execute("INSERT INTO t VALUES (1, 99)")  # duplicate key
    assert _rows(conn) == [(1, 10)]


def test_connection_is_usable_after_a_failure(conn):
    with pytest.raises(RuntimeError):
        with transaction(conn):
            conn.execute("INSERT INTO t VALUES (1, 10)")
            raise RuntimeError
    with transaction(conn):
        conn.execute("INSERT INTO t VALUES (2, 20)")
    assert _rows(conn) == [(2, 20)]


# ─── nesting ───

def test_nested_failure_undoes_only_the_inner_block(conn):
    with transaction(conn):
        conn.execute("INSERT INTO t VALUES (1, 10)")
        with pytest.raises(ValueError):
            with transaction(conn):
                conn.execute("INSERT INTO t VALUES (2, 20)")
                raise ValueError
        assert conn.in_transaction  # outer still open
        conn.execute("INSERT INTO t VALUES (3, 30)")
    assert _rows(conn) == [(1, 10), (3, 30)]


def test_outer_failure_undoes_a_committed_inner_block(conn):
    with pytest.raises(ValueError):
        with transaction(conn):
            with transaction(conn):
                conn.execute("INSERT INTO t VALUES (1, 10)")
            raise ValueError
    assert _rows(conn) == []
    assert not conn.in_transaction


def test_deeply_nested(conn):
    with transaction(conn):
        with transaction(conn):
            with transaction(conn):
                conn.execute("INSERT INTO t VALUES (1, 10)")
    assert _rows(conn) == [(1, 10)]


# ─── locking ───

def test_holds_the_write_lock_from_the_first_statement(conn, tmp_path):
    """BEGIN IMMEDIATE: a second writer is shut out as soon as the block opens,
    while readers carry on (WAL)."""
    other = get_db(tmp_path)
    other.execute("PRAGMA busy_timeout=0")
    try:
        with transaction(conn):
            assert other.execute("SELECT count(*) FROM t").fetchone()[0] == 0
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                other.execute("INSERT INTO t VALUES (99, 99)")
        other.execute("INSERT INTO t VALUES (99, 99)")  # free again afterwards
    finally:
        other.close()


def test_read_modify_write_from_two_writers_never_loses_or_fails(tmp_path):
    """Check-then-write, the pattern edit_entity uses. With a plain BEGIN, the
    second writer to commit hits 'database is locked' immediately (busy_timeout
    does not apply to an upgrade from reader to writer). With the lock taken up
    front, writers queue and every increment lands."""
    seed = get_db(tmp_path)
    seed.execute("CREATE TABLE counter (id INTEGER PRIMARY KEY, n INTEGER)")
    seed.execute("INSERT INTO counter VALUES (1, 0)")
    seed.close()

    errors = []

    def worker():
        c = get_db(tmp_path)  # connections are per thread
        try:
            for _ in range(25):
                with transaction(c):
                    n = c.execute("SELECT n FROM counter WHERE id=1").fetchone()[0]
                    c.execute("UPDATE counter SET n=? WHERE id=1", (n + 1,))
        except Exception as e:  # pragma: no cover - only on failure
            errors.append(e)
        finally:
            c.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    check = get_db(tmp_path)
    try:
        assert errors == []
        assert check.execute("SELECT n FROM counter WHERE id=1").fetchone()[0] == 100
    finally:
        check.close()
