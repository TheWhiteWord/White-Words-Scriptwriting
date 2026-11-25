# T4 — `ProjectView` and the logical entity

Spec: `../spec-draft-versioning.md` §4.3 (open read-only), §4.7 (schema versions),
§5 (the logical entity), §5.2 (structure as lists), §9 (module layout), §13 T4, §15.
Branch: `draft-versioning`.
Baseline: `1816 passed, 1 failed` on this branch before starting (the known
`test_no_hermes_imports`; same count T3 recorded).

## Objective

Everything after this task reads a saved state rather than the live database, so
two things have to exist and be exactly right:

1. **`ProjectView`** — read a frozen draft without touching it. `get_db` opens
   `story.db` read-write and migrates it; pointed at a draft that would create
   `-wal`/`-shm` beside a `0444` file and could rewrite it (T3's Notes). So a
   `ProjectView` copies the draft into a temp directory as `.story/story.db` and
   hands out that temp *project path*, which is the shape every read function
   already takes (F10).
2. **The logical entity** — the entity as an author writes it: `{id, type,
   fields, sections}`, computed fields excluded (§5.1). It is what T6 diffs do
   not see (diff), T7 plans and T8 executes against, so a materializer that drops
   or invents one fact breaks every later task silently.

The gate (§5.1, §13 T4): materialize every entity of a fixture project →
`create_entity` it into an empty project → materialize again, and the two must be
equal. If exactness cannot be had, stop and revisit §5.

Out of scope (later tasks): `refmap` (T5), diff (T6), plan/execute (T7/T8),
sessions (T9), HTTP (T10), tools (T11).

## Verified before starting

Every row below is a probe against the fixture or a temp project on this branch.

| Claim | Evidence |
|---|---|
| Suite is at `1816 passed, 1 failed` | `.venv/bin/python -m pytest -q`; the failure is the known `test_no_hermes_imports` |
| The fixture holds 26 live entities across **all 11 types**, and every one's section set is exactly the standard set | probe: `Counter` by type = act 1, character 6, location 2, plot 2, project 1, relationship 3, scene 3, scene_beats 3, sequence 1, value 2, world 2; zero entities whose headings differ from `standard_sections(type)` |
| A round trip in **creation order** is already exact for the fixture | probe: materialize → `create_entity` each → materialize. `original == rebuilt` true, child order true. 0 create failures |
| `create_entity` **numbers scenes and sequences itself**; the order is a function of creation order, not of the ids | probe: created `zulu` then `alpha` in one sequence → story order `zulu, alpha`; rebuilt in id order → `alpha, zulu`. Preserved only when the ids are created in the parent's declared order |
| `create_entity` does **not** number acts | probe: `act-a`, `act-b` both created at `order_key 0.0`; an explicit `order` in the fields is honoured |
| Sections are `(entity_id, heading, body)` and the write path creates the whole standard set | `core/writes.py:343`; `edit_entity` upserts, never deletes, so a live entity's section set stays the standard one |
| A pruned section row does not break exactness **only if the materializer normalizes to the standard set** | probe: delete every empty section row, materialize → the set is the one heading left; recreating walks the whole standard set back. Raw comparison false, normalized true |
| Two live siblings may share an `order_key`, and the id list still round-trips | probe: forced a tie, materialize → rebuild → order preserved |
| The fixture has **one stray `extra` key the schema does not declare**: `project.extra["memory"]` | probe over all 26 entities: one hit, `('save-the-children','project','memory')`. Sections: zero strays |
| `project.memory` is live content, not dead weight | `core/db.py:598-640` `get_project_memory`/`set_project_memory`; `tools/story_memory.py` is an agent-facing tool; `story_export` strips it from frontmatter and writes `.story/memory.md` instead |
| A memory write **moves the fingerprint** (`§4.4` hashes raw `extra`, computed keys only removed) | probe: `set_project_memory` → `of_conn` changes |
| `create_entity` **refuses** an undeclared field, so `memory` cannot be passed to it | probe: `ValueError: Unrecognised project field(s): memory` |
| **Act order was invisible to the fingerprint** (fixed below as F-2 → A) | `core/history/fingerprint.py` `ORDERED_TYPES` held `("scene","sequence")` at task start. Probe: reorder two acts → hash **unchanged** |
| Act order is authored and readable by four places | `core/db.py` `ORDER BY order_key`, `core/manual_structure.py`, `tools/story_load.py` `ORDER BY order_key, id`, `manual_entities` numbering |
| An agent **can** move an act: `edit_entity` accepts `order` | probe: `edit_entity(p,'act','act-a',{'order':5})` → `order_key 5.0`, accepted |
| Consequence: a project whose only change is act order cannot be saved as a draft | probe: change only an act's `order`, then `save_snapshot` → `Nothing has changed since Draft 1` |
| `_RELATION_FIELDS` + `BESPOKE_RELATION_FIELDS` + `ENTITY_COLUMN_MAP` cover every stored field of every type | probe over `ENTITY_SCHEMAS`: every non-computed field lands in a column, a relation, or `extra` |
| The scratch-project pattern already exists | `core/drafts.py:617` `dry_run`: `TemporaryDirectory`, `.story/story.db`, `Connection.backup()` |

## Findings that need a decision

Two claims in the spec do not hold on this branch. Both are recorded in the task
file and in `Notes.md`; neither is resolved yet.

### F-1 — `project.extra["memory"]` is logical content the write path refuses

§5.1 defines the logical entity as "`{id, type, fields, sections}` … obtained
through the same code path the retrieve tool and `validate_entity` use", and the
gate is a `create_entity` round trip. `project.memory` sits in that shape's blind
spot on both sides:

- The materializer built from `ENTITY_SCHEMAS` cannot see it: `memory` is not a
  declared field, so it never appears in `fields`.
- `create_entity` refuses it if the materializer did emit it.

So the round trip can be **exact and still lose content**: a fixture without
memory passes; a real project with memory rebuilt from its logical entities comes
back with none. Probe output:

```
1. logical round trip exact:        True     (fixture)
4. a memory write moves the hash:   True
   ... and the logical entity sees it: False
   memory in the rebuilt project:   []
```

This matters beyond T4: T6 diffs two states through this materializer, so a
memory-only change would diff as **no change** while the fingerprint says it
changed — a draft with real content and an empty diff. T7's planner would then
never carry it. §4.4's "logical content" and §5.1's logical entity would disagree
about the same project.

Options (recommendation first):

| # | Option | What it costs |
|---|---|---|
| **A** | Declare `memory` in `ENTITY_SCHEMAS["project"]` as an `object` field, and materialize it | One schema entry. `create_entity` then accepts it, the round trip carries it, and the form shows it as `unsupported` (as other object fields do) unless hidden. Touches a shared constant, so it wants an owner decision |
| B | Materialize it but keep it out of `create_entity`'s write path, and have the round-trip helper apply it separately | Two paths for one fact; `diff` and the executor need the same special case, so the exception spreads to T6–T8 |
| C | Exclude `memory` from the fingerprint so "logical content" means what §5.1 says | Changes T3's shipped hash; a memory-only change then reports "nothing changed", and the user's recorded decisions stop being part of a draft at all |
| D | Leave it; document that memory is outside the logical entity | Every later task inherits a known content loss on a real project. Needs an explicit "this is acceptable" |

### F-2 — `act` order is content the fingerprint ignores

§5.2 says "Acts are not reorderable through `core.writes` (F13: `REORDERABLE_TYPES`);
the spec treats act order as part of the act entity's fields". `reorder(act)` is
indeed refused, and `order` is a real schema field — but §4.4's fingerprint
serializes order only for `scene` and `sequence`, so **moving an act is invisible
to the "nothing changed" guard**:

```
act reorder visible TODAY:      False
act reorder visible WITH FIX:   True
act renumber only (with fix):   changed = False   (correct: renumbering is not reordering)
```

Consequence, probed end to end: change only an act's order, then save → "Nothing
has changed since Draft 1". The user's edit is real, appears in the outline
(`ORDER BY order_key` in four readers), and cannot be captured in a draft.

Options (recommendation first):

| # | Option | What it costs |
|---|---|---|
| **A** | Add `"act"` to `fingerprint.ORDERED_TYPES` | One tuple entry; the per-parent id list already handles a null parent, and the probe shows renumbering still hashes stable. Changes T3's hash for any project with more than one act — which is correct, since the old hash was blind to it |
| B | Treat act order as a plain `order` field in the hash instead | Contradicts the rule that order is never hashed as a key value; renumbering would then read as a change |
| C | Leave it; a draft cannot record an act-only reorder | A silent, unreachable edit in a feature whose purpose is capturing state |

Both decisions are the owner's: A in each case edits something T3 shipped (a
shared schema constant, a shipped hash), and this task's own copy is what it is.

