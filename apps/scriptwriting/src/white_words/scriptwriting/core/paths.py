"""White Words — where the app keeps its own state on disk.

Two locations, and nothing else in the code decides them:

    config dir   ~/.config/white-words/   config.toml, state.json, token, api_key
    data root    ~/white-words/           projects/<slug>/.story/story.db

The config dir follows XDG_CONFIG_HOME; the data root hangs off the home
directory. Both carry the app's name so a person can find them.

Before the rebrand the name was `story-architect`, and an install from that
time has its token, settings and projects in those folders. `migrate_legacy()`
renames them once, so the rename costs the owner nothing: the old folders are
the new folders a moment later. It moves only when the current path is missing
and the old one is there, which makes a second call a no-op and leaves alone
anyone who moved things by hand.
"""
from __future__ import annotations

import os
from pathlib import Path

# The folder name both locations use.
DIR_NAME = "white-words"
LEGACY_DIR_NAME = "story-architect"


def config_base() -> Path:
    """The platform config root: XDG_CONFIG_HOME, else ~/.config."""
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def config_dir() -> Path:
    return config_base() / DIR_NAME


def config_file() -> Path:
    """config.toml: the file that holds port, root and the response budget."""
    return config_dir() / "config.toml"


def data_root() -> Path:
    """The default folder holding `projects/<slug>`."""
    return Path.home() / DIR_NAME


def migrate_legacy(*, include_data_root: bool = True) -> list[tuple[Path, Path]]:
    """Rename the pre-rebrand folders to the current ones, once each.

    Returns the (from, to) pairs that moved. The data root is optional because
    a caller pointed at an explicit root with `--root` is not using the default
    one, and moving a folder of projects it never reads would be rude.
    """
    pairs = [(config_base(), config_dir())]
    if include_data_root:
        pairs.append((Path.home(), data_root()))
    moved: list[tuple[Path, Path]] = []
    for base, current in pairs:
        legacy = base / LEGACY_DIR_NAME
        if current.exists() or not legacy.exists():
            continue
        current.parent.mkdir(parents=True, exist_ok=True)
        legacy.rename(current)
        moved.append((legacy, current))
    return moved
