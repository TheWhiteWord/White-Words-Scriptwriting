# DB management & versioning cleanup — task file

> **Purpose.** Working document for cleaning up the DB / backup / soft-delete /
> versioning layers of `hermes-story-architect`. It is the hand-off between
> sessions: a new Claude instance should be able to read this file, clone the
> repo, and continue. Keep it updated at the end of every task.
>
> **Source material.** `db-management-and-versioning-audit.md` (descriptive
> audit of the code at `dev` @ `10de943`) and the review that followed it
> (summarised in the task list below).

---

## 0. How to resume (instructions for the Claude instance reading this)

1. Read this whole file, then the audit if it is provided.
2. Clone the repo:
   `git clone --depth 1 --branch dev https://github.com/TheWhiteWord/hermes-story-architect.git`
   then `pip install -e . --break-system-packages --ignore-installed PyJWT`
   (system PyJWT blocks a plain install) and `pip install pytest --break-system-packages`.
3. Run `python -m pytest tests -q -p no:cacheprovider` (~35 s). Compare with the
   **baseline** in §2. Do not run bare `pytest` at the repo root: `tasks/` holds
   a test that fails collection.
4. Check §3 for which patches the user has already applied. If the user's `dev`
   is ahead of `10de943`, ask for the current commit hash or have them apply the
   patches listed as "applied" before you start, so your work is stacked on the
   same base.
5. Work on the next unchecked task, one at a time (see §1).
6. When done: update this file (status, patch name, notes, decisions) and give
   the user both the patch and the updated file.

## 1. Working protocol

- **One task = one patch**, produced as a git commit and exported with
  `git format-patch -1 --stdout > NN-short-name.patch`. The user applies it with
  `git am NN-short-name.patch` (keeps the commit message) or `git apply`.
- Patches are **numbered and stacked**: patch N assumes patches < N are applied.
- Before handing over a patch: the full test suite must pass apart from the
  known baseline failure, new behaviour must have new tests, and the patch must
  apply cleanly to a fresh clone of the base.
- **Decision points** (marked ⚖) must be answered by the user before work
  starts. Record the answer in §4.
- Prefer deleting code to adding it. The aim is conformity to standard
  patterns, not new features beyond the listed QoL ones. No new dependencies
  unless a task says so.
- The user has little DB experience: explain each change in plain language, say
  what the standard pattern is called, and say what the risk is.
- Do not edit the repo's `tasks/` folder for this work; this file lives wherever
  the user keeps it.

## 2. Baseline (dev @ 10de943)

- `python -m pytest tests -q` → **1329 passed, 1 failed** at `10de943`.
  After patch 01: 1336 passed. After patch 02: 1353 passed. After patch 03: 1366. After 04: 1372. After 05: 1383. After 06: **1399 passed**, same 1 failure.
- Known pre-existing failure, unrelated to this work:
  `tests/test_no_hermes_imports.py` (finds the word "hermes" in
  `src/story_architect/app/config.py`). Leave it alone unless asked.

## 3. Task list

Status key: `[ ]` todo · `[~]` in progress · `[x]` done (patch produced) ·
`[A]` done and applied by user to dev.

### Phase A — Bugs (do first)

- [A] **A1. Live-update stream never fires.** *(patch 01 — applied)*
  `app/routes/projects.py` `/events` opens a *new* SQLite connection every
  second and reads `PRAGMA data_version`. That value only changes for commits
  made by *other* connections while *this* one stays open. Verified with a
  script: fresh connections return the same number after several writes.
  Fix: open one connection before the loop and poll on it. Also check the
  frontend for a fallback that hides the problem.
  Test: write from a second connection, assert an `update` event is emitted.
  *Result:* new `DbChangeWatcher` + `event_stream()` in `app/routes/projects.py`
  (one persistent read-only connection; reopens if the db file is replaced, so
  it will survive the backup-restore in C4; never creates an empty db). Verified
  end to end against a real uvicorn server: original code sends the client
  nothing after an external write, patched code sends the `update` event.
  The frontend (`web/js/core.js` `watchUpdates`) had no fallback, so the
  "Project updated" banner never appeared before this fix. Frontend unchanged.

