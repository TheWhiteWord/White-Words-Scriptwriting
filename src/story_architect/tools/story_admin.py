"""story_admin tool — project lifecycle and the admin-only entity operations.

Ten actions, none of them proposals. Entity *authoring* goes through
story_draft, which shows the user what will change and writes nothing until they
say so. What is here cannot be drafted at all: a project has no database to hold
a draft before it exists, and purge/restore/delete-project are the operations
that must never be a side effect of committing a batch.

`list_deleted`, `restore` and `purge` are the trash: look at what was deleted,
bring one back, or remove it for good. `list_revisions` and `restore_revision`
are the undo for *text*: an entity's earlier versions, and putting one back.

`create_project`, `list_projects`, `delete_project`, `list_trashed_projects`
and `restore_project` are the project lifecycle. Deleting a project moves its
folder to a trash folder under the root; nothing drafts, because a draft exists
to exist before it is written.
"""
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

# Deleted projects wait here, under the root but outside projects/, so they are
# not listed as projects. Hidden so a vault that is also opened in Obsidian does
# not index the deleted Markdown; not named ".trash", which Obsidian also uses.
TRASH_DIR = ".story-trash"

SCHEMA = {
    "description": "Project lifecycle and admin operations: create_project (a new project), "
                   "list_projects, delete_project (moves a project to the trash), "
                   "list_trashed_projects / restore_project (bring a deleted project back), "
                   "list_deleted (the trash: what was deleted and "
                   "when), restore (bring a soft-deleted entity back), "
                   "purge (permanently remove deleted entities: all those deleted over 30 days ago, "
                   "or one you name), list_revisions / restore_revision (the earlier versions of "
                   "an entity's text, and putting one back). Entity content "
                   "itself is NOT here — create and edit through story_draft. "
                   "Deleting an entity is a soft delete and is exactly reversible via restore; "
                   "purge is the only irreversible one. delete_project takes a whole project out of "
                   "the projects list into a trash folder, from where restore_project returns it.",
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["create_project", "list_projects", "delete_project", "list_deleted",
                     "restore", "purge", "list_revisions", "restore_revision",
                     "list_trashed_projects", "restore_project"],
            "description": "create_project (initialise a new project folder + database), "
                           "list_projects (every project under the root, no database opened), "
                           "delete_project (move a project folder, with everything in it, to the "
                           "trash — recoverable with restore_project), "
                           "list_trashed_projects (deleted projects, newest first), "
                           "restore_project (bring one back; needs trash_id), "
                           "list_deleted (every soft-deleted entity, newest first, with the "
                           "id and type that restore and purge need; entities deleted "
                           "together with their parent are listed under it), "
                           "restore (undelete one entity, bringing back its prose and relations "
                           "exactly as they were), purge (permanently remove soft-deleted "
                           "entities — those older than the age floor, or the one named in "
                           "`target` — irreversible), "
                           "list_revisions (the earlier versions kept of an entity's sections, "
                           "newest first; every edit keeps the text it replaced), "
                           "restore_revision (put one of those back as the current text; the "
                           "text it replaces is kept in turn, so this is undoable)"
        },
        "trash_id": {
            "type": "string",
            "description": "For restore_project: which deleted project to bring back, exactly "
                           "as list_trashed_projects shows it.",
        },
        "revision_id": {
            "type": "integer",
            "description": "For restore_revision: the id of the revision to put back, from "
                           "list_revisions.",
        },
        "heading": {
            "type": "string",
            "description": "For list_revisions: only the revisions of this section, e.g. "
                           "\"Content\". Default: all sections of the entity.",
        },
        "project": {
            "type": "string",
            "description": "Project slug or path. For create_project this is the new project's "
                           "folder name and the project does not exist yet.",
        },
        "frontmatter": {
            "type": "object",
            "description": "For create_project: the project entity's field values, e.g. "
                           "{name, logline}. Missing fields fall back to schema defaults; "
                           "required fields must be present and non-empty.",
        },
        "target": {
            "type": "object",
            "description": "For restore: the entity to bring back. For purge: the one deleted "
                           "entity to remove permanently (it must already be deleted; the age "
                           "floor does not apply). For list_revisions / restore_revision: the "
                           "entity whose text history it is (only `id` is needed).",
            "properties": {
                "entity_type": {"type": "string",
                                "description": "Type of entity to restore"},
                "id": {"type": "string", "description": "Entity id, as returned by story_load"},
            },
        },
        "summary": {
            "type": "string",
            "description": "For restore: one line naming what was restored",
        },
        "delete_confirm": {
            "type": "string",
            "description": "Required for action=\"delete_project\". Must contain the literal text "
                           "\"DELETE <project slug>\", e.g. \"DELETE my-film\". This is the "
                           "user's call to make — do not supply it unless the user has asked for "
                           "the project to be removed entirely. The project goes to the trash "
                           "and can be restored with restore_project."
        },
        "purge_confirm": {
            "type": "string",
            "description": "Required for action=\"purge\". Must contain the literal text "
                           "\"DELETE <project slug>\", e.g. \"DELETE my-film\". This is the "
                           "user's call to make — do not supply it unless the user has asked for "
                           "the deleted entities to be removed permanently."
        },
        "older_than_days": {
            "type": "integer",
            "description": "For action=\"purge\" without a target: only purge entities deleted "
                           "longer ago than this many days. Default 30. Anything newer stays "
                           "restorable. Ignored when a target is given. "
                           "For action=\"list_deleted\": the same threshold, used to mark "
                           "which entries a purge would remove."
        },
    },
    "required": ["action"],
}


