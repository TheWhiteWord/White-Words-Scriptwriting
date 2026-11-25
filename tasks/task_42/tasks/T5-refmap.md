# T5 — `refmap`

Spec: `../spec-draft-versioning.md` §7.4 (dependencies, "must resolve"), §7.5 D1 (keep-both
rewrites references), §9 (`refmap.py`), §13 T5, §15 (`refmap` pinned to `ENTITY_SCHEMAS`,
`REFERENCE_*` and relation kinds).
Branch: `draft-versioning`.
Baseline: `1844 passed, 1 failed` on this branch before starting (the known
`test_no_hermes_imports`; same count T4 recorded).

## Objective

One declaration of every place an entity names another entity, so the merge engine can
answer the three questions the storage does not: **which** fields hold a reference, **what
type** each one may name, and **whether dropping it leaves a valid entity**.

F15: reference sites are only partly declared. `REFERENCE_LISTS`/`REFERENCE_MAPS`/
`REFERENCE_COLUMNS` exist for the soft-delete readers, `ref` markers exist for write-time
checking, relation kinds exist for storage — three partial views of one fact, and no single
one is complete. Five sites are declared by none of them — four of them accepted by the
write path with a dangling slug (§"Verified", row 6). A merge that reads any one of those
three views misses the others, and a missed site is a reference that is never resolved and
never rewritten — silently, on a real project.

`refmap` is the fourth view, and it is the complete one. It is not a new source of truth
about storage: it declares sites and a test pins it to the other three, so adding a
reference anywhere else fails the suite.

Out of scope (later tasks): the dependency expansion that consumes this (T7), diff (T6),
execute (T8), the script-level grouping (T7).

## Verified before starting

Every row is a probe against the fixture on this branch, not a reading of the spec.

| # | Claim | Evidence |
|---|---|---|
| 1 | Since T4 the shape is `{id, type, fields, sections}` from `logical.materialize`, computed fields excluded — except the plot's six role lists, which are the read side of `scene.plot_roles` and **are** in the shape | probe: `plot_roles[].description` edited on one scene → differences at `scene.plot_roles` **and** `plot.inciting_incident`, one authored edit reported twice |
| 2 | `value_turns[].value` stores the value's **display name**, not its id | probe: a turn created for value `free-will` (name `Free Will`) stores `"Free Will"`; writing `"free-will"` is refused ("is not a defined value") |
| 3 | `scene.act_id` is a denormalized copy of the parent chain and **drifts** | probe: `edit(scene, sequence_id=seq-2)` where `seq-2` sits in `act-2` → scene parent `seq-2`, `extra.act_id` still `act-1`; `create_entity` then refuses the entity ("Sequence seq-2 belongs to act act-2, not act-1"), so the logical round trip fails |
| 4 | `plot.<role>` is `computed` in the schema and no write path applies it | probe: `edit(plot, climax=[…])` → `success`, `skipped_read_only=['climax']`, data unchanged |
| 5 | The validators' type tuples already exist and are the write-path authority | `core/entity.py:965` `_BY_TYPES = (character, location, world)`, `:966` `_CHANGE_TYPES = (character, relationship, location, world)`; `manual_entities.py` holds a second copy of each — a third copy is how these drift |
| 6 | Five sites are declared by **none** of the three mechanisms; two more are `ref`-less but caught by a bespoke validator | probe with a dangling slug: `location.variant_of`, `sequence.primary_plot`, `relationship.characters`, `relationship.scenes`, `scene.characters` all **accepted** by `create_entity` (only `scene.characters` has a relation kind, so only it is visible to a storage-based scan). `value_turns[].value`, `changes[].entity` and `beats[].by` are refused — but by `validate_scene_value_turns` / `validate_beat_references`, not by a declaration |
| 7 | Two sites have **no single target type**, as F15 says | `beats[].action.by` / `beats[].reaction.by` → character\|location\|world; `changes[].entity` → character\|relationship\|location\|world. Both enforced by `validate_beat_references` |
| 8 | 22 reference sites exist across 10 entity types; a fixture sweep over every materialized field finds id-shaped values at 22 site paths, and the 4 hits it cannot place are the `plot.<role>` duplicate of row 1 | probe: sweep of every string equal to an entity id in `materialize()` output, matched against the site list |
| 9 | `location.variant_of` is the one site the fixture never exercises | probe: zero `location_variant` rows; the world counterpart has one (`the-real-world → the-i`) |
| 10 | A reference to a **deleted** entity stays in storage — `live_extra`/`live_column` only hide it from readers | `core/references.py` docstring and T4's `materialize`, which reads through them; so the logical shape a merge sees never carries a trashed id |
| 11 | `check_references` walks `ref` at any nesting depth (field-level and sub-field, lists and keyed objects) | `core/entity.py:837` `_collect_refs` / `:861` `_collect_refs_entry`; the site paths in refmap use the same `[i]` / `.key` notation so an error names one path in both |
| 12 | `materialize` reads cast from `live_relations`, so a trashed character is absent from `scene.characters` but present in the raw relation row | T1/T4 Notes; not a refmap concern, but it fixes what "the value at a site" means: the logical value, never the stored row |
| 13 | `scene.scene_beats` is a declared `ref` that is `computed` and **absent from the shape**; the record is reached from the other end by its `scene` column | probe over all seven declared refs vs the materialized shape: only this one is missing. `plot.<role>` and `plot_roles` are relation-backed, so `materialize` fills them after the computed filter (`logical.py:131`) |

