"""`white-words seed-demo` must leave a project that opens, and `--restore` must reset it."""

import sqlite3

from white_words.scriptwriting.app.launcher import main
from white_words.scriptwriting.core.db import LATEST_VERSION, get_db


def _count_scenes(proj):
    conn = sqlite3.connect(str(proj / ".story" / "story.db"))
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM entities WHERE type='scene' AND is_deleted=0"
        ).fetchone()[0]
    finally:
        conn.close()


def test_seed_demo_creates_an_openable_project(tmp_path, capsys):
    root = tmp_path / "root"

    assert main(["seed-demo", "--root", str(root)]) == 0
    proj = root / "projects" / "demo"
    conn = get_db(proj)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_VERSION
        row = conn.execute("SELECT name FROM entities WHERE type='project'").fetchone()
        assert row[0] == "The Wizard of Oz"
    finally:
        conn.close()

    # The bundle carries the story, not just a project row.
    assert _count_scenes(proj) == 14

    # The history comes with it: ten drafts, four branches, one merge left open.
    from white_words.scriptwriting.core.history import store

    assert len(store.list_branches(proj)["snapshots"]) == 10

    # A second run is a no-op, not an error, and says how to reset.
    assert main(["seed-demo", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "already exists" in out
    assert "--restore" in out


def test_restore_resets_a_changed_demo(tmp_path):
    root = tmp_path / "root"
    assert main(["seed-demo", "--root", str(root)]) == 0
    proj = root / "projects" / "demo"

    # Mangle it the way a user would: delete the scenes, rename the project.
    conn = sqlite3.connect(str(proj / ".story" / "story.db"))
    try:
        conn.execute("DELETE FROM entities WHERE type='scene'")
        conn.execute("UPDATE entities SET name='Mine' WHERE type='project'")
        conn.commit()
    finally:
        conn.close()
    assert _count_scenes(proj) == 0

    assert main(["seed-demo", "--root", str(root), "--restore"]) == 0
    assert _count_scenes(proj) == 14
    conn = get_db(proj)
    try:
        assert (
            conn.execute("SELECT name FROM entities WHERE type='project'").fetchone()[0]
            == "The Wizard of Oz"
        )
    finally:
        conn.close()


def test_restore_brings_back_a_deleted_demo(tmp_path):
    import shutil

    root = tmp_path / "root"
    assert main(["seed-demo", "--root", str(root)]) == 0
    proj = root / "projects" / "demo"
    shutil.rmtree(proj)
    assert not proj.exists()

    assert main(["seed-demo", "--root", str(root), "--restore"]) == 0
    assert _count_scenes(proj) == 14


def test_a_new_root_gets_the_demo_on_first_launch(tmp_path, monkeypatch):
    """A fresh install must find the demo without being told to seed it."""
    import white_words.scriptwriting.app.launcher as launcher

    root = tmp_path / "fresh"
    # Stop the launcher after the root is prepared: the server is not what is under test.
    monkeypatch.setattr(launcher, "is_healthy", lambda port: True)

    assert launcher.main(["--root", str(root), "--no-open"]) == 0
    assert _count_scenes(root / "projects" / "demo") == 14


def test_a_deleted_demo_stays_deleted_on_relaunch(tmp_path, monkeypatch):
    """Deleting it is a decision, not a gap to be filled on next launch."""
    import shutil

    import white_words.scriptwriting.app.launcher as launcher

    root = tmp_path / "root"
    assert launcher.main(["seed-demo", "--root", str(root)]) == 0
    shutil.rmtree(root / "projects" / "demo")

    monkeypatch.setattr(launcher, "is_healthy", lambda port: True)
    assert launcher.main(["--root", str(root), "--no-open"]) == 0
    assert not (root / "projects" / "demo").exists()
