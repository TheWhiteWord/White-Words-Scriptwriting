# DB management and versioning — state of the code

Audit of the dev branch (`dev` @ `10de943`), covering the database layer, backups,
soft delete / restore / purge, project lifecycle, import/export, drafts, and the
concurrency "version" mechanisms. Scope is the `story_architect` plugin source
under `src/story_architect/`. Everything below is descriptive: what exists, where,
and what it does. No evaluation, no proposals.

---

## 1. The stores

### 1.1 Per project — `<root>/projects/<slug>/`

| Path | What it is | Where defined |
|---|---|---|
| `.story/story.db` | Main database. Source of truth. | `core/db.py:121` |
| `.story/story_<YYYYMMDD_HHMMSS>[_n].db` | Backup snapshots of `story.db` | `core/db.py:155-160` |
| `.story/chat.db` | Conversations + messages (separate SQLite file) | `chat/store.py:42-43` |
| `.story/exported.json` | Manifest of files the last `story_export` wrote | `tools/story_export.py:107` |
| `.story/memory.md` | Project memory file, read by `story_import` | `tools/story_import.py:156-162` |
| `project.md`, `values.md`, `characters/`, `locations/`, `worlds/`, `plots/`, `scenes/`, `scene_beats/`, `sequences/`, `acts/`, `relationships/` | Markdown export / import surface | `tools/story_export.py:53-69`, `tools/story_import.py:71-73` |

`<root>` is `story_architect.root_path`, default `~/story-architect`
(`core/config.py:11,19-28`).

### 1.2 Global

| Path | What it is | Where defined |
|---|---|---|
| `<root>/backups/<project>_<stamp>[_n].db` | Snapshots taken by `delete_project`, deliberately outside the folder it deletes | `tools/story_admin.py:211-219` |
| `~/.config/story-architect/state.json` | UI settings, not story data | `app/state_store.py:7-9` |

### 1.3 Tables in `story.db`

Defined in `SCHEMA_SQL`, `core/db.py:19-75`:

- `entities` — `id, type, name, one_sentence, order_key, status, parent_id,
  location_id, is_deleted, deleted_at, extra` (JSON)
- `relations` — `(from_id, to_id, kind, note, "order")`, PK `(from_id, to_id, kind)`
- `sections` — `(entity_id, heading, body)`, PK `(entity_id, heading)`
- `sections_fts` — FTS5 external-content index over `sections.body`, kept in sync
  by three triggers (`sections_ai`, `sections_ad`, `sections_au`)
- `drafts` — `id, ops, prev_ops, summary, created_at, status`

`chat.db` tables: `conversations`, `messages` (`chat/store.py:11-35`). The
`messages` row carries `tools`, `drafts`, `attachments` as JSON text columns.

---

## 2. Connection, schema, migration

**`get_db(project_path)`** — `core/db.py:109-135`. Every caller reaches the DB
through it. It:

- creates `.story/` if missing, opens `story.db`;
- sets `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=3000`,
  `PRAGMA foreign_keys=ON`;
- opens with `isolation_level=None` (autocommit); transactions are explicit
  `BEGIN`/`COMMIT`/`ROLLBACK` at call sites;
- if an `entities` table exists, runs `ensure_soft_delete_columns`
  (`db.py:95-106`) — adds `is_deleted` / `deleted_at` by `ALTER TABLE` when absent;
- if a `drafts` table exists, runs `ensure_draft_status_column`
  (`db.py:77-92`) — adds `status` when absent.

**`create_schema(conn)`** — `db.py:174-183`. Runs `SCHEMA_SQL`
(`CREATE TABLE IF NOT EXISTS`). Called by `create_project` and by
`story_import` when `has_schema` is false.

**`has_schema(conn)`** — `db.py:186-192`. True when `entities`, `relations`,
`sections`, `sections_fts` all exist.

**Migration model.** There is no schema-version number and no ordered migration
list. Compatibility is two idempotent `ensure_*` repairs executed on every
connection open, guarded on the table existing. `chat.db` has its own inline
`ALTER TABLE` loop for `messages` columns (`chat/store.py:52-62`).

---

## 3. Project lifecycle

| Action | Entry point | Behaviour |
|---|---|---|
| create | `story_admin(action="create_project")` → `writes.create_project` (`core/writes.py:26-83`) | `get_db` → `create_schema` → `BEGIN` → refuses if a `project` row already exists → inserts the project row + its standard sections → `COMMIT` |
| list | `story_admin(action="list_projects")` (`story_admin.py:122-146`) | Directory listing only; reports `has_database` per folder. Opens no DB |
| delete | `story_admin(action="delete_project")` (`story_admin.py:149-196`) | Requires `delete_confirm` containing the literal `DELETE <slug>`; requires `.story/story.db` to exist; takes a backup into `<root>/backups/`; `shutil.rmtree` the project folder |