- [A] **A2. Transaction helper; stop running multi-statement writes in
  autocommit.** *(patch 02 — done 2026-11-16)*
  **Correction to the original review:** it said `create_entity` and the
  `manual_*` paths had no transaction. That was wrong — `create_project`,
  `create_entity`, `edit_entity`, `reorder` and the import handler already had
  a hand-written `BEGIN … COMMIT / except → swallowed ROLLBACK`. The real
  findings were: that block was copy-pasted five times, and `delete_entity`,
  `_purge_deleted` and `_restore_entity` (story_admin) had **no** transaction.
  (The `manual_*` modules call the `core/writes.py` functions, so they were
  already covered.)
  *Result:* `core.db.transaction(conn)` — `BEGIN IMMEDIATE`, commit on exit
  (also on early `return`), rollback on any exception without masking it,
  `SAVEPOINT` when nested (needed by E2). All five hand-written blocks now use
  it; delete / purge / restore are atomic. Also fixed: `story_import` crashed
  with `cannot rollback - no transaction is active` if anything failed before
  its `BEGIN` (e.g. the safety backup); it now returns the JSON error.
  *Why IMMEDIATE:* verified by experiment — with a plain `BEGIN`, a block that
  reads then writes fails instantly with `database is locked` if another writer
  commits in between (`busy_timeout` does not apply); with IMMEDIATE the second
  writer waits. The web UI and the agent's tools can write concurrently.
  *Tests:* `tests/test_transaction.py` (helper, nesting, locking, 4-thread
  read-modify-write) and `tests/test_write_atomicity.py` (a SQLite trigger makes
  the last step of delete / purge / restore / import fail; the database must be
  unchanged). Against the original code 4 of the 6 behaviour tests fail.
  Not changed on purpose: `chat/store.py` (Python's implicit transactions plus
  an explicit `commit()` — fine as is); `drafts.commit` (E2).

### Phase B — Foundations

- [A] **B1. Schema versioning with `PRAGMA user_version`.** *(patch 03 — done 2026-11-17)*
  Replaced `ensure_soft_delete_columns` / `ensure_draft_status_column` (4
  catalogue queries on every `get_db`) and `chat/store.py`'s per-open
  `executescript` + `table_info` + `ALTER` loop.
  *Result:* `core.db.SCHEMA_MIGRATIONS` (ordered, **append-only**; the number of
  entries is the schema version), `apply_migrations(conn, list, name=)`,
  `SchemaTooNewError`. The two old repairs are steps 1 and 2 and stay guarded
  (they also run on unstamped databases of unknown shape). `chat.store.MIGRATIONS`
  uses the same runner (step 1 = the five `messages` columns).
  Rules of the design: `get_db` reads one pragma and runs nothing on a current
  db; a file with no tables is left alone; `create_schema` stamps a *new* db
  current without running steps, so future steps never have to cope with a
  freshly built db; pending steps + version stamp are one transaction and the
  version is re-read under the write lock (two processes opening an old db
  upgrade it once); a db *newer* than the build is refused (⚖ see §4);
  `Connection.backup()` keeps `user_version`, so a restored old backup is
  upgraded on open (matters for C4).
  *How to add a schema change from now on:* (1) put the new shape in
  `SCHEMA_SQL`, (2) append one function to `SCHEMA_MIGRATIONS` that upgrades an
  existing db, using `conn.execute()` only (never `executescript` — it commits).
  Steps after #2 may assume the shape the earlier ones leave.
  *Verified:* tests (13 new) incl. mutation checks; and against databases built
  from the repo's own history (`SCHEMA_SQL` at `2e9cb29^` = before soft delete,
  `b5a1c24^` = drafts without `status`): data kept, columns added, stamped.
  Existing real databases are unstamped (version 0): they run both guarded steps
  once (no-ops) and get stamped on first open.
  *Test changes:* `test_legacy_db_migration.py` follows the renamed steps;
  `test_drafts.py::test_a_database_with_the_old_drafts_table_still_works` now
  builds an *unstamped* file. Reason: it used to put an old-shaped table into a
  file stamped current, which the old per-open repair happened to fix; a stamp
  is trusted by design, and that state cannot occur in real use.
  Measured: opening a connection went from ~227 µs to ~189 µs. Not the reason
  for the change.
  *Observed, not changed (candidates for E3):* (1) `app/services.py`,
  `tools/story_load.py`, `tools/story_resolve.py`, `core/value_focus.py` open
  story.db with a bare `sqlite3.connect`, bypassing `get_db` (no upgrade, no WAL
  or busy_timeout settings). Harmless while every database has been upgraded by
  some earlier `get_db`, but they would fail on an un-upgraded old file.
  (2) `chat.db` connections set no WAL / busy_timeout (default 5 s timeout
  applies). (3) `get_db` still runs `PRAGMA journal_mode=WAL` on every open
  (persistent setting; harmless).

