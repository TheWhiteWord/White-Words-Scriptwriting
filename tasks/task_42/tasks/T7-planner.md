# T7 — Planner: three-way, dependencies, decisions D1–D9

Spec: `../spec-draft-versioning.md` §7.1–7.6 (shape, items, three-way, dependencies,
decisions), §7.7.1 (plan output), §9 (`plan.py`), §13 T7, §15 (merge tests).
Branch: `draft-versioning`.
Baseline: `1906 passed, 1 failed` on this branch before starting (the known
`test_no_hermes_imports`; same count T6 recorded).

Status: **done** — planner, merge base, 55 planner tests + 6 merge-base tests, suite
green against baseline. See Final Brief at the end.

## Objective

Three states in, an ordered op list plus the list of decisions that are still open, out.
Nothing is applied and nothing is guessed silently.

The planner is the only place that answers, for one authored difference: *did this
change on my side, on theirs, both, or neither — and if both, what are the user's
options?* §7.3 fixes the four-row table for a single item; §7.4 expands a selection
into the items it drags along; §7.5 is the catalogue of the eight situations that
cannot be resolved by the table alone. The output is §7.7.1's: ops in the existing
`core.drafts` vocabulary (`create` / `edit` / `delete` / `reorder`, plus `restore`
internal to the executor, §7.7.2) and the decisions still unresolved.

Out of scope (later tasks): executing the plan, the dry run and the stale-plan guard
(T8); persisting a session (T9); routes (T10); agent tools (T11); any UI.

## Verified before starting

Every row is a probe on this branch against the fixture, not a reading of the spec.

