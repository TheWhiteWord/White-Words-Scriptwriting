"""story_backup tool — make, list and restore backups of the project database."""
import json
from pathlib import Path

SCHEMA = {
    "description": "Backups of the project database, which holds every write — story_draft "
                   "commits and story_memory all persist there, and the Markdown files are only "
                   "a stale export. action=create (the default) takes a backup; give it a `label` "
                   "to name it — a labelled backup is a milestone: it is kept for good and can be "
                   "restored later. action=list shows what exists. action=restore replaces the "
                   "WHOLE project with an earlier backup: do it only when the user asks, since "
                   "everything done after that backup is gone from the project. A safety backup "
                   "of the current state is taken first, so a restore can be undone by restoring "
                   "that one. Automatic backups (taken before an import or a purge, and before a "
                   "restore) are pruned to the newest 20; backups made here are never pruned. "
                   "To go back to an earlier version of one scene's text, use story_admin "
                   "list_revisions instead.",
    "type": "object",
    "properties": {
        "project": {"type": "string", "description": "Project slug or path"},
        "action": {
            "type": "string",
            "enum": ["create", "list", "restore"],
            "description": "create (default), list, or restore.",
        },
        "label": {
            "type": "string",
            "description": "For create: a name for this backup, e.g. \"after the table read\". "
                           "It appears in the file name (lowercase, hyphens).",
        },
        "backup": {
            "type": "string",
            "description": "For restore: the backup's file name, exactly as list shows it.",
        },
    },
    "required": ["project"],
}


def handler(args, **kwargs) -> str:
    from .story_resolve import resolve_project
    from white_words.scriptwriting.core.config import resolve_root

    root_path = resolve_root(kwargs)

    try:
        project_path = resolve_project(args["project"], root_path)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    if not (project_path / ".story" / "story.db").exists():
        return json.dumps({"error": "No story.db found. Run story_import first."})

    from white_words.scriptwriting.core import backups

    action = args.get("action") or "create"
    try:
        if action == "create":
            path = backups.create_backup(project_path, label=args.get("label"))
            return json.dumps({
                "success": True,
                "message": f"Backed up to {Path(path).name}",
                "backup": path,
            })
        if action == "list":
            found = backups.list_backups(project_path)
            result = {"success": True, "count": len(found), "backups": found,
                      "automatic_kept": backups.AUTO_BACKUPS_KEPT}
            if found:
                result["hint"] = ('Restore one with action="restore" and backup=<name>. '
                                  "Only automatic backups are ever pruned.")
            else:
                result["message"] = "There are no backups yet."
            return json.dumps(result)
        if action == "restore":
            name = args.get("backup")
            if not name:
                raise ValueError('restore needs backup=<name> (see action="list").')
            return json.dumps(backups.restore_backup(project_path, name))
        return json.dumps({"error": f"Unknown action: {action}"})
    except ValueError as e:
        return json.dumps({"error": str(e)})