## Decisions taken

### Resolved (§ owner: "A in both")

- **F-1 → A.** `memory` is declared in `ENTITY_SCHEMAS["project"]` as an `object`
  field, hidden from the entity form (`manual_entities.HIDDEN`) and skipped by
  `unfilled_fields`, because `story_memory` writes it one entry at a time and it
  is not prose the author owes the project. `create_entity` now accepts it, so it
  materializes, round-trips and diffs. Verified: a memory-only change is visible
  in the logical entity and survives the round trip (two tests pin it).
- **F-2 → A.** `"act"` is in `fingerprint.ORDERED_TYPES`. Verified: reordering
  two acts moves the hash, renumbering them without reordering does not, and a
  save captures an act-only reorder where it used to refuse with "Nothing has
  changed". Both directions are pinned.

- **`create_entity` is the rebuild path, so the round trip is exact only in
  creation order.** It numbers scenes and sequences from the live sibling set
  when no `order` is given, so the rebuild must create children in the parent's
  declared order. The materializer therefore does not carry a `scene.order` or
  `sequence.order` field (order is the per-parent id list, §5.2); an act keeps
  its `order`, because acts are not auto-numbered.
- **Section bodies are normalized to the standard set.** `create_entity` creates
  every standard heading, so a materializer that emits only the headings it found
  cannot round-trip a state whose empty rows were pruned. A section with no prose
  reads as empty, not absent.