- [x] **B2. Backup helper cleanup.** *(patch 04 — done 2026-11-17)*
  `backup_database(project, *, dest_dir=None, prefix="story")` is now the only
  backup function. The name is reserved with `tempfile.mkstemp` (no hand-written
  counter loop); the snapshot is written as `*.partial` and renamed to `.db`
  only when complete, and a failed one is deleted, so a half-written file can
  never look like a backup. `delete_project` calls it with
  `dest_dir=<root>/backups, prefix=<slug>`; `story_admin._backup_outside` (a
  second naming loop plus a move) is gone. `core/drafts.py` `new_draft_id`
  keeps its own counter loop on purpose (it guards a primary key, not a file).
  *Found:* the old check-then-create loop lost or duplicated backups in 9 of 40
  rounds with 8 simultaneous backups (0 of 40 now). Artificial load, but two
  at once (UI + agent) is plausible and the failure was silent.
  *Names:* `story_<date>_<time>_<id>.db` (still match `story_*.db`). Not moved
  to `.story/backups/` — it would break every existing glob for no real gain.
  Files are created `0600` (mkstemp), private to the user.
  **For C4:** a listing must match `story_*.db` and ignore `*.partial`.

### Phase C — Features a writing app is expected to have

- [x] **C1. Trash: list deleted entities.** *(patch 05 — done 2026-11-17)*
  `story_admin(action="list_deleted")`: every soft-deleted entity, newest
  first, with `type`, `id`, `name`, `deleted_at`, `purge_eligible` (would a
  purge with `older_than_days`, default 30, remove it) and `includes` (children
  deleted in the same operation: same parent, same `deleted_at` stamp — one
  entry per deletion, as a trash UI would show). Rows with no `deleted_at`
  (deleted by an earlier build) are listed and never eligible. `type`+`id`
  feed straight into restore/purge. A UI trash view is still a separate task.

- [x] **C2. Delete a single item forever.** *(patch 06 — done 2026-11-17)*
  `story_admin(action="purge", target={entity_type, id}, purge_confirm=…)`
  removes exactly that entity plus what was deleted with it (children with the
  same stamp), leaving the rest of the trash alone. Same guards as the sweep
  (confirm phrase, backup first, one transaction). Refused with nothing
  changed: entity not in the trash, unknown id, wrong `entity_type`.
  Works on rows with no `deleted_at`, which the sweep can never see. The shared
  `_hard_delete()` now also clears the `parent_id`/`location_id` of any
  remaining row that pointed at a purged entity (a trashed child deleted
  separately) — in the bulk sweep too.
  ⚖ **Decision made (see §4): the age floor does not apply to a named item.**
  **Contract change:** a `target` on `purge` used to be silently ignored (the
  schema said "for restore") and the call swept everything old enough; now it
  means "just this one". `tests/test_purge.py`'s helper sent a target on every
  call, so it now sends one for `restore` only.

- [ ] **C3. Scene revision history.** Table `revisions(id, entity_id, heading,
  body, created_at)`; one choke-point where section bodies are written snapshots
  the *previous* body; keep last N per (entity, heading) (default 20); tool/API
  to list and restore a revision. Schema via a B1 migration.
  ⚖ Decide N, and whether to snapshot on every write or only when the body
  actually changed (recommended: only when changed).

- [ ] **C4. Backups: list, restore, retention.** *(note from B2: list `story_*.db`, ignore `*.partial`; `user_version` travels with a backup, so a restored old one is upgraded on open.)* `story_backup` actions to list
  and restore. Restore must (1) snapshot the current DB first, (2) remove stale
  `story.db-wal` / `-shm` files before replacing `story.db`. Retention: keep the
  last N auto snapshots (⚖ N, suggested 20). Also prune committed `drafts` rows
  older than N days. Fix the manual-restore instruction returned by
  `delete_project` (copying over a live DB next to a stale WAL is unsafe).

- [ ] **C5. Project delete moves the folder to a trash folder** (`<root>/.trash/`
  or `send2trash`) instead of `rmtree` plus a `story.db`-only backup, which
  currently destroys `chat.db`, `memory.md` and hand-edited Markdown.
  ⚖ stdlib `shutil.move` into `<root>/.trash/` (recommended, no dependency) vs
  `send2trash` (OS trash).

### Phase D — Simplify soft delete and the confirmation gates

