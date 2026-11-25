"""Version history for section text: what a scene said before it was changed.

Every write of a section body goes through ``edit_entity`` (the agent's draft
commits and the script editor's Save alike), which calls
:func:`snapshot_replaced_body` just before it overwrites. The table therefore
holds the *replaced* versions; the current one is still in ``sections``. Listing
a scene's history is "now" plus these, newest first.

Restoring a revision is itself an ordinary edit, so it snapshots what it
replaces: a restore can always be undone by restoring again.

Not covered: the structured fields of an entity (a scene's heading parts, its
cast, status). They change often and are small; this is the *text*. Not
touched by the Markdown import either, which rebuilds sections wholesale after
taking a full backup of its own.
"""

from . import clock
from pathlib import Path

# How many replaced versions to keep per (entity, section). The script editor
# saves on demand, not automatically, so every distinct save is worth keeping;
# 50 leaves room for a heavy revision session without losing yesterday's text.
REVISIONS_KEPT = 50


def snapshot_replaced_body(
    conn, entity_id: str, heading: str, new_body: str, summary: str = ""
) -> bool:
    """Keep the current body of a section before it is overwritten with new_body.

    Call it inside the write's transaction, before the UPDATE. Returns whether a
    revision was kept. Nothing is kept when the section does not exist yet, when
    the new body is identical (no information would be lost), or when the old
    body is empty (nothing to lose).
    """
    row = conn.execute(
        "SELECT body FROM sections WHERE entity_id=? AND heading=?", (entity_id, heading)
    ).fetchone()
    if row is None or not row[0] or row[0] == new_body:
        return False
    conn.execute(
        "INSERT INTO revisions (entity_id, heading, body, replaced_at, summary) "
        "VALUES (?, ?, ?, ?, ?)",
        (entity_id, heading, row[0], clock.now_iso(), summary or ""),
    )
    conn.execute(
        "DELETE FROM revisions WHERE entity_id=? AND heading=? AND id NOT IN ("
        " SELECT id FROM revisions WHERE entity_id=? AND heading=? "
        " ORDER BY id DESC LIMIT ?)",
        (entity_id, heading, entity_id, heading, REVISIONS_KEPT),
    )
    return True


def list_revisions(project_path: Path, entity_id: str, heading: str | None = None) -> list[dict]:
    """Replaced versions of an entity's sections, newest first.

    Each: id, heading, replaced_at (when it stopped being the current text),
    summary (of the edit that replaced it), chars, preview (its first line).
    """
    from .db import get_db

    sql = "SELECT id, heading, replaced_at, summary, body FROM revisions WHERE entity_id=?"
    params = [entity_id]
    if heading:
        sql += " AND heading=?"
        params.append(heading)
    conn = get_db(project_path)
    try:
        rows = conn.execute(sql + " ORDER BY id DESC", params).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r[0],
            "heading": r[1],
            "replaced_at": r[2],
            "summary": r[3],
            "chars": len(r[4]),
            "preview": next((ln.strip() for ln in r[4].splitlines() if ln.strip()), "")[:100],
        }
        for r in rows
    ]


def get_revision(project_path: Path, entity_id: str, revision_id: int) -> dict | None:
    """One revision with its full text, or None if it is not this entity's."""
    from .db import get_db

    conn = get_db(project_path)
    try:
        r = conn.execute(
            "SELECT id, heading, body, replaced_at, summary FROM revisions "
            "WHERE id=? AND entity_id=?",
            (revision_id, entity_id),
        ).fetchone()
    finally:
        conn.close()
    if r is None:
        return None
    return {"id": r[0], "heading": r[1], "body": r[2], "replaced_at": r[3], "summary": r[4]}


def restore_revision(
    project_path: Path, entity_id: str, revision_id: int, summary: str | None = None
) -> dict:
    """Put a revision's text back as the section's current text.

    An ordinary edit, so the text it replaces becomes a revision in turn.
    Raises ValueError (nothing changed) if the revision is not this entity's,
    the scene is locked, or the entity no longer has that section.
    """
    from .db import get_db
    from .writes import edit_entity

    rev = get_revision(project_path, entity_id, revision_id)
    if rev is None:
        raise ValueError(f"Revision {revision_id} not found for {entity_id}.")

    conn = get_db(project_path)
    try:
        ent = conn.execute(
            "SELECT type, status FROM entities WHERE id=? AND is_deleted=0", (entity_id,)
        ).fetchone()
    finally:
        conn.close()
    if ent is None:
        raise ValueError(f"Entity not found: {entity_id}")
    if ent[1] == "locked":
        raise ValueError(f"{entity_id} is locked. Unlock it before restoring a revision.")

    result = edit_entity(
        project_path,
        ent[0],
        entity_id,
        {rev["heading"]: rev["body"]},
        summary or f"Restored the version of {rev['replaced_at']}",
    )
    if rev["heading"] not in result.get("applied", {}).get("sections", []):
        raise ValueError(f"{entity_id} has no section '{rev['heading']}' any more.")
    return {
        "success": True,
        "entity_id": entity_id,
        "heading": rev["heading"],
        "restored_from": rev["replaced_at"],
        "revision_id": rev["id"],
    }
