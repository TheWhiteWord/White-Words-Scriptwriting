# T1 — Restore guard

Spec: `../spec-draft-versioning.md` §8, §13 T1, §14-B.
Branch: `draft-versioning`.
Baseline: `1744 passed, 1 failed` (the known `test_no_hermes_imports`), re-run
on this branch before starting.

## Objective

A soft-deleted scene keeps its `plot_<role>` relation rows and its `order_key`.
While it sits in the trash nothing counts it: a second scene may take its
singular role, and a new scene is handed its position. `restore` then clears the
flag and produces two live holders of one climax, and two siblings sharing an
`order_key`. No writer permits either state, and nothing today reports it.

Close both, in `restore_check` (so the caller sees it before acting) and in
`restore` / `restore_many` (so it cannot be written).

## Verified before starting

| Claim | Evidence |
|---|---|
| `restore` only clears flags | `core/trash.py:805` — `_clear_flags`, no role or order check |
| A trashed scene's role rows survive the delete | `core/writes.py` delete leaves `relations` intact; the `live_relations` view hides them |
| The singular-role rule counts live scenes only | `core/entity.py:1119` filters `e.is_deleted=0`, so a trashed climax frees the slot |
| A role collision is writable today | probe: delete `central-room-day`, give `central-room-night` `inciting_incident`, restore → two live holders |
| `_get_next_order_db` counts live rows only | `core/writes.py:1155` — `MAX(order_key)+1 WHERE is_deleted=0`, so the deleted key is handed out again |
| A duplicate `order_key` puts the restored scene last | probe: delete `the-core-day` (key 3), create `the-roof-dawn` (key 3), restore → order becomes `day, night, roof-dawn, core-day`; ties break on the id string |
| The duplicate reaches the tracked markdown | probe: export writes `order: 3` into both `The Core - Day.md` and `The Roof - Dawn.md` |
| `plot_roles` is relation storage, not `extra` | fixture scene `extra` keys: no `plot_roles`; rows are `(plot, plot_<role>)` |
| Removing a role cannot invalidate the loser | `validate_scene_dramatic_role` (`core/entity.py:1165`): `plot_role` or empty is allowed with empty `plot_roles` |
| Only scenes and sequences are reorderable | `REORDERABLE_TYPES` (`core/writes.py:1006`); other types legitimately share key `0` |
| Both callers route through one function | dashboard → `restore_many`; agent → `story_admin` → `restore` |

## Decisions taken

- **§14-B approved.** A role collision refuses the restore and names the fix;
  `story_admin` gains a `resolutions` property so the agent can resolve it, both
  paths in one transaction. Dashboard route forwards per-target resolutions.
- **Position collision resolves itself (option A).** The spec offers a choice
  ("after its old neighbour [default] / before the next / pick a position"); the
  default is the only answer with information behind it, and asking dead-ends the
  Trash tab until T13 builds a picker. So `restore_check` reports it, and
  `restore` renumbers the parent's live children with `reorder()` — the same
  function and the same result as any other ordering change — placing the
  restored row directly after the sibling it followed before it was deleted.
  Reported back as `placed`, so the caller can say where it landed.

## Tasks

- [x] `core/trash.py`: `_singular_role_collisions` — every singular role the
      restore would put on a second live scene, from the `plot_<role>` rows, with
      the current holder named.
- [x] `core/trash.py`: `_position_collision` — the sibling that now holds the
      restored row's `order_key`, and the neighbour it followed before the delete.
- [x] `core/trash.py`: `restore_check` returns both as `collisions` and
      `placement`, next to `blockers` / `warnings` / `returned`.
- [x] `core/trash.py`: `restore(..., resolutions=None)` — resolves first, then
      clears the flags, applies the choices and settles positions, all in the
      one transaction; refuses with `collisions` and writes nothing when a role
      collision has no resolution.
- [x] `core/trash.py`: `restore_many(..., resolutions=None)` — the same, per
      target, still all-or-nothing; `RestoreRefused` entries carry `collisions`.
- [x] `core/trash.py`: `_settle_positions` renumbers a parent whose live children
      share an `order_key`, via `reorder()`.
- [x] `app/routes/trash.py`: `409 restore_needs_decision` with the `collisions`
      payload; per-target `resolutions` accepted on both restore endpoints.
- [x] `web/js/views/trash.js`: the row says "needs a decision", the panel draws
      the collision with the two choices (keeping the current holder is
      checked), and the batch call sends the choice as `resolutions`. Without
      this the refusal would dead-end the tab.
