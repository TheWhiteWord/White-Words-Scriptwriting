# Scene plot roles — spec

## Problem

A scene's `plot_roles` is the write side of a plot role: a list of
`(plot, role, description)` entries, stored as one `plot_<role>` relation row
each (`core/entity.py:606-640`). Two things are wrong.

**1. The manual form and the agent path disagree.** Measured on the current
branch (`task-38-structured-scene-heading`):

| Path | Same plot, two different roles | Same plot, same role twice |
|---|---|---|
| Agent (`create_entity` / `edit_entity` / `story_draft`) | allowed — two rows (`plot_setup`, `plot_inciting_incident`) | `IntegrityError: UNIQUE constraint failed: relations.from_id, relations.to_id, relations.kind` |
| Manual form (`create_form_entity` / `edit_form_entity`) | refused | refused |

So an agent can write a scene the form then refuses to save.

**2. No role is marked unique.** Every role is treated as spans-many-scenes,
but three of them are one-moment-by-definition. A plot can currently hold two
climaxes — the same class of error as the split above, and nothing says which
roles are singular.

The read side is not involved in either: `core/db.py:491-500`,
`core/manual_entities.py:663-668` and `tools/story_load.py:339-351` all build a
list and already report every role (`story_load.py:350` documents "One plot can
promote the same scene twice (setup and crisis)").

Enforcement of the current rule lives at **two** layers:

1. `core/manual_entities.py:967-970` — a `seen` set of plots rejects a repeated
   plot. Live on create and edit (`_validate` runs in both).
2. `web/js/forms/entity-form.js:324,330` — `repeaterHtml` removes every plot
   already picked in another card from the dropdown, so the second card cannot
   even be filled in. `chosen` is used only here.

## Target model

Two rules, both about the **pair** `(plot, role)`:

- **R1 — within a scene.** A scene lists each `(plot, role)` once. The
  `relations` primary key `(from_id, to_id, kind)` (`core/db.py:34-41`) already
  makes this the storage rule; it just surfaces as a raw `IntegrityError`.
- **R2 — across scenes, for singular roles.** A plot holds a singular role on
  **one scene at most**.

| Role | Spans scenes | Singular per plot |
|---|---|---|
| `setup` | yes | no |
| `inciting_incident` | no | **yes** |
| `complication` | yes | no |
| `crisis` | no | **yes** |
| `climax` | no | **yes** |
| `resolution` | yes | no |

So `UNIQUE_PLOT_ROLES = ("inciting_incident", "crisis", "climax")`, defined
beside `PLOT_ROLES` (`core/constants.py:27`).

Both rules live in one place: `validate_scene_plot_roles`
(`core/entity.py:951-973`), which every `writes` scene create/edit already calls.
It gains two optional arguments — `scene_id` (a scene editing itself is not a
conflict with itself) and `conn` (see the importer below).

**The importer is a third write path and must be covered.**
`tools/story_import.py` inserts scenes directly (`:377`), so it never calls the
validator today — it only calls `validate_scene_dramatic_role` (`:629`). It
also runs one transaction for the whole pass (`:190-205`) while `get_db` opens
a **new** connection each call (`core/db.py:109-123`), so a validator using its
own connection would not see scenes imported earlier in the same pass. The
validator therefore takes the caller's `conn`; the importer passes the one it is
transactioning on. This also fixes a silent drop on import: a role outside the
six currently yields no row and no complaint (`plot_role_relations` skips it).

The form needs no rule of its own. `create_form_entity` validates at `:1174-1179`
before writing at `:1196`, so a refusal from the shared validator reaches the
user through the existing `_form` banner (`_write_error`) — the same channel
`_write_sheet` already uses for a beats refusal. The per-card `seen` branch is
deleted rather than re-keyed.

## How the agent hears about it

The agent has no direct create/edit tool — every write goes through
`story_draft`. Staging is **structural only**: `validate_ops`
(`core/drafts.py:61-68`) says cross-entity rules "stay at commit: they read
committed state, and a staged create is not there yet". So a uniqueness
violation is caught at **commit**, never at stage — the same as every other
cross-entity rule (`validate_scene_location`, `check_references`,
`validate_scene_dramatic_role`).

Commit funnels it: `_call` (`core/drafts.py:478-489`) turns the raise into
`{"error": "ValueError: ..."}`, the report names the op (`❌ ops[N] — …`) under
`⚠️ Partly saved`, the draft stays open and the ops before it stay landed. The
agent is told to re-stage the remainder. That channel is already pinned by
`tests/test_draft_preview.py:239-249`.

The rule reaches the agent *in advance* through `story_describe`, which reads
`ENTITY_SCHEMAS[].description` (`tools/story_describe.py:96-133`) — so change
#2 is the agent-facing contract, not just prose for the form.

Two consequences for the message itself:

- It must name the **plot**, the **role**, and the **scene that already holds
  it** — otherwise the agent cannot fix the draft, which is the whole point of
  refusing.
- It is prefixed `ValueError:` by `_call`. That is the existing shape for every
  write refusal; not worth a special case.

Existing data is unaffected: the rule is checked on write. Measured on the live
project (`browser-verification-test`), the only multi-scene role is
`the-resistance / plot_setup` — `setup` is not singular, so nothing violates R2
today.

## Changes

| # | File | Change |
|---|---|---|
| 1 | `core/constants.py:27` | Add `UNIQUE_PLOT_ROLES = ("inciting_incident", "crisis", "climax")` beside `PLOT_ROLES`. |
| 2 | `core/constants.py:247` | `plot_roles` description: state R1 and R2 — one entry per plot *and* role; `inciting_incident`, `crisis` and `climax` belong to one scene per plot; a scene may hold several roles in one plot. Fix the stale comment above it (`:241-244`): "the plot's five fields" — there are six. |
| 3 | `core/entity.py:951-973` | `validate_scene_plot_roles(project_path, entries, scene_id=None, conn=None)`: keep the role-enum and plot-present checks; add R1 (duplicate `(plot, role)` in `entries`) and R2 (`SELECT` for another live scene holding `from_id=plot, kind=plot_<role>`, excluding `scene_id`). Opens its own connection only when `conn` is not given. Each message names the plot, the role, and the scene that already holds it — the agent must be able to act on it at commit. |
| 4 | `core/writes.py:241,690` | Pass the scene's slug / `entity_id`, and the `conn` already in scope. |
| 5 | `tools/story_import.py` (`_import_folder`, scene branch, before `_insert_entity`) | Call `validate_scene_plot_roles(project_path, fm.get("plot_roles", []), conn=conn)`. The existing `validate_scene_dramatic_role` call is in `_extra_for` (`:627-630`), reached through `_columns_for` (`:375`) — that path has no `conn`, so the new call goes here, not beside it. `_absorb_content_heading` does not touch `plot_roles`, so the raw frontmatter is the right thing to validate. |
| 6 | `core/manual_entities.py:967-970` | Delete the `seen` duplicate-plot branch. Keep plot-required, plot-exists and role-valid. |
| 7 | `web/js/forms/entity-form.js:324,330` | Drop the `chosen` const and pass `[]` to `entityOptions`, so a plot used in another card is offered again. |
| 8 | `core/entity.py:979-981` | `validate_scene_dramatic_role` docstring says "one entry per plot"; reword to match. Docstring only. |
| 9 | `tests/test_manual_structure.py:139-146` | `plot_roles.1.plot` (main/crisis after main/climax) must be **absent** from errors; `ghost` and the role-less card still error. Add a round-trip: one plot, two roles saves and reads back as two entries. |
| 10 | `tests/test_scene_plot_roles.py` (`TestValidation`) | R1: same plot, same role twice → `ValueError`, not `IntegrityError`. R2: a second scene taking another scene's `climax` (or `crisis` / `inciting_incident`) in the same plot → `ValueError`; the same role in a *different* plot, and a second `setup`, are allowed. |

No skill change: the shipped `SKILL.md` does not mention `plot_roles`; the
"one entry per plot" line lives only in the historical task doc
`tasks/task_30/skill/references/craft/scene-design.md`, which is not shipped.

## Implementation notes

- **Import `get_db` inside the function.** `core/db.py:10` imports
  `PLOT_BEAT_FIELDS` from `entity.py`, so a module-level `from .db import get_db`
  in `entity.py` is circular. Copy `validate_scene_location`
  (`core/entity.py:733`), which imports locally.
- **The plot's singular fields stay lists.** `inciting_incident`, `crisis` and
  `climax` are `type: list`, computed (`core/constants.py:145,147,148`). R2
  makes them hold at most one entry; every reader already handles a list. Do not
  "fix" them to scalars.
- **Change #2 does not change the form.** The repeater's help line comes from
  the `HELP` table, not the schema description (`web/js/forms/entity-form.js:
  220,223`; `core/manual_entities.py:324-350` returns before reading it). The
  description is the agent's contract, via `story_describe`.
- **`restore` cannot create an R2 violation.** `delete_entity` sweeps the
  scene's rows (`tests/test_scene_plot_roles.py:232-237`), and `_restore_entity`
  only clears `is_deleted` (`tools/story_admin.py:321-322`) — a restored scene
  comes back with no roles. No check needed on that path.
- **No fixture breaks.** `tests/fixtures/save-the-children` has no multi-scene
  role at all, so the new import check does not disturb the export/import
  round-trip tests.

## Verification

```
.venv/bin/python -m pytest tests/test_manual_structure.py tests/test_scene_plot_roles.py tests/test_write_shape.py -q
```

Plus the probe that produced the table above: agent write of one plot with two
roles → two rows; exact duplicate → `ValueError`; a second scene taking the
plot's `climax` → `ValueError`; the form saving one plot with two roles → saved.

## Rejected alternatives

- **Silently dedupe in `plot_role_relations`.** Drops a description the author
  wrote. A duplicate is an authoring error and should be said, not absorbed.
- **Enforce R2 with a DB partial unique index on `(from_id, kind)`.** A schema
  migration for three roles, and it would refuse the first write without naming
  the scene that already holds the role. The app-level check says which scene,
  which is what the author needs.
- **Per-card uniqueness message in the form.** Duplicates the query the shared
  validator runs — the same duplication that produced the split. The `_form`
  banner already names the plot and role.
- **Refuse multiple roles per plot on both paths.** That is the split the owner
  is removing, in the other direction.
- **Delete the form check only.** An exact duplicate then reaches the DB and
  surfaces as a raw `IntegrityError` — a trust boundary with no message.

## Open questions

None. Decisions taken: allow multiple roles per plot; R1 and R2 refused on
every write path — agent, form, importer.
