"""`story-architect seed-demo` must leave a project that opens."""
from story_architect.app.launcher import main
from story_architect.core.db import LATEST_VERSION, get_db


def test_seed_demo_creates_an_openable_project(tmp_path, capsys):
    root = tmp_path / "root"

    assert main(["seed-demo", "--root", str(root)]) == 0
    proj = root / "projects" / "demo"
    conn = get_db(proj)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_VERSION
        row = conn.execute(
            "SELECT name FROM entities WHERE type='project'").fetchone()
        assert row[0] == "Demo"
    finally:
        conn.close()

    # A second run is a no-op, not an error.
    assert main(["seed-demo", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "already exists" in out
