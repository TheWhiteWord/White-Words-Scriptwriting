"""What the branch graph draws: branches, drafts, parents, and each head's tip.

`store.list_branches` is nearly the whole payload — branches with `is_current`, and
drafts with `parents`. What it cannot say is where each branch's WORKING state sits
relative to its last saved draft, because only the current branch's head is a
project path: every other branch's head is a parked file, and answering for it
costs a copy of that file.

So this is the one place that pays for all of them, and the landing-page listing
(which pays for nothing) does not use it.
"""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path

from . import diff, fingerprint, store, view

# §7.9's cherry-pick records no parent, and a "picked from" edge is in the session
# rows instead: an applied session's source is what the dashed edge points at.
_PICKED = "SELECT target_branch_id, source_ref FROM merge_sessions WHERE status='applied'"


def summary(project_path: Path) -> dict:
    """Branches, drafts and per-branch tips. Never adopts: a project with no
    manifest has no graph, and a read must not create one."""
    if not store.history_path(project_path).exists():
        return {"branches": [], "snapshots": [], "current": None, "picked_from": []}

    listed = store.list_branches(project_path)
    tips = {
        branch["id"]: _tip(project_path, branch, listed["snapshots"])
        for branch in listed["branches"]
    }

    return {
        **listed,
        "current": next((b["id"] for b in listed["branches"] if b["is_current"]), None),
        "head": tips,
        "picked_from": _picked_from(project_path),
    }


def _tip(project_path: Path, branch: dict, saved: list[dict]) -> dict:
    """One branch's head: its saved draft, whether it moved, and by how many items.

    A clean head costs one fingerprint. A dirty one costs a copy of the head and a
    diff — 11 ms for the live database, 20 ms for a parked file on the fixture.
    """
    base = next((s for s in saved if s["id"] == branch["base_snapshot_id"]), None)
    if base is None:
        return {"draft": None, "changed": False, "changes": 0}

    with ExitStack() as stack:
        head = (
            project_path
            if branch["is_current"]
            else stack.enter_context(view.head_view(project_path, branch["id"]))
        )
        if fingerprint.of_project(head) == base["fingerprint"]:
            return {"draft": base, "changed": False, "changes": 0}
        saved_view = stack.enter_context(view.project_view(project_path, base["id"]))
        return {
            "draft": base,
            "changed": True,
            "changes": len(diff.compare(saved_view, head)["items"]),
        }


def _picked_from(project_path: Path) -> list[dict]:
    """Applied cherry-picks: the dashed "picked from" edges (§7.9)."""
    import json
    import sqlite3

    conn = sqlite3.connect(f"file:{store.history_path(project_path)}?mode=ro", uri=True)
    try:
        return [
            {"branch": branch, "source": json.loads(source_ref)}
            for branch, source_ref in conn.execute(_PICKED)
        ]
    except sqlite3.Error:
        return []
    finally:
        conn.close()
