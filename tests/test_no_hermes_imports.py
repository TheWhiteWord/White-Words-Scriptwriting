import pathlib
import re


def test_no_hermes_imports():
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "white_words" / "scriptwriting"
    for p in root.rglob("*.py"):
        if "adapters/hermes" in str(p).replace("\\", "/"):
            continue
        if p.name == "launcher.py":
            continue
        text = p.read_text()
        assert "hermes" not in text.lower(), f"hermes reference in {p}"
