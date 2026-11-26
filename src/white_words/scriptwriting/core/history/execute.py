"""Applying a merge plan: the dry run, the write, and the guards around both.

`plan` decides *what* changes; this module is the only place that changes it. A plan
carries its own op order (§7.7.2), so nothing here sorts: the release that frees a
singular role must run before the create that takes it, and `sorted_ops` would put
every create first.

Two entry points, one op runner:

  * ``dry_run`` replays the plan against a scratch copy of the target with the real
    validators, and maps each refusal back to the plan item or decision that produced
    it (§7.7.3). It writes nothing, so it is safe to call on a preview.
  * ``apply`` takes a draft of the target first — the restore point — then runs the
    ops in ONE transaction on the live database, all or none (§7.7.4). It refuses a
    plan whose target fingerprint no longer matches, and refuses one with an
    unanswered decision.

A refusal is data, not an exception: both entry points return
``{"status": "refused", "failures": [...]}`` or ``{"status": "blocked"}``, because the
caller's job is to show them. Only an unexpected failure inside `apply` raises, after
the transaction has rolled back.

§7.8's other target — another branch's parked head — is not here: the executor works on
a project path, which for the live head is the project's own database.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from .. import drafts, trash
from ..db import get_db, transaction
from . import fingerprint, store

__all__ = ["apply", "dry_run"]

# An op kind `drafts.apply_op` cannot dispatch: it falls through to `reorder` for
# anything it does not recognise, so an unrecognised kind must never reach it.
_INTERNAL = ("restore",)


def dry_run(project_path: Path, planned: dict) -> dict:
    """Replay the whole plan against a throwaway copy of the target (§7.7.3).

    The copy is a real project directory, so every op reaches the same validators it
    will at apply time — there is no second copy of any rule. Nothing is written to
    `project_path`, and the copy is removed on every path.

    Returns ``{"status": "clean"}``, or ``{"status": "refused", "failures": [...]}``
    with each failure naming the op, its error, and the item and decision that
    produced it. `ready` is reported so a caller can tell a clean default plan from
    one that may be applied.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        story = Path(tmp) / ".story"
        story.mkdir()
        source = get_db(project_path)
        try:
            dest = sqlite3.connect(str(story / "story.db"))
            try:
                # backup(), not a file copy: committed writes can still be in
                # story.db-wal, and a plain copy would replay against a stale state.
                source.backup(dest)
            finally:
                dest.close()
        finally:
            source.close()
        failures = _run(Path(tmp), planned)

    if failures:
        return {"status": "refused", "failures": failures, "ready": planned.get("ready", True)}
    return {"status": "clean", "ready": planned.get("ready", True)}


def apply(
    project_path: Path,
    planned: dict,
    *,
    parent_source: str | None = None,
    label: str | None = None,
) -> dict:
    """Apply a plan to the live database: one draft first, then one transaction.

    `parent_source` is a snapshot id, and passing one IS §7.9's "complete merge"
    declaration: everything in that draft is accounted for, so it becomes a parent at
    the next save. A cherry-pick passes nothing and its unselected changes are offered
    again next time.

    The whole operation holds the manifest lock (§4.5): a merge moves files and content
    together, and a second caller that passed its own checks mid-merge would act on a
    state that is about to change. Inside it, the fingerprint is checked before anything
    is written, so a stale plan leaves no trace; then the restore point is taken, then
    the ops run in one content transaction that re-checks the fingerprint — between the
    two checks only another writer could move the target, and the second is the one that
    counts.

    Returns ``{"status": "applied", "applied": [...], "baseline": {...}, "parents":
    [...] | None}``.
    """
    if not planned.get("ready", True):
        return {
            "status": "blocked",
            "open": planned.get("open") or [],
            "message": "Some decisions are still unanswered. Apply stays disabled until "
            "each one has a choice.",
        }

    with store.locked(project_path) as history:
        stale = _stale(planned, fingerprint.of_project(project_path))
        if stale:
            return stale

        baseline = _restore_point(project_path, history, label)
        ops = planned.get("ops") or []

        live = get_db(project_path)
        try:
            with transaction(live):
                stale = _stale(planned, fingerprint.of_conn(live))
                if stale:
                    return stale
                failures = _run(project_path, planned, conn=live, ops=ops)
                if failures:
                    raise _Refused(failures)
        except _Refused as stop:
            # The content transaction has rolled back: the target is untouched, and the
            # draft taken above is still the state to return to.
            return {"status": "refused", "failures": stop.failures, "baseline": baseline}
        finally:
            live.close()

        parents = (
            store.record_pending_parent(project_path, parent_source, conn=history)
            if parent_source
            else None
        )
        return {
            "status": "applied",
            "applied": [
                {"op": op["op"], "summary": op.get("summary", ""), "source": op.get("source")}
                for op in ops
            ],
            "baseline": baseline,
            "parents": parents["pending_merge_parents"] if parents else None,
        }


