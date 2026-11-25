"""Task 5 asset tests."""

import re
from pathlib import Path

import yaml

from white_words.scriptwriting.app.mcp_server import build_registry

APP = Path(__file__).resolve().parents[1]
ASSETS = APP / "src" / "white_words" / "scriptwriting" / "adapters" / "hermes" / "assets"
SOUL = ASSETS / "SOUL.md"
SKILL = ASSETS / "skills/ww-scriptwriter/SKILL.md"


def test_soul_has_marker():
    text = SOUL.read_text()
    assert "<!-- ww-scriptwriter adapter -->" in text


def test_skill_frontmatter_parses():
    text = SKILL.read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "no frontmatter"
    fm = yaml.safe_load(m.group(1))
    assert fm["name"] == "ww-scriptwriter"
    assert "description" in fm


def test_skill_tool_names_exist_in_registry():
    text = SKILL.read_text()
    reg_names = {n for n, _, _ in build_registry()}
    # collect the comma-separated tool list line
    m = re.search(r"^admin, backup,.*search\.$", text, re.M)
    assert m
    names = [
        x.strip().rstrip(".")
        for x in re.split(r"[,\s]+", m.group(0))
        if x.strip() and not x.startswith("#")
    ]
    for n in names:
        assert n in reg_names, f"{n} not in registry"
