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
  live database. **Corrected in T3:** it is called with `safety_label=None`, and
  the parked head is the safety net (see Deviations). Source validation is no
  longer a gap: T3 extracted `core.backups.check_source(source, label)` and the
  switch runs it on the parked head first.
- Two strings inside the loader said `"cannot be restored in place"` (page size)
  and `"failed its integrity check after the restore"`. **T3 reworded both**
  ("copied into this project", "after the copy"). The earlier note here claimed
  two `tests/test_backups.py` assertions pinned the old wording — **that was
  wrong**: both pin only `match="page size"` (lines 314, 413), so the reword
  needed no test change. Verified by grepping the assertions, not assumed.
- `restore_backup` takes its safety backup inside the loader, so a caller that
  wants a labelled "before" state gets it from the same call. Unchanged by T3;
  `restore_backup` still passes `"before-restore"`.
- `versions.token(payload)` (`core/versions.py:15`) is the repo's one
  canonical-JSON → short-sha256 function, and its docstring already says the
  caller decides what to hash. `core/history/fingerprint.py` is a second caller,
  not a second implementation.
- `FROM live_relations` does **not** count as a raw `relations` read:
  `tests/test_live_relations.py:328`'s pattern is
  `(?<!DELETE )\b(?:FROM|JOIN)\s+relations\b` and `_` is a word character, so the
  view never matches. A fingerprint or diff can read the view freely; a
  `FROM relations` would need a registry edit.