## Findings that needed a decision

All four are answered (§"Decisions taken"). None is open.

### F-1 — the branch is not `dev` (settled: continue here)

The brief says "branch off `dev`". The tree is `draft-versioning` @ `479eaea`, 10 commits
ahead of `dev` @ `610cf06`, holding T0–T4 committed. Spec T0 *was* "branch off dev", so
that branch is this one. A fresh branch off `dev` would drop five tasks of work.

**Decision:** continue on `draft-versioning`; T5 is its next commit.

### F-2 — `value_turns[].value` is name-keyed (settled: model it as such)

§7.4.2 lists "a value turn's value" among the must-resolve, non-optional references, and
§7.5 D1 says every reference is rewritten by `refmap`. Both assume a reference holds an id.
This one holds a display name (row 2), so an `{old_id: new_id}` mapping cannot rewrite it.

**Decision:** refmap records the site as `keyed_by="name"`. `rewrite` takes the two lookup
spaces separately (`by_id`, `by_name`) rather than one merged dict, so a name that happens
to equal some other entity's id cannot be substituted by the wrong mapping. The merge
planner builds the name mapping from the two value entities it already holds.

### F-3 — the plot's six role lists are the same rows as `scene.plot_roles` (settled: derived)

`materialize` emits both sides (row 1), so one authored role change would be two merge
items and two dependency expansions.

**Decision:** refmap declares **authored** sites only. `scene.plot_roles[].plot` is the
site; the six `plot.<role>` lists are declared **derived** and excluded, with the pinning
test asserting they are exactly the read side of that one site. A merge that touches a role
touches the scene.

They are also `computed` (row 4), so no write path accepts them — a site that cannot be
written cannot be a merge target.

### F-4 — `scene.act_id` is a denormalized duplicate that drifts (settled: field REMOVED, derived at read time)