| # | Claim | Evidence |
|---|---|---|
| 1 | `diff.compare(base, side)` reports an added or removed entity as a key and identity **only** — no fields, no sections | probe: adding character `newbie` in `b` → `entities["newbie"] == {"id","type","status":"added"}`. The incoming content is **not** in the diff; the planner must load its own shapes (`diff.load`) to build a create. |
| 2 | An entity id is global across types and is refused at create even when the row is in the **trash** | probe: `create_entity` over a trashed `mira` → `ValueError: Entity already exists: character/mira`. So D6 cannot be a create; it must be a restore-then-edit. |
| 3 | `edit_entity` refuses a trashed row | probe: `Entity not found: scene/the-core-day` after a delete. Nothing can be edited into place while it sits in the bin. |
| 4 | `delete_entity` cascades a scene's `scene_beats` row and hides referring relations | probe: `cascade_deleted: ['central-room-day-beats']`, `references_hidden: [kael-mira, kael-the-administrator]`. §7.4's "the scene's beats go with it automatically" is the write path's own behaviour, so the planner emits no separate beat delete. |
| 5 | `create_entity` from a **full materialized shape** reproduces the scene exactly, including `characters` and `plot_roles` | probe: create scene from `logical.materialize` fields + sections → re-materialized fields equal. The shape is creatable as-is, which is what makes one `create` op enough. |
| 6 | A singular role already held in the target is refused at create with the holder named | probe: `PlotRoleError: Plot 'the-resistance' already has its inciting_incident on scene 'central-room-day' — one scene per plot.` That refusal is what D4 (and §7.7.2's ordering) exists to avoid. |
| 7 | `reorder` accepts a **partial** sibling list and renumbers it `1..n`, silently leaving the rest | probe: `reorder(["central-room-day"])` in a three-scene sequence → `success`, keys `1,2,3` with the untouched scenes keeping stale numbers. Confirms F13/T2: completeness is the caller's assertion. |
| 8 | An add produces **two** items: the entity and the parent's order list | probe: add a scene → `entity:scene:extra` **and** `order:scene:seq-discovery`. So a parent's order item is present whenever either side added or removed a child. |
| 9 | Each side adding a *different* scene to the same sequence produces the **same** `order:` key on both sides, while the order of the common ids is unchanged on both | probe: ours adds `ours-new`, theirs adds `theirs-new` → both emit `order:scene:seq-discovery`; restricting each side's list to the ids all three states share makes the two lists **equal**. So that shared order item is not a D7 conflict. |
| 10 | A removal in ours against a rename/edit in theirs yields two different keys, not a conflict the table can see | probe: ours deletes `central-room-night`, theirs renames it → ours `entity:scene:central-room-night` (removed), theirs `field:scene:central-room-night:name`. §7.3 has no row for "removed there, changed here"; §7.5 has no decision for it (see D-T7-B). |
| 11 | Trashing an entity adds cascade field-change items to every live referrer | probe: delete scene → `field:relationship:kael-mira:scenes` and `field:relationship:mira-the-administrator:scenes` appear as well as the two `removed` entities. T6 recorded the mechanism; the planner must not emit ops for these. |
| 12 | `logical.materialize` sees live entities only, so the target's **trash** is invisible to any diff | `WHERE is_deleted=0`. D6 needs its own query against `entities WHERE is_deleted=1`. |
| 13 | `restore_check(conn, id)` returns `collisions` (`{plot, plot_name, role, holder, choices, message}`) and `placement`, and `restore(..., resolutions=[{plot, role, choice}])` applies `drop` / `take` | `core/trash.py:412`, `:478`, `:957`, `:1014`. T1/T7 Notes: D6 reuses this; no second collision scan. |
| 14 | `restore` settles the restored row's position itself and reports `placed` | `core/trash.py:1081–1093`. Re-emitting a reorder for that parent would renumber it twice from a stale list. |
| 15 | `refmap.iter_references` yields concrete paths (`value_turns[0].effects[1].character`) and `rewrite` takes separate `by_id` / `by_name` spaces | `core/history/refmap.py:141`, `:155`. `value_turns[].value` is keyed by display **name**, so a keep-both on a value maps by name. |
| 16 | `refmap.DERIVED` covers `plot.<role>` (six) and `scene.act_id` / `scene.scene_beats`; `diff` already excludes them | `refmap.py:117`; T6 test pins a role edit to exactly `field:scene:<id>:plot_roles`. |
| 17 | An item's key is stable and already carries kind, type, id and name | `diff._items`: `entity:<type>:<id>`, `field:<type>:<id>:<name>`, `section:<type>:<id>:<name>`, `order:<type>:<parent>`. |
| 18 | No merge-base walk exists anywhere in the tree | `grep snapshot_parents` → only `store`'s save/delete/prune paths. `store` exposes `list_branches` (branches + snapshots + `parents`), which is the whole graph, and nothing computes an ancestor. |

## Decisions

### D-T7-A — where the merge base is computed (settled)

§7.1 needs the most recent common ancestor of the target branch's `base_snapshot` and
the source snapshot, walked over `snapshot_parents`. Nothing owned that before this task.

**Decision (owner):** `store.merge_base(project_path, target_snapshot_id,
source_snapshot_id)` → `{"base": id | None, "imprecise": bool}`, in the module that
already owns `snapshot_parents` and `list_branches`. `plan.py` takes three project
paths, keeping §9's layering (store = manifest, plan = files). T9 persists sessions on
top; it does not re-resolve the base.

### D-T7-B — "removed on one side, changed on the other" (settled: new decision D9)

Row 10. §7.3's table works per item and §7.5 has no decision for an entity deleted in
ours while edited in theirs (or the reverse). A mechanical "take theirs" would try to
edit a deleted row (impossible, row 3) or resurrect it silently.

**Decision (owner):** a ninth decision, `D9`, kind `deleted_and_changed`, options
**keep mine** (default: the deletion stands, the incoming edits are dropped), **take
theirs** (restore the row, then apply the edits — the side effect is that a deletion
the user made is undone), **keep the deletion** (same outcome as mine, offered
explicitly so the choice reads as a choice, not an omission). The warning names what
each side loses.

### D-T7-C — granularity of the multi-entry fields (settled: whole-value)

**Decision (owner):** keep T6's granularity. `scene.plot_roles`,
`scene_beats.beats`, a plot's role lists, `relationship.perspectives` and
`project.memory` are merged as whole values. Consequences the planner must handle
rather than hide: a `plot_roles` take replaces the scene's whole list, and the D4
role-collision check runs on the *resulting* list, so a take that would create a second
singular role is reported at plan time rather than half-applied. Revisit per-entry
selection only if real use demands it.

### D-T7-D — D1's conservative default (settled)

**Decision (owner):** **keep mine** — the incoming duplicate is dropped and ours is
untouched. `keep both` (new id) and `combine` remain available but are never the
default, because both of them write.

### Settled without asking

- **The planner emits ops; it never writes.** `segment`-free by construction: no
  `create_entity`/`edit_entity` call in `plan.py`.
- **`restore` is not an op kind in the public vocabulary** (§7.7.2, T8 Notes). The plan
  carries it as an internal `restore` entry the executor consumes; `OP_ORDER` and the
  agent's `scene_draft`-facing schema stay untouched.
- **Every decision is evaluated against the plan's starting state**, before any op is
  emitted (T7 Notes; the `restore_many` lesson).
- **A removal's cascade items produce no ops** (rows 4, 11).
- **An order list is asserted complete before it becomes an op** (row 7, F13/E).
- **Decisions are keyed on the diff's item key** (§7.5; T6's chosen format), so a
  re-plan keeps them.

## Tasks

- [x] `core/history/plan.py`: the item set — `base`/`ours`/`theirs` shapes, the union of
      diff items from both sides, each classified by §7.3's table.
- [x] `core/history/plan.py`: three-way resolution per item (`take theirs`, `keep ours`,
      `nothing`, `conflict`) built only on `diff.compare` output and the loaded shapes.
- [x] `core/history/plan.py`: the decision record — stable key, kind, options,
      conservative default, `set_by` (`default` | `user` | `agent-suggested`).