def handler(args: dict, **kwargs) -> str:
    from story_architect.core.config import resolve_root

    root_path = resolve_root(kwargs)
    action = args["action"]

    try:
        if action == "create_project":
            return json.dumps(_create_project(args, root_path))
        if action == "list_projects":
            return json.dumps(_list_projects(root_path))
        if action == "delete_project":
            return json.dumps(_delete_project(args, root_path))
        if action == "list_trashed_projects":
            return json.dumps(_list_trashed_projects(root_path))
        if action == "restore_project":
            return json.dumps(_restore_project(args, root_path))
        if action == "list_deleted":
            return json.dumps(_list_deleted(_resolve(args, root_path), args))
        if action == "purge":
            return json.dumps(_purge_deleted(args, _resolve(args, root_path)))
        if action == "restore":
            return json.dumps(_restore_entity(args, _resolve(args, root_path)))
        if action == "list_revisions":
            return json.dumps(_list_revisions(args, _resolve(args, root_path)))
        if action == "restore_revision":
            return json.dumps(_restore_revision(args, _resolve(args, root_path)))
        return json.dumps({"error": f"Unknown action: {action}"})
    except ValueError as e:
        return json.dumps({"error": str(e)})


def _resolve(args: dict, root_path: Path) -> Path:
    """Resolve the `project` argument, which every project-scoped action takes."""
    from .story_resolve import resolve_project
    return resolve_project(args.get("project", ""), root_path)


# ─── the actions ───

def _create_project(args: dict, root_path: Path) -> dict:
    from story_architect.core.writes import create_project
    return create_project(
        args.get("project", ""), args.get("frontmatter") or {}, root_path)


def _list_projects(root_path: Path) -> dict:
    """Every project folder under the root. Directory listing only.

    A project is a directory holding `.story/story.db` — so this reads the
    listing and nothing else. Opening a database per project to recover its
    display name would be a connection per candidate on every call, on a root
    that may hold hundreds; `resolve_project` already does that once, when
    there is a specific project to resolve.
    """
    projects_dir = root_path / "projects"
    if not projects_dir.is_dir():
        return {"success": True, "projects": [], "count": 0,
                "note": f"No projects directory at {projects_dir}"}

    projects = []
    for folder in sorted(projects_dir.iterdir()):
        if not folder.is_dir():
            continue
        db = folder / ".story" / "story.db"
        projects.append({
            "slug": folder.name,
            "path": str(folder),
            "has_database": db.exists(),
        })
    return {"success": True, "projects": projects, "count": len(projects)}


