# Scene plot roles — implementation plan

Spec: `roles_spec.md`. Three phases, in order. Each ends at a gate; the order is
not negotiable — Phase 2 removes the form's own enforcement, so the shared
validator must already refuse the same inputs, or an exact duplicate reaches
the `relations` primary key and surfaces as a raw `IntegrityError`.

## Comment hygiene

When editing a file, delete comments that only record history — "was X, now Y",
"used to", "this used to be", phase and issue references ("B12", "D1a"), and
"restored/rewritten after <incident>". State only what the code does now. Keep a
comment only when it explains a non-obvious *why* (a constraint, an invariant, a
trap). If a comment describes a change, it is a line in the git log, not a
comment.

## Code practices

- **One rule, one place.** R1 and R2 live only in `validate_scene_plot_roles`.
  The form and the importer call it; neither restates it. A second copy of this
  rule is what produced the split being fixed.
- **No new abstraction.** One tuple in `constants.py`, one function extended,
  two call sites. No helper, no config flag, no registry.
- **Deletion over re-keying.** The form's `seen` branch is deleted, not changed
  to hold pairs — the validator owns that now.
- **Do not touch the plot's computed fields.** `inciting_incident`, `crisis` and
  `climax` stay `type: list`; R2 caps them at one entry and every reader already
  handles a list.
- **Match the surrounding idiom.** Local `from ...db import get_db` inside the
  function (`entity.py` is imported by `db.py`), error messages that name what
  to fix, `ValueError` for a refused write.
- **Every new branch leaves a runnable check.** The validator's two rules get
  tests in `TestValidation`; the form change gets the updated card test.

## Phase 1 — The rule

**Goal:** both uniqueness rules exist, on every write path, and nothing else
changes behaviour.

Checklist:
- [x] `core/constants.py:27` — add `UNIQUE_PLOT_ROLES = ("inciting_incident",
      "crisis", "climax")` directly after `PLOT_ROLES`.
- [x] `core/constants.py:241-247` — rewrite the comment above `plot_roles`
      (it says "the plot's five fields"; there are six) so it states that a
      scene may hold several roles in one plot, and rewrite the field
      `description` to state R1 and R2: one entry per plot *and* role;
      `inciting_incident`, `crisis` and `climax` belong to one scene per plot.
- [x] `core/entity.py:951-973` — rewrite `validate_scene_plot_roles` as
      `(project_path, entries, scene_id=None, conn=None)`. Keep the role-enum
      and plot-present checks. Add:
      - **R1** — a `seen` set of `(plot, role)`; a repeat raises
        `Duplicate plot role: {plot} / {role} appears twice in this scene's plot_roles.`
      - **R2** — for each `role in UNIQUE_PLOT_ROLES`, query another live scene:
        ```sql
        SELECT e.id FROM relations r JOIN entities e ON e.id = r.to_id
        WHERE r.from_id=? AND r.kind=? AND e.is_deleted=0
        ```
        with `AND r.to_id<>?` appended only when `scene_id` is given. On a hit:
        `Plot '{plot}' already has its {role} on scene '{other}' — one scene per plot.`
      - Import `get_db` inside the function; open a connection only when
        `conn` is `None`, and close only the one it opened.
- [x] `core/writes.py:241` — pass `slug` and `conn` (create). `core/writes.py:690`
      — pass `entity_id` and `conn` (edit). Both are already in scope.
- [x] `tools/story_import.py` (`_import_folder`, scene branch) — before
      `_insert_entity`, call
      `validate_scene_plot_roles(project_path, fm.get("plot_roles", []), conn=conn)`.
      Local import, matching `_extra_for`.
- [x] `tests/test_scene_plot_roles.py` (`TestValidation`) — R1: same plot, same
      role twice → `ValueError`, not `IntegrityError`. R2: a second scene taking
      another scene's `climax` (and one each for `crisis` /
      `inciting_incident`) → `ValueError`; the same role in a different plot,
      a second `setup` on another scene, and re-saving a scene's own roles are
      allowed.