class _Refused(Exception):
    """Named so `apply` can tell its own rollback from an unexpected failure."""

    def __init__(self, failures):
        super().__init__(failures[0]["error"] if failures else "refused")
        self.failures = failures


def _stale(planned: dict, current: str) -> dict | None:
    """§7.7.4's stale-plan refusal, or None when the target is where the plan left it.

    A plan without a fingerprint has no guard to enforce; `plan()` always sets one.
    """
    expected = planned.get("fingerprint")
    if not expected or expected == current:
        return None
    return {
        "status": "refused",
        "code": "stale_plan",
        "message": "The target changed since this plan was made. Re-plan against the "
        "current state; decisions that still apply are kept by key.",
    }


def _restore_point(project_path: Path, conn: sqlite3.Connection, label: str | None) -> dict:
    """The draft a merge can be undone to (§7.7.4); see `store.restore_point`."""
    return store.restore_point(project_path, conn, label or "Before merge")


def _run(project_path: Path, planned: dict, *, conn=None, ops=None) -> list[dict]:
    """Run the ops in the plan's order; stop at the first failure and explain it.

    Stopping is deliberate: every later op was planned against a state in which the
    failed one had already happened, so running it would report a second, derived
    failure and bury the first.
    """
    failures = []
    for op in (planned.get("ops") if ops is None else ops) or ():
        result = _apply_one(project_path, op, conn)
        if result.get("error") or result.get("success") is False:
            failures.append(
                {
                    "op": op["op"],
                    "summary": op.get("summary", ""),
                    "source": op.get("source"),
                    "error": str(result.get("error") or result.get("message") or "refused"),
                    **_explain(planned, op),
                }
            )
            break
    return failures


def _apply_one(project_path: Path, op: dict, conn) -> dict:
    """Dispatch one op, turning a raise into the `error` dict the runner reads.

    `restore` is dispatched here rather than through `drafts.apply_op`: it is not in
    the agent-facing op vocabulary (§7.7.2), and `apply_op` would send an unknown kind
    to `reorder`. Everything else is exactly what a staged draft does.
    """
    try:
        if op["op"] in _INTERNAL:
            return trash.restore(
                None if conn is not None else project_path,
                op["entity_type"],
                op["entity_id"],
                op.get("summary", ""),
                resolutions=op.get("resolutions") or [],
                conn=conn,
            )
        return drafts.apply_op(project_path, op, conn=conn)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _explain(planned: dict, op: dict) -> dict:
    """The plan item and decision a failed op came from (§7.7.3).

    Keyed on the op's `source`, not on its target: a release op edits the scene that
    HOLDS a role while the decision belongs to the scene arriving, so the op's own id
    names the wrong item. A D4 raised while checking a `plot_roles` field edit is keyed
    on the entity, so the entity key is tried too.
    """
    source = op.get("source")
    if not source:
        return {"item": None, "decision": None}
    entity_key = (
        f"entity:{op['type']}:{op['id']}"
        if op["op"] == "create"
        else f"entity:{op.get('entity_type')}:{op.get('entity_id')}"
    )
    subjects = {source, entity_key}
    item = next((i for i in planned.get("items") or () if i.get("key") in subjects), None)
    decision = next((d for d in planned.get("decisions") or () if d.get("item") in subjects), None)
    return {"item": item, "decision": decision}