- A new `src/` file that calls `datetime.now(` / `.isoformat(` fails
  `tests/test_utc_stamps.py:283` until it is added to `LOCAL_TIME_ALLOWED` with a
  reason. `core/history/store.py` is registered for a snapshot id's timestamp
  (an identifier, like a draft id's).
- **Trashing an entity DOES move the fingerprint**, though §4.4 says the trash is
  excluded. Reason: a delete drops the trashed entity's references out of the
  live `extra`s that named it and hides its relations, so `live_extra`/the
  `live_relations` view return different content. "Trash excluded" means the
  trashed row's own columns, `extra` and sections are not hashed — verified: a
  rename inside the bin moves nothing, and delete+restore returns to the same
  hash. Anything that reads §4.4 as "a delete is not a change" is wrong.
- A staged draft takes an **automatic backup** (`core/trash.py:209`,
  `:1365` via `create_backup(automatic=True)`) — unrelated to this feature, but
  it is why a test asserting "no backup was taken" must start from an empty
  backup list.
- SQLite creates `-wal`/`-shm` beside a file **before** it discovers the file is
  read-only, so one read-write open of a frozen draft leaves two empty files.
  They are harmless to the draft's bytes but are exactly the debris that makes a
  later reader open a stale view. `store._drop_sidecars` sweeps them on every
  write and a test pins it.
- `store.delete_branch` prunes by **reachability** (walk `snapshot_parents` from
  every branch's `base_snapshot_id`), not by `snapshots.branch_id`. §4.3 says
  "reachable from no remaining branch head and not an ancestor of any remaining
  snapshot"; ownership would delete a draft a merge brought into a surviving
  branch.

### Deviations
- **Switch takes no safety backup** (owner decision). §4.3 asks for one *and* a
  park. The park is byte-for-byte the pre-switch state and is addressable by
  branch name, while `prune_automatic_backups` keeps the newest
  `AUTO_BACKUPS_KEPT` of `kind="automatic"` regardless of label — a
  `before-switch` copy would evict a daily one. `load_database_in_place` grew
  `safety_label=None`. Undo is switching back.
- **Switch refuses while the head has an open staged draft** (owner decision).
  §4.3 is silent. A staged draft lives only in `story.db` and is deliberately not
  part of a draft, so the copy would destroy it. The parked head keeps its
  drafts, so switching back restores them; only the destructive direction is
  refused. Carrying them to the target is not an option — the ops were validated
  against the old head's ids.
- **Snapshot files are `chmod 0444`** (owner decision), as §4.3 asks. Deletion is
  by directory, so delete-branch/delete-snapshot still work.
- A branch's id is slugged from its name **once** and survives a rename (§4.3
  calls the name a label). `heads/<branch_id>.db` therefore reads
  `heads/main.db`. Renaming does not move files or snapshot rows.
- `snapshot_parents` is written by `save_snapshot`, which turns
  `branches.pending_merge_parents` into a second parent row and clears it (§7.9).
  Nothing sets that column until T8; the column and the writer exist now because
  §4.2 puts them in this schema.
- `merge_sessions` is created here and left empty — §4.2 lists it in the T3
  schema, so T9 extends a table rather than migrating one in.
- The `heads/<branch>.db` of the branch being switched **to** is deleted after
  the copy: its head is the live database now, and a stale duplicate left behind
  would be what a later switch loaded.

### Issues
- **Safety copies share the 20-slot automatic cap with the daily backup.** Still
  true of `restore_backup` (`before-restore` copies evict daily ones); T3's
  switch avoids adding to it by not taking a backup at all. If the daily history
  matters on a heavily-restored project, the cap needs to count kinds
  separately — not this feature's change.
- Backups stay the escape hatch worth keeping when `history.db` is what broke: a
  draft is a file plus a manifest row, so losing the manifest orphans it, while
  `restore_backup` on a plain `story_*.db` needs only the app. Do not delete the
  backup path on the grounds that drafts cover it.
- `switch` refuses on any `status='open'` draft row, including one staged by the
  agent and never shown to the user. That is deliberate (the alternative is
  silent loss), but T10's route must relay the id list, or the refusal reads as
  an unexplained dead end in the UI.
- `head_state()` opens `story.db` through `get_db`, which **migrates** it. That is
  correct for the live database (it is what every reader does) and must never be
  pointed at a draft file — the migration would rewrite a frozen draft. T4's
  `ProjectView` is the copy-in, copy-out path for drafts.

---

## T4 — `ProjectView` and the logical entity

### Findings
- **A draft file is `chmod 0444` and SQLite writes `-wal`/`-shm` beside it BEFORE
  it discovers the file is read-only.** So one read-write open of a draft (what
  `get_db` would do) leaves two empty files beside a frozen draft, and a `-wal`
  beside a snapshot is what makes a later reader see a stale view of it.
  `store._drop_sidecars` sweeps them after every history write, and
  `tests/test_history_store.py` pins it. `core.history.view.project_view` copies
  the draft out with the backup API and never opens it in place; its test asserts
  the snapshot directory is byte-for-byte unchanged across a read.
- `fingerprint.of_project` and `store.head_state` go through `get_db`, which
  **migrates**. That is right for the live database and wrong for a draft: the
  migration would rewrite a frozen file. Anything that reads a draft goes through
  `project_view`'s copy; the view validates the draft with `check_source` and lets
  `get_db` migrate the copy.
- `core/history/store.py` is registered in `LOCAL_TIME_ALLOWED`
  (`tests/test_utc_stamps.py`) for a snapshot id's timestamp. A new
  `core/history/*.py` that needs `datetime.now`/`.isoformat` must add itself with
  a reason or the stamp guard fails. **T4 added no such file**: neither `view.py`
  nor `logical.py` reads the clock.
- Snapshot ids are `s-<stamp>[-n]`, so a draft's file is
  `history/snapshots/s-<stamp>.db`. `project_view` takes a snapshot id, not a
  path, and resolves it through `store.snapshot_file`.
- `FROM live_relations` is free of the raw-relations registry
  (`tests/test_live_relations.py:328`), so `logical.materialize` reads the view
  with no registry edit. A raw `FROM relations` would need one.
- **The fixture has one `extra` key no schema declares: `project.memory`.** It is
  live content (`story_memory` is an agent-facing tool, `story_export` writes it
  to `.story/memory.md`, a write moves the fingerprint) but `create_entity`
  refused the key, so a logical-entity round trip could be exact and still drop
  it. **Settled in T4, option A** (owner): `memory` is declared on `project` as
  an `object` field, hidden from the entity form and skipped by
  `unfilled_fields`, since `story_memory` writes it one entry at a time.
- **Act order was content the fingerprint ignored.** `reorder(act)` is refused,
  but `edit_entity` accepts `order` on an act and four readers sort by
  `order_key`, so an act-only reorder was refused by `save_snapshot` as "Nothing
  has changed". **Settled in T4, option A** (owner): `act` is in
  `fingerprint.ORDERED_TYPES`. Renumbering acts without reordering still hashes
  stable, which is why the per-parent id list was already the right
  serialization.
- **`create_entity` auto-numbers scenes and sequences, and does not number acts.**
  It numbers a child from the live sibling set, so a rebuild in id order gives a
  different story order than the source. `logical.rebuild_copy` therefore sorts
  children by the parent's declared order; `materialize` drops a scene's or
  sequence's `order` field (order is the id list) and keeps an act's.
- **`create_entity` creates every standard section heading**, so a materializer
  that emits only the headings it found cannot round-trip a state whose empty
  rows were pruned. `logical.materialize` normalizes to `standard_sections(type)`
  with `""` for a missing body.
- `edit_entity` and `delete_entity` both need more than the obvious arguments:
  `delete_entity(project_path, type, id, summary, confirm=True)` refuses without
  `confirm`, returning `would_delete` as a preview rather than deleting. A probe
  that omits it silently tests nothing.

### Deviations
- **`memory` is declared, form-hidden and unfilled-suppressed, not given a form
  field** (owner decision, F-1 option A). The spec's §5.1 defines the logical
  entity through the schema, so declaring it is the smallest change that makes it
  part of the shape; a form field would imply an author edits it there, which is
  not how it is written.
- **`act` joins `ORDERED_TYPES` while `reorder()` still refuses acts** (owner
  decision, F-2 option A). `order` remains an act field for writes, and the
  per-parent id list carries the same fact for the hash — two views of one
  ordering, both read from `order_key`.

### Issues
- **The T3 fingerprint changed for any project with more than one act**, because
  `act` order is now hashed. A project with a single act is unaffected (a
  one-element list). This is a hash value change only: `history.db` stores
  fingerprints, so a draft saved before this commit will not match a recomputed
  fingerprint of the same state. Pre-publication, and no migration is needed —
  but a stale `changed` flag on an old draft is expected, not a bug.
- §4.3's "views are cached per session" is not implemented: `project_view` copies
  per block with no cache. T10 owns sessions and is where a cache belongs.

---

## T5 — `refmap`

### Findings
- **22 reference sites over 10 entity types.** Five are declared by none of the four
  mechanisms (`ref`, `REFERENCE_*`, relation kind, bespoke validator); probed with a
  dangling slug, four are **accepted** by `create_entity`: `sequence.primary_plot`,
  `location.variant_of`, `relationship.characters[]`, `relationship.scenes[]`. The fifth,
  `value_turns[].value`, is refused by `validate_scene_value_turns`. `sequence.primary_plot`
  is declared by nothing at all — that is the module's justification.
- **`value_turns[].value` stores the value's display NAME, not its id.** Verified: a turn
  for value `free-will` (name `Free Will`) stores `"Free Will"`; writing `"free-will"` is
  refused ("is not a defined value"). So `refmap.rewrite` takes `by_id` and `by_name` as
  SEPARATE lookup spaces — a merged dict lets a name equal to another entity's id rewrite
  the wrong site. Both directions are pinned.
- **`plot.<role>` (six lists) are the same relation rows as `scene.plot_roles`**, read from
  the plot side, and `logical.materialize` emits both. One authored role edit therefore
  shows as **two** changed fields (probe: `plot_roles[].description` → differences at
  `scene.plot_roles` and `plot.inciting_incident`). They are `computed`, so `edit_entity`
  reports `success` with `skipped_read_only=['climax']` and changes nothing.
  `refmap.DERIVED` is the exclusion list.
- **`scene.act_id` duplicates the parent chain and drifts.** Verified: `edit(scene,
  sequence_id=seq-2)` where `seq-2` sits in `act-2` → scene parent `seq-2`, `extra.act_id`
  still `act-1`; `create_entity` then refuses the entity ("Sequence seq-2 belongs to act
  act-2, not act-1") and the logical round trip fails. Declared DERIVED, not a site.
- **`scene.scene_beats` is a declared `ref` that is `computed` and absent from the shape** —
  the only one of the seven `ref`s that is missing from `materialize` output. `plot.<role>`
  and `plot_roles` are relation-backed, so `materialize` fills them after the computed
  filter (`logical.py:131`).
- **The write path accepts an entity that no longer says what it is**: `sequence_id=""`,
  `beats=[]`, `characters=[]`, `act_id=""` are all accepted. So `required` in refmap is
  §7.4.2's decision, not a fact derived from what the code refuses.
- **An empirical sweep of `materialize` output cannot catch an unused reference field.** A
  new site on `project` with no fixture value fails nothing; one whose default holds a real
  id is caught. The declared-ref walk is the other half and is not optional.
- `location.variant_of` is the one site the fixture never exercises (zero
  `location_variant` rows; the world counterpart has one).

### Deviations
- **`Site.checked_by` records the validator, or `None`** rather than a boolean "declared".
  Nine sites have no validator; the test names the exact set, so a new unchecked site cannot
  join it quietly.
- **No storage field on a `Site`.** T7 emits drafts ops by field name, so `extra` vs column
  vs relation is invisible to it; the pinning test resolves each site against the maps.

### Issues
- **`scene.act_id` must be written together with `sequence_id` by the merge executor.** Any
  plan that moves a scene across acts and writes only `sequence_id` produces an entity
  `create_entity`/`edit` will refuse, so the plan's own dry run fails. Recorded under T7/T8.

---

## T6 — Diff

### Findings
- `live_relations` hides every relation row either end of which is deleted, so
  "trash ignored" (§6.1) comes for free on that path. A raw `FROM relations`
  read does not: a trashed scene still holds its `plot_<role>` rows and its
  cast rows. Read the view, or filter `is_deleted` explicitly.
- **Order is NOT part of `logical.materialize`'s output.** It returns
  `{id: {id, type, fields, sections}}`; child order lives in
  `logical.order_of(conn)` as a per-parent id list. A diff that compares only the
  materialized shapes reports a pure reorder as **no change** — pair both sides
  with `order_of`. (`order_of` reads the same rows and tie-break as
  `fingerprint`, so the two cannot disagree.)
- **`fields` values arrive in their authored shape, not as flat strings:**
  `scene.plot_roles` is `[{plot, role, description}]`, a plot's beat lists are
  `[{scene_id, description}]`, `relationship.perspectives` is a keyed object, and
  only `character_scene` cast is a plain id list. §6.1's element-wise
  `REFERENCE_LISTS` diff therefore applies to the plain id lists only; the rest
  are whole-value until the diff is taught their shape.
- `project.memory` is part of `fields` now (an object of four string lists). It
  diffs as a whole value; there is no per-entry granularity unless §6.1 asks for
  it.
- Two **live** siblings can already share an `order_key`: a delete frees a key,
  `_get_next_order_db` reissues it, and a restore leaves the pair in place. So
  the child order must be serialized as the `(order_key, id)` id list (§4.4's
  fingerprint does this too), never as the raw key values — two states that
  differ only in which of two tied siblings sorts first would otherwise diff as
  equal.
- `tests/test_live_relations.py` pins every raw `relations` read with a count
  per file. A diff that needs one must add itself to that registry and its
  docstring reason, or the suite fails with an unexplained count mismatch.
- **One authored role edit appears as TWO changed fields.** `logical.materialize`
  emits a role on both sides of the same relation rows: `scene.plot_roles` (the
  authored side) and the plot's six `setups`/`inciting_incident`/… lists (the read
  side). A diff that reports both makes a merge item out of a derived view.
  `refmap.DERIVED["plot"]` is the exclusion list, verified in T5.

### Deviations
### Issues

---

## T7 — Planner

### Findings
- `logical.rebuild_copy(entities, order, dest)` creates a whole materialized shape
  through `create_entity`, but it sorts by an `order` mapping. A plan bringing ONE
  entity has no such mapping and must not invent one: `create` the entity and let
  the reorder step settle its position.
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
- **`refmap` is the reference source: `iter_references(type, fields)` and
  `rewrite(type, fields, by_id=…, by_name=…)`.** Paths are concrete
  (`value_turns[0].effects[1].character`), so the decision key can name the entry.
  `by_name` is a SEPARATE lookup space: `value_turns[].value` holds the value's
  display name, not its id, so a D1 keep-both on a value maps by name and an id
  mapping must never be used for it.
- **The plot's six `<role>` lists are `refmap.DERIVED`.** A role change is an edit
  of `scene.plot_roles`; nothing may emit an op against `plot.setups` and friends,
  because they are `computed` and `edit_entity` returns `success` with
  `skipped_read_only` while changing nothing — a silent no-op in a merge.
- **`scene.act_id` drifts and must be written with `sequence_id`.** Moving a scene
  to a sequence in another act with only `sequence_id` leaves `act_id` stale, and
  the resulting entity is refused ("Sequence X belongs to act Y, not Z"), so the
  dry run fails on the plan's own output. §7.6's scene move is exactly this shape:
  write both fields in the one edit.

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
- §7.9's "complete merge" has its storage ready: `branches.pending_merge_parents`
  exists and `store.save_snapshot` already turns it into a second
  `snapshot_parents` row and clears it. The executor's only job is to append the
  source's snapshot id to that column; it must not insert into
  `snapshot_parents` directly, or a save would double-write the parent.
- `store.save_snapshot` takes the history lock (`BEGIN IMMEDIATE` on
  `history.db`) for its whole body. A complete merge that sets
  `pending_merge_parents` and then saves **must not hold its own connection to
  `history.db`** across that call — it would deadlock against itself. Set the
  column in one history transaction, commit, then call `save_snapshot`.
- `store.switch` refuses on any `status='open'` draft. Applying a plan inside one
  transaction on the live database needs no switch; if the executor ever
  sequences one after a merge, it must land after the commit, not inside it.
- **A scene op that changes `sequence_id` must carry `act_id` too.** Probed: the
  two drift apart, and the entity is then refused by the write path ("Sequence X
  belongs to act Y, not Z") — so the executor's own dry run fails on the plan's
  output rather than at apply time. Applies to any op that moves a scene between
  acts, including §7.6's post-reorder step.
- `refmap.rewrite` returns a NEW `fields` dict and never mutates the incoming
  items, so an executor can rewrite an item and still compare against what the
  plan was computed from.

### Deviations
### Issues

---

## T9 — Persistent merge sessions

### Findings
- **The `merge_sessions` table already exists**, created by T3 verbatim from
  §4.2 (`id, target_branch_id, source_ref, base_snapshot_id, target_fingerprint,
  selection, decisions, status, created_at, updated_at`) and left empty. T9
  writes rows; it does not migrate the table in. `history.db`'s `MIGRATIONS` list
  is empty, at `BASELINE = 1`.
- A session's stored decisions are keyed by item path; T1's `resolutions` shape
  (`{plot, role, choice: drop|take}`) is the value a D4 decision writes. Persist
  the shape as-is — the executor hands it straight to `core.trash.restore`, so a
  session that round-trips through the manifest must not rename `choice`.
- `restore_needs_decision` is a refusal *result*, not an exception, and it
  carries `collisions`. If a session records "unresolved" it must record which
  collision, not only that apply failed.
- `store._locked` is the pattern for any new history transaction: `BEGIN
  IMMEDIATE` up front and hold it over the file moves. Writing a session row is a
  plain manifest write and needs only `store.connect` + `core.db.transaction`.
- Timestamps in `history.db` come from `core.clock.now_iso()`, like every other
  stored stamp. A new `core/history/*.py` that calls `datetime.now` directly
  fails `tests/test_utc_stamps.py` until registered in `LOCAL_TIME_ALLOWED`.

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
- **The history API is all `ValueError` for a refusal, and there is no refusal
  payload yet.** `store.save_snapshot` (nothing changed), `switch` (open drafts,
  already current, no parked head), `branch_from` (missing draft, duplicate
  name), `delete_branch` (current branch) and `delete_snapshot` (a branch's
  latest draft) all raise `ValueError` with an actionable message, following the
  core convention (§9). The routes map them to `409`/`400` with the envelope
  above; a `switch` refusal must carry the open draft ids *as data*, because the
  message alone is not something the UI can act on.
- `store.list_branches(project_path)` is the whole `GET /history/` payload already
  — branches (`is_current` included) and snapshots with `parents`. `head_state`
  adds `changed`. T10 computes `changes_since_save` from that flag; nothing new
  needs storing.
- `list_projects` (`app/services.py:16`) opens each project's `story.db` with a
  bare `sqlite3.connect` to read the name. Enriching it with
  `current_draft`/`branch_count`/`last_saved` means opening `history.db` too, per
  project, on every landing-page call. `history.db` may not exist yet (a project
  never touched by this feature) — treat a missing manifest as "no history", and
  do **not** call `store.adopt` from a listing, which would write during a read.

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
- `story_history` has its whole surface ready as plain functions:
  `store.list_branches` (branches + drafts + parents), `store.head_state`
  (`changed`, the base draft), `store.save_snapshot`, `store.branch_from`,
  `store.switch`. They take a *project path* and raise `ValueError`.
- **`switch` is not safe to expose as an agent action before T12.** It replaces
  the live database, refuses on open staged drafts, and has no approval card
  until T12. §11's "until the card exists, those actions are UI-only" applies:
  `story_history` gets `list`, `save`, `branch`; `switch` and the deletes wait.
- A `switch` refusal for open drafts carries the draft ids only inside the
  message. An agent tool must surface them verbatim — the fix is
  commit-or-discard, which the agent cannot do on the user's behalf.

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
