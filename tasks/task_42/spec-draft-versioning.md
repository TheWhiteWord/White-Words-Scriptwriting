# Spec — Drafts: versioning, branching, diff and merge

Status: **for review** · Target branch: work on a branch off `dev` · UI mock-up follows after this spec is approved.

How to read this: facts marked **Verified** were read in the code at `dev`. Anything marked **To verify** is an assumption the first task that touches it must confirm before building on it. Decisions that need your review are collected in §14.

---

## 1. Vocabulary

"Draft" already means something else in the code: the `drafts` table, `core/drafts.py`, the `story_draft` tool (staged agent proposals), the title-page `draft` field, and a column in the chat store. "Version" is the concurrency token in `core/versions.py`; "revision" is section-text history; "backup" is `core/backups.py`.

| UI term | Internal term | Meaning |
|---|---|---|
| Draft | **snapshot** | An immutable, saved copy of the whole project database. |
| Branch | **branch** | A named line of snapshots. |
| (Open draft / "in progress") | **head** | The one mutable state of a branch: where the user is working. |
| Merge | **merge session** | A persistent, reviewable plan for bringing changes from one snapshot or head into a branch's head. |

Rule for code and comments: never write "draft" in new code for this feature except in user-facing strings. Existing staged proposals keep the name `draft`.

## 2. Goals and non-goals

Goals
1. Save the whole project state as a snapshot; branch from any snapshot; open any snapshot read-only.
2. Diff any two states two ways: by entity (field/section) and by script (composed scene text and placement).
3. Merge from any state into a branch's head, selecting individual fields, sections, scenes or entities, with dependencies resolved by explicit rules and explicit user decisions.
4. A landing page that lists projects, shows each project's current draft, and expands to the branch graph and the diff/merge workspace.
5. The agent can do through tools what the user can do in the UI, and can help fill in decisions. It is never required.

Non-goals (this spec)
- Merging two *projects*. Branches live inside one project.
- Real-time collaboration.
- Compression or delta storage of snapshots (§4.6).
- Chat history in snapshots. `chat.db` stays outside; one conversation continues across drafts.

## 3. Verified facts about the code