Row 3. It is a copy of the parent chain, it goes stale on a parent edit, and a full merge
design would hit exactly this when it moves a scene (§7.6: "an `edit` of its parent field
followed by a `reorder` of both sequences").

**Decision:** T5 declares it **derived** and out of the rewrite set — it is a copy, not a
reference the merge resolves, so it stays derived either way. The field itself was then
**deleted** in a follow-up commit: it is no longer in `ENTITY_SCHEMAS["scene"]`, every
writer rejects it as unrecognised, `story_export` omits it, and `db.get_dashboard_data`
supplies it from the scene's sequence for every reader. One copy of the fact, and no
writer can introduce a second one.

## Decisions taken

- **The site list is authored here and pinned by a test, in the style of
  `test_live_references`.** refmap does not import `REFERENCE_*` to build itself: those
  lists exist for the soft-delete readers and are incomplete for this purpose (row 6). The
  test asserts the two agree, so a change to either fails the suite instead of drifting.
- **Two sites are declared `derived`, not skipped silently** (F-3, F-4). The empirical
  test needs an explicit allowlist, or the next reader cannot tell a deliberate exclusion
  from a missed site.
- **Five sites the three mechanisms miss are declared here, and the test names the
  validator for each** (`sequence.primary_plot`, `relationship.characters`,
  `relationship.scenes`, `location.variant_of`, `value_turns[].value`) plus the two
  multi-type sites. Four of the seven are enforced by no validator at all (probe: a dangling
  slug is accepted), so refmap is the first place they are declared. That is the point of
  the module, and the test pins each to its evidence.
- **`required` is a spec decision, not something the code enforces.** Probed: `edit(scene,
  sequence_id="")`, `edit(scene_beats, beats=[])`, `edit(relationship, characters=[])`,
  `edit(sequence, act_id="")` are all **accepted** — the write path lets a structurally
  meaningless entity through. So `required` cannot be derived from what `create_entity`
  refuses; it means "§7.4.2's *drop* is not offered here". §7.4.2 names eight sites and the
  rest follow its stated principle — *drop is offered where the reference is enrichment; it
  is not where the reference is what the containing value means*. The pinning test asserts
  §7.4.2's eight are marked exactly as it marks them.
- **`rewrite` returns a new `fields` dict and never mutates its input.** Callers hold the
  incoming items in a diff; mutating them would change what the plan was computed from.
- **One walker for iterate and rewrite.** A path language with two implementations is two
  chances to disagree about what `beats[].action.by` means.
- **No storage field on a site.** T7 emits drafts ops (`edit` with a field), so storage is
  invisible to it; the pinning test resolves each site against the maps itself and is the
  only reader that needs to know.

## Site list

`[]` descends into list entries; `{}` is a keyed object whose **keys** are the references.
`keyed_by` is `id` unless stated.

| # | Type | Path | Targets | Drop? | Declared by |
|---|---|---|---|---|---|
| 1 | world | `variant_of` | world | optional | relation `world_variant` |
| 2 | location | `world` | world | optional | column `parent_id` |
| 3 | location | `variant_of` | location | optional | relation `location_variant` |
| 4 | plot | `characters[]` | character | optional | `ref` |
| 5 | sequence | `act_id` | act | **required** | column `parent_id` |
| 6 | sequence | `primary_plot` | plot | optional | **nothing** |
| 7 | scene | `sequence_id` | sequence | **required** | column `parent_id` |
| 8 | scene | `location` | location | optional (§7.4.2) | column `location_id` |
| 9 | scene | `characters[]` | character | optional (§7.4.2) | relation `character_scene`, `REFERENCE_LISTS` |
| 10 | scene | `plot_roles[].plot` | plot | optional (§7.4.2) | `ref` + relation `plot_<role>` |
| 11 | scene | `value_turns[].plot` | plot | **required** | `ref` |
| 12 | scene | `value_turns[].value` | value | **required** | **nothing** — `validate_scene_value_turns`; `keyed_by=name` |
| 13 | scene | `value_turns[].effects[].character` | character | **required** | `ref` |
| 14 | scene_beats | `scene` | scene | **required** | `ref` + column `parent_id` |
| 15 | scene_beats | `driver` | character | optional | `ref` |
| 16 | scene_beats | `true_character[].character` | character | **required** | `ref` |
| 17 | scene_beats | `changes[].entity` | character\|relationship\|location\|world | **required** | **nothing** — `validate_beat_references` |
| 18 | scene_beats | `beats[].action.by` | character\|location\|world | **required** (§7.4.2) | **nothing** — `validate_beat_references` |
| 19 | scene_beats | `beats[].reaction.by` | character\|location\|world | **required** (§7.4.2) | **nothing** — `validate_beat_references` |
| 20 | relationship | `characters[]` | character | **required** | `REFERENCE_LISTS` |
| 21 | relationship | `perspectives{}` | character | **required** | `REFERENCE_MAPS` |
| 22 | relationship | `scenes[]` | scene | optional (§7.4.2) | `REFERENCE_LISTS` |

**`(§7.4.2)`** marks §7.4.2's eight named sites: four optional — cast, `location`,
`plot_roles` entries, relationship scene lists — and four required — a beat's actor (both
sides), a value turn's value, a scene's parent sequence. The other seven required sites
follow §7.4.2's stated principle (*drop is offered only where the reference is
enrichment*); three of them the write path already refuses outright, which is the firmest
evidence available: `scene_beats.scene` ("requires a scene"), `value_turns[].plot` and
`value_turns[].value` ("is required"). `relationship.characters[]`, `true_character[].character`,
`changes[].entity` and `value_turns[].effects[].character` are accepted when emptied, so
their `required` is the spec's call, not the code's.