def _delete_project(args: dict, root_path: Path) -> dict:
    """Move a project folder to the trash. Refuses without a typed string.

    The folder is moved whole, not copied-from and removed: the database (with
    its WAL files, which only mean something next to it), chat history, memory
    and any hand-edited Markdown all survive, and bringing the project back is a
    move in the other direction (`restore_project`). Deleting used to keep only
    a copy of story.db and `rmtree` the rest.

    `delete_confirm` must contain "DELETE <project slug>". It is kept for now as
    the explicit "yes, this project" step; the delete is no longer destructive.
    """
    project_path = _resolve(args, root_path)
    slug = project_path.name

    required = f"DELETE {slug}"
    given = args.get("delete_confirm", "")
    if required not in given:
        return {
            "error": "Delete refused. It takes the whole project out of the projects "
                     "list.",
            "action_required": f'Re-run with delete_confirm="{required}" if the user has '
                               f"asked for this project to be removed.",
            "project": str(project_path),
            "hint": "To keep the project but tidy it up, use action=\"purge\" "
                    "instead — that only touches entities already soft-deleted. A "
                    "deleted project can be brought back with restore_project.",
        }

    if not (project_path / ".story" / "story.db").exists():
        return {
            "error": f"Not a story project — no .story/story.db in {project_path}. "
                     f"Nothing was deleted.",
            "project": str(project_path),
        }

    trash = root_path / TRASH_DIR
    trash.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # mkdtemp reserves a name nobody else holds; the project lands inside it, so
    # two deletes of the same slug never collide.
    slot = Path(tempfile.mkdtemp(prefix=f"{slug}_{stamp}_", dir=str(trash)))
    try:
        (slot / "deleted.json").write_text(json.dumps({
            "slug": slug,
            "original_path": str(project_path),
            # Full precision: two deletes in one second must still sort newest-first.
            "deleted_at": datetime.now().isoformat(),
        }), encoding="utf-8")
        shutil.move(str(project_path), str(slot))
    except BaseException:
        shutil.rmtree(slot, ignore_errors=True)   # a failed move leaves the project where it was
        raise

    trashed = slot / slug
    return {
        "success": True,
        "message": f"Moved project {slug} to the trash.",
        "project": str(project_path),
        "trash_id": slot.name,
        "trashed_to": str(trashed),
        "note": 'Bring it back with action="restore_project" and trash_id. To remove it '
                "for good, delete the folder under the trash directory by hand.",
    }


def _trashed_projects(root_path: Path) -> list[dict]:
    """The projects in the trash, newest first. Only complete entries are listed."""
    trash = root_path / TRASH_DIR
    found = []
    if not trash.is_dir():
        return found
    for slot in trash.iterdir():
        try:
            meta = json.loads((slot / "deleted.json").read_text(encoding="utf-8"))
            slug = meta["slug"]
        except (OSError, ValueError, KeyError):
            continue
        folder = slot / slug
        if not folder.is_dir():
            continue
        found.append({
            "trash_id": slot.name,
            "slug": slug,
            "deleted_at": meta.get("deleted_at", ""),
            "has_database": (folder / ".story" / "story.db").exists(),
            "path": str(folder),
        })
    found.sort(key=lambda e: (e["deleted_at"], e["trash_id"]), reverse=True)
    return found


def _list_trashed_projects(root_path: Path) -> dict:
    found = _trashed_projects(root_path)
    result = {"success": True, "count": len(found), "trashed": found}
    if found:
        result["hint"] = 'Bring one back with action="restore_project" and trash_id.'
    else:
        result["message"] = "No projects are in the trash."
    return result


