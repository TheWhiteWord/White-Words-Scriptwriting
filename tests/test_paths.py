"""Where the app keeps its state, and the one-time rename that moves it.

The folders carry the app's name, so the rebrand moved them. These pin the new
locations and the fact that the old ones are carried across exactly once.
"""

from white_words.scriptwriting.core import paths


def test_the_config_dir_follows_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert paths.config_dir() == tmp_path / "white-words"
    assert paths.config_file() == tmp_path / "white-words" / "config.toml"


def test_the_data_root_is_named_after_the_app(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.data_root() == tmp_path / "white-words"


class TestMigration:
    def test_the_old_config_dir_is_carried_across(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        legacy = tmp_path / "story-architect"
        legacy.mkdir()
        (legacy / "token").write_text("secret")

        moved = paths.migrate_legacy(include_data_root=False)

        assert moved == [(legacy, tmp_path / "white-words")]
        assert not legacy.exists()
        assert (tmp_path / "white-words" / "token").read_text() == "secret"

    def test_the_old_data_root_is_carried_across(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        legacy = tmp_path / "story-architect"
        (legacy / "projects" / "save-the-children").mkdir(parents=True)

        moved = paths.migrate_legacy()

        assert moved == [(legacy, tmp_path / "white-words")]
        assert (tmp_path / "white-words" / "projects" / "save-the-children").is_dir()

    def test_an_explicit_root_leaves_the_default_folder_alone(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        legacy = tmp_path / "story-architect"
        legacy.mkdir()

        paths.migrate_legacy(include_data_root=False)

        assert legacy.is_dir()

    def test_it_runs_once(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        (tmp_path / "story-architect").mkdir()

        assert paths.migrate_legacy(include_data_root=False)
        assert paths.migrate_legacy(include_data_root=False) == []

    def test_a_current_folder_wins_over_an_old_one(self, tmp_path, monkeypatch):
        """Both present: the new one is the app's, so nothing is merged or lost."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        (tmp_path / "story-architect").mkdir()
        current = tmp_path / "white-words"
        current.mkdir()
        (current / "state.json").write_text("{}")

        assert paths.migrate_legacy(include_data_root=False) == []
        assert (tmp_path / "story-architect").is_dir()