- **`ProjectView` copies with `Connection.backup()`, not a file copy.** WAL mode
  means a committed write can still be in `story.db-wal`, and a plain copy would
  read a stale draft.
- **`ProjectView` takes a snapshot id, not a path**, and resolves it through
  `store.snapshot_file`, so the layout stays in one module.
- **`check_source` is the version gate, and `get_db` is the migration.** The view
  validates the draft through the same function a backup goes through (§4.7),
  then hands the copy to `get_db`, which migrates a *copy*. Nothing new validates
  schema versions.
- **Views are not cached across calls.** §4.3 says "views are cached per
  session"; a lifetime policy belongs with the HTTP layer that owns a session
  (T10). A context manager that copies and cleans up is the whole mechanism v1
  needs.

## Tasks

- [x] `core/history/view.py`: `project_view(project_path, snapshot_id)` — a
      context manager that copies the draft into a temp dir as `.story/story.db`
      via `Connection.backup()`, yields the temp project path, and removes the
      directory on exit. Refuses a draft from a newer build or below
      `BASELINE_VERSION` through `check_source` (§4.7).
- [x] `core/history/logical.py`: `materialize(conn)` → `{id: {id, type, fields,
      sections}}` over live entities; computed fields and `order_key` excluded;
      columns, `extra` and relation-backed fields merged; `plot_roles` read from
      the plot side; sections normalized to `standard_sections(type)`.