**Gate:**
```
.venv/bin/python -m pytest tests/test_scene_plot_roles.py -q
```
Plus the probe: agent write of one plot with two roles → two rows; exact
duplicate → `ValueError`; a second scene taking the plot's `climax` →
`ValueError`; a second `setup` → allowed.

## Phase 1 brief — the rule

**Summary.** R1 and R2 now live in `validate_scene_plot_roles`
(`src/story_architect/core/entity.py:951`) and are reached from all three write
paths: `writes.create_entity`, `writes.edit_entity` (both pass `scene_id` and
the `conn` already in scope) and `tools/story_import.py:_import_folder` (passes
the transaction's `conn`). `UNIQUE_PLOT_ROLES` sits beside `PLOT_ROLES` in
`constants.py:30`. The `plot_roles` description — the agent-facing contract via
`story_describe` — now states both rules.

**Deviations.**

- **The spec's "no fixture breaks" claim was wrong.** It measured
  `tests/fixtures/save-the-children` (one scene, no multi-scene role) but
  `tests/test_response_budget.py::_grow` clones that fixture scene 48 times, so
  the grown vault had 48 scenes holding `the-resistance / inciting_incident`.
  The new import check refused it: **31 errors** in `test_response_budget.py`.
  Fixed in the test, not the rule — the clones are filler for a response-size
  test and their roles are noise. `_grow` now emits `plot_roles: []` for the
  clones (`tests/test_response_budget.py:53`). Errors → 0.
- **One test added beyond the checklist** — `TestImport`: two scene notes in one
  folder, the second taking the first's `climax`, import refused. The plan's
  `conn` requirement is a branch no write-path test covers: a validator on its
  own connection sees no uncommitted rows and would pass silently.
- **`test_one_plot_two_roles_writes_two_rows` added** — the split's core shape
  (one plot, two roles → two rows), which the checklist's R1/R2 items did not
  name but the gate probe does.

**Contract changes.** None beyond the spec. `plot_roles.description` changed
(agent-facing, via `story_describe`); the form's help line is untouched, as the
spec predicts.

**Verification.**

- Gate: `pytest tests/test_scene_plot_roles.py -q` → **35 passed** (26 at HEAD
  + 9 collected: 7 new methods, one of them parametrised over the three singular
  roles).
- Spec set: `pytest tests/test_manual_structure.py tests/test_scene_plot_roles.py
  tests/test_write_shape.py -q` → **133 passed**.
- Probe (agent path, `story_draft` stage → commit, scratch project):
  one plot two roles → `Committed`, rows `('main','sc1','plot_setup')` +
  `('main','sc1','plot_complication')`; exact duplicate →
  `ValueError: Duplicate plot role: main / climax appears twice in this scene's plot_roles.`
  under `⚠️ Partly saved`, draft kept; second scene taking `main`'s `climax` →
  `ValueError: Plot 'main' already has its climax on scene 'sc2' — one scene per plot.`;
  same role in another plot → committed; second `setup` → committed; re-saving
  a scene's own `climax` → committed.
- Full suite: **1310 passed, 2 failed, 0 errors** (baseline before the change:
  1279 passed, 31 errors, same 2 failures). Both failures reproduce at HEAD
  `625beac` in a clean worktree — `test_no_hermes_imports` (`app/server.py`
  already names `hermes`; my diff does not touch it) and
  `tasks/task_30/test_skill_references.py` (SKILL.md names `success: false`).
  Neither is this phase's.

Phase 1 → Phase 2 is ready to proceed.

## Phase 2 — The form

**Goal:** the form stops refusing what the agent may write, and stops filtering
the plot dropdown.

Checklist:
- [x] `core/manual_entities.py:959-970` — delete the `seen` set and its
      duplicate-plot branch. Keep plot-required, plot-exists and role-valid.
      Remove `seen` entirely if nothing else in the function uses it.
- [x] `web/js/forms/entity-form.js:322-337` — delete the `chosen` const and
      pass `[]` to `entityOptions` in the `sf.kind === 'ref'` branch, so a plot
      used in another card is offered again.
- [x] `core/entity.py:979-981` — reword the `validate_scene_dramatic_role`
      docstring ("one entry per plot") to match R1/R2. Docstring only.
- [x] `tests/test_manual_structure.py:139-146` — `plot_roles.1.plot`
      (main/crisis after main/climax) must be **absent** from the errors;
      `ghost` and the role-less card still error. Add a round-trip: one plot,
      two roles saves and reads back as two entries.

**Gate:**
```
.venv/bin/python -m pytest tests/test_manual_structure.py -q
```
Plus the probe: `create_form_entity` with one plot and two roles saves and
returns both entries.

## Phase 2 brief — the form

**Summary.** The form no longer restates the pair rules.
`_validate_kind_specific` (`core/manual_entities.py:951`) keeps only
plot-required, plot-exists and role-valid; the `seen` set and its
"one role per plot" branch are gone. `repeaterHtml`
(`src/story_architect/web/js/forms/entity-form.js:322`) passes `[]` to
`entityOptions`, so a plot picked in one card is offered again in the next.
`validate_scene_dramatic_role`'s docstring now states the pair rules instead
of "one entry per plot". A refusal from the shared validator still reaches the
user through the existing `_form` banner, unchanged.

**Deviations.** None. The spec's `web/js/forms/entity-form.js` path is the
repo-relative form; the file lives at
`src/story_architect/web/js/forms/entity-form.js`. `chosen` in
`refListWidget` (`:289`) is a different widget and was left alone.

**Contract changes.** None. The form's help line is untouched, as the spec
predicts; the only agent-facing contract remains the `plot_roles` description.

**Verification.**

- Gate: `pytest tests/test_manual_structure.py -q` → **40 passed**.
- Spec set: `pytest tests/test_manual_structure.py tests/test_scene_plot_roles.py
  tests/test_write_shape.py -q` → **134 passed**.
- Probe (`create_form_entity`, scratch project): one plot, two roles
  (`main/crisis`, `main/climax`) → saved and read back as
  `[('main', 'crisis'), ('main', 'climax')]`; `relations` holds
  `('main', 'dinner', 'plot_climax')` and `('main', 'dinner', 'plot_crisis')`.
- Grep: `one role per plot`, `already has a role`, `chosen(sf)` → no hits in
  `src/`; no test asserts the old refusal.

Phase 2 → Phase 3 is ready to proceed.

## Phase 3 — Cleanup

**Goal:** nothing the change made unused is left behind, and the whole suite is
green.

Checklist:
- [x] Grep for leftovers of the old rule and remove every hit:
      `one role per plot`, `One entry per plot`, `already has a role`,
      `chosen(sf)`, `seen` in `_validate_kind_specific`.
- [x] Confirm `UNIQUE_PLOT_ROLES` is imported where used and used once; confirm
      `PLOT_ROLES` is still imported/used in `entity.py`.
- [x] Confirm no new import is unused (`get_db` is used; `conn`/`scene_id`
      parameters are both read).
- [x] Confirm the `plot_roles` comment at `constants.py:241-244` and the
      `validate_scene_dramatic_role` docstring no longer contradict the rules.
- [x] Confirm no test asserts the old refusal
      (`grep -rn "one role per plot" tests/` → no hits).
- [x] Full suite:
      ```
      .venv/bin/python -m pytest -q
      ```
- [x] Re-run the four probes from Phase 1 and Phase 2 against a scratch project
      and confirm the outputs named in the gates.

**Gate:** the full suite is green and every grep above returns nothing.

## Phase 3 brief — cleanup

**Summary.** No leftovers found: nothing needed removing. The old rule's only
remaining strings are the two plan files' own briefs (history, not code) and
`tasks/to_do/NOTES.md:39-42`, which records the gap this change closed. Every
live copy is gone:

- `grep "one role per plot|One entry per plot|already has a role"` over `src/`
  → one hit, `constants.py:251`, which is the new description ("One entry per
  plot AND role"); zero hits in `tests/`.
- `chosen(sf)` → no hits; the `repeaterHtml` `chosen` const is deleted and
  `entityOptions` gets `[]`. `refListWidget`'s separate `chosen` is untouched.
- `seen` inside `_validate_kind_specific` (range 937–980) → no hits. The other
  `seen`s in `manual_entities.py` (value rungs, perspectives) belong to other
  branches and were already there.

`UNIQUE_PLOT_ROLES` is imported at `entity.py:10` and used once (`:992`);
`PLOT_ROLES` is still imported and used at `:631`, `:978`, `:981`. The local
`get_db` import at `:996` is reached on every singular check, and both new
parameters are read (`scene_id` at `:1005`, `conn` at `:997`). The
`plot_roles` comment (`constants.py:244-248`) now says "six fields" and states
the pair rules; `validate_scene_dramatic_role`'s docstring matches.

**Deviations.** None in code. Two things worth recording:

- **Full-suite count is 1311 passed / 2 failed**, not the 1310/2 in the Phase 1
  brief. `--collect-only` reports 1313 tests; the difference from 1310 is three
  extra collected tests, i.e. a test file changed outside this branch after the
  Phase 1 run. Same two failures as before, same cause (below), so not a
  regression from this phase.
- **Both failures are pre-existing and reproduce at `625beac`** (verified in a
  clean worktree): `test_no_hermes_imports` — `app/server.py:77` imports
  `adapters.hermes.chat_backend`, and the task_38 diff does not touch that
  file; `tasks/task_30/test_skill_references.py` — `SKILL.md` names
  `success: false`, which is not a schema parameter. Neither is this change's.
  The plan's gate ("full suite is green") is therefore met as far as this
  change can reach it: 0 failures attributable to task_38.

**Contract changes.** None.

**Verification.**

- Greps: every checklist pattern returns nothing in `src/` and `tests/` (see
  Summary).
- `pytest tests/test_manual_structure.py tests/test_scene_plot_roles.py
  tests/test_write_shape.py -q` → **134 passed**.
- Probe (scratch project, direct write + form + draft/commit):
  one plot two roles → committed, rows `(main, sc1, plot_setup)` +
  `(main, sc1, plot_complication)`; exact duplicate →
  `ValueError: Duplicate plot role: main / climax appears twice in this scene's plot_roles.`
  under `⚠️ Partly saved`; second scene taking `main`'s `climax` →
  `ValueError: Plot 'main' already has its climax on scene 'sc2' — one scene per plot.`;
  Same role in another plot → committed; second `setup` → committed; re-saving
  a scene's own `climax` → committed; form save of one plot with two roles →
  read back `[('main','crisis'), ('main','resolution')]`.
- Full suite: `.venv/bin/python -m pytest -q` → **1311 passed, 2 failed**
  (both reproduced at `625beac`).

## Phase 2.B — the form's live check

**Goal:** a singular-role conflict is reported while the person is still
choosing the role, instead of at save.

Checklist:
- [x] `core/entity.py` — `validate_scene_plot_roles` raises `PlotRoleError`, a
      `ValueError` carrying the offending `plot`/`role`, for R1 and R2.
- [x] `core/manual_entities.py:_validate_kind_specific` — once every card names
      a real plot and a real role, call the shared validator with the `conn` and
      `entity_id` already in scope; key the message to the offending card.
- [x] Tests: a taken `climax` names the other scene and lands on the card; the
      scene being edited excludes itself; a second `setup` and the same role in
      another plot pass; a duplicated pair lands on the second card.

**Gate:**
```
.venv/bin/python -m pytest tests/test_manual_structure.py -q
```
Plus the probe: `check_entity` with a taken `climax` returns the conflict under
`plot_roles.0.role`.

## Phase 2.B brief — the form's live check

**Summary.** The dry run now reaches the same rule the write path does.
`_validate_kind_specific` (`core/manual_entities.py:968-977`) calls
`validate_scene_plot_roles` with the connection and `entity_id` it already has,
after the per-card plot/role checks have passed, and keys the resulting message
to `plot_roles.{i}.role`. The JS already debounces `/check` and paints any error
keyed that way under the card, and its save button blocks review when
`check` returns `ok: false` — so no JS change was needed. The validator's pair
violations now raise `PlotRoleError`, which carries the pair so the caller can
find the card without parsing the message.

**Deviations.**

- **`PlotRoleError` is new.** The first cut attached `plot`/`role` to a plain
  `ValueError`; Pyright rejects attribute assignment on a built-in type. A
  small typed subclass states the contract instead of dodging the checker.
- **`project_path` may be `None`** when the caller supplies `conn` (only read
  to open one otherwise). Documented in the validator docstring.
- **One stale line removed:** `entity-form.js` re-rendered the body when a
  repeater's plot changed, because the other cards' choices used to exclude it.
  With the filtering gone nothing depends on that (`SHOW_IF` has no entry for
  `plot_roles`; the derived block reads the original values), so the re-render
  and its comment are deleted rather than reworded.

**Contract changes.** None. The agent path never used the dry-run channel; the
write path's behaviour and messages are unchanged, and `PlotRoleError` is a
`ValueError`, so every existing `except ValueError` still catches it.

**Verification.**

- Gate: `pytest tests/test_manual_structure.py -q` → **45 passed**.
- Spec set + neighbours (`test_manual_structure`, `test_scene_plot_roles`,
  `test_write_shape`, `test_core`, `test_story_load_views`, `test_plot_roles`,
  `test_draft_preview`, `test_import_enum_validation`, `test_response_budget`,
  `test_story_describe`) → **400 passed**.
- Full suite: `pytest -q` → **1316 passed, 2 failed** — the same two
  pre-existing failures recorded in the Phase 1 and Phase 3 briefs
  (`test_no_hermes_imports`, `tasks/task_30/test_skill_references`), both
  reproduced at `625beac`.
- Probe (`check_entity`, the endpoint the form calls on every keystroke):
  a second scene taking `main`'s `climax` →
  `errors["plot_roles.0.role"] == "Plot 'main' already has its climax on scene 'first' — one scene per plot."`;
  the scene that owns the `climax` re-checked against itself → no `plot_roles.*`
  errors; a second `setup` → clean; `sub`/`climax` while `main`/`climax` exists →
  clean; `main`/`crisis` twice in one scene →
  `errors["plot_roles.1.role"] == "Duplicate plot role: main / crisis appears twice in this scene's plot_roles."`

## Phase 1 brief — the draft dry-run replay

**Summary.** `dry_run(project_path, draft_id)`
(`src/story_architect/core/drafts.py:430`) copies `<project>/.story/story.db`
into a `TemporaryDirectory` outside the project through `Connection.backup()`
(WAL-safe), runs the existing `commit()` against the copy, maps the result to
`clean` / `refused` / `unavailable`, and lets the context manager remove the
copy on every path. `stage()` now sets `result["dry_run"]` after the draft row
is written; nothing else in the response changed. The module docstring names
`commit` (the stale `commit_draft` is gone) and states that the replay
dispatches into `core.writes` on the copy, so the project's tables go
untouched.

**Deviations.** None. The two HIGH findings from `verification_findings.md` are
met as resolved: the copy's file set — not the real project's — is the primary
isolation assertion, and a `commit` exception maps to `unavailable` rather than
propagating. The `unavailable` path is exercised by patching `drafts.commit` to
raise.

**Contract changes.** `stage`'s response gains `dry_run` (spec change #2). The
three verdict shapes are the spec's: `{"status": "clean"}`, `{"status":
"refused", "failed_op", "error"}`, `{"status": "unavailable", "error"}`.

**Verification.**

- Gate: `pytest tests/test_draft_dry_run.py tests/test_drafts.py -q` →
  **44 passed**.
- Neighbours: `tests/test_draft_preview.py tests/test_story_draft_tool.py
  tests/test_value_turns.py` → **109 passed** with the gate files.
- Probe (scratch project built from the fixture markdown): refused batch →
  `{"status": "refused", "failed_op": "edit scene/the-core-day", "error":
  "PlotRoleError: Plot 'the-resistance' already has its climax on scene
  'central-room-night' — one scene per plot."}`; the real `commit` of the same
  draft returned the identical `failed.error`; entity/section/relation counts
  and the project file tree were unchanged; the freeing batch (clear night's
  climax, give it to the core) → `{"status": "clean"}`.
- Full suite: **1323 passed, 2 failed** — the same two pre-existing failures
  (`tests/test_no_hermes_imports.py`, `tasks/task_30/test_skill_references.py`),
  both unrelated to this change. 1323 = the 1316 baseline + 7 new tests.


