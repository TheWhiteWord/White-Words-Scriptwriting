"""Where the app keeps its state: per-app config, family-wide projects.

The two names differ on purpose and these pin it, because getting it wrong is
silent — the app would simply start with an empty project list.
"""

from white_words.scriptwriting.core import paths


def test_the_config_dir_follows_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert paths.config_dir() == tmp_path / "white-words"
    assert paths.config_file() == tmp_path / "white-words" / "config.toml"


def test_the_data_root_is_the_studio(monkeypatch, tmp_path):
    """The projects folder is the family's, so it carries the studio name."""
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.data_root() == tmp_path / "white-words-studio"


def test_a_project_lands_under_the_studio(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.data_root() / "projects" / "save-the-children" == (
        tmp_path / "white-words-studio" / "projects" / "save-the-children"
    )
