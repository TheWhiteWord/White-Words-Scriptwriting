"""A backup is taken when a project is opened, at most once a day, only if it changed."""
import logging
import os
import re
import shutil
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from story_architect.core import backups
from story_architect.core.backups import (create_backup, list_backups,
                                          maybe_periodic_backup)
from story_architect.core.writes import edit_entity


@pytest.fixture
def fixture_path(fixture_path):
    """The shared fixture project, minus the backups that building it left behind."""
    for f in (fixture_path / ".story").glob("story_*.db"):
        f.unlink()
    return fixture_path


def _automatic(project):
    return [b for b in list_backups(project) if b["kind"] == "automatic"]


def _age_backups(project, delta: timedelta):
    """Make every backup look `delta` older (the time lives in the file name)."""
    for f in (project / ".story").glob("story_*.db"):
        m = re.match(r"^(story(?:_auto)?_)(\d{8}_\d{6})(.*)$", f.name)
        old = datetime.strptime(m[2], "%Y%m%d_%H%M%S") - delta
        f.rename(f.with_name(m[1] + old.strftime("%Y%m%d_%H%M%S") + m[3]))


def _make_db_look_untouched_for(project, days):
    long_ago = datetime.now().timestamp() - days * 86400
    for name in ("story.db", "story.db-wal"):
        f = project / ".story" / name
        if f.exists():
            os.utime(f, (long_ago, long_ago))


# ─── the rule ───

def test_the_first_open_takes_a_backup(fixture_path):
    path = maybe_periodic_backup(fixture_path)
    assert path and Path(path).exists()
    assert [b["kind"] for b in list_backups(fixture_path)] == ["automatic"]


def test_a_second_open_the_same_day_takes_none(fixture_path):
    """Even when the project has clearly changed since (the backup is an hour old
    and the edit is now), a day has not passed."""
    maybe_periodic_backup(fixture_path)
    _age_backups(fixture_path, timedelta(hours=1))
    edit_entity(fixture_path, "character", "kael", {"name": "Changed"}, "x")
    assert maybe_periodic_backup(fixture_path) is None
    assert len(_automatic(fixture_path)) == 1


def test_a_day_later_it_backs_up_if_the_project_changed(fixture_path):
    maybe_periodic_backup(fixture_path)
    _age_backups(fixture_path, timedelta(days=2))
    edit_entity(fixture_path, "character", "kael", {"name": "Changed since"}, "x")
    assert maybe_periodic_backup(fixture_path)
    assert len(_automatic(fixture_path)) == 2


def test_a_day_later_it_does_not_if_nothing_changed(fixture_path):
    maybe_periodic_backup(fixture_path)
    _age_backups(fixture_path, timedelta(days=2))
    _make_db_look_untouched_for(fixture_path, days=5)
    assert maybe_periodic_backup(fixture_path) is None
    assert len(_automatic(fixture_path)) == 1


def test_opening_a_project_every_day_without_editing_never_piles_up_copies(fixture_path):
    for day in range(10):
        maybe_periodic_backup(fixture_path, now=datetime.now() + timedelta(days=day + 1))
        _age_backups(fixture_path, timedelta(days=1))
        _make_db_look_untouched_for(fixture_path, days=30)
    assert len(_automatic(fixture_path)) <= 1


def test_its_own_checkpoint_does_not_make_the_next_one_look_needed(fixture_path):
    """Taking a backup can touch story.db a moment later; that is not a change."""
    maybe_periodic_backup(fixture_path)
    backup = _automatic(fixture_path)[0]
    taken = datetime.fromisoformat(backup["created_at"])
    # the database touched 2 s after the backup was stamped: inside the slack
    t = (taken + timedelta(seconds=2)).timestamp()
    for name in ("story.db", "story.db-wal"):
        f = fixture_path / ".story" / name
        if f.exists():
            os.utime(f, (t, t))
    assert maybe_periodic_backup(fixture_path, now=taken + timedelta(days=3)) is None


def test_a_manual_backup_does_not_stand_in_for_the_daily_one(fixture_path):
    create_backup(fixture_path, label="mine")
    assert maybe_periodic_backup(fixture_path)
    assert [b["kind"] for b in list_backups(fixture_path)].count("automatic") == 1


def test_a_project_without_a_database_is_left_alone(tmp_path):
    (tmp_path / ".story").mkdir()
    assert maybe_periodic_backup(tmp_path) is None
    assert list((tmp_path / ".story").iterdir()) == []


def test_the_cap_still_applies(fixture_path, monkeypatch):
    monkeypatch.setattr(backups, "AUTO_BACKUPS_KEPT", 3)
    for day in range(6):
        edit_entity(fixture_path, "character", "kael", {"name": f"v{day}"}, "x")
        _age_backups(fixture_path, timedelta(days=2))
        maybe_periodic_backup(fixture_path, now=datetime.now() + timedelta(days=day))
    assert len(_automatic(fixture_path)) == 3


def test_several_simultaneous_opens_make_one_backup(fixture_path):
    results = []
    gate = threading.Barrier(8)

    def worker():
        gate.wait()
        results.append(maybe_periodic_backup(fixture_path))

    ts = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len([r for r in results if r]) == 1
    assert len(_automatic(fixture_path)) == 1


# ─── the hook: opening a project in the web app ───

@pytest.fixture
def web(tmp_path, fixture_path, monkeypatch):
    from fastapi.testclient import TestClient
    from story_architect.app.config import Config
    from story_architect.app.server import create_app

    monkeypatch.setattr("story_architect.app.token.load_api_key", lambda: "k")
    root = tmp_path / "vault"
    shutil.copytree(str(fixture_path), str(root / "projects" / "stc"))
    c = TestClient(create_app(Config(root=root)), base_url="http://127.0.0.1:8731")
    c.headers.update({"X-Story-Architect": "1"})
    c.root = root
    return c


def test_opening_the_dashboard_takes_the_backup(web):
    proj = web.root / "projects" / "stc"
    assert _automatic(proj) == []
    r = web.get("/api/projects/stc/dashboard")
    assert r.status_code == 200
    assert len(_automatic(proj)) == 1
    web.get("/api/projects/stc/dashboard")
    assert len(_automatic(proj)) == 1            # not again the same day


def test_an_unknown_project_makes_nothing(web):
    r = web.get("/api/projects/no-such-film/dashboard")
    assert r.status_code == 404
    assert not (web.root / "projects" / "no-such-film").exists()


def test_a_failing_backup_never_breaks_the_page(web, monkeypatch, caplog):
    def boom(project_path):
        raise OSError("disk full")
    monkeypatch.setattr(backups, "maybe_periodic_backup", boom)
    with caplog.at_level(logging.WARNING):
        r = web.get("/api/projects/stc/dashboard")
    assert r.status_code == 200 and r.json()
    assert "periodic backup of stc failed" in caplog.text


def test_a_slug_with_a_path_in_it_is_not_followed(tmp_path):
    """root/projects/../outside is tmp_path/outside: a real project, but not one
    the slug may reach."""
    from story_architect.app.routes.projects import periodic_backup
    outside = tmp_path / "outside"
    (outside / ".story").mkdir(parents=True)
    c = sqlite3.connect(str(outside / ".story" / "story.db"))
    c.execute("CREATE TABLE entities (id TEXT)")
    c.commit()
    c.close()
    (tmp_path / "projects").mkdir()
    periodic_backup(tmp_path, "../outside")
    assert not list((outside / ".story").glob("story_*.db"))
