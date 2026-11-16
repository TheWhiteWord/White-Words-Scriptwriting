"""The live-update signal: the dashboard's "Project updated" banner.

PRAGMA data_version only changes on a connection that stays open while another
connection commits. The first version of the events route opened a fresh
connection per poll, so the number never moved and the banner never appeared.
"""
import asyncio
import sqlite3
import threading

from story_architect.app.routes.projects import DbChangeWatcher, event_stream


def _make_db(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    w = sqlite3.connect(str(path), isolation_level=None)
    w.execute("PRAGMA journal_mode=WAL")
    w.execute("CREATE TABLE t (x)")
    return w


def test_first_call_is_baseline_not_change(tmp_path):
    db = tmp_path / "s.db"
    w = _make_db(db)
    watcher = DbChangeWatcher(db)
    assert watcher.changed() is False
    w.close()
    watcher.close()


def test_detects_commit_from_another_connection(tmp_path):
    db = tmp_path / "s.db"
    w = _make_db(db)
    watcher = DbChangeWatcher(db)
    watcher.changed()
    assert watcher.changed() is False  # nothing happened
    w.execute("INSERT INTO t VALUES (1)")
    assert watcher.changed() is True
    assert watcher.changed() is False  # reported once
    w.execute("INSERT INTO t VALUES (2)")
    w.execute("INSERT INTO t VALUES (3)")
    assert watcher.changed() is True
    w.close()
    watcher.close()


def test_missing_database_is_quiet_and_not_created(tmp_path):
    db = tmp_path / "nope" / "s.db"
    watcher = DbChangeWatcher(db)
    assert watcher.changed() is False
    assert not db.exists()
    assert not db.parent.exists()


def test_recovers_when_database_appears_later(tmp_path):
    db = tmp_path / "s.db"
    watcher = DbChangeWatcher(db)
    assert watcher.changed() is False
    w = _make_db(db)
    assert watcher.changed() is False  # baseline of the new file
    w.execute("INSERT INTO t VALUES (1)")
    assert watcher.changed() is True
    w.close()
    watcher.close()


def test_reopens_when_file_is_replaced(tmp_path):
    """A backup restored over story.db swaps the file under the watcher."""
    db = tmp_path / "s.db"
    w = _make_db(db)
    w.execute("INSERT INTO t VALUES (1)")
    watcher = DbChangeWatcher(db)
    watcher.changed()
    w.close()

    replacement = tmp_path / "other.db"
    w2 = _make_db(replacement)
    w2.close()
    for suffix in ("", "-wal", "-shm"):
        f = tmp_path / ("s.db" + suffix)
        if f.exists():
            f.unlink()
    replacement.rename(db)

    assert watcher.changed() is False  # new file: baseline, not a false alarm
    w3 = sqlite3.connect(str(db), isolation_level=None)
    w3.execute("INSERT INTO t VALUES (9)")
    assert watcher.changed() is True
    w3.close()
    watcher.close()


class _Request:
    """Stand-in for starlette's Request: disconnects after N polls."""

    def __init__(self, polls):
        self.polls = polls

    async def is_disconnected(self):
        self.polls -= 1
        return self.polls < 0


def test_event_stream_emits_update_frame(tmp_path):
    db = tmp_path / "s.db"
    w = _make_db(db)
    watcher = DbChangeWatcher(db)

    async def run():
        frames = []

        def write_later():
            import time
            time.sleep(0.05)
            c = sqlite3.connect(str(db), isolation_level=None)  # own connection
            c.execute("INSERT INTO t VALUES (1)")
            c.close()

        t = threading.Thread(target=write_later)
        t.start()
        async for frame in event_stream(watcher, _Request(polls=15), interval=0.02):
            frames.append(frame)
        t.join()
        return frames

    frames = asyncio.run(run())
    assert frames, "no update event was emitted"
    assert frames[0].startswith("event: update\n")
    assert '"type": "update"' in frames[0]
    assert watcher._conn is None  # closed when the stream ended
    w.close()


def test_event_stream_silent_without_changes(tmp_path):
    db = tmp_path / "s.db"
    w = _make_db(db)

    async def run():
        return [f async for f in event_stream(
            DbChangeWatcher(db), _Request(polls=5), interval=0.01)]

    assert asyncio.run(run()) == []
    w.close()
