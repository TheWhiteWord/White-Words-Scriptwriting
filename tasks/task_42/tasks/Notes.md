# Task 42 — Notes

Cross-task record for draft versioning, branching, diff and merge.
One section per task. Each task reads every earlier section before it starts,
and writes its findings into the sections of the tasks they affect.

Rules for entries: a finding is a fact about the code or the spec that a later
task would otherwise have to rediscover. State the fact, where it was verified,
and what it changes. No narration.

---

## T0 — Branch off `dev`, ruff config, formatting

### Findings
- Baseline at `dev` @ `610cf06`: `1744 passed, 1 failed`. The failure is
  `tests/test_no_hermes_imports.py::test_no_hermes_imports` — `app/server.py`
  mentions `adapters.hermes.chat_backend` in a local import. Pre-existing, by
  owner decision not this feature's concern. Every boundary check in later
  tasks compares against **1744 passed / 1 failed**; a count that moves down is
  a regression.
- `build_registry()` output is byte-identical before and after the reformat, so
  no agent-facing tool schema changed. Verified by dumping the registry to JSON
  on both trees and diffing.
- `ruff format` **also rewrites Python code fences inside `.md` files**: 83
  documents under `tasks/` would be reformatted. `tasks/` is excluded from ruff
  for this reason.

### Deviations
- The spec's T0 line reads "`ruff` config; apply formatting". A `[tool.ruff]`
  block already existed at `dev` (`line-length=100`, `target-version=py311`,
  `select=["E","F"]`); T0 therefore adds only the pin and the `tasks/` exclude,
  rather than introducing a config.
- Scope of the `ruff` work is format only, by owner decision. 263 `ruff check`
  findings remain after formatting and are **not** this task's. A later commit
  owns them.

### Issues
- Ruff was neither installed nor pinned at `dev`, so `ruff format` was not
  reproducible: 0.15.8 and 0.17.6 reformat a different set of 6 files. Pinned to
  `0.15.8` in the `dev` extra. A future ruff upgrade is its own commit with its
  own reformat, not a side effect of an unrelated task.
- Of the 263 remaining findings, 113 of the 127 `E501`s are string literals
  (prompt text, SQL, regexes) that the formatter cannot split. Adding `E501` to
  the ignore list is the standing ruff guidance when the formatter owns line
  length; not done here, since it belongs with the lint-backlog commit.
- Six `F841` findings in `src/` are worth reading, not deleting:
  `core/db.py:858 plot_scopes`, `chat/service.py:191 cancelled`,
  `adapters/hermes/setup.py:333 gateway_ok`, `core/fountain_lexer.py:437
  emptytitlepage`, `core/fountain_validator.py:200 prev_line_num`,
  `tools/story_load.py:299 act_extra`. Each is assigned and never read; at least
  two read like an unimplemented check. Line numbers are post-format. Carry them
  to the lint-backlog commit with this note.

---

## T1 — Restore guard

### Findings
- A role collision is only reachable because the validator counts live scenes
  only (`core/entity.py:1119`, `e.is_deleted=0`). The fix is in `restore`, not
  there: the validator is right to let a live scene take a role nobody is using.
- A trashed scene's `plot_<role>` rows are readable only from the `relations`
  table. The `live_relations` view hides every row either end of which is
  deleted, so `restore_check`'s collision scan must not use it. Verified by the
  two-trashed-holders test, which finds nothing through the view.
- `_get_next_order_db` (`core/writes.py:1154`) counts live rows only, by design —
  a soft-deleted child's key is meant to be reused. The reissue is not a bug; the
  tie it creates on restore was. Reproduced: keys `1,2,3`, delete 3, create → 3
  again, restore → two live rows on key 3, order decided by id string.
- `reorder()` (`core/writes.py:1009`) is the only writer of `order_key` that
  takes a complete sibling list, and it renumbers `1..n` live rows. Any
  post-restore placement goes through it rather than writing keys directly.
- `validate_scene_dramatic_role` (`core/entity.py:1139`) allows `plot_role` with
  empty `plot_roles`, so a scene that loses its only role in a `take` stays valid.
  No follow-up decision is needed for the loser.