The app also exposes `GET /api/projects` and
`GET /api/projects/{slug}/dashboard` (`app/routes/projects.py:10-24`), both
backed by `app/services.py:15-37`.

---

## 4. Backups

### 4.1 One implementation

`backup_database(project_path)` — `core/db.py:138-171`:

- destination `<project>/.story/story_<YYYYMMDD_HHMMSS>.db`, with `_1`, `_2`, …
  appended on collision (one-second stamp granularity);
- copies with `sqlite3.Connection.backup()`, not a file copy, so committed writes
  still sitting in `story.db-wal` are included;
- returns the absolute path as a string.

### 4.2 Callers

| Caller | When | Destination |
|---|---|---|
| `story_backup` tool (`tools/story_backup.py:19-42`) | Explicit agent call | project `.story/` |
| `story_import._backup` (`tools/story_import.py:27-34`) | (a) refusal path when DB-only entities would be destroyed — `story_import.py:142`; (b) immediately before the wipe, whenever `project.md` exists — `story_import.py:188` | project `.story/` |
| `story_admin._purge_deleted` (`story_admin.py:270`) | Before purge | project `.story/` |
| `story_admin._backup_outside` (`story_admin.py:199-220`) | Before `delete_project` | `<root>/backups/`, and the snapshot is moved there |

### 4.3 Properties

- Backups are full copies of `story.db`, including soft-deleted rows, `drafts`
  rows, and the FTS index.
- No retention, pruning, listing, or deletion mechanism exists for backups.
- The `story_backup` tool description states a backup "can be copied but NOT
  restored by any tool yet" (`story_backup.py:9-10`).
- Recovery is by hand: copy the snapshot back over `<project>/.story/story.db`
  (instruction returned by `delete_project`, `story_admin.py:194-195`).

---

## 5. Soft delete

### 5.1 Storage

Deleted entities stay in the same `story.db`. `entities.is_deleted` (0/1) and
`entities.deleted_at` (ISO timestamp) are the only markers (`db.py:29-30`).

### 5.2 Delete path

`writes.delete_entity(project_path, entity_type, slug, summary, confirm)` —
`core/writes.py:803-937`.

- **Without `confirm`**: returns a preview and writes nothing — `would_delete`,
  `cascade_children`, `affected_relationships`, `sections_deleted`,
  `relations_deleted`, and an `action_required` line.
- **Structural children**: a row with a child of type `scene` or `sequence`
  (`parent_id` = target) refuses the delete outright, with or without `confirm`
  (`writes.py:869-880`).
- **With `confirm`**, all in one pass:
  1. every row whose `parent_id` is the target is flagged
     `is_deleted=1, deleted_at=<stamp>` (`writes.py:887-890`);
  2. the target row is flagged the same way (`writes.py:891-893`);
  3. relations **pointing at** a deleted id (live `from_id`, dead `to_id`) are
     `DELETE`d (`writes.py:901-905`);
  4. `plot_*` relations **owned by** a deleted plot are `DELETE`d
     (`writes.py:917-920`);
  5. `_purge_references` (`writes.py:1128-1202`) walks every surviving entity and
     strips the dead ids out of `extra` (`characters`, `scenes`, `perspectives`)
     and empties the `parent_id` / `location_id` columns.
- The response reports `reversible: True` and `how_to_undo` naming `restore`
  (`writes.py:928-937`).

`sections` rows are never removed by the delete. Relations owned by the deleted
entity (`from_id` = dead) are not removed by the delete.

### 5.3 Readers

Every reader filters `is_deleted=0`. The filter appears in:

- `core/db.py` — `get_project_summary` (`:474`), relation loads (`:482-483`,
  `:866-867`, `:1069-1070`), `get_dashboard_data` (`:1054`), structural stats
  (`:1492`, `:1521-1526`, `:1531`, `:1536`), `_screenplay_rows` (`:1667`),
  `get_scene_value_turns` (`:327`);
- `core/writes.py` (`:584`, `:589`, `:833`, `:1053`, `:1095`, `:1112`);
- `core/entity.py` (`:841`, `:849`, `:871`, `:1011`, `:1107`);
- `core/manual_entities.py`, `core/manual_structure.py`, `core/manual_edits.py`,
  `core/track.py`, `core/value_focus.py`;
- `tools/story_load.py`, `tools/story_retrieve.py`, `tools/story_export.py`.

FTS search adds a live-entity join so deleted prose is not returned
(`db.py:987-1004`). Relation reads exclude any relation with a deleted endpoint
on either side.

---

## 6. Restore