def _restore_project(args: dict, root_path: Path) -> dict:
    """Move a trashed project back under projects/. Refuses to overwrite one."""
    trash_id = args.get("trash_id")
    if not trash_id:
        raise ValueError('restore_project needs trash_id (see action="list_trashed_projects").')
    # Only names from the listing: that is what keeps a path like ../x out.
    entry = next((e for e in _trashed_projects(root_path) if e["trash_id"] == trash_id), None)
    if entry is None:
        raise ValueError(f"No such project in the trash: {trash_id}")

    dest = root_path / "projects" / entry["slug"]
    if dest.exists():
        raise ValueError(
            f"A project named {entry['slug']} already exists. Rename or delete it first; "
            f"the trashed one was not touched.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(entry["path"], str(dest))
    shutil.rmtree(root_path / TRASH_DIR / trash_id, ignore_errors=True)   # the empty slot
    return {"success": True, "message": f"Restored project {entry['slug']}.",
            "slug": entry["slug"], "project": str(dest)}


def _purge_cutoff(days: int) -> str:
    """ISO timestamp: entities deleted at or before it are old enough to purge."""
    from datetime import datetime, timedelta
    return (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")


def _list_deleted(project_path: Path, args: dict) -> dict:
    """The trash: every soft-deleted entity, newest deletion first.

    One entry per *deletion*. Deleting a scene also deletes its beats, all
    stamped with the same `deleted_at`; they are folded under the scene as
    `includes` instead of listed as separate things, because restoring the scene
    brings them back with it. An entity deleted separately, at another time, is
    its own entry.

    `purge_eligible` says whether a purge with the current age floor would
    remove it. Rows with no `deleted_at` (deleted by an earlier build) are listed
    too, and never eligible: bulk purge cannot see them.
    """
    from story_architect.core.db import get_db

    days = args.get("older_than_days", 30)
    cutoff = _purge_cutoff(days)

    conn = get_db(project_path)
    try:
        rows = conn.execute(
            "SELECT id, type, name, deleted_at, parent_id FROM entities "
            "WHERE is_deleted=1 ORDER BY deleted_at DESC, type, id").fetchall()
    finally:
        conn.close()

    by_id = {r[0]: r for r in rows}

    entries, includes = {}, {}
    for row in rows:
        parent = by_id.get(row[4])
        if parent is not None and row[3] is not None and parent[3] == row[3]:
            # Same deletion stamp as its parent: deleted in the same operation.
            includes.setdefault(parent[0], []).append(
                {"type": row[1], "id": row[0], "name": row[2] or row[0]})
        else:
            entries[row[0]] = row

    deleted = [
        {
            "type": r[1],
            "id": r[0],
            "name": r[2] or r[0],
            "deleted_at": r[3],
            "purge_eligible": r[3] is not None and r[3] <= cutoff,
            "includes": includes.get(r[0], []),
        }
        for r in entries.values()
    ]
    result = {"success": True, "count": len(deleted), "deleted": deleted,
              "purge_older_than_days": days}
    if not deleted:
        result["message"] = "Nothing has been deleted."
    else:
        result["hint"] = ('Bring one back with action="restore" and target '
                          '{entity_type, id}; anything in `includes` comes back with it.')
    return result


def _purge_deleted(args: dict, project_path: Path) -> dict:
    """Permanently remove soft-deleted entities. Irreversible, so two guards.

    Two forms, the same guards:

    * no `target` — everything deleted more than `older_than_days` ago (default
      30). The age floor means tidying up can never destroy a fresh mistake.
    * `target` {entity_type, id} — exactly that one entity, plus whatever was
      deleted along with it. The age floor does not apply: naming one item is
      the opposite of a sweep. It must already be in the trash; a live entity
      is refused.

    Guards:

    1. `purge_confirm` must contain the literal "DELETE <project slug>".
    2. A backup is taken first, so even this is recoverable by hand.
    """
    from story_architect.core.backups import create_backup
    from story_architect.core.db import get_db, transaction

    required = f"DELETE {project_path.name}"
    given = args.get("purge_confirm", "")
    if required not in given:
        return {
            "error": "Purge refused. It is irreversible and must be the user's call.",
            "action_required": f'Re-run with purge_confirm="{required}" if you are sure.',
            "hint": 'To undo a delete instead, use action="restore" — that is exact.',
        }

    target = args.get("target")
    days = args.get("older_than_days", 30)
    cutoff = _purge_cutoff(days)

    conn = get_db(project_path)
    try:
        # Selecting what to purge and deleting it are one transaction: the
        # deletes below must land together, or a stop part-way leaves entities
        # with no sections, or sections with no entity.
        with transaction(conn):
            if target:
                rows, refusal = _select_one_deletion(conn, target)
                if refusal:
                    return refusal
            else:
                rows = conn.execute(
                    "SELECT id, type, deleted_at FROM entities "
                    "WHERE is_deleted=1 AND deleted_at IS NOT NULL AND deleted_at <= ? "
                    "ORDER BY type, id", (cutoff,)).fetchall()
                if not rows:
                    younger = conn.execute(
                        "SELECT count(*) FROM entities WHERE is_deleted=1").fetchone()[0]
                    return {
                        "success": True,
                        "purged": [],
                        "message": (
                            f"Nothing is old enough to purge ({younger} deleted entities are "
                            f"younger than {days} days). They stay restorable."),
                    }

            ids = [r[0] for r in rows]
            backup = create_backup(project_path, automatic=True)
            _hard_delete(conn, ids)
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


def _select_one_deletion(conn, target: dict):
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
    return [(row[0], row[1], row[2])] + _deleted_together(conn, row[0], row[2]), None


def _deleted_together(conn, entity_id: str, deleted_at) -> list:
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


def _hard_delete(conn, ids: list) -> None:
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


def _restore_entity(args: dict, project_path: Path) -> dict:
    """Undelete an entity by clearing is_deleted. The exact inverse of the delete.

    The delete changes nothing but the flags: sections, relation rows, the names
    other entities hold in `extra`, and `location_id` all stay as written, and
    readers hide the ones that name a deleted entity (the `live_relations` view
    and core/references.py). So there is nothing to rebuild here — clearing the
    flag makes cast, location links, plot roles, relationship characters and
    perspectives visible again, and the stored data is byte for byte what it was.

    The one thing that is not given back: a field someone set to a new value
    while the entity was in the trash. An edit that sets `characters` replaces
    the stored list, hidden names included.
    """
    from story_architect.core.db import get_db, transaction

    target = args.get("target") or {}
    entity_type = target.get("entity_type") or ""
    entity_id = target.get("id") or ""
    summary = args.get("summary", "")
    conn = get_db(project_path)
    try:
        # The parent and its children come back together or not at all.
        with transaction(conn):
            # Deliberately NOT filtered on is_deleted — that is the point.
            row = conn.execute(
                "SELECT id, is_deleted, deleted_at FROM entities WHERE id=?",
                (entity_id,),
            ).fetchone()
            if not row:
                return {"error": f"Entity not found: {entity_type}/{entity_id}"}
            entity_id, is_deleted, deleted_at = row
            if not is_deleted:
                return {
                    "error": f"{entity_id} is not deleted — nothing to restore.",
                    "entity_id": entity_id,
                }
            conn.execute(
                "UPDATE entities SET is_deleted=0, deleted_at=NULL WHERE id=?", (entity_id,))
            # Children come back with their parent — the ones THIS delete flagged,
            # and only those. The delete cascades on `parent_id`, so leaving such a
            # child deleted would restore a scene with no scene_beats, silently; but
            # a child that was already in the trash before (or was deleted on its
            # own after) carries a different stamp, and bringing it back would undo
            # a deletion nobody asked to undo.
            #
            # Keyed on `parent_id` for every type rather than a per-type branch: the
            # cascade is one fact (this row owned that row).
            restored_children = sorted(
                r[0] for r in _deleted_together(conn, entity_id, deleted_at))
            if restored_children:
                conn.executemany(
                    "UPDATE entities SET is_deleted=0, deleted_at=NULL WHERE id=?",
                    [(c,) for c in restored_children])
    finally:
        conn.close()

    return {
        "success": True,
        "message": f"Restored: {summary}",
        "entity_id": entity_id,
        "was_deleted_at": deleted_at,
        "restored_cascade_children": restored_children,
    }


def _target_id(args: dict, action: str) -> str:
    entity_id = (args.get("target") or {}).get("id")
    if not entity_id:
        raise ValueError(f'{action} needs target {{"id": <entity id>}}.')
    return entity_id


def _list_revisions(args: dict, project_path: Path) -> dict:
    """The earlier versions kept of an entity's sections, newest first."""
    from story_architect.core.revisions import REVISIONS_KEPT, list_revisions

    entity_id = _target_id(args, "list_revisions")
    revisions = list_revisions(project_path, entity_id, args.get("heading"))
    result = {"success": True, "entity_id": entity_id, "count": len(revisions),
              "revisions": revisions, "kept_per_section": REVISIONS_KEPT}
    if revisions:
        result["hint"] = ('Put one back with action="restore_revision", target '
                          '{id}, revision_id. The text it replaces is kept too.')
    else:
        result["message"] = "No earlier versions are kept for this entity."
    return result


def _restore_revision(args: dict, project_path: Path) -> dict:
    """Put an earlier version of a section back. Undoable: it keeps what it replaces."""
    from story_architect.core.revisions import restore_revision

    entity_id = _target_id(args, "restore_revision")
    revision_id = args.get("revision_id")
    if not isinstance(revision_id, int) or isinstance(revision_id, bool):
        raise ValueError("restore_revision needs an integer revision_id (see list_revisions).")
    return restore_revision(project_path, entity_id, revision_id, args.get("summary") or None)