- Batch checks must all run against the state the batch started in, before any
  write. Interleaved, a target's collision was judged after an earlier target had
  moved the role, and the caller's resolution was silently dropped.

### Deviations
- Spec §8 offers three position resolutions ("after its old neighbour [default] /
  before the next / pick a position"). By owner decision the restore always takes
  the first and reports it in `placed`; only the role collision is refused for a
  decision. The reason: "after its old neighbour" is the only option carrying
  information, and a refusal would dead-end the Trash tab until T13 builds a
  position picker.
- Spec §8 says `restore` "returns an error". It returns a dict carrying
  `code=restore_needs_decision` and `collisions`, which `story_admin` passes
  through as JSON — the refusal is data the agent can act on, and the HTTP route
  turns the same dict into a 409. `restore_many` still raises `RestoreRefused`
  for a batch, because there the payload is per-target.

### Issues
- `restore` (single) does not apply `restore_check`'s structural blockers — a
  parent still in the trash — and did not before this task. The dashboard route
  checks first; the agent's path does not. Unchanged here because it is not this
  feature's guard, but a T11 agent tool that restores must not rely on it.
- `ruff check` reports a pre-existing `F401` in `tools/story_admin.py`
  (`purge_cutoff`, imported and unused at `dev`). Part of T0's 263-finding
  backlog, not touched here.
- `tests/test_live_relations.py` pins the exact set of raw `relations` reads with
  a count per file — currently `core/db.py` 1 (the view's definition),
  `core/integrity.py` 2 (the oracle), `core/trash.py` 3 (the restore guard). A
  new legitimate read means updating that registry **and** its docstring reason,
  because the assertion message alone does not tell the next reader why the count
  moved.
- The Trash tab's UI work landed in this task, not T13: the refusal it introduces
  would otherwise make a collided scene unrestorable from the browser. The panel
  now sends `resolutions`; the `placed` result is still not surfaced.

---

## T2 — `load_database_in_place`, `apply_op` public

### Findings
- `reorder()` now accepts `project_path=None` when the caller supplies `conn`
  (`core/writes.py:1009`, with an assert spelling out the contract). T1 needed
  it to renumber from inside `restore`'s transaction. An `apply_op` that issues a
  reorder inside the executor's transaction uses the same form; do not reopen a
  second connection for it.
- `reorder()` takes a **complete** sibling list and renumbers `1..n`  — it does
  not verify completeness (`F13`). Inside a transaction it will happily number a
  partial list, so the completeness assertion belongs to the caller (T7's
  planner). Extracting `apply_op` must not move that responsibility into the
  already-public function.
- `core.backups.load_database_in_place(project_path, source, *, safety_label)`
  copies a **checked** file into the live database and returns the safety
  backup's path. Source validation (integrity, entities table, schema version)
  stays in `restore_backup`; the loader owns the target-missing refusal, the
  page-size refusal (before the safety backup, as before), the copy, the
  migration and the post-copy integrity check. T3's branch switch calls it with
  a snapshot or parked head and `safety_label="before-switch"`; it must still
  run `restore_backup`'s source checks itself, since the loader does not.
- `core.drafts.apply_op(project_path, op, conn=None)` is the former `_dispatch`,
  renamed only. It returns a refusal as `{"error": …}` via `_call` and never
  raises for a refused write; `commit`'s loop and the merge executor both key on
  that. `sorted_ops` and `OP_ORDER` are untouched.

### Deviations
- The loader takes the safety backup (decision in the T2 task file). The spec
  describes the extraction as "extracted into a function that takes any
  validated source file"; the safety backup had to land on one side of the split
  and the loader is the side T3 needs it on.

### Issues

---

## T3 — `history.db` and `store.py`

### Findings
- Branch switch calls `core.backups.load_database_in_place(project_path, source,
  safety_label="before-switch")` to copy a snapshot or a parked head into the
  live database. It returns the safety backup's path. It does **not** validate
  the source: integrity, `entities` table and schema-version checks stay in
  `restore_backup` and the switch must run the equivalent itself. It also does
  not check page size against anything but the live database — a snapshot has
  the same page size by construction, so that is the only case it refuses.
- Two strings inside the loader still say `"cannot be restored in place"` (page
  size) and `"failed its integrity check after the restore"`. They reach the
  caller for a switch too. Reword both to the neutral copy in T3's commit and
  update the two `tests/test_backups.py` assertions that pin them; T2 left them
  byte-identical on purpose, because rewording is observable behaviour. A third,
  `"This project has no story.db to restore into."`, cannot fire during a switch
  (the live database is the current branch's head) and needs no change.
- `restore_backup` now takes its safety backup *inside* the loader, so a caller
  that wants a labelled "before" state of the live database around a switch gets
  it from the same call — do not take a second one.

### Deviations
### Issues

---

## T4 — `ProjectView` and the logical entity

### Findings
### Deviations
### Issues

---

## T5 — `refmap`

### Findings
### Deviations
### Issues

---

## T6 — Diff

### Findings
- `live_relations` hides every relation row either end of which is deleted, so
  "trash ignored" (§6.1) comes for free on that path. A raw `FROM relations`
  read does not: a trashed scene still holds its `plot_<role>` rows and its
  cast rows. Read the view, or filter `is_deleted` explicitly.
- Two **live** siblings can already share an `order_key`: a delete frees a key,
  `_get_next_order_db` reissues it, and a restore leaves the pair in place. So
  the child order must be serialized as the `(order_key, id)` id list (§4.4's
  fingerprint does this too), never as the raw key values — two states that
  differ only in which of two tied siblings sorts first would otherwise diff as
  equal.
- `tests/test_live_relations.py` pins every raw `relations` read with a count
  per file. A diff that needs one must add itself to that registry and its
  docstring reason, or the suite fails with an unexplained count mismatch.

### Deviations
### Issues

---

## T7 — Planner

### Findings
- D6 ("trashed in target") reuses the restore guard. `restore_check(conn, id)`
  already reports `collisions` (a singular role held by a live scene, with the
  holder and the two choices) and `placement` (another live sibling on the same
  `order_key`). The planner's D6 decision and D4/D3 expansions map onto those two
  payloads; it does not need a second collision scan.
- A plan that applies several ops has the same hazard `restore_many` had: a
  check evaluated after an earlier op moved the state it depended on reports the
  wrong thing. Evaluate every decision against the plan's starting state, then
  emit the ordered ops.
- **The D4 "to verify" is settled.** §7.5 asked whether a scene that loses its
  only plot role to `Theirs` stays valid. It does:
  `validate_scene_dramatic_role` (`core/entity.py:1139`) accepts
  `dramatic_role='plot_role'` or empty with an empty `plot_roles`, and
  `validate_scene_plot_roles` only rejects a *singular* role held twice. The
  loser needs no follow-up decision (no mark-as-transition, no
  assign-another-role): its beats, cast and other plots' roles are untouched, and
  T1's `take` resolution performs exactly this write.
- **D6 must not double-place.** `core.trash.restore` already settles the restored
  row's position (renumbers the parent through `reorder`, reports `placed`). A D6
  plan that also emits a `reorder` for the same parent renumbers it twice, and
  the second is built from a list the planner computed before the restore ran.
  Take the restore's `placed` as the outcome and emit no reorder for that parent.

### Deviations
### Issues

---

## T8 — Executor

### Findings
- A restore executed by the merge is `core.trash.restore(..., resolutions=[…])`
  with the `take`/`drop` the D4 decision chose. It resolves the role and settles
  the position in the same transaction as the flag clear, so the executor does
  not need a separate reorder step after an incoming scene that lands on a taken
  key.
- `restore` returns `code=restore_needs_decision` and writes nothing when a
  collision has no resolution. The executor must treat that return as a failed
  dry run mapped back to the D4 item, not as a success with a missing role.
- A `restore` op is not in the agent-visible op vocabulary (`OP_ORDER`), and
  `_dispatch` (`core/drafts.py:692`) has no `restore` branch — it dispatches
  `create`/`edit`/`delete`/`reorder` to `core.writes` and `purge` straight to
  `core.trash.purge_deleted`. So there is precedent for an op reaching
  `core.trash`, but `apply_op` will be the first caller of `trash.restore` from an
  op. §7.7's "restore is internal to the executor" means the executor calls
  `core.trash.restore` itself; do not add a `restore` kind to the public op
  vocabulary, which is what the agent's `story_draft` schema is built from.
- `reorder` inside the executor's transaction passes `project_path=None` and the
  live `conn`; it does not open a connection per op.
- Position is already settled by a restore and already released by a delete;
  the executor's own ordering work is the §7.7 order (restores → edits that
  release roles → deletes → creates → other edits → reorders) and the
  complete-sibling-list rule from F13, nothing more.

### Deviations
### Issues

---

## T9 — Persistent merge sessions

### Findings
- A session's stored decisions are keyed by item path; T1's `resolutions` shape
  (`{plot, role, choice: drop|take}`) is the value a D4 decision writes. Persist
  the shape as-is — the executor hands it straight to `core.trash.restore`, so a
  session that round-trips through the manifest must not rename `choice`.
- `restore_needs_decision` is a refusal *result*, not an exception, and it
  carries `collisions`. If a session records "unresolved" it must record which
  collision, not only that apply failed.

### Deviations
### Issues

---

## T10 — HTTP routes

### Findings
- The trash routes are the shape to copy for a core refusal: the core returns a
  dict with `error` **plus** a `code` (`restore_needs_decision`) and its payload
  (`collisions`), and the route maps it to `409` with
  `{"error": {code, message, …payload}}` (`app/routes/trash.py:56`,
  `_restore_refusal`). §10's "existing error shape" is that envelope;
  `_err(status, code, message, **extra)` (`app/routes/trash.py:31`) is the helper,
  defined locally in that module and not yet shared.
- A refusal that a caller must act on carries its payload at the **top level of
  the error object**, not nested under a second key — `collisions` and `blockers`
  sit beside `code` and `message`, and the dashboard reads them there.
- `restore_many` raises `RestoreRefused` for a batch while `restore` returns a
  dict; the route catches the exception and folds `refused[*].collisions` into one
  list. A merge route that applies a planned batch will hit the same split.

### Deviations
### Issues

---

## T11 — Agent tools

### Findings
- `story_admin`'s `restore` now refuses a singular-role collision with
  `code=restore_needs_decision` and an optional `resolutions` array
  (`[{plot, role, choice: drop|take}]`). The `story_history` / `story_merge`
  modules must not restate this: the refusal names the fix, and the role
  decision is the user's.
- `core.trash.restore` (single) still does not apply structural blockers (a
  parent in the trash). The dashboard route checks `restore_check` first. A new
  tool that restores must check it too, or the refusal text it relays will not
  match what the app would do.

### Deviations
### Issues

---

## T12 — Agent approval card

### Findings
- A scene that loses its only plot role to a `take` stays valid
  (`core/entity.py:1139`), so an approval card never needs a follow-up prompt for
  the losing scene.
- The core's refusal carries everything the card draws: the collision's `message`
  is written in the repo's agent-facing style and names the fix, `holder` names
  the other scene, and `choices` says what to offer. The card renders those; it
  must not invent a third option.

### Deviations
### Issues

---

## T13 — UI

### Findings
- The Trash tab's own restore path is already wired for the guard: a collided
  row carries a "needs a decision" chip, the panel draws the two choices, and
  `restoreKeys` sends `resolutions`. What T13 adds is the *history* workspace's
  version of the same decision, not the Trash tab's.
- `GET /api/projects/{slug}/trash` carries `restore.collisions` on every row,
  next to `restore.blockers` and `restore.placement`.
- `POST /trash/restore` and `POST /trash/{etype}/{eid}/restore` accept
  `resolutions: {target_id: [{plot, role, choice}]}`. `choice` is `drop` or
  `take`; the payload's `choices` per collision is what to offer.
- `restore` and `restore_many` return `placed` when the row's position was taken
  while it was in the trash: `{position, after, was_taken_by}` (single) or a list
  (batch). The Trash tab does not surface it yet — it says how many came back,
  not where the scene landed.

### Deviations
### Issues