- [ ] **D1. Soft delete = flag only; filter on read.** ⚖ *Needs the user's
  go-ahead and a verification step first.* Claim to verify: relation reads
  already exclude relations with a deleted endpoint, so the relation `DELETE`s
  in `delete_entity` (inbound relations, `plot_*` rows) and the scrub in
  `_purge_references` are redundant for relations. Dead ids in `extra`
  (`characters`, `scenes`, `perspectives`) and `parent_id` / `location_id`
  would need read-side filtering. If it holds, `delete_entity` shrinks and
  restore becomes truly exact. Also make restore restore only the children that
  *this* delete flagged (same `deleted_at` stamp), not children deleted earlier.
  Update the "exactly as they were" wording in tool descriptions once true.
  Optional follow-up: collapse `is_deleted` + `deleted_at` into one nullable
  `deleted_at` (migration).
  *Confirmed while doing C1/C2 (2026-11-17):* (1) `delete_entity`'s child query
  (`SELECT id, type FROM entities WHERE parent_id=?`, core/writes.py) has no
  `is_deleted=0`, so deleting a parent **re-stamps children that were already in
  the trash**: their own deletion time is overwritten, a later restore of the
  parent brings them back, and the confirmation preview (`would_delete` /
  `cascade_children`) lists them as if this action would delete them. (2) The
  cascade is one level. A *live* grandchild of the deleted entity is not
  deleted, and the reference scrub then blanks its `parent_id` (seen with a
  synthetic grandchild only — check real hierarchies, e.g. nested locations,
  before treating it as a bug). (3) `list_deleted` and targeted purge group
  "deleted together" by (same parent, same `deleted_at`), which is exactly what
  D1's "restore only what this delete flagged" needs too — reuse that rule.


- [ ] **D2. Rethink the `DELETE <slug>` confirmation strings.** Today the
  refusal message *prints the required string*, so the agent can supply it
  itself; it is not a human gate. ⚖ Proposal: remove the two-step `confirm` from
  entity soft delete (reversible, so just delete and report how to undo);
  keep a real human step for project delete and purge/empty-trash, ideally as a
  UI confirmation. Decide how far to go before touching tool schemas.

### Phase E — Consistency / integrity

- [ ] **E1. One optimistic-concurrency mechanism.** Replace the three hash
  tokens (`manual_entities._version`, `manual_structure._version`,
  `manual_edits.content_hash`) with a `rev INTEGER` column bumped on every
  write and checked atomically: `UPDATE … WHERE id=? AND rev=?`, check
  `rowcount`. Structure tree needs a project-level rev. Keep HTTP 409 +
  `current_version` behaviour so the frontend does not change.

- [ ] **E2. Atomic draft commit.** Let the write functions accept an open
  connection (or use savepoints) so a whole draft commits or fails as one
  transaction. Then remove the resume machinery (`draft_kept`, re-stage
  remainder, `already_committed` replay) *only if* it is no longer reachable.
  Largest refactor in the list; do after A2 and E1.

- [ ] **E3. Minor hygiene** (can be split): indexes on `relations(to_id)`,
  `entities(parent_id)`, `entities(type, is_deleted)`; declare foreign keys with
  `ON DELETE CASCADE` on `sections` / `relations` (needs a table-rebuild
  migration; currently `PRAGMA foreign_keys=ON` has nothing to enforce); UTC
  timestamps everywhere (db/purge use naive local time, chat uses UTC); one
  source of truth for draft status (the `drafts` table vs the chat message JSON).

### Phase F — Design decision, not yet a task

- [ ] **F1. ⚖ `story_import` wipe-and-rebuild.** It deletes every row and
  rebuilds from Markdown, guarded by a diff and refusals. Alternative: import
  by id (update existing, create new, never wipe). Depends on whether Markdown
  is a real editing surface (Obsidian etc.) or just an export. Discuss with the
  user before planning.

## 4. Decisions log

| Date | Task | Decision |
|---|---|---|
| 2026-11-17 | B1 | Refuse (raise `SchemaTooNewError`) a db whose version is newer than the build, rather than open it. Risk: switching to an older branch after a newer one has upgraded a db will refuse to open it until the app is updated or a backup restored. Say if you would rather it only warn. |
| 2026-11-17 | C2 | Targeted purge (`purge` + `target`) **ignores the 30-day age floor**: naming one already-trashed item is not a sweep; it still needs `purge_confirm`, takes a backup, and refuses live entities. To keep the floor for named items too, add the check in `_select_one_deletion`. |

## 5. Patch log

