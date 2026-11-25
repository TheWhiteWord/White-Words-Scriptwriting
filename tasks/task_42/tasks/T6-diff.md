# T6 — Diff: entity, order, script

Spec: `../spec-draft-versioning.md` §5.2 (structure as lists), §6.1 (entity diff),
§6.2 (script diff), §7.2 (items), §9 (`diff.py`), §13 T6, §15 (diff tests).
Branch: `draft-versioning`.
Baseline: `1878 passed, 1 failed` on this branch before starting (the known
`test_no_hermes_imports`).

## Objective

Two states in, one structured result out, because three readers consume it and none may
disagree: the entity view, the script view, and the planner. §6.2 is explicit that the
script view is "a lens over the same items, never a separate engine", and §7.2 that "the
diff yields items". So `compare(a, b)` returns all of it from one pass: per-entity field and
section changes, the per-parent child order, the per-scene script rows, and the flat item
list the planner builds selection and decisions on.

Out of scope (later tasks): three-way resolution and dependencies (T7), execution (T8),
routes (T10).

## Verified before starting

Every row is a probe on this branch, not a reading of the spec.

| # | Claim | Evidence |
|---|---|---|
| 1 | Order is NOT in the materialized shape, so a diff of shapes alone reports a pure reorder as no change | probe: `reorder(scene, [the-core-day, central-room-day, central-room-night])` → every entity's `fields` byte-identical, `order_of` list changed. The diff must pair both sides. |
| 2 | `act` order exists in BOTH places: as an `order` field on the act and as the `act:` entry of `order_of` | probe: act fields `{…, 'order': 1.0}`, order dict has `"act:": ["act-1"]`. Reporting both makes two items of one authored edit. §5.2 settles it: "the spec treats act order as part of the act entity's fields". So the order diff covers scenes and sequences; acts stay a field. |
| 3 | One authored role edit appears as two changed fields | probe: `plot_roles[].description` edit → differences at `scene.plot_roles` **and** `plot.inciting_incident`. `refmap.DERIVED["plot"]` is the exclusion list (T5). |
| 4 | §6.1's element-wise diff covers FOUR fields, not one | `REFERENCE_LISTS = ("characters", "scenes")`; probed present as plain id lists on `plot.characters`, `scene.characters`, `relationship.characters`, `relationship.scenes`. The T6 Notes claim "only `character_scene` cast is a plain id list" was **wrong** — corrected in Notes.md. |
| 5 | **`materialize` is the one reader that shows trashed ids** | probe: trash `mira` → `scene.characters` = `["kael"]` (relation-backed, `live_relations` filters) but `relationship.characters` = `["kael","mira"]` and `location.world` keeps a dead `parent_id`. `core/references.py` states the rule ("a reader that parses `extra`, or reads `location_id`, passes it through `live_extra` / `live_column`"); `logical.py` did not. Fixed in this task — decision A below. |
| 6 | The script composer drops a scene with an empty `Content` | probe: `_screenplay_rows` filters `s.body != ''`, so a heading-only scene is absent from `get_screenplay_text` while present in the entity view. A script diff that reused the composer would silently lose a scene. |
| 7 | `scene.act_id` and `scene.order` are not in the shape | probe: absent. The scene's act reaches the diff through its sequence's `act_id`; its position through `order_of`. |
| 8 | A staged-op reorder is the only writer of order in the fixture paths, and it takes a complete list | `core/writes.reorder`; T1/T2 Notes. Not this task's concern beyond reading `order_key`. |

## Decision

### D-1 — trashed references in the diff input (settled: A)

`logical.materialize` bypassed `live_extra`/`live_column`, so a reference to a trashed
entity survived in the materialized `fields` although the entity it names is absent from the
shape. A diff would then report a character's delete as a *change to every relationship that
named them*, and a merge could carry a dead id into the target.

**Decision (owner): A —** fix `materialize` to route `extra` through `live_extra` and the
`REFERENCE_COLUMNS` values through `live_column`. One guard where every consumer routes:
materialized shape then equals what a reader sees, the diff needs no trash special-case, and
T7 inherits a clean input. The fixture holds no trash, so T4's round-trip gate is unaffected;
a test now pins the trash behaviour instead of leaving it accidental.

## Decisions taken (no further input needed)

