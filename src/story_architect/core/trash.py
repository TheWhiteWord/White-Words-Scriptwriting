"""The trash: who was deleted together, and removing them for good.

A delete only flags rows (core/writes.py), so everything here works on rows that
are flagged `is_deleted=1`. `deleted_together` is the one definition of "deleted
in the same operation", shared by restore and purge. `purge_deleted` is the only
irreversible entity operation; it is reached through an approved draft
(core/drafts.py), never on the agent's word alone.
"""
from __future__ import annotations

from pathlib import Path


def purge_cutoff(days: int) -> str:
    """ISO timestamp: entities deleted at or before it are old enough to purge."""
    from datetime import datetime, timedelta
    return (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")


def select_one_deletion(conn, target: dict):
    """The rows a targeted purge removes: the entity and what was deleted with it.

    Returns (rows, None), or (None, refusal) when the target is not something
    that may be purged. "Deleted with it" is the same test list_deleted uses: a
    child of the target carrying the target's own deletion stamp. A child that
    was deleted separately keeps its own entry and stays in the trash.
    """
    entity_id = target.get("id") or ""
    entity_type = target.get("entity_type") or ""
    row = conn.execute(
        "SELECT id, type, deleted_at, is_deleted FROM entities WHERE id=?",
        (entity_id,)).fetchone()
    if not row:
        return None, {"error": f"Entity not found: {entity_type}/{entity_id}"}
    if entity_type and entity_type != row[1]:
        return None, {"error": f"{row[0]} is a {row[1]}, not a {entity_type}. "
                               f"Nothing was purged."}
    if not row[3]:
        return None, {
            "error": f"{row[0]} is not in the trash — purge only removes entities "
                     f"that are already deleted. Nothing was purged.",
            "entity_id": row[0],
        }
    return [(row[0], row[1], row[2])] + deleted_together(conn, row[0], row[2]), None


def deleted_together(conn, entity_id: str, deleted_at) -> list:
    """The children that were deleted in the same operation as `entity_id`.

    One rule, used by restore, by targeted purge and (as a Python grouping) by
    list_deleted: a child in the trash whose deletion stamp equals the parent's.
    A child deleted on its own, earlier or later, carries another stamp and is a
    separate item in the trash.

    `IS ?` rather than `= ?` so that a row with no deletion time (deleted by an
    earlier build) still matches its own, equally unstamped, children.
    Returns (id, type, deleted_at) rows.
    """
    return conn.execute(
        "SELECT id, type, deleted_at FROM entities "
        "WHERE parent_id=? AND is_deleted=1 AND deleted_at IS ? ORDER BY type, id",
        (entity_id, deleted_at)).fetchall()


def hard_delete(conn, ids: list) -> None:
    """Remove entities and everything that hangs off them. Inside a transaction.

    Anything else still pointing at one of them as its parent or location (a
    trashed child that was deleted separately) loses that link; a link to a row
    that no longer exists is worse than none.
    """
    marks = ",".join("?" * len(ids))
    conn.execute(f"DELETE FROM sections WHERE entity_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM revisions WHERE entity_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM relations WHERE from_id IN ({marks}) "
                 f"OR to_id IN ({marks})", ids + ids)
    conn.execute(f"DELETE FROM entities WHERE id IN ({marks})", ids)
    conn.execute(f"UPDATE entities SET parent_id='' WHERE parent_id IN ({marks})", ids)
    conn.execute(f"UPDATE entities SET location_id='' WHERE location_id IN ({marks})", ids)


def select_for_purge(conn, target: dict | None, older_than_days: int):
    """What a purge would remove: (rows of id, type, deleted_at, refusal).

    Shared by the purge itself and by the preview the person approves, so the
    card can never describe a different set from the one that goes.
    """
    if target:
        return select_one_deletion(conn, target)
    rows = conn.execute(
        "SELECT id, type, deleted_at FROM entities "
        "WHERE is_deleted=1 AND deleted_at IS NOT NULL AND deleted_at <= ? "
        "ORDER BY type, id", (purge_cutoff(older_than_days),)).fetchall()
    return rows, None


def preview_purge(project_path: Path, target: dict | None = None,
                  older_than_days: int = 30) -> dict:
    """What `purge_deleted` would remove, read-only: {items, refusal}.

    Each item is {id, type, name, deleted_at}; `refusal` is the error dict a purge
    of this target would return (a live entity, an unknown id), or None.
    """
    from story_architect.core.db import get_db

    conn = get_db(project_path)
    try:
        rows, refusal = select_for_purge(conn, target, older_than_days)
        if refusal:
            return {"items": [], "refusal": refusal}
        names = {r[0]: r[1] for r in conn.execute(
            f"SELECT id, name FROM entities WHERE id IN ({','.join('?' * len(rows))})",
            [r[0] for r in rows])} if rows else {}
        return {"items": [{"id": r[0], "type": r[1], "name": names.get(r[0]) or r[0],
                           "deleted_at": r[2]} for r in rows], "refusal": None}
    finally:
        conn.close()


def purge_deleted(project_path: Path, target: dict | None = None,
                  older_than_days: int = 30) -> dict:
    """Remove deleted entities for good. The ONLY irreversible entity operation.

    * no `target` — everything deleted more than `older_than_days` ago (default
      30). The age floor means tidying up can never destroy a fresh mistake.
    * `target` {entity_type, id} — exactly that one entity, plus whatever was
      deleted along with it. The age floor does not apply: naming one item is
      the opposite of a sweep. It must already be in the trash; a live entity
      is refused.

    There is no confirmation here: the person's approval is the draft they
    approve in the app (core/drafts.py, op "purge"), and a backup is taken
    first, so even this is recoverable by hand.
    """
    from story_architect.core.backups import create_backup
    from story_architect.core.db import get_db, transaction

    cutoff = purge_cutoff(older_than_days)

    conn = get_db(project_path)
    try:
        # Selecting what to purge and deleting it are one transaction: the
        # deletes below must land together, or a stop part-way leaves entities
        # with no sections, or sections with no entity.
        with transaction(conn):
            rows, refusal = select_for_purge(conn, target, older_than_days)
            if refusal:
                return refusal
            if not rows:
                younger = conn.execute(
                    "SELECT count(*) FROM entities WHERE is_deleted=1").fetchone()[0]
                return {
                    "success": True,
                    "purged": [],
                    "message": (
                        f"Nothing is old enough to purge ({younger} deleted entities are "
                        f"younger than {older_than_days} days). They stay restorable."),
                }

            ids = [r[0] for r in rows]
            backup = create_backup(project_path, automatic=True)
            hard_delete(conn, ids)
    finally:
        conn.close()

    return {
        "success": True,
        "message": f"Purged {len(ids)} entities permanently.",
        "purged": [{"id": r[0], "type": r[1], "deleted_at": r[2]} for r in rows],
        "backup": backup,
        "note": ("Markdown files for these entities are removed by the next "
                 "story_export."),
    }
