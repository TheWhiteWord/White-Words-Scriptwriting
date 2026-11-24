"""Small UI-writable settings store (state.json next to config.toml)."""
from __future__ import annotations
import json
from pathlib import Path

from white_words.scriptwriting.core import paths

def state_file() -> Path:
    return paths.config_dir() / "state.json"

def load_state() -> dict:
    p = state_file()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}

def save_state(patch: dict) -> dict:
    p = state_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    cur = load_state()
    cur.update(patch)
    p.write_text(json.dumps(cur))
    return cur