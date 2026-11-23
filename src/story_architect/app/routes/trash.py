"""Trash API — what was deleted, bringing it back, and removing it for good.

Thin, like `entities.py`: resolve the project, call `core.trash`, map its
refusals to HTTP. Non-GET requests already pass through the Host / Origin /
`X-Story-Architect` checks in `server.py`; this adds no second auth model.

Error bodies are `{"error": {"code", "message", ...}}`, the same envelope the
form routes use. Two of them carry structure the dashboard draws:

  * `409 restore_blocked` — `blockers` (a structural parent still in the trash,
    with `fix` naming it);
  * `409 not_in_trash` — the target is live, usually because the agent restored
    it while the tab was open.

The rules themselves live in `core/trash.py`, shared with the agent's
`story_admin` tool, so the browser cannot offer an action the agent would
describe differently. In particular a restore whose parent is still in the trash
is refused HERE, not there: `core.trash.restore` stays permissive for the agent,
and this route is the one that reads `restore_check` first.
"""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse


def _err(status: int, code: str, message: str, **extra):
    return JSONResponse(status_code=status,
                        content={"error": {"code": code, "message": message, **extra}})


def make_router(config, app):
    router = APIRouter()

    def _project(slug):
        from story_architect.tools.story_resolve import resolve_project
        return resolve_project(slug, Path(config.root))

    def _run(slug, fn):
        """Resolve the project, run `fn(project_path)`, translate refusals."""
        try:
            project = _project(slug)
        except ValueError as e:                     # unknown project
            return _err(404, "not_found", str(e))
        try:
            return fn(project)
        except ValueError as e:                     # refused by core.trash
            return _err(422, "invalid", str(e))

    def _restore_refusal(result):
        """A core "error" dict → the status it deserves."""
        message = result.get("error") or "Nothing was restored."
        if result.get("code") == "not_found" or message.startswith("Entity not found"):
            return _err(404, "not_found", message)
        if result.get("blockers"):
            return _err(409, "restore_blocked", message, blockers=result["blockers"])
        return _err(409, "not_in_trash", message)

    def _purge_refusal(result):
        message = result.get("error") or "Nothing was removed."
        if message.startswith("Entity not found"):
            return _err(404, "not_found", message)
        return _err(409, "not_in_trash", message)

    @router.get("/api/projects/{slug}/trash")
    def list_trash(slug: str, older_than_days: int = 30):
        """The list: one entry per deletion, children nested, restore readiness."""
        from story_architect.core import trash
        return _run(slug, lambda p: trash.trash_for_ui(p, older_than_days))

    @router.get("/api/projects/{slug}/trash/{etype}/{eid}")
    def detail(slug: str, etype: str, eid: str):
        """The preview: fields, prose, links, references, and what would change."""
        from story_architect.core import trash
        result = _run(slug, lambda p: trash.trash_detail(p, etype, eid))
        if isinstance(result, dict) and result.get("error"):
            if result.get("code") == "not_deleted":
                return _err(409, "not_in_trash", result["error"])
            return _err(404, "not_found", result["error"])
        return result

    def _targets(body) -> list:
        return [t for t in ((body or {}).get("targets") or []) if isinstance(t, dict)]

    @router.post("/api/projects/{slug}/trash/{etype}/{eid}/restore")
    def restore_one(slug: str, etype: str, eid: str, body: dict | None = None):
        """Restore one deletion, its bundle included. Reversible: no confirm."""
        from story_architect.core import trash

        def go(p):
            from story_architect.core.db import get_db
            conn = get_db(p)
            try:
                check = trash.restore_check(conn, eid)
            finally:
                conn.close()
            if check["blockers"]:
                return {"error": check["blockers"][0]["message"],
                        "blockers": check["blockers"]}
            result = trash.restore(p, etype, eid, "restored from the trash")
            if result.get("error"):
                return result
            result["returned"] = check["returned"]
            return result

        result = _run(slug, go)
        if isinstance(result, dict) and result.get("error"):
            return _restore_refusal(result)
        return result

    @router.post("/api/projects/{slug}/trash/restore")
    def restore_many(slug: str, body: dict | None = None):
        """Restore several deletions at once. All-or-nothing."""
        from story_architect.core import trash

        targets = _targets(body)
        if not targets:
            return _err(422, "invalid",
                        "restore needs targets: [{entity_type, id}, …]")

        def go(p):
            try:
                return trash.restore_many(p, targets)
            except trash.RestoreRefused as refused:
                return {"error": str(refused), "refused": refused.refused,
                        "blockers": refused.refused[0].get("blockers") or []}

        result = _run(slug, go)
        if isinstance(result, dict) and result.get("error"):
            blockers = result.get("blockers") or []
            return _err(409, "restore_blocked" if blockers else "not_in_trash",
                        result["error"],
                        refused=result.get("refused") or [],
                        blockers=blockers)
        return result

    @router.post("/api/projects/{slug}/trash/purge-preview")
    def purge_preview(slug: str, body: dict | None = None):
        """What "delete permanently" would remove, and what else loses a link."""
        from story_architect.core import trash

        targets = _targets(body)
        if not targets:
            return _err(422, "invalid",
                        "purge needs targets: [{entity_type, id}, …]. To remove "
                        "everything, select every item: nothing is swept implicitly.")
        result = _run(slug, lambda p: trash.purge_preview(p, targets))
        if result.get("refusal"):
            return _purge_refusal(result["refusal"])
        return result

    @router.post("/api/projects/{slug}/trash/purge")
    def purge(slug: str, body: dict | None = None):
        """Remove the named deletions for good: one backup, one transaction."""
        from story_architect.core import trash

        targets = _targets(body)
        if not targets:
            return _err(422, "invalid",
                        "purge needs targets: [{entity_type, id}, …]")
        result = _run(slug, lambda p: trash.purge_selected(p, targets))
        if result.get("error"):
            return _purge_refusal(result)
        return result

    return router