22 sites over 10 entity types. `project`, `character`, `act` and `value` name nothing.

Derived — declared, deliberately not sites, each for a stated reason:

| Type | Path | Why |
|---|---|---|
| plot | `setups`, `inciting_incident`, `complications`, `crisis`, `climax`, `resolutions` | read side of `scene.plot_roles[].plot` (F-3) |
| scene | `act_id` | copy of the parent chain; supplied at read time from the sequence, no longer a writable field |
| scene | `scene_beats` | a declared `ref`, but `computed` and absent from the shape (row 13); the record is reached by its `scene` column from the other end |

## Tasks

- [x] `core/history/refmap.py`: the `Site` record and `SITES` — 22 entries from the table
      above, plus `DERIVED` (8 paths: the six plot role lists, `scene.act_id`,
      `scene.scene_beats`) with a one-line reason each.
- [x] `core/history/refmap.py`: `sites(entity_type)` — the sites of one type.
- [x] `core/history/refmap.py`: `iter_references(entity_type, fields)` — every reference
      actually present, as `(path, value, site)` with the concrete path
      (`plot_roles[0].plot`), so a plan can name the item that is unresolved.
- [x] `core/history/refmap.py`: `rewrite(entity_type, fields, *, by_id, by_name)` — a new
      `fields` dict with site values substituted; `by_name` is used only by name-keyed
      sites, and the input is never mutated.
- [x] `core/history/refmap.py`: one path walker shared by both, `[]` and `{}` as specified.
- [x] `tests/test_history_refmap.py`: 32 tests — every `ref` in `ENTITY_SCHEMAS` (any
      nesting) is a site with the same target; every relation kind is a site or derived;
      the soft-delete maps are sites; every site path starts with a declared field; the
      two multi-type sites equal `_BY_TYPES`/`_CHANGE_TYPES`; `value_turns[].value` is the
      only name-keyed site; §7.4.2's eight named sites marked as it marks them; the
      fixture's materialized shape has no id at an undeclared path; every site but one is
      exercised by the fixture and the one is constructed; the walker on a real scene,
      concrete paths, keyed sites, empty and wrong-typed fields; rewrite at every depth,
      input untouched, the two lookup spaces kept apart, keyed rename, no-op rewrite; and a
      rename that the real write path then accepts.
- [x] Suite `1844 passed, 1 failed` → **`1876 passed, 1 failed`** (+32), the same
      `test_no_hermes_imports`; `ruff format --check src tests` clean; `ruff check` clean on
      both new files; 10 mutations of the new logic each killed.

## Final Brief

**What T5 adds.** `core/history/refmap.py`, a single declaration of the 22 places an entity
names another, and the two operations the merge engine needs on top of it:
`iter_references(entity_type, fields)` → every reference actually present, with a concrete
path (`value_turns[0].effects[1].character`), and `rewrite(entity_type, fields, by_id=…,
by_name=…)` → the same shape with those references substituted.

**Why a new declaration rather than reading the existing ones.** Every mechanism the
codebase already has is partial, and they disagree: a `ref` in `ENTITY_SCHEMAS` is only the
subset the write path checks; `REFERENCE_LISTS`/`MAPS`/`COLUMNS` exist so a *reader* hides a
deleted id; a relation kind is storage; and a bespoke validator is a fifth, separate list.
Five sites are missing from all of them. Probed with a dangling slug, four are **accepted**
by `create_entity`:

| Site | Today |
|---|---|
| `sequence.primary_plot` | declared by nothing at all — the module's reason to exist |
| `location.variant_of` | declared by nothing; a bad slug is accepted |
| `relationship.characters[]` | in a soft-delete map; a bad slug is accepted |
| `relationship.scenes[]` | in a soft-delete map; a bad slug is accepted |

`value_turns[].value` is the fifth — refused, but by `validate_scene_value_turns` rather than
by any declaration.