- [x] `tools/story_admin.py`: `resolutions` property on the schema; forwarded to
      `core.trash.restore`; the refusal is data, not an exception.
- [x] `tests/test_restore_guard.py`: role collision reported, refused without a
      resolution, `drop` and `take` both land, `restore_many` all-or-nothing,
      position renumbered and exported 1..4, no collision leaves behaviour alone.
- [x] `tests/test_trash_routes.py`: 409 `restore_needs_decision`, then 200 with
      the resolution.
- [x] `tests/test_story_admin.py`: the agent refuses, then succeeds with
      `resolutions`.
- [x] `tests/trash_harness.js`: the panel draws both choices, and does not draw
      `take` when it is not on offer.
- [x] Suite still `1744 passed, 1 failed` plus the new tests: **1770 passed, 1
      failed** (26 new tests; the one failure is the known
      `test_no_hermes_imports`).

## Final Brief

**What T1 changes.** Two states that only a restore could produce are now
closed, in the two places every caller routes through.

*Role collision.* A trashed scene keeps its `plot_<role>` rows while
`validate_scene_plot_roles` counts live scenes only, so another scene may take
its `climax`; clearing the flag then left two live holders. `restore_check`
reports it as `collisions` (plot, role, current holder, the two choices), and
`restore` / `restore_many` refuse with `code=restore_needs_decision` and write
nothing until `resolutions` names who keeps each role. `drop` leaves the role on
the scene holding it; `take` moves it, and only off a **live** holder — a row
hiding on another trashed scene is that scene's own restore to decide. When two
scenes holding the role are in one batch, `take` is not offered: both would
arrive with it.

*Position collision.* `_get_next_order_db` hands a new scene `MAX(order_key)+1`
over live rows, so a deleted row's key is reissued, and readers broke the tie on
the id string — the restored scene landed wherever its id sorted. `restore_check`
reports it as `placement`, and the restore places the row directly after the
sibling it followed before the delete and renumbers the parent through
`reorder()` — the same function, and the same invariant, as any other ordering
change. The response carries `placed` so the caller can say where it landed.
Types outside `REORDERABLE_TYPES` are untouched: a shared key means nothing on
an unordered type.

**Files.** `core/trash.py` (guard, resolution, placement, both restore paths),
`app/routes/trash.py` (`409 restore_needs_decision`, per-target resolutions on
both endpoints), `tools/story_admin.py` (`resolutions` on the schema, forwarded;
refusal returned as data), `web/js/views/trash.js` (the decision is drawn and
sent, so the refusal does not dead-end the tab), `core/writes.py` (`reorder`
accepts `None` for a caller inside its own transaction — one line of annotation
and an assert).

**Verification, as run.**

- New: `tests/test_restore_guard.py`, 20 tests — role collision reported /
  refused / dropped / taken, no false positive for a spanning role, one
  unresolved target refusing a batch, both trashed holders offering only `drop`,
  position renumbered and id-order-independent, no collision leaving the
  sequence alone.
- `tests/test_trash_routes.py` +4, `tests/test_story_admin.py` +2, and two
  checks in `tests/trash_harness.js` (`tests/test_trash_ui.py` drives it): the
  409 shape, the listing reporting collisions before a click, both endpoints
  accepting a resolution, and the panel drawing both choices.
- `tests/test_live_relations.py`: the guard is registered as a third legitimate
  raw read of `relations`, with its reason. Verified the read is required — the
  `live_relations` view returns `[]` for the two-trashed-holders case.
- End to end against the fixture: delete `the-core-day`, create `the-roof-dawn`
  (same key), restore → order `day, night, core-day, roof-dawn`, keys
  `1,2,3,4`, and `story_export` writes `order: 1,2,3,4` with no duplicate.
- Full suite: **1770 passed, 1 failed** — baseline 1744 plus 26 new, same single
  known failure (`test_no_hermes_imports`).

**Deliberate simplification.** `drop` and `take` only. The spec also names
"restore without the role" vs "take the role from the current holder", which is
these two; a "Custom" role for the incoming scene is a scene edit, not a restore
decision, and `story_draft` already does it.

**One finding for T7.** The batch first interleaved its per-target checks with
its writes, which meant a target's collision was judged *after* an earlier
target had moved the role — the caller's resolution was silently dropped. Checks
now all run against the state the batch started in, then the writes. The merge
planner's dry run has the same shape of hazard and must order its checks the
same way.