`story_admin(action="restore")` → `_restore_entity` — `story_admin.py:288-347`.

- Target is `{entity_type, id}` plus a free-text `summary`.
- The row is looked up **without** an `is_deleted` filter; a row that is not
  deleted is an error (`:316-320`), a missing row is an error (`:313-314`).
- Clears `is_deleted=0, deleted_at=NULL` on the target row and on every row
  whose `parent_id` is the target (`:321-337`).
- Returns `was_deleted_at` and `restored_cascade_children`.
- It does not re-create relation rows (they were deleted in the delete path), it
  does not restore scrubbed `extra` references, and it does not restore a plot's
  `plot_*` role rows. The plot-role exception is documented in the function
  docstring (`story_admin.py:294-298`).

---

## 7. Purge

`story_admin(action="purge")` → `_purge_deleted` — `story_admin.py:223-285`.

Two guards:

1. `purge_confirm` must contain the literal `DELETE <project slug>`
   (`:239-246`).
2. An age floor: only rows with `is_deleted=1 AND deleted_at IS NOT NULL AND
   deleted_at <= cutoff`, where `cutoff = now - older_than_days` and
   `older_than_days` defaults to 30 (`:248-256`).

Sequence: select eligible ids → `backup_database` → `DELETE FROM sections`,
`DELETE FROM relations` (both directions), `DELETE FROM entities` for those ids
(`:268-274`). Returns the purged list and the backup path. If nothing is old
enough, it reports the count of younger deleted rows and changes nothing.

---

## 8. Import and export

### 8.1 `story_import` — markdown → DB (destructive)

`tools/story_import.py`.

- `dry_run=true` → `_diff` (`:37-89`) reports DB entities that have no Markdown
  note behind them; nothing is written.
- Without `confirm`, if `_diff` finds DB-only entities → refuses, takes a backup,
  returns the at-risk list (`:139-152`).
- Otherwise: `backup_database` (`:188`) → `BEGIN` → `_clear_all`
  (`DELETE FROM relations`, `sections`, `entities` — `:219-223`) → `_import_all`
  (`:226-242`) → `COMMIT`.
- Memory: `.story/memory.md` is parsed if present; if absent, the existing DB
  memory is carried over (`:193-204`).
- Frontmatter is validated by the same rules as the write paths
  (`_extra_for`, `:567-637`).

### 8.2 `story_export` — DB → markdown

`tools/story_export.py`.

- Writes only `is_deleted=0` rows (`:143-146`).
- `_sweep_stale` (`:96-126`) deletes files listed in `.story/exported.json` that
  this pass did not write, then rewrites the manifest. A note the database has
  never seen is never touched.

---

## 9. Drafts (staging as a change-level record)

`core/drafts.py`, tool `tools/story_draft.py`. A draft is one row in the
project's `drafts` table.

- **stage** (`drafts.py:197-260`): validates the op list, then
  `INSERT … ON CONFLICT(id) DO UPDATE`. Re-staging the same `draft_id` replaces
  the op list; the replaced list is kept in `prev_ops` and a structural diff is
  returned as `changes`. Status is set to `open`.
- **commit** (`drafts.py:339-427`): reads `ops` and `status`. If `status` is
  already `committed`, it replays the same report instead of re-writing. Otherwise
  it dispatches ops in `create → edit → delete → reorder` order, one write
  function per op, each op atomic. On failure the row is kept and the response
  names what landed. On success the row is marked `status='committed'`.
- **discard** (`drafts.py:313-324`): `DELETE FROM drafts`.
- **list** (`drafts.py:283-310`): only `status='open'` rows.
- **dry_run** (`drafts.py:430-472`): copies the project DB into a temp dir with
  `src.backup(dest)` and runs `commit` there; the copy is removed on every path.
- Committed drafts are not removed by any automatic process.

---

## 10. Concurrency "version" mechanisms

These are per-editor change tokens, not database schema versions.

| Mechanism | Token | Where | Refusal |
|---|---|---|---|
| Entity form | `_version(values, sections)` — sha256 of the values+sections JSON, first 16 chars | `core/manual_entities.py:635-637`, returned by `load_entity` (`:701`) | `edit_form_entity` requires `base_version` to match (`:1217-1218`); route maps `EntityConflict` to HTTP 409 with `current_version` (`app/routes/entities.py:41`) |
| Structure (acts/sequences/scenes tree) | `_version(tree)` — sha256 of the flattened id tree, first 16 chars | `core/manual_structure.py:79-82`, `load_tree` (`:91`) | `plan`/`apply` require `base_version` (`:180-181`); `StructureConflict` → 409 (`routes/entities.py:95`) |
| Script editor (scene Content) | `content_hash(state)` — sha256 over content + heading fields + characters, first 16 chars | `core/manual_edits.py:103-114` | `ScriptConflict` |
| Live update signal | `PRAGMA data_version` polled every second; an `event: update` SSE frame is emitted when it changes | `app/routes/projects.py:26-52` | none |
| Chat draft cards | `drafts` JSON array on the message row, statuses `open` / `committed` / `discarded` | `chat/store.py:29`, `app/routes/drafts.py` | none |

