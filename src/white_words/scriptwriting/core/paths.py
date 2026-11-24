"""White Words — where the app keeps its state on disk.

Two locations, and nothing else in the code decides them:

    config dir   ~/.config/white-words/      config.toml, state.json, token, api_key
    data root    ~/white-words-studio/       projects/<slug>/.story/story.db

They are named differently on purpose. The config dir belongs to this app: a
token, a port, a response budget. The data root belongs to the family: it holds
the projects themselves, so another White Words app can open the same ones.
That is why the studio name lives here and nowhere else — the writer sees it as
the folder where their writing is, not as a product they installed.

The config dir follows XDG_CONFIG_HOME; the data root hangs off the home
directory.
"""
from __future__ import annotations

import os
from pathlib import Path

CONFIG_DIR_NAME = "white-words"
DATA_DIR_NAME = "white-words-studio"


def config_base() -> Path:
    """The platform config root: XDG_CONFIG_HOME, else ~/.config."""
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def config_dir() -> Path:
    return config_base() / CONFIG_DIR_NAME


def config_file() -> Path:
    """config.toml: the file that holds port, root and the response budget."""
    return config_dir() / "config.toml"


def data_root() -> Path:
    """The default folder holding `projects/<slug>`, shared by the family."""
    return Path.home() / DATA_DIR_NAME