- [x] `core/history/logical.py`: `of_project(project_path)` — the same shape from
      a path, so a caller need not hold a connection.
- [x] `core/history/logical.py`: `order_of(conn)` — the per-parent child order as
      an id list (§5.2), and `rebuild_copy(entities, order, dest)` — the round-trip
      helper, iterating types in dependency order and children in declared order.
- [x] `core/constants.py`: `memory` declared on `project` (F-1 → A), hidden from
      the form and skipped by `unfilled_fields` because `story_memory` writes it.
- [x] `core/history/fingerprint.py`: `act` added to `ORDERED_TYPES` (F-2 → A).
- [x] `tests/test_history_view.py`: 8 tests — the view reads the draft and leaves
      its bytes and mode alone, no `-wal`/`-shm` appear, the copy is gone after
      the block including on an exception, a newer-build draft is refused, two
      views do not share a directory, a draft read shows the state it holds rather
      than the live one.
- [x] `tests/test_history_logical.py`: 17 tests — the round trip over all 11 types
      (exact, order preserved, still writable), computed fields absent, a scene
      carries no `order` while an act does, relation fields assembled, location
      appears once, sections are the standard set and an empty one reads as empty,
      memory is part of the entity and survives a round trip, children created in
      parent order, a shared `order_key` round-trips, acts keep story order, one
      field edit shows as one difference, a trashed entity is absent.
- [x] `tests/test_history_store.py`: 3 tests for F-2 — an act reorder moves the
      hash, renumbering acts does not, a save captures an act-only reorder.
- [x] Suite `1816 passed, 1 failed` → **`1844 passed, 1 failed`** (+28), the same
      `test_no_hermes_imports`; `ruff format` clean; the 9 mutations of the new
      logic each kill the test that pins them.

## Final Brief

**What T4 changes.** Everything after this reads a saved state instead of the live
database; these are the two things that makes possible.

*`core/history/view.py`.* `project_view(project_path, snapshot_id)` copies a
draft into a throwaway `.story/story.db` and yields that path. It never opens the
draft for writing: the source is read `immutable`, so no `-wal`/`-shm` appears
beside it, and the migration `get_db` runs lands on the copy. `check_source` — the
same gate a backup goes through — refuses a newer-build or below-baseline draft
*after* producing the temp path and before the copy, so a refused view leaves
nothing behind and never reports a migration error as the reason.

*`core/history/logical.py`.* `materialize` assembles `{id, type, fields,
sections}` over live entities: columns, `extra` and relation-backed fields merged,
`plot_roles` read from the plot side (they are rows the plot owns), computed
fields and `order_key` excluded. `order_of` returns the per-parent child order as
an id list — the same list the fingerprint hashes, so the two cannot disagree
about what "the order" means. `rebuild_copy` creates a materialized shape in an
empty project through `create_entity`, which is what the §5.1 gate runs on.

Two rules make the round trip exact, and both are pinned by tests because both
fail silently otherwise: children must be created in their parent's declared order
(`create_entity` numbers scenes and sequences from the live siblings, so id order
would reorder the story), and sections are normalized to the standard set
(`create_entity` always writes every heading, so a pruned row otherwise reads as
a difference).

**The two spec claims that did not hold, both fixed as option A.**

- `project.extra["memory"]` was logical content with no way in or out: not a
  schema field, and `create_entity` refused the key, so the round trip could be
  exact and still drop it. It is now declared on `project` as an object field,
  hidden from the entity form and skipped by `unfilled_fields` — `story_memory`
  writes it one entry at a time, so a form field is the wrong home and an empty
  memory is not a gap the author owes. `memory` now materializes, round-trips and
  will diff.
- Act order was content the fingerprint ignored, so an agent's `edit_entity`
  reorder was refused as "Nothing has changed" — a real edit, visible in four
  readers, that no draft could capture. `"act"` is in `fingerprint.ORDERED_TYPES`.
  Renumbering acts without reordering still hashes stable, which is why the
  per-parent id list was already the right serialization.

