"""Install and remove the desktop launcher entry (XDG).

The app is a local server, so the launcher starts the server and opens the
browser. Written by the app itself: no flatpak sandbox, no browser install step.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# The XDG identity, which is what the .desktop file and the icon are named after.
# Kept apart from the command that starts the app: renaming the CLI is its own
# change, and until then the entry has to keep pointing at something that exists.
APP_ID = "white-words"
CLI = "white-words"

NAME = "White Words"
GENERIC_NAME = "Story writing"
COMMENT = "Structure-first writing for novels and screenplays."
KEYWORDS = "writing;screenplay;novel;story;"

# The launcher carries the ink-on-paper mark, the alternate of the pair, while the
# browser and PWA keep the white-on-ink primary. It ships as a scalable icon so
# the desktop can pick whatever size it wants without a resample, plus the 512
# raster for themes that only read PNG.
_ICONS = (("scalable", "icon-paper.svg"), ("512x512", "icon-512-paper.png"))


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or "~/.local/share").expanduser()


def _apps_dir() -> Path:
    return _data_home() / "applications"


def _icon_dir(theme_dir: str) -> Path:
    return _data_home() / "icons" / "hicolor" / theme_dir / "apps"


def _exec_line() -> str:
    exe = shutil.which(CLI)
    return exe or f"{sys.executable} -m white_words.scriptwriting.app.launcher"


def _desktop_file() -> str:
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        f"Name={NAME}",
        f"GenericName={GENERIC_NAME}",
        f"Comment={COMMENT}",
        f"Exec={_exec_line()}",
        f"Icon={APP_ID}",
        "Terminal=false",
        "Categories=Office;TextEditor;",
        f"Keywords={KEYWORDS}",
        "StartupNotify=true",
        "",
    ])


def _refresh() -> None:
    try:
        subprocess.run(["update-desktop-database", str(_apps_dir())],
                       capture_output=True, check=False)
    except FileNotFoundError:
        pass                                    # not every system ships it


def install() -> int:
    written = []
    apps = _apps_dir()
    apps.mkdir(parents=True, exist_ok=True)
    entry = apps / f"{APP_ID}.desktop"
    entry.write_text(_desktop_file())
    written.append(entry)

    icons = Path(__file__).resolve().parents[1] / "web" / "icons"
    for theme_dir, name in _ICONS:
        src = icons / name
        if not src.exists():
            print(f"Missing icon: {src}")
            return 1
        dst_dir = _icon_dir(theme_dir)
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / f"{APP_ID}{src.suffix}"
        shutil.copyfile(src, dst)
        written.append(dst)

    _refresh()
    for p in written:
        print(f"Wrote {p}")
    return 0


def uninstall() -> int:
    removed = []
    entry = _apps_dir() / f"{APP_ID}.desktop"
    if entry.exists():
        entry.unlink()
        removed.append(entry)
    for theme_dir, name in _ICONS:
        icon = _icon_dir(theme_dir) / f"{APP_ID}{Path(name).suffix}"
        if icon.exists():
            icon.unlink()
            removed.append(icon)

    _refresh()
    for p in removed:
        print(f"Removed {p}")
    if not removed:
        print("Nothing was installed.")
    return 0