| # | Fact | Where |
|---|---|---|
| F1 | A project is a folder with one SQLite file `.story/story.db` (WAL mode). Chat is a separate `.story/chat.db`. | `core/db.py`, `chat/store.py` |
| F2 | Entity ids are human slugs, fixed at creation; there is no id-rename path. Identity across snapshots is therefore the id. | `core/writes.py` (`create_entity`, comment in the value-edit check) |
| F3 | `entities(id PK, type, name, one_sentence, order_key REAL, status, parent_id, location_id, is_deleted, deleted_at, extra JSON)`; `relations(from_id,to_id,kind PK, note, "order")`; `sections(entity_id, heading PK, body)`; `drafts`; `revisions`. Reads go through the `live_relations` view. | `core/db.py` |
| F4 | Soft delete keeps every row. Ids stay occupied while in the trash. | `core/trash.py`, schema |
| F5 | All writes go through `core.writes` (`create_entity`, `edit_entity`, `delete_entity`, `reorder`), each accepting an optional `conn` to run inside the caller's transaction. | `core/writes.py` |
| F6 | `core.drafts` already stages an op list (`create`/`edit`/`delete`/`reorder`/`purge`), replays it against a throwaway copy (`dry_run`: a temp dir holding `.story/story.db` made by `Connection.backup()`), and commits it all-or-none by calling `_dispatch` per op. | `core/drafts.py` |
| F7 | `sorted_ops` orders ops create → edit → delete → reorder. | `core/drafts.py` |
| F8 | `backup_database()` copies story.db with SQLite's backup API (WAL-safe, atomic via `.partial`). `restore_backup()` validates a file (integrity, schema version, page size), takes an automatic safety backup, then copies the backup **into the live DB in place** so other open connections see it. Manual backups are never pruned. | `core/db.py`, `core/backups.py` |
| F9 | Schema versioning: `PRAGMA user_version`, `BASELINE_VERSION = 5`, `SCHEMA_MIGRATIONS = []`, `apply_migrations()`. `chat.db` uses the same pattern independently. | `core/db.py`, `chat/store.py` |
| F10 | `get_db(project_path)` opens `<project>/.story/story.db`, and migrates it. Every read and write function takes a *project path*, not a connection. | `core/db.py` |
| F11 | Three scene roles are singular per plot (`UNIQUE_PLOT_ROLES`: `inciting_incident`, `crisis`, `climax`). The rule lives in `validate_scene_plot_roles` and is enforced at write time only. The `relations` primary key `(from_id,to_id,kind)` does not prevent two scenes holding the same singular role. | `core/entity.py`, `core/constants.py` |
| F12 | `trash.restore()` only clears `is_deleted`. It does not check role collisions or `order_key` collisions. `restore_check()` (used by the dashboard route) checks parents, hidden links and stranded children, but not those two. | `core/trash.py` |
| F13 | `reorder()` supports only `scene` and `sequence`, renumbers `1..n` inside one parent, does **not** verify the list is the complete sibling set, and does not filter `is_deleted` when looking items up. | `core/writes.py` |
| F14 | Name uniqueness is enforced only for `value`. Characters, locations, etc. may share a display name. | `core/writes.py` (`validate_value`) |
| F15 | Reference sites are partly declared: `REFERENCE_LISTS`, `REFERENCE_MAPS`, `REFERENCE_COLUMNS` in `core/references.py`, `ref` markers in `ENTITY_SCHEMAS`, relation kinds. Some sites have no single target type (beat `by`, `changes.entity`). | `core/references.py`, `core/constants.py` |
| F16 | The agent reaches the app through one MCP server (`ww-script`) whose tools are a flat list `TOOL_MODULES`; each module is one noun with an `action` enum (`story_backup`: create/list/restore). There is no toolset grouping inside the repo; the Hermes profile disables built-in toolsets. | `app/mcp_server.py`, `adapters/hermes/setup.py` |
| F17 | Hermes spills MCP results above a size threshold that shrinks with the model's context. Tool results and schemas must stay small. | `adapters/hermes/budget.py` |
| F18 | `chat.db` and the chat routes are per project (`/api/projects/{slug}/…`). The chat context carries `attachments` (`kind`, `id`, `label`). | `chat/store.py`, `chat/context.py`, `web/js/chat-api.js` |
| F19 | `list_projects()` returns only slug, `has_db`, name. | `app/services.py` |

**To verify during the tasks that touch them:** the logical-entity materializer's exact source (§5.1); the HTTP error shape; what `delete_project` does with files under `.story/`; whether anything other than the app process opens `story.db` for writing (CLI, other Hermes processes), which decides the locking in §4.5.

## 4. Data model

### 4.1 Files

```
<project>/.story/
  story.db                      the live database = the working copy of the CURRENT branch's head
  chat.db                       untouched
  history.db                    manifest: branches, snapshots, parents, merge sessions   (new)
  history/
    snapshots/<snapshot_id>.db  frozen, never modified after creation                    (new)
    heads/<branch_id>.db        the parked head of every NON-current branch              (new)
```

