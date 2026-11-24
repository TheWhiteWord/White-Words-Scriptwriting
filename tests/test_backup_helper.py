"""backup_database: one function, atomic, with an optional destination."""
import re
import sqlite3
import threading
from pathlib import Path

import pytest

from white_words.scriptwriting.core import db as core_db
from white_words.scriptwriting.core.db import backup_database
from white_words.scriptwriting.core.writes import create_project


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "v"
    (root / "projects").mkdir(parents=True)
    create_project("stc", {"name": "STC", "logline": "L"}, root)
    return root / "projects" / "stc"


def _entity_count(db_file):
    c = sqlite3.connect(str(db_file))
    try:
        return c.execute("SELECT count(*) FROM entities").fetchone()[0]
    finally:
        c.close()


def test_default_destination_and_name(project):
    path = Path(backup_database(project))
    assert path.parent == project / ".story"
    assert re.fullmatch(r"story_\d{8}_\d{6}_\w+\.db", path.name), path.name
    assert _entity_count(path) == _entity_count(project / ".story" / "story.db")


def test_destination_and_prefix(project, tmp_path):
    dest = tmp_path / "elsewhere" / "deeper"   # does not exist yet
    path = Path(backup_database(project, dest_dir=dest, prefix="stc"))
    assert path.parent == dest
    assert path.name.startswith("stc_") and path.suffix == ".db"
    assert _entity_count(path) > 0


def test_nothing_but_the_backup_is_left_behind(project, tmp_path):
    """No .partial file, no -wal / -shm sidecar from the copy."""
    dest = tmp_path / "out"
    path = Path(backup_database(project, dest_dir=dest))
    assert [p.name for p in dest.iterdir()] == [path.name]


def test_a_failed_snapshot_leaves_no_file(project, tmp_path, monkeypatch):
    """A crash or full disk mid-copy must not leave something that looks like a backup."""
    real_get_db = core_db.get_db

    class BreaksMidCopy:
        def __init__(self, conn):
            self._conn = conn

        def backup(self, target):
            target.execute("CREATE TABLE half_written (x)")  # something was written...
            raise OSError("disk full")                        # ...then it failed

        def close(self):
            self._conn.close()

    monkeypatch.setattr(core_db, "get_db", lambda p: BreaksMidCopy(real_get_db(p)))
    dest = tmp_path / "out"
    with pytest.raises(OSError, match="disk full"):
        backup_database(project, dest_dir=dest)
    assert list(dest.iterdir()) == []


def test_concurrent_backups_never_collide(project, tmp_path):
    dest = tmp_path / "out"
    made, errors = [], []

    def worker():
        try:
            made.append(backup_database(project, dest_dir=dest))
        except Exception as e:  # pragma: no cover - only on failure
            errors.append(e)

    ts = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert errors == []
    assert len(set(made)) == 8
    assert sorted(p.name for p in dest.iterdir()) == sorted(Path(m).name for m in made)
    assert all(_entity_count(m) > 0 for m in made)
