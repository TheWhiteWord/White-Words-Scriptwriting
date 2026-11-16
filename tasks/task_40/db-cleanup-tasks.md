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
  After patch 01: 1336 passed. After patch 02: **1353 passed**, same 1 failure.
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

- [x] **A2. Transaction helper; stop running multi-statement writes in
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

- [ ] **B1. Schema versioning with `PRAGMA user_version`.** Replace
  `ensure_soft_delete_columns`, `ensure_draft_status_column` (in `get_db`, run
  on every open) and the `ALTER TABLE` loop in `chat/store.py` with an ordered
  list of migration functions, run once when `user_version` is behind.
  Existing legacy DBs (no version, partially migrated) must land on the current
  version. Keep `tests/test_legacy_db_migration.py` passing and extend it.
  This is the place later tasks add their schema changes.

- [ ] **B2. Backup helper cleanup.** One place for naming and destination.
  Use a microsecond timestamp (`%Y%m%d_%H%M%S_%f`) and drop both
  collision-counter loops. Give `backup_database` an optional destination so
  `_backup_outside` no longer backs up then moves. Optionally move snapshots to
  `.story/backups/`. Keep WAL-safe `Connection.backup()`.

### Phase C — Features a writing app is expected to have

- [ ] **C1. Trash: list deleted entities.** Restore needs an id, but nothing
  lists deleted entities. Add `story_admin(action="list_deleted")` returning
  id, type, name, `deleted_at`. (A UI trash view is a later, separate task.)

- [ ] **C2. Delete a single item forever.** Purge is currently all-or-nothing
  by age. Add a per-entity hard delete that only works on already-soft-deleted
  rows. Reuse the purge internals.

- [ ] **C3. Scene revision history.** Table `revisions(id, entity_id, heading,
  body, created_at)`; one choke-point where section bodies are written snapshots
  the *previous* body; keep last N per (entity, heading) (default 20); tool/API
  to list and restore a revision. Schema via a B1 migration.
  ⚖ Decide N, and whether to snapshot on every write or only when the body
  actually changed (recommended: only when changed).

- [ ] **C4. Backups: list, restore, retention.** `story_backup` actions to list
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
| — | — | none yet |

## 5. Patch log

| Patch file | Task | Base | Applied by user? | Notes |
|---|---|---|---|---|
| `01-A1-live-update-stream.patch` | A1 | dev @ 4e15cc2 | yes | +7 tests (1336 pass, same 1 baseline failure). Touches `app/routes/projects.py`, adds `tests/test_db_change_watcher.py` |
| `02-A2-transaction-helper.patch` | A2 | dev @ d6756d9 | pending | +17 tests (1353 pass, same 1 baseline failure). core/db.py, core/writes.py, tools/story_admin.py, tools/story_import.py, docstring in core/drafts.py; two new test files. Source net ≈ +94/−64 ignoring re-indentation |

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

## 7. Things that are fine, leave alone

WAL mode and `busy_timeout`; `Connection.backup()` for snapshots; FTS5
external-content table with its three triggers; fractional `order_key`;
short-lived connections; snapshots before import / purge / project delete; the
separate `chat.db` (chat is not story data); the existing test coverage.
- 2026-11-16 — Session 1 (cont.): A1 applied by user. A2 done → patch 02
  (base dev @ d6756d9). Next: B1 (`PRAGMA user_version` migrations).
  More practical notes: (e) to prove a new test can fail, run it against an
  unmodified checkout: `git worktree add /tmp/base HEAD`, copy the test in, run
  with `PYTHONPATH=/tmp/base/src`; (f) a SQLite trigger that `RAISE(ABORT)` is a
  neat way to make the last step of a multi-step write fail in a test; (g) use
  `git diff -w` to review a re-indentation refactor.