The manifest lives in its own file because `story.db` is overwritten when the user switches branch (F8's in-place copy). It follows the `chat.db` pattern (F9): its own baseline version and migration list.

### 4.2 Manifest tables (`history.db`)

```
branches(id TEXT PK, name TEXT UNIQUE, base_snapshot_id TEXT NOT NULL,
         is_current INTEGER, created_at TEXT, pending_merge_parents JSON)
snapshots(id TEXT PK, branch_id TEXT, seq INTEGER, label TEXT, note TEXT,
          created_at TEXT, schema_version INTEGER, fingerprint TEXT, counts JSON)
snapshot_parents(snapshot_id TEXT, parent_id TEXT, ord INTEGER, PK(snapshot_id, parent_id))
merge_sessions(id TEXT PK, target_branch_id TEXT, source_ref JSON, base_snapshot_id TEXT,
               target_fingerprint TEXT, selection JSON, decisions JSON,
               status TEXT, created_at TEXT, updated_at TEXT)
```

- Snapshot ids are generated like draft ids (`new_draft_id` style, unused-id check) with a distinct prefix.
- `branches.base_snapshot_id` is the branch's latest frozen snapshot: the head is "that plus whatever was done since".
- Exactly one branch has `is_current = 1`; its head is the live `story.db`.
- A first-time project is adopted lazily: the first call that touches history creates branch `main` and snapshot "Draft 1" from the current state. Existing projects need no migration.

### 4.3 Operations

**Save draft.** Refuse if the head's fingerprint equals the base snapshot's (nothing changed). Otherwise: `backup_database(dest_dir=history/snapshots, prefix="snap")` from the live DB, then on the copy `DELETE FROM drafts` (staged proposals belong to the head they were made on, not to the story) and `VACUUM`, then mark the file read-only, insert the manifest rows in one transaction, and move `base_snapshot_id`. The head state is unchanged, so there is nothing to copy back.

**Branch from a snapshot.** Create a branch row with `base_snapshot_id = that snapshot`; its head is a copy of the snapshot, parked at `heads/<branch>.db`. The user then chooses whether to switch to it.

**Switch branch.** Under the history lock (§4.5): park the live DB as `heads/<current>.db` (backup API), then load `heads/<target>.db` into the live DB in place, then update `is_current`. The in-place load is the core of `restore_backup()` (F8) extracted into a function that takes any validated source file; `restore_backup` and switch both call it. A safety backup is taken first, as restore does today.

**Open read-only.** Reading a frozen draft with the existing read functions needs a project-path-shaped directory (F10). `get_db` opens read-write and migrates, so pointing it at a snapshot file would create `-wal` files beside the snapshot and could modify it. Therefore a **`ProjectView`** context manager copies the snapshot with the backup API into a temp dir as `.story/story.db`, hands out that temp *project path*, and deletes it on exit. The data is text only and small (about 7 ms per copy, 18 ms for a diff of two views, measured in T10), so each request makes its own copy and nothing is cached: a cache would leave temp dirs outliving requests and need invalidation on save, switch and merge, and a stale view is the one failure this feature cannot afford. A cache can be added behind `project_view` later without changing a caller. Nothing writes to `history/snapshots/`.

**Rename branch.** Label only.

**Delete branch.** Deletes the branch row, its parked head, and every snapshot reachable from no remaining branch head and not an ancestor of any remaining snapshot. Shared ancestors and merged-in snapshots stay. The current branch cannot be deleted. The confirmation shows the exact count of drafts and the files that will go.

**Delete a draft (snapshot).** The branch's open head and a branch's `base_snapshot_id` cannot be deleted. For any other snapshot, its children are re-attached to its parents (all of them, preserving order), then its file and rows are removed. A later merge may find an older, less precise common ancestor and show more conflicts; it never produces a wrong result.

### 4.4 Fingerprint

A SHA-256 over a canonical serialization of **logical content**: live entities (excluding `deleted` ones), their fields (columns and `extra`, computed fields excluded), their sections, and live relations, sorted by id. It excludes timestamps, `revisions`, `drafts`, trash, and `order_key` values themselves (order is serialized as the per-parent id list instead, so renumbering without reordering does not change it). Used for: the "nothing changed" guard, "N changes since Draft 3", and the stale-plan check in §7.7.

### 4.5 Concurrency

History operations (save, switch, branch, delete, apply merge) take an exclusive lock: `BEGIN IMMEDIATE` on `history.db`, which also serializes across processes, plus a process lock around the file moves (precedent: `_periodic_lock` in `core/backups.py`). **To verify:** whether any non-app process writes `story.db`; if one can, the in-place load is already as safe as `restore_backup` is today, and the app should refuse a switch while a staged proposal commit is running.

### 4.6 Disk use

Snapshots are written compacted (`VACUUM`), duplicates are refused by the fingerprint guard, the data is text, and unreachable files are removed on delete. No compression or delta storage: reading a frozen draft would then need unpacking, and the saving is small at this size. This can be added later behind `ProjectView` without changing anything else.

### 4.7 Schema versions

A snapshot records `schema_version`. `ProjectView` and load-in-place migrate a *copy* forward with `apply_migrations` (as `restore_backup` already does); snapshots from a newer build than the app, or older than `BASELINE_VERSION`, are refused with the same messages `restore_backup` uses today.

## 5. Reading a state: the logical entity

### 5.1 Why not raw rows

An entity is columns + `extra` + `sections` + `relations`, and some facts are stored twice or from the other end: a scene's `location_id` column and its `location_scene` relation (F-note in `trash._warning`); `plot_roles` on a scene are stored as `plot_*` relations owned by the plot; cast and scene beats are linked through relations and `parent_id`. Diffing rows would report one authored change as several.

The **logical entity** is the entity as an author writes it: `{id, type, fields, sections}` with computed fields excluded (the schema marks them `computed`: `value_focus`, `turning_point`, `places`, `scene_beats`, plot role lists, …). It is obtained through the same code path the retrieve tool and `validate_entity` use. **To verify in task T4 with a spike**, because everything later depends on it: for every entity in a fixture project, materialize → `create_entity` into an empty project → materialize again, and the two must be equal. That round-trip test is permanent.

### 5.2 Structure as lists

Order is not a field. For each parent, the **child order** is the id list ordered by `(order_key, id)` over live scenes (per sequence) and sequences (per act). It is diffed and merged as one unit (§7.6). Acts are not reorderable through `core.writes` (F13: `REORDERABLE_TYPES`); the spec treats act order as part of the act entity's fields until that changes.

## 6. Diff

Two states in, one structured result out; the same result feeds the entity view, the script view, and the merge planner.

### 6.1 Entity diff

For each id present in either state (live content only; trash ignored, §7.5 covers the exception):

- `added`, `removed`, `unchanged`, or `changed`.
- For `changed`: per **field** and per **section**, `(a, b)` values.
- List-valued fields that hold ids (the `REFERENCE_LISTS`, unordered) are diffed per element (added/removed ids). Other lists (e.g. `beats`, arrays of objects) and scalars are whole-value.
- Section text: line-level diff with `difflib` (stdlib). Optional dependency, ask before adding: `merge3` for the three-way text merge in §7.3.

### 6.2 Script diff

Per scene: the composed text (heading from `int_ext`, `location`, `place`, `time_of_day`, `forced_heading`, and the `Content` body) produced by the existing screenplay composer on each state's `ProjectView`, plus the scene's placement (act, sequence, position). Result units are scenes: `added`, `removed`, `moved`, `edited` (heading and/or body), with the text diff inline. A scene's script-level row links to its entity-level items; the script view is a **lens** over the same items, never a separate engine.

## 7. Merge

### 7.1 Shape

A merge brings changes from a **source** (any snapshot, or another branch's head) into the **target** (a branch's head). The target is always a head: frozen drafts are never merge targets. The engine runs on files, so the target need not be the branch loaded in `story.db` (§7.8).

Three states: **base** (merge base), **ours** (target head), **theirs** (source). The merge base is the most recent common ancestor of the target branch's `base_snapshot` and the source snapshot, found in the snapshot graph. If several equally recent ancestors exist (criss-cross merges), the engine takes the most recent and marks the session `imprecise_base` so the UI says so. Without a base we could not tell "added there" from "deleted here"; the graph guarantees one exists because all branches descend from the project's first snapshot.

### 7.2 Items and selection

The diff yields **items**: one per entity create/remove, one per changed field, one per changed section, one per child-order list. A **selection** is a set of items. Nothing is applied that is not selected, and a dependency of a selected item is pulled in by the rules of §7.4. Selecting at script level selects a scene's *group*: the scene's fields, its `Content`, its `scene_beats` entity, its placement.

### 7.3 Resolution of one item (three-way)

| Changed in ours? | Changed in theirs? | Result |
|---|---|---|
| no | yes | take theirs (if selected) |
| yes | no | keep ours |
| yes, equal | yes, equal | nothing to do |
| yes | yes, different | **conflict** |

Every conflict has the same three outcomes: **Mine**, **Theirs**, **Custom**. Custom is a typed value for a scalar, an element picker for an id list, an editor for a section (pre-filled with theirs, with `merge3`/`difflib` showing the divergent regions), and a drag-to-arrange list for order. Custom input is validated by the real validators during the dry run (§7.7); an invalid value shows the validator's own message next to the field and disables Apply. Computed fields are never offered.

### 7.4 Dependencies

Selecting an item expands it, in four kinds:

1. **Comes with it** (automatic): a scene's `Content`, its `scene_beats` entity, its placement.
2. **Must resolve**: references the incoming content makes. Satisfied if the target already has the id (matched by id) or if the referenced entity is brought along (recursively applying these rules). Otherwise the user chooses: *bring it*, *drop the reference*, or *cancel the pick*. "Drop" is offered only where the reference is optional (cast, `location`, `plot_roles` entries, relationship scene lists). A beat's actor (`by`), a value turn's value, a scene's parent sequence are not optional.
3. **Collides**: the incoming content breaks a rule in the target (§7.5).
4. **Needs placement**: a scene entering the target (§7.5).

The reference sites come from a single module, `refmap` (§9), pinned to the schema by a test, in the style of `test_live_references`. Sites without a single target type (F15) resolve by id lookup across types.

**Removal** (selecting a deletion): the scene's beats go with it automatically. Entities that only the removed scene referenced are listed as optional cleanup, **unticked**; anything with another live referrer is never offered. Roles it held disappear with it (relations owned by the plot).

### 7.5 Decisions catalogue

Every decision has a stable key (item path + kind), a set of options, a conservative default, and a record of who set the current choice (`default` | `user` | `agent-suggested`).

- **D1 same id, different thing** (added on both sides, or id present in ours but absent from base and from theirs' history): *keep mine*, *take theirs*, *combine field by field* (the Mine/Theirs/Custom rule per field), *keep both* under a new id. For keep-both the engine suggests `<id>-2`, the user may type any valid id (alphanumeric, hyphens, underscores; for a `value` the id is derived from its name and shown, not editable, F2/`validate_value`). The conflicting fields (typically `name`) are pre-filled as Custom inputs. Every reference inside the *incoming* items is rewritten by `refmap`. A warning, not a block, when the display name equals an existing one (F14).
- **D2 field/section/order conflict**: Mine / Theirs / Custom (§7.3).
- **D3 placement of an incoming scene**: propose in order (a) after the scene that preceded it in the source, if that scene is in the target; (b) else before the one that followed it; (c) else the user picks a sequence and position from the target's scenes. Override always allowed. If its sequence or act is missing in the target: *bring the sequence (and act) along* (must-resolve), or *place it in another existing sequence*. A fourth option, **in place of `<scene>`**, is Replace (below).
- **D4 role collision**: an incoming scene holds a singular role (F11) for a plot whose target already has it on another scene. Options: **Mine** (the existing scene keeps it; the incoming scene arrives without that entry), **Theirs** (the incoming scene takes it; the existing scene loses it), **Replace** (the incoming scene takes the existing scene's position and the role; the existing scene is soft-deleted), **Custom** (the incoming scene arrives with a different role for that plot).
  - Theirs edits a scene the user did not pick; the plan lists it as a side effect ("Also changes *X*: loses its inciting-incident role in *Plot*"). **To verify:** if the loser then serves no plot, whether `validate_scene_dramatic_role` leaves it valid with an empty `plot_roles` (the rule says `plot_role`/empty is allowed); if not, a follow-up decision offers mark-as-transition, assign another role, or cancel.
  - Replace transfers nothing else: its beats, cast links and roles in other plots are listed as lost ("Replacing X also removes: …"). Restoring is exact (F4), and a snapshot of the target is taken before the merge.
- **D5 missing reference**: bring / drop / cancel (§7.4.2).
- **D6 trashed in target**: the incoming entity's id exists in the target's trash. An INSERT would hit the primary key (F3/F4), so the plan says "*X* is in your trash; it will be restored and updated" and runs the restore guard (§8) with its own D4/D3 decisions.
- **D7 order conflict**: both sides reordered the same parent: Mine / Theirs / Custom list.
- **D8 cleanup after removal**: optional, unticked (§7.4).

### 7.6 Order

Per parent, the child order is a single item. One side changed it: take that side. Both changed it: D7. When a merge adds or removes children, the resulting complete list for each affected parent is computed once and applied through `reorder` (F13) with the **complete** sibling set, live rows only, so the known partial-list hazard is not reached. The planner asserts completeness before emitting the op. Moving a scene to another sequence is an `edit` of its parent field followed by a `reorder` of both sequences.

### 7.7 Plan, dry run, apply

1. **Plan**: diff + selection + dependency expansion → an ordered op list in the existing `core.drafts` vocabulary (`create`, `edit`, `delete`, `reorder`) plus the list of open decisions. Nothing is guessed silently.
2. **Execution order is explicit and not `sorted_ops`** (F7). `sorted_ops` puts creates before deletes, which breaks Replace and Theirs-swap: the incoming scene's singular role cannot be created while the old holder still has it. The executor orders: restores → edits that release roles → deletes → creates → other edits → reorders, and calls the per-op dispatcher directly. `_dispatch` is made public (`apply_op`) for this; `sorted_ops` and the drafts flow are unchanged. `restore` is not added to the agent-visible op vocabulary (`OP_ORDER`); it is internal to the executor.
3. **Dry run**: copy the target head into a scratch project directory (the F6 pattern), run the whole plan with the real validators, and map each failure back to the decision or item that produced it. Apply stays disabled while any decision is unresolved or the dry run refuses.
4. **Apply**: take an automatic snapshot of the target ("before merge from …"), then run the ops inside one transaction (all or none). The plan stores the target's fingerprint at plan time; if it differs at apply time the apply is refused and the session is re-planned. Decisions are kept by key wherever they still apply.
5. **Parents**: see §7.9.

### 7.8 Where the target lives

The executor always works on a database file. Target = current branch → the live `story.db`, applied inside one transaction with the history lock held. Target = another branch → its parked head: copy to a scratch project directory, apply, then write back to `heads/<branch>.db`. This is what lets merging happen from the landing page without loading the project.

### 7.9 What a merge records (decision needing review, §14-A)

Git records the source as a parent only for whole merges, because a recorded parent means "everything in it is already accounted for". A cherry-pick records none. This design needs the same distinction, or a partial merge would make the skipped changes disappear from every future merge.

- **Cherry-pick** (default): only the selected items are applied; no second parent; the graph draws a dashed "picked from" edge (informational). Unselected changes are offered again next time.
- **Complete merge**: the user declares "everything in the source is now accounted for; unselected items stay as mine". Only then is the source recorded in `branches.pending_merge_parents`, and the next *Save draft* writes it as a second `snapshot_parents` row, so the graph draws the join and later merges use the better base.

## 8. Restore guard (prerequisite, own commit)

F12 shows the gap: restoring a soft-deleted scene can create a second singular role for a plot and a duplicate `order_key`, and nothing warns. It exists today independent of this feature, and Replace makes it easy to reach, so it is fixed first.

- `restore_check` gains two findings, neither a blocker: **role collision** (options: restore without the role / restore and take the role from the current holder) and **position collision** (options: after its old neighbour [default] / before the next / pick a position; siblings renumbered).
- `restore` accepts the chosen resolutions and applies them in the same transaction. Without resolutions and with a collision present, it returns an error that names the fix, in the repo's agent-facing style, rather than writing an invalid state. **Behaviour change for the agent's `story_admin` restore: needs your approval (§14-B).**
- The merge planner reuses this guard for D6.

## 9. Module layout

```
core/history/
  store.py      history.db: branches, snapshots, parents; save/branch/switch/rename/delete
  fingerprint.py
  view.py       ProjectView (scratch copy of a snapshot as a project path)
  logical.py    logical-entity materializer + round-trip helper
  refmap.py     every reference site, pinned to the schema by a test
  diff.py       entity diff, order diff, script diff
  plan.py       items, selection, dependencies, decisions, op list
  execute.py    ordering, dry run, apply, stale-plan guard
  session.py    persistent merge sessions
```

Layering as in the repo: `core` raises exceptions with actionable messages; routes and tool handlers translate; adapters contain no business logic.

## 10. HTTP surface (sketch)

Under `/api/projects/{slug}/history/`.

- **Project resolution is by exact slug.** A slug that names no project is a 404. These routes can switch the live database and delete branches and drafts, so the fuzzy match `resolve_project` offers the agent's tools is not used here.
- **Error envelope:** `{"error": {code, message, …payload}}`, with the payload at the top level of `error` (as the trash routes do), built by one shared helper.
- **Decision keys** are `<item>#<code>` and contain `#`, `:` and sometimes spaces. The client percent-encodes the key in the path; the route takes it as a `path` parameter. A key with no `#D<n>` suffix, or one that is not a decision of the session's current plan, is a 422 that lists the valid keys (the check lives in `session.set_decision`, so the agent tools get it too).

- `GET /` → branches, snapshots with parents (the graph), head summaries ("N changes since Draft 3"), current branch.
- `POST /snapshots` (save, `label`, `note`) · `POST /branches` (from snapshot) · `POST /switch` · `PATCH /branches/{id}` (rename) · `DELETE /branches/{id}` · `DELETE /snapshots/{id}`.
- `GET /diff?a=…&b=…&view=entity|script`.
- `GET /read/{ref}/entities/{type}/{id}` · `GET /read/{ref}/script` (read-only views).
- `POST /merges` (start) · `GET /merges/{id}` · `PUT /merges/{id}/selection` · `PUT /merges/{id}/decisions/{key}` · `POST /merges/{id}/preview` (dry run) · `POST /merges/{id}/apply` · `DELETE /merges/{id}`.

`list_projects` is extended with `current_draft`, `branch_count`, `last_saved`, `changes_since_save` for the landing page (F19), computed on demand from `history.db`, not stored.

## 11. Agent tools

**Where they go (F16, F17).** There is no toolset grouping to join; the choice is between extending an existing module and adding new ones. Recommendation: **new modules**, not new `action`s on `story_draft` or `story_backup`.

- `story_draft` is the staged-proposal flow, and the name collision would confuse the agent and the maintainers; `story_backup` is a safety net with different semantics (labelled backups never pruned, restore replaces everything). Their descriptions would need to distinguish four concepts at once.
- Every tool schema is sent to the model each turn and the budget logic (F17) shows small-context models are a supported target; separate modules with short descriptions cost less than bloating two heavily used ones.
- Existing `story_retrieve` / `story_search` stay unchanged. Reading another draft is an action of the new history tool.

Modules (both added to `TOOL_MODULES`):

- `story_history` — `list` (branches, drafts, graph summary), `diff` (two refs, `view`), `read` (entity or script from any draft, read-only), `save`, `branch`.
- `story_merge` — `start`, `show` (selection, open decisions, dry-run verdict), `suggest` (set a decision's value with a rationale, recorded as `agent-suggested`), `preview`, and `apply`.

**Confirmation gate.** Suggestions never apply: they appear pre-filled in the decision, marked as from Hermes, and the user accepts, edits, or ignores them. Destructive and state-changing actions (`apply`, switch, delete branch/draft) follow the existing draft pattern: the agent stages, the app shows a card with Approve and Reject, the user's approval executes. A later AUTO mode skips only that approval. Delivery in two steps (§13): read, suggest and save first; the approval card for apply, switch and delete second. Until the card exists, those actions are UI-only.

**Guidance.** `adapters/hermes/assets/SOUL.md` and `skills/ww-scriptwriter/SKILL.md` gain the behaviour: help the user decide, search either draft before proposing, never claim a merge happened unless the tool confirmed it. `chat/context.py` gains a merge attachment kind (`merge_decision`, with the session and decision key) so "Ask Hermes" on a decision sends exactly that decision with both versions, the base, and the entity's context.

## 12. UI (outline; mock-up after approval)

- **Landing page**: a simple project list, each row showing the current draft and a "changes since" hint; expanding a row shows its branches; expanding further shows the graph.
- **Graph**: lanes with nodes (drafts) and lines (parents), solid for parents, dashed for "picked from", a dashed tip node per branch labelled "in progress". Drawn without a library.
- **Workspace**: pick two drafts → diff in an entity view and a script view; select; the decisions appear as a form; the plan and its dry-run verdict are always visible; the chat panel docks on the right, as in the current project view, scoped to the project and aware of the open decision.
- **Principle**: not overwhelming, expandable, intuitive. The whole feature works with no agent.

## 13. Tasks and commit order

Each is its own commit (or small group), each with tests; the existing suite stays green (one known failing test is not our concern).

- **T0** Branch off `dev`. `ruff` config; apply formatting in its own commit.
- **T1** Restore guard (§8): `restore_check` + `restore` + tests.
- **T2** Extract `load_database_in_place` from `restore_backup`; make `apply_op` public; no behaviour change.
- **T3** `history.db` and `store.py`: branches/snapshots/parents, fingerprint, save/branch/switch/rename/delete, adoption of existing projects.
- **T4** `ProjectView` and the logical-entity materializer with the round-trip test (§5.1). Gate: if the round trip cannot be made exact, stop and revisit §5.
- **T5** `refmap` and its schema-pinning test.
- **T6** Diff: entity, order, script.
- **T7** Planner: three-way, dependencies, decisions D1–D8.
- **T8** Executor: ordering, dry run, apply, stale-plan guard, parent recording.
- **T9** Persistent merge sessions.
- **T10** HTTP routes and the `list_projects` enrichment.
- **T11** Agent tools: read, suggest, save; skills and SOUL; merge attachment in `chat/context.py`.
- **T12** Agent approval card for apply/switch/delete.
- **T13** UI, after the mock-up is approved.

Unrelated cleanup noticed in a file we edit: `app/mcp_server.py` writes `/tmp/draft_debug.txt` on every draft call. It should be removed in its own commit when T11 touches `TOOL_MODULES`.

## 14. Risks and decisions for review

**A. Partial merges and parentage (§7.9).** Cherry-pick records no parent; only an explicit "complete merge" does. Confirm this default.
**B. Restore behaviour for the agent (§8).** `story_admin` restore would refuse a restore that creates a second singular role or a duplicate order, naming the fix, instead of silently writing it. Confirm.
**C. Reading drafts uses a scratch copy (§4.3).** Cheap for text data, but it is a copy per open view; revises the earlier idea of a "write-blocked connection" because every read function takes a project path (F10).
**D. Executor order (§7.7).** `sorted_ops` cannot be reused for merges; the drafts flow is untouched.
**E. Ordering hazards (F13).** `reorder` is only safe with the complete live sibling list. The planner asserts this. If ordering problems you already see come from the same cause, they are outside this spec but worth a separate fix.
**F. Criss-cross merges (§7.1).** Most-recent-ancestor with an "imprecise base" flag, not a recursive merge. Acceptable unless real use shows otherwise.
**G. Dependencies.** None added in v1 (stdlib `difflib`). `merge3` for conflicting section text only on your approval.
**H. Names.** Duplicate display names are allowed (F14); keep-both warns but does not block.
**I. Locking (§4.5).** To verify whether anything outside the app process writes `story.db`.
**J. Agent apply (§11).** Until T12, apply, switch and delete are UI-only.

## 15. Tests

- Round trip: materialize → create → materialize (T4), over a fixture with every entity type.
- `refmap` pinned to `ENTITY_SCHEMAS`, `REFERENCE_*` and relation kinds.
- Snapshot save/branch/switch/delete: immutability, fingerprint guard, re-parenting on delete, reachability on branch delete, schema-version refusal, `.partial` crash safety.
- Diff: field, list-element, section, order, script; trash ignored.
- Merge table (§7.3) per row; D1–D8 each with the accepted and refused paths; Replace with beats; Theirs-swap ordering; restore guard; stale-plan refusal; dry run maps failures to decisions.
- Cherry-pick vs complete merge parentage, and a later merge's base.
- Agent tools: schema size within the §F17 budget; `suggest` never applies; approval gate.

## Appendix — code practice (applies to every task)

### Comment hygiene
When editing a file, delete comments that only record history — "was X, now Y", "used to", "this used to be", phase and issue references ("B12", "D1a"), and "restored/rewritten after <incident>". State only what the code does now. Keep a comment only when it explains a non-obvious *why* (a constraint, an invariant, a trap). If a comment describes a change, it is a line in the git log, not a comment.

### Engineering practices
- **Layers and boundaries.** Keep the layering rule above. Adapters translate; they do not contain business logic.
- **Errors.** `core` raises exceptions with actionable messages ("Errors raise; previews return" is the existing convention). Boundaries (HTTP, MCP) translate exceptions into responses. One consistent JSON error shape for the HTTP API.
- **No dead code.** Delete rather than comment out. When something is retained deliberately for a later phase, say so in the phase file or a short comment.
- **Dependencies.** Add only what a task needs. Approved so far: `fastapi`, `uvicorn`; the official `mcp` SDK. Ask before adding anything else.
- **Config.** One module resolves configuration (precedence: CLI flag, then environment variable, then config file, then default). No scattered `os.environ` reads.
- **Logging.** Standard `logging`, no prints outside the CLI's user-facing output.
- **Typing and size.** Type hints on new code. Prefer small, single-purpose functions and modules; split files that grow unwieldy.
- **Tests.** `pytest`. Every task that adds behavior adds tests. The existing suite must stay green; adapt tests to refactors, do not delete them to make things pass.
- **Formatting.** Add `ruff` config (lint + format). Apply formatting in its own commit so diffs stay readable.
- **Git.** Work on a branch off `dev`. Small commits, one concern each, imperative messages. Commit after each task or logical group.