**The four decisions this task needed, all yours.** `value_turns[].value` stores the value's
display **name**, not its id (verified: writing the id is refused with "is not a defined
value"), so it is `keyed_by="name"` and `rewrite` takes the id and name mappings as
**separate** lookups — a name that happens to equal some other entity's id can never be
substituted by the wrong one, and both directions are pinned. The plot's six `<role>` lists
are the same rows as `scene.plot_roles` read from the plot side, so they are `DERIVED`, not
sites: a role change is one edit on the scene, and they are `computed`, so no write path
accepts them anyway. `scene.act_id` is `DERIVED` too — a copy, not a reference the merge
resolves, and now supplied at read time rather than stored. And the branch: this is
`draft-versioning`, which already is the branch T0 created.

**`required` is the spec's, not the code's.** Probing showed the write path accepts
`sequence_id=""`, `beats=[]`, `characters=[]` — so an entity that no longer says what it is
gets through, and `required` cannot be derived from what the code refuses. It means "§7.4.2
does not offer *drop* here"; the eight sites §7.4.2 names are marked exactly as it marks
them (four optional, four required) and a test holds that.

**That the pin cannot be fully empirical, and what it is instead.** `materialize`'s shape is
swept for any string that is an entity id and nobody declared; a used, undeclared reference
field fails there (verified by adding one to `project` with a fixture id in its default —
caught). It cannot see a field no fixture entity fills. The declared half is a second test
walking every `ref` in `ENTITY_SCHEMAS` and every relation kind. Together they cover both
directions; neither alone would.

**Verification, as run.**

- `tests/test_history_refmap.py`, **32 tests**, all passing.
- Full suite: **1876 passed, 1 failed** — +32, same known `test_no_hermes_imports`. No
  count moved down.
- `ruff format --check src tests` clean; `ruff check` clean on both new files.
- **Mutation pass, 10 mutations, all killed**: dropping `sequence.primary_plot`; dropping a
  `DERIVED` entry (`act_id`, a plot role, the whole scene group); making the name-keyed site
  id-keyed; merging the two lookup spaces; the keyed walker ignoring keys; rewrite skipping
  list entries; rewrite mutating its input in place.
  Two survived the first run and were **my tests, not the code**: `out = dict(fields)` →
  `out = fields` is not a mutation because every branch builds a new dict, and one
  `DERIVED` pattern never applied. Replaced with real mutations, both killed.
- **The empirical sweep's limit, proven rather than assumed**: adding an unused reference
  field to `project` does **not** fail the suite (nothing to observe), and adding one whose
  default holds a real id **does**. That is why the declared-ref test exists.

**Deliberate simplifications.**

- **No `storage` field on a `Site`.** T7 emits drafts ops — an `edit` with a field name — so
  whether the value lives in `extra`, a column or a relation is invisible to it. The pinning
  test resolves each site against the maps itself and is the only reader that needs to know.
- **`checked_by` records the validator, not the absence of one.** `None` is a real answer
  for nine sites; naming the exact set in a test is stricter than a boolean and survives a
  reader asking "but who checks this?".
- **One walker for iterate and rewrite.** They share `_steps`; a path language with two
  implementations is two chances to disagree about what `beats[].action.by` means.

**Findings for later tasks** (also in `Notes.md`).

- **T7/T8 (planner, executor).** `scene.act_id` is not a writable field and needs no op:
  it is supplied at read time from the scene's sequence, so §7.6's scene move is one edit of
  `sequence_id` plus the reorders. A plan that emits `act_id` fails as an unknown field.
- **T7 (planner).** `rewrite` takes `by_id` and `by_name`; for a D1 keep-both on a *value*,
  the name mapping is the one built from the two value entities' `name` fields, and the id
  mapping must not contain it.
- **T7 (planner).** The plot's six `<role>` lists are `DERIVED`. A plan that changes a role
  edits the scene; nothing may emit an edit against `plot.setups` and friends — they are
  `computed` and `edit_entity` reports success while changing nothing (`skipped_read_only`).
- **T6 (diff).** One authored role edit appears as **two** changed fields in `materialize`
  (`scene.plot_roles` and the plot's role list). A diff that reports both will make a merge
  item out of a derived view; `refmap.DERIVED` is the list to exclude.

