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
- [ ] `core/constants.py:27` — add `UNIQUE_PLOT_ROLES = ("inciting_incident",
      "crisis", "climax")` directly after `PLOT_ROLES`.
- [ ] `core/constants.py:241-247` — rewrite the comment above `plot_roles`
      (it says "the plot's five fields"; there are six) so it states that a
      scene may hold several roles in one plot, and rewrite the field
      `description` to state R1 and R2: one entry per plot *and* role;
      `inciting_incident`, `crisis` and `climax` belong to one scene per plot.
- [ ] `core/entity.py:951-973` — rewrite `validate_scene_plot_roles` as
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
- [ ] `core/writes.py:241` — pass `slug` and `conn` (create). `core/writes.py:690`
      — pass `entity_id` and `conn` (edit). Both are already in scope.
- [ ] `tools/story_import.py` (`_import_folder`, scene branch) — before
      `_insert_entity`, call
      `validate_scene_plot_roles(project_path, fm.get("plot_roles", []), conn=conn)`.
      Local import, matching `_extra_for`.
- [ ] `tests/test_scene_plot_roles.py` (`TestValidation`) — R1: same plot, same
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

## Phase 2 — The form

**Goal:** the form stops refusing what the agent may write, and stops filtering
the plot dropdown.

Checklist:
- [ ] `core/manual_entities.py:959-970` — delete the `seen` set and its
      duplicate-plot branch. Keep plot-required, plot-exists and role-valid.
      Remove `seen` entirely if nothing else in the function uses it.
- [ ] `web/js/forms/entity-form.js:322-337` — delete the `chosen` const and
      pass `[]` to `entityOptions` in the `sf.kind === 'ref'` branch, so a plot
      used in another card is offered again.
- [ ] `core/entity.py:979-981` — reword the `validate_scene_dramatic_role`
      docstring ("one entry per plot") to match R1/R2. Docstring only.
- [ ] `tests/test_manual_structure.py:139-146` — `plot_roles.1.plot`
      (main/crisis after main/climax) must be **absent** from the errors;
      `ghost` and the role-less card still error. Add a round-trip: one plot,
      two roles saves and reads back as two entries.

**Gate:**
```
.venv/bin/python -m pytest tests/test_manual_structure.py -q
```
Plus the probe: `create_form_entity` with one plot and two roles saves and
returns both entries.

## Phase 3 — Cleanup

**Goal:** nothing the change made unused is left behind, and the whole suite is
green.

Checklist:
- [ ] Grep for leftovers of the old rule and remove every hit:
      `one role per plot`, `One entry per plot`, `already has a role`,
      `chosen(sf)`, `seen` in `_validate_kind_specific`.
- [ ] Confirm `UNIQUE_PLOT_ROLES` is imported where used and used once; confirm
      `PLOT_ROLES` is still imported/used in `entity.py`.
- [ ] Confirm no new import is unused (`get_db` is used; `conn`/`scene_id`
      parameters are both read).
- [ ] Confirm the `plot_roles` comment at `constants.py:241-244` and the
      `validate_scene_dramatic_role` docstring no longer contradict the rules.
- [ ] Confirm no test asserts the old refusal
      (`grep -rn "one role per plot" tests/` → no hits).
- [ ] Full suite:
      ```
      .venv/bin/python -m pytest -q
      ```
- [ ] Re-run the four probes from Phase 1 and Phase 2 against a scratch project
      and confirm the outputs named in the gates.

**Gate:** the full suite is green and every grep above returns nothing.