- **`compare(a, b)` takes two project paths** — the live project or the directory a
  `ProjectView` hands out. That is the shape every read function takes (F10), so a draft is
  compared through its copy and nothing opens a frozen file.
- **Acts' order is a field, not a list item** (row 2). One authored edit, one item.
- **`refmap.DERIVED` paths are skipped** in the field walk (row 3). `DERIVED` is the single
  declaration of "in the shape, not authored"; a second list here would drift from it.
- **A `REFERENCE_LISTS` field is unordered**: two states listing the same ids in a different
  order are the same state, and the entry carries `added`/`removed` ids (row 4).
- **Script text is composed per scene from the materialized fields with the existing
  `scene_heading`**, not via `get_screenplay_text`: the composer drops empty-`Content`
  scenes (row 6), and a diff that loses a scene is worse than one that shows an empty body.
  A test pins the per-scene composition against `get_screenplay_text` on the fixture so the
  two cannot drift.
- **`difflib` only.** §14-G: `merge3` is not added without approval, and it belongs to the
  merge editor (T7/T13), not to a read-only diff.
- **Items are emitted by the diff** (§7.2: "the diff yields items"), with a stable
  `kind:type:id[:name]` key so a decision can be stored against one and survive a re-plan.

## Tasks

- [x] `core/history/logical.py`: route `extra` through `live_extra` and `REFERENCE_COLUMNS`
      values through `live_column` (D-1).
- [x] `core/history/diff.py`: `text_diff(a, b)` — line-level `difflib`, the one helper the
      section and script diffs share.
- [x] `core/history/diff.py`: `compare(a, b)` → `{entities, order, items, script}`.
- [x] `core/history/diff.py`: entity rows — `added`/`removed`/`unchanged`/`changed`, per
      changed field `(a, b)` with `added`/`removed` ids for the plain id lists, per changed
      section `(a, b)` plus its line diff, `refmap.DERIVED` skipped.
      *(the element-wise set is four fields derived from `refmap`, not `REFERENCE_LISTS` alone
      — see the deviation below)*
- [x] `core/history/diff.py`: order rows — per parent the two id lists, scenes and
      sequences only.
- [x] `core/history/diff.py`: script rows — per scene `added`/`removed`/`moved`/`edited`/
      `unchanged`, placement `(act, sequence, position)` on each side, the composed text and
      its line diff, and the item keys the row selects.
- [x] `core/history/diff.py`: the flat item list — one per entity create/remove, changed
      field, changed section, changed order list.
- [x] `tests/test_history_diff.py`: 25 tests — the rows above, a pure reorder, act order as a
      field (two acts), a derived role field not reported twice, trash ignored in both
      directions (`extra` list and reference column), `compare` across a `ProjectView`, and
      the script composition pinned to `get_screenplay_text`.
      *(the three materialize-trash tests belong to the first commit and live in
      `tests/test_history_logical.py`, next to the shape they pin)*
- [x] Suite green against the `1878 passed, 1 failed` baseline → **`1906 passed, 1 failed`**
      (+28: 25 diff + 3 `logical`), same known `test_no_hermes_imports`;
      `ruff format --check src tests` clean; `ruff check` clean on every touched file;
      13 mutations, all killed.

Deviations, recorded on the items rather than only below:

- **The element-wise diff covers four fields, not `REFERENCE_LISTS` alone**, and the set is
  derived from `refmap` (a site declared `field[]`) instead of restated. `relationship.scenes`,
  `relationship.characters` and `plot.characters` are plain id lists in the shape too; the
  pre-task note claimed only the scene cast was one.
- **An item carries its key and identity, not its change payload.** The change is already in
  `entities` / `order` under the same key; repeating a section body on its item sends it twice
  to every consumer.
- **A scene's script row also carries the item keys it selects** (`items`), so the script view
  is a completed lens rather than one a caller re-derives.

## Final Brief

**What T6 adds.** `core/history/diff.py`: `compare(a, b)` over two project paths →
`{entities, order, items, script}`, plus `load()` and `text_diff()`. One pass, because §6.2's
script view is a lens over §7.2's items and neither may disagree with the entity rows.

**Two facts the materialized shapes cannot express, both settled in the diff.**

- **Order is not a field.** `reorder` of three scenes leaves every `fields` dict byte-identical
  and only changes `logical.order_of`'s list, so a shapes-only diff reports a pure reorder as
  **no change**. `compare` pairs both sides and reports `order:scene:<parent>`; the script view
  calls the same scene `moved` with both positions (probed: 3 → 1).