**Verification, as run.**

- `tests/test_history_view.py`, 8 tests: the draft's bytes and `0444` mode are
  unchanged across a read, no `-wal`/`-shm` appear, the copy is removed on the
  normal and the raising path, a newer-build draft is refused, two views get
  separate directories and an edit in one is not in the other, and a draft read
  returns the state the draft holds rather than the live head.
- `tests/test_history_logical.py`, 17 tests: the round trip over the fixture —
  **26 entities, all 11 types, `original == rebuilt`, child order preserved** — and
  one test per rule it depends on. Plus: computed fields absent, a scene carries
  no `order` while an act does, relations assembled from both directions, sections
  are the standard set, an empty section reads `""`, memory is part of the entity
  and survives a copy, act story order survives, and a single field edit shows as
  a single difference (the property the whole shape exists for).
- `tests/test_history_store.py`, +3: act reorder moves the hash, renumbering acts
  does not, a save captures an act-only reorder.
- Full suite: **1816 → 1844 passed, 1 failed** — 28 new, same known
  `test_no_hermes_imports`. No count moved down.
- `ruff format --check src tests` clean; `ruff check` clean on every touched file
  (the 79 remaining findings are T0's lint backlog, and the two I introduced were
  fixed).
- Mutation check, 9 mutations of the new logic (memory removed from the schema,
  sections not normalized, id-order creation, acts auto-numbered, relations not
  assembled, computed fields not excluded, the view opening the draft in place,
  the temp dir left behind, `act` out of the ordered types): **all 9 killed**.
  Two survived the first run and both were my tests, not the code — one asserted
  a subtotal instead of a delta, and no test pinned act order in the fingerprint.
  Both added.
- End to end on the fixture: adopt → rename → save "Draft 2" → rename and retitle
  the live head again. The live project reads `Kael Later | The Door`; the view of
  Draft 2 reads `Kael The Elder | Central Room - Day`, 26 entities, file `444`,
  and the snapshot directory holds only the two `.db` drafts — no sidecars.
- Agent-facing surface unchanged: `build_registry()` is byte-identical before and
  after the two schema edits, apart from function addresses.

**Deliberate simplifications.**

- **A copy per view, no cache.** §4.3 says views are cached per session; a cache
  is a lifetime policy and T10 owns the session. A context manager that copies and
  deletes is the whole mechanism v1 needs.
- **`check_source` does the version gate.** Nothing new validates schemas; the
  view calls the function a restore already trusts, and `get_db` migrates the copy.
- **`order_of` is a separate function, not a field.** It reads the same rows the
  fingerprint does, so the two cannot drift; putting order in the shape would make
  T6 diff a key value.

**Findings for later tasks.**

- **T6 (diff).** The logical shape is `{id, type, fields, sections}`; order is
  `order_of`, a separate per-parent id list. A diff that only compares
  `materialize` output will report a pure reorder as **no change** — both sides of
  that comparison must be paired with `order_of`.
- **T6 (diff).** `fields` holds relation-backed values in their authored shape
  (`plot_roles` as `[{plot, role, description}]`, plot beats as
  `[{scene_id, description}]`) and plain id lists for cast (`characters`). The
  `REFERENCE_LISTS` element-wise diff in §6.1 therefore applies only to the plain
  id lists; the others are whole-value unless the diff is taught their shape.
- **T5 (refmap).** Every reference site is now visible in one place: the fields
  the materializer fills from relations are exactly `_RELATION_FIELDS` plus
  `plot_roles`, and the column-backed ones are `ENTITY_COLUMN_MAP`. `memory` is an
  object of strings with no ids, so it is not a reference site.
- **T7/T8 (planner/executor).** `rebuild_copy` is the create path a merge could
  reuse for a whole-entity bring, but it takes an `order` mapping and sorts by it.
  A planner bringing one entity does not have one, and must not invent one: create
  the entity and let the reorder step settle its position.
