"""Read the history manifest for a listing, without creating or migrating one.

The landing page asks about every project under the root, including ones this
feature has never touched. `connect()` creates `history.db` and runs its schema,
so a listing that used it would write during a read — and `list_branches` would
then report a branchless manifest as if the project had no history, which is a
different fact. This reads an existing manifest only.

Nothing here adopts: a project with no manifest is simply a project with no
history, and the first real history operation creates one.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .store import history_path


def summary(project_path: Path) -> dict:
    """A project's current draft, branch count and last save, or the four empties.

    `changes_since_save` is a COUNT of the items that differ from the current
    branch's saved draft, not the boolean `store.head_state` reports: the landing
    page shows "N changes since Draft 3", and a clean head is the count 0. A dirty
    head costs one draft copy and one diff; a clean head costs one fingerprint.
    """
    empty = {
        "current_draft": None,
        "branch_count": 0,
        "last_saved": None,
        "changes_since_save": 0,
    }
    path = history_path(project_path)
    if not path.exists():
        return empty

    # mode=ro: opening a manifest must never create one, and a listing is a read.
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        current = conn.execute(
            "SELECT id, base_snapshot_id FROM branches WHERE is_current=1"
        ).fetchone()
        if current is None:
            return empty
        count = conn.execute("SELECT count(*) FROM branches").fetchone()[0]
        base = conn.execute(
            "SELECT label, created_at FROM snapshots WHERE id=?", (current[1],)
        ).fetchone()
    except sqlite3.Error:
        # A manifest this build cannot read is not a reason to fail the listing.
        return empty
    finally:
        conn.close()

    return {
        **empty,
        "branch_count": count,
        "current_draft": base[0] if base else None,
        "last_saved": base[1] if base else None,
        "changes_since_save": _changes(project_path, current[1] if base else None),
    }


def _changes(project_path: Path, base_snapshot_id: str | None) -> int:
    """How many items differ from the current branch's saved draft."""
    if base_snapshot_id is None:
        return 0
    from . import diff, fingerprint
    from .view import project_view

    if fingerprint.of_project(project_path) == _base_fingerprint(
        project_path, base_snapshot_id
    ):
        return 0
    with project_view(project_path, base_snapshot_id) as base:
        return len(diff.compare(base, project_path)["items"])


def _base_fingerprint(project_path: Path, snapshot_id: str) -> str | None:
    """The saved draft's own fingerprint, read from the manifest."""
    conn = sqlite3.connect(f"file:{history_path(project_path)}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT fingerprint FROM snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()