- **A role edit is in the shape twice.** Editing `plot_roles[].description` moves
  `scene.plot_roles` *and* `plot.inciting_incident`. `diff._derived` reads `refmap.DERIVED`
  (not a second list) and drops the plot's read side, so a role edit is exactly one item and
  the plot stays `unchanged`. Pinned by test.

**Decision A, implemented.** `logical.materialize` was the only reader in the codebase that
showed a trashed id — it parsed raw `extra` and raw `location_id`/`parent_id` while
`core/references.py`'s own docstring states the rule (`live_extra` / `live_column`, applied by
`scratch_live_extras` and friends). Probed after trashing `mira`: `scene.characters` =
`["kael"]` (relation-backed) but `relationship.characters` = `["kael","mira"]`. Fixed at the
materializer, where every consumer routes, so the diff needs no trash special case and T7
inherits an input equal to what a reader sees. A trashed reference column now reads `""`.
The fixture holds no trash, so T4's round-trip gate is untouched; both directions are now
pinned — a delete reads as a delete, and a rename *inside* the bin changes nothing.

**The script text is composed here, not read from `get_screenplay_text`.** That composer
filters `s.body != ''`, so a heading-only scene is in the entity view and absent from the
assembly (probed: created scene, `get_screenplay_text` unchanged). A script diff that loses a
scene is worse than one showing an empty body, so `diff._text` composes per scene with the
existing `scene_heading`, and a test pins the joined output **equal to** `get_screenplay_text`
on the fixture — the two cannot drift.

**Verification, as run.**

- `tests/test_history_diff.py`, **25 tests**, all passing; plus **3 tests in
  `tests/test_history_logical.py`** for the materializer's trash behaviour (same task, first
  commit — the shape and what it hides belong in one file).
- Full suite: **`1878 passed / 1 failed` → `1906 passed / 1 failed`** (+28: 25 diff, 3
  `logical`), the same known `test_no_hermes_imports`. No count moved down.
- **The first commit was verified standing alone**: in a `git worktree` at that commit,
  `test_history_logical.py` + `test_history_view.py` + `test_history_store.py` → 73 passed. A
  commit that only passes with the next one's files is not a commit that can be reverted.
- `ruff format --check src tests` clean; `ruff check` clean on `diff.py`, `logical.py` and the
  test file.
- **Mutation pass, 13 mutations, all killed**: order dropped from `compare`; act order
  reported as a list item; derived fields not excluded; id list diffed whole-value; added
  elements only; placement ignored; empty-body scene dropped; removed scenes unlisted; scene
  items missing the order key; removed entities unlisted as items; `live_extra` skipped;
  `live_column` skipped; field changes exported whole-value.
  Two survived the first run and were **my tests, not the code**: the act test used a single
  act (a one-element list cannot exhibit a reorder — a lesson `verification-pitfalls.md`
  already names), and the trash test asserted only relation-backed fields, which never reach
  `live_extra`. Both tests were rebuilt around the real path and re-run; 13/13.

**Deliberate simplifications.**

- **`difflib` only.** §14-G keeps `merge3` out until approved, and it belongs to the conflict
  editor, not a read-only diff.
- **A reference list is a set.** A reordered cast list is not a change and yields no item, so
  no plan can offer to reorder one; only the child order is an order.
- **Other list-shaped fields are whole-value.** `plot_roles`, a plot's role lists,
  `scene_beats.beats`, `perspectives`, `project.memory` are reported as `(a, b)`; a merge item
  that must act on one entry resolves it through `refmap`'s concrete path. Add per-entry
  granularity when a consumer needs to select inside one.

**For later tasks** (also distributed in `Notes.md`).

- **T7.** The item key is stable (`entity:<type>:<id>`, `field:…`, `section:…`,
  `order:scene:<parent>`) because decisions are keyed on it; a re-plan must not renumber it.
  A script-level selection unions the row's `items` rather than recomputing the grouping.
- **T7/T8.** A delete arrives as the entity `removed` **plus** a field change on every live
  entity that named it (the same mechanism that moves the fingerprint, T3). Expanding a
  removal must not also emit ops for those cascade rows.
- **T7.** The four element-diffed lists are `plot.characters`, `scene.characters`,
  `relationship.characters`, `relationship.scenes`; a cast reorder is not a change.