---

## 11. Tool and UI surface

### 11.1 Agent tools

Registered in `app/mcp_server.py:21-33` and `tools/__init__.py`:
`load, retrieve, search, admin, resolve, import, export, backup, describe, draft,
memory, dashboard_link`.

Tool descriptions that mention the DB lifecycle:

- `story_backup` — "a backup can be copied but NOT restored by any tool yet".
- `story_import` — "DESTRUCTIVE … deletes every row and re-imports".
- `story_export` — "does not create a restorable database copy — use story_backup".
- `story_admin` — create/list/delete project, restore, purge; "Deleting an entity
  is a soft delete and is exactly reversible via restore; purge is the only
  irreversible one".

### 11.2 App HTTP routes

`app/routes/`: `projects.py` (list, dashboard, events), `entities.py` (form
spec, load, check, create, edit, delete-preview, delete, structure
load/plan/apply), `scripts.py`, `drafts.py` (approve/reject a draft card),
`chat.py`.

### 11.3 UI

- Entity form: delete shows a preview and the note "It can be restored later by
  asking the agent." (`web/js/forms/entity-form.js:433-442`).
- Chat: a soft-deleted tool call renders "Soft delete — it can be restored
  later." (`web/js/chat-render.js:162`).
- No UI control exists for backup, restore, purge, import, or export. The
  dashboard is a static surface; `tasks/task_21/open_questions_undo_and_trash.md`
  records that UI buttons for import/export/purge were a plan, not started.

---

## 12. What a user can do by hand

- Copy any `story_*.db` back over `<project>/.story/story.db`.
- Delete a project folder directly on disk.
- Run `story_export` to get a Markdown copy (not a restorable DB).
- Ask the agent to call `backup`, `admin(action="restore")`,
  `admin(action="purge")`, `import`, `export`.

---

## 13. Test coverage of these areas

| File | Pins |
|---|---|
| `tests/test_backup_integrity.py` | WAL-safe backup, completeness, no filename collisions, live DB untouched, backup stays in `.story/` |
| `tests/test_soft_delete.py` | Flag-not-erase, `deleted_at`, prose/owned relations survive, invisibility across retrieve/load/search/dashboard/arc/unfilled, restore round-trip, legacy column migration |
| `tests/test_purge.py` | Both guards, age floor, what purge removes (cascade children, prose), backup taken and contains the rows, export sweep + import does not resurrect, soft delete survives export→import |
| `tests/test_legacy_db_migration.py` | `get_db` repairs a legacy DB, idempotent repairs, `drafts.status` added |
| `tests/test_delete_cascade.py` | Cascade and reference purge |
| `tests/test_import_safety.py` | Import refusal / diff |
| `tests/test_export_sweep.py` | Stale-note sweep and manifest |
| `tests/test_drafts.py`, `test_draft_dry_run.py`, `test_draft_preview.py`, `test_story_draft_tool.py` | Staging, commit, discard, list, dry run |
| `tests/test_connection_lifecycle.py` | Connection handling |
| `tests/test_manual_entities.py`, `test_manual_structure.py`, `test_manual_edits.py` | Form/structure/script concurrency tokens |

---

## 14. Capability inventory (facts only)

Present:

- Timestamped, WAL-safe, collision-free DB snapshots, on demand and before the
  three destructive operations (import, purge, delete-project).
- Soft delete with a timestamp, cascade, and reference scrubbing.
- Exact restore of the flagged rows and their `parent_id` children.
- Age-floored, consent-gated permanent purge.
- Full-project rebuild from Markdown, gated by a dry-run diff.
- Markdown export with a stale-file sweep.
- Draft staging with a kept, re-playable commit record.
- Per-editor change tokens (entity, structure, script) and a live DB change
  signal.

Not present:

- No tool lists the soft-deleted entities, the backups, or the drafts beyond
  `status='open'`.
- No tool restores a backup, and no tool deletes a backup.
- No tool hard-deletes a single soft-deleted entity; purge is the only path and
  it is all-or-nothing by age.
- No retention or pruning of backups or of committed draft rows.
- No schema-version counter or ordered migration chain; repairs are two
  idempotent `ensure_*` calls in `get_db`.
- No undo of an edit (field-level history or change journal); `dry_run` only
  previews a staged batch.
- No UI control for backup / restore / purge / import / export.