| Patch file | Task | Base | Applied by user? | Notes |
|---|---|---|---|---|
| `01-A1-live-update-stream.patch` | A1 | dev @ 4e15cc2 | yes | +7 tests (1336 pass, same 1 baseline failure). Touches `app/routes/projects.py`, adds `tests/test_db_change_watcher.py` |
| `02-A2-transaction-helper.patch` | A2 | dev @ d6756d9 | yes | +17 tests (1353 pass, same 1 baseline failure). core/db.py, core/writes.py, tools/story_admin.py, tools/story_import.py, docstring in core/drafts.py; two new test files. Source net ≈ +94/−64 ignoring re-indentation |
| `03-B1-schema-migrations.patch` | B1 | dev @ 3ca8c3b | yes | +13 tests (1366 pass, same 1 baseline failure). core/db.py, chat/store.py; tests/test_schema_migrations.py new; test_legacy_db_migration.py and one test in test_drafts.py adjusted |
| `04-B2-backup-helper.patch` | B2 | dev @ 6ae613f | pending | +6 tests (1372). core/db.py, tools/story_admin.py, comment in core/drafts.py |
| `05-C1-list-deleted.patch` | C1 | stacked on 04 | pending | +11 tests (1383). tools/story_admin.py (new action `list_deleted`) |
| `06-C2-purge-one.patch` | C2 | stacked on 05 | pending | +16 tests (1399). tools/story_admin.py; tests/test_purge.py helper changed (sends `target` for restore only) |

## 6. Session notes

- 2026-11-16 — Session 1: audit read, code reviewed (db.py, story_admin,
  delete_entity, drafts.commit, story_import, version tokens, SSE route, chat
  store), baseline recorded, this file created. No patches produced yet.
  Suggested start: A1, then A2.
- 2026-11-16 — Session 1 (cont.): A1 done → patch 01. Base used: dev @ 4e15cc2
  (includes this task folder). Suite is now 1336 passed + 1 baseline failure.
  Next: A2 (transaction helper).
  Practical notes for the next instance: (a) background servers die when the
  tool call's shell ends — start the server, run the client and kill it all in
  one bash call; (b) never `pkill -f` a pattern that appears in your own
  command line; (c) `get_db()` takes the *project folder*, not the db path;
  (d) tests create SQLite connections per thread — a connection can't be used
  from another thread.

- 2026-11-16 — Session 1 (cont.): A1 applied by user. A2 done → patch 02
  (base dev @ d6756d9). Next: B1 (`PRAGMA user_version` migrations).
  More practical notes: (e) to prove a new test can fail, run it against an
  unmodified checkout: `git worktree add /tmp/base HEAD`, copy the test in, run
  with `PYTHONPATH=/tmp/base/src`; (f) a SQLite trigger that `RAISE(ABORT)` is a
  neat way to make the last step of a multi-step write fail in a test; (g) use
  `git diff -w` to review a re-indentation refactor.

- 2026-11-17 — Session 2: A2 applied. B1 done → patch 03 (base dev @ 3ca8c3b).
  Next: B2 (backup helper cleanup), then C1/C2 (trash list, delete forever).
  More practical notes: (h) `git fetch --unshallow origin dev` gives the full
  history, useful for rebuilding real old schemas (`git grep -l 'SCHEMA_SQL = """'
  <rev> -- '*.py'`); (i) when probing with plain `sqlite3.connect`, commit or use
  `isolation_level=None` — an uncommitted INSERT vanishes when the connection
  closes; (j) mutate the code on purpose to prove a test can fail (restore from a
  saved copy afterwards).
- 2026-11-17 — Session 2 (cont.): B1 applied. B2, C1, C2 done → patches 04, 05,
  06, stacked in that order (base dev @ 6ae613f). Next: A-phase and B-phase are
  finished; remaining order suggestion: C3 (scene revisions), C4 (backup
  list/restore/retention), C5 (project delete → trash folder), then D1/D2 (need
  your decisions), E-phase. Practical notes: (k) use the `fixture_path` fixture
  (tests/conftest.py) for tests that need an imported project; (l) when a
  mutation check says "passed", make sure the mutation text was actually found
  — a missed target silently tests the unmutated code; (m) a test whose setup
  relies on an existing quirk (here: re-stamped children) should set the state
  up in the database directly instead.

## 7. Things that are fine, leave alone

WAL mode and `busy_timeout`; `Connection.backup()` for snapshots; FTS5
external-content table with its three triggers; fractional `order_key`;
short-lived connections; snapshots before import / purge / project delete; the
separate `chat.db` (chat is not story data); the existing test coverage.
