"""story_admin tool — project lifecycle and the admin-only entity operations.

Ten actions. Entity *authoring* goes through story_draft, which shows the user
what will change and writes nothing until they say so. What is here cannot be
drafted at all, with one exception: a project has no database to hold a draft
before it exists, and restore / delete-project act on something that is not a
batch of edits.

The exception is `purge`, the only irreversible operation. It does not run when
called: it STAGES a draft with a single `purge` op, and the person approves it on
the card in the app (core/drafts.py, core/trash.py). A purge is never bundled
with other changes, so approving a batch can never remove anything for good as a
side effect. Nothing here asks for a typed confirmation any more: a soft delete,
`delete_project` and `restore` are all undoable, and the one thing that is not
waits for the person rather than for a string the caller could echo back.

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

from story_architect.core import clock
from story_architect.core.trash import purge_cutoff

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
                   "purge (PROPOSE removing deleted entities for good: all those deleted over 30 days "
                   "ago, or one you name — nothing is removed until the user approves it in the app), "
                   "list_revisions / restore_revision (the earlier versions of "
                   "an entity's text, and putting one back). Entity content "
                   "itself is NOT here — create and edit through story_draft. "
                   "Deleting an entity is a soft delete and is exactly reversible via restore; "
                   "purge is the only irreversible one, and the only one that waits for the user. "
                   "delete_project takes a whole project out of the projects list into a trash folder, "
                   "from where restore_project returns it; neither needs a confirmation, so do it "
                   "only when the user asked.",
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
                           "exactly as they were), purge (propose permanently removing soft-deleted "
                           "entities — those older than the age floor, or the one named in "
                           "`target`. Irreversible, so it is staged as a draft: the user sees "
                           "an approval card and nothing is removed until they approve. Relay "
                           "preview_md verbatim), "
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
            "description": "For restore: one line naming what was restored. For purge: one \
line the user will read on the approval card, naming what is to be removed for good",
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
            return json.dumps(_stage_purge(args, _resolve(args, root_path)))
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
    """Move a project folder to the trash.

    The folder is moved whole, not copied-from and removed: the database (with
    its WAL files, which only mean something next to it), chat history, memory
    and any hand-edited Markdown all survive, and bringing the project back is a
    move in the other direction (`restore_project`). Deleting used to keep only
    a copy of story.db and `rmtree` the rest.

    No confirmation: nothing is lost by it. (It used to demand a typed
    "DELETE <slug>", which the refusal message printed for the caller to echo
    back, so it stopped nobody; the only irreversible operation, purge, now needs
    the person's approval in the app.)
    """
    project_path = _resolve(args, root_path)
    slug = project_path.name

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
            "deleted_at": clock.now_iso("microseconds"),
        }), encoding="utf-8")
        shutil.move(str(project_path), str(slot))
    except BaseException:
        shutil.rmtree(slot, ignore_errors=True)   # a failed move leaves the project where it was
        raise

    trashed = slot / slug
    return {
        "success": True,
        "message": f"Moved project {slug} to the trash. Nothing was lost.",
        "project": str(project_path),
        "trash_id": slot.name,
        "trashed_to": str(trashed),
        "note": 'Undo with action="restore_project" and this trash_id. To remove it '
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


def _stage_purge(args: dict, project_path: Path) -> dict:
    """Propose a purge as a draft. Removes nothing.

    A purge is irreversible, so it is the one admin action that waits for the
    person. It used to wait for a typed string, which the refusal message printed
    for the caller to echo back; now it is a draft the person approves on the
    same card as any other change (core/drafts.py, op "purge"). Approving runs
    core/trash.purge_deleted, which takes a backup first.
    """
    from story_architect.core import drafts

    target = args.get("target")
    if target is not None and not (isinstance(target, dict) and target.get("entity_type")
                                   and target.get("id")):
        return {"error": "purge: `target` needs both entity_type and id."}
    op = {"op": "purge",
          "summary": args.get("summary") or ("Permanently remove "
                                             + (f"{target['entity_type']} {target['id']}"
                                                if target else "old deleted items"))}
    if target:
        op["target"] = {"entity_type": target["entity_type"], "id": target["id"]}
    if "older_than_days" in args:
        op["older_than_days"] = args["older_than_days"]
    try:
        staged = drafts.stage(project_path, [op], summary=op["summary"])
    except drafts.DraftError as e:
        return {"error": str(e)}
    staged["purged"] = False
    staged["message"] = ("Nothing has been removed. This waits for the user: they approve "
                         "it on the card in the app. Relay preview_md verbatim and tell them "
                         "it cannot be undone.")
    return staged


def _list_deleted(project_path: Path, args: dict) -> dict:
    """The trash: every soft-deleted entity, newest deletion first.

    Delegates to `core.trash.list_deleted`, which the dashboard's Trash tab also
    reads: what the agent is told and what the person sees come from one
    function, so a bundle cannot be described two ways.

    One entry per *deletion*. Deleting a scene also deletes its beats, all
    stamped with the same `deleted_at`; they are folded under the scene as
    `includes` instead of listed as separate things, because restoring the scene
    brings them back with it. An entity deleted separately, at another time, is
    its own entry.

    `purge_eligible` says whether a purge with the current age floor would
    remove it.
    """
    from story_architect.core import trash

    return trash.list_deleted(project_path, args.get("older_than_days", 30))


def _restore_entity(args: dict, project_path: Path) -> dict:
    """Undelete an entity by clearing is_deleted. The exact inverse of the delete.

    Delegates to `core.trash.restore` for the reason `_list_deleted` delegates:
    one implementation of what a restore brings back, used by the agent and by
    the dashboard's Trash tab alike.

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
    from story_architect.core import trash

    target = args.get("target") or {}
    return trash.restore(project_path,
                         target.get("entity_type") or "",
                         target.get("id") or "",
                         args.get("summary", ""))


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