- [x] `core/history/plan.py`: D1 — same id added on both sides / added here and arriving
      from there; keep-mine, take-theirs, combine, keep-both with a new id; `refmap`
      rewrite of the incoming items on keep-both; the display-name warning (F14).
- [x] `core/history/plan.py`: D2 — the field / section / order conflict, Mine / Theirs /
      Custom, with computed fields never offered.
- [x] `core/history/plan.py`: D3 — placement of an incoming scene (after its source
      predecessor → before its successor → user picks), and the missing
      sequence/act resolution.
- [x] `core/history/plan.py`: D4 — singular-role collision: Mine / Theirs / Replace /
      Custom, reusing `restore_check`'s `collisions`; Theirs lists the losing scene as a
      side effect; Replace lists what else it loses.
- [x] `core/history/plan.py`: D5 — missing reference: bring / drop / cancel, driven by
      `refmap`'s `required` flag; recursion for "bring it".
- [x] `core/history/plan.py`: D6 — trashed in target: restore-then-edit, mapped onto
      `restore_check`'s `collisions` and `placement`, no duplicate reorder (row 14).
- [x] `core/history/plan.py`: D7 — order conflict, Mine / Theirs / Custom, computed over
      the ids the three states share (rows 8, 9).
- [x] `core/history/plan.py`: D8 — optional cleanup after a removal, unticked, only for
      entities no other live referrer keeps.
- [x] `core/history/plan.py`: the dependency expansion — "comes with it", "must resolve",
      "collides", "needs placement" (§7.4), and the removal expansion (§7.4's second
      half).
- [x] `core/history/plan.py`: the ordered op list in the `core.drafts` vocabulary, with
      §7.7.2's execution order recorded (the executor owns applying it).
- [x] `tests/test_history_plan.py`: §7.3's four rows; D1–D8 each with the accepted and
      the refused path; Replace with beats; the swap ordering; restore guard reuse;
      complete-sibling assertion; cascade items producing no ops.
- [x] `store.merge_base(project, target, source)` — the ancestor walk over
      `snapshot_parents`; `imprecise` on a tie (D-T7-A). Six cases: self, parent,
      siblings, nearest-ancestor preference, criss-cross tie, unknown draft.
- [x] `diff.compare_states(a, b)` — so the planner loads and compares one state pair
      per side instead of re-opening three database files.
- [x] `core/history/plan.py`: D9 — deleted on one side, changed on the other (D-T7-B).
- [x] Suite green against the `1906 passed, 1 failed` baseline; `ruff format --check`
      and `ruff check` clean on every touched file.

## Final Brief

**What the planner is.** `plan(base, ours, theirs, *, selection=None, decisions=None)`
returns `{items, decisions, open, ops, ready}`. It reads three project paths, never
writes, and imports nothing from `writes`. Ops are always returned with every default
already applied, so a caller's preview is exactly what Apply would do; `ready` is the
gate, and it is false only while an unanswered non-optional decision exists.

**Suite.** 1961 passed, 1 failed — the baseline's `test_no_hermes_imports`, unchanged.
1906 → 1961 is the 55 new planner tests plus 6 merge-base tests, minus none.

**Decisions shipped.** D1–D8 per §7.5, plus **D9** (`deleted_and_changed`) added for the
crossing §7.3's table cannot see (D-T7-B). D1 defaults keep-mine (D-T7-D); D4 is
evaluated on the resulting role list (D-T7-C); D2/Custom leaves the custom editor's
value alone; D3 is a proposal, never a blocker; D5 and D8 default to the non-destructive
option and are marked `optional`, so neither can hold Apply.

**Verified by mutation, not by assertion count.** Fourteen deliberate breaks were
introduced and each had to fail a test: item ordering, D9 detection, create dedupe,
release-before-create, D5's option list, keep-both, D8's candidate set and its optional
flag, D4 mine/theirs, both halves of placement, the sibling-completeness assert, and four
in `merge_base`. All are killed. Every plan-shape test that matters is also applied
through `apply_op` and re-read from the database, so "the plan is right" means "the
target ends up right".

**Deliberate ceilings.**

- `_settle_orders` asserts sibling-list completeness against a reorder that renumbers
  anything handed to it (F13). The assert now has a test that trips it on purpose;
  no well-formed plan reaches it.
- Whole-value merge for `plot_roles`, `beats`, perspectives and `memory` (D-T7-C). A
  take replaces the list; D4 catches the consequence.
- `merge_base` takes one candidate on a tie and sets `imprecise`, rather than merging
  recursively (§14-F). T9 and T10 must surface the flag; the planner accepts the base
  it is given.
- `restore` stays an internal op kind (§7.7.2). It is in `ops` for the executor only;
  `OP_ORDER` and the agent-facing schema are untouched.

**Not in this task.** Nothing applies the plan (T8), nothing persists a session (T9),
no route, no agent tool. `plan` takes paths, not snapshot ids — resolving a branch's
head and its base into those three paths is the caller's job (T9).

