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
- `_get_next_order_db` (`core/writes.py:1155`) counts live rows only, by design —
  a soft-deleted child's key is meant to be reused. The reissue is not a bug; the
  tie it creates on restore was. Reproduced: keys `1,2,3`, delete 3, create → 3
  again, restore → two live rows on key 3, order decided by id string.
- `reorder()` (`core/writes.py:1009`) is the only writer of `order_key` that
  takes a complete sibling list, and it renumbers `1..n` live rows. Any
  post-restore placement goes through it rather than writing keys directly.
- `validate_scene_dramatic_role` (`core/entity.py:1165`) allows `plot_role` with
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
  a count per file. Adding a legitimate one means updating that registry **and**
  its docstring reason; the assertion message alone is not enough context for
  whoever hits it next. `core/trash.py` went from 1 to 3.
- The Trash tab's UI work landed in this task, not T13: the refusal it introduces
  would otherwise make a collided scene unrestorable from the browser. The panel
  now sends `resolutions`; the `placed` result is still not surfaced.

---

## T2 — `load_database_in_place`, `apply_op` public

### Findings
### Deviations
### Issues

---

## T3 — `history.db` and `store.py`

### Findings
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

### Deviations
### Issues

---

## T9 — Persistent merge sessions

### Findings
### Deviations
### Issues

---

## T10 — HTTP routes

### Findings
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
