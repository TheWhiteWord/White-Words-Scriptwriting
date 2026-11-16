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

- `python -m pytest tests -q` → **1329 passed, 1 failed**.
- Known pre-existing failure, unrelated to this work:
  `tests/test_no_hermes_imports.py` (finds the word "hermes" in
  `src/story_architect/app/config.py`). Leave it alone unless asked.

## 3. Task list

Status key: `[ ]` todo · `[~]` in progress · `[x]` done (patch produced) ·
`[A]` done and applied by user to dev.

### Phase A — Bugs (do first)

- [ ] **A1. Live-update stream never fires.**
  `app/routes/projects.py` `/events` opens a *new* SQLite connection every
  second and reads `PRAGMA data_version`. That value only changes for commits
  made by *other* connections while *this* one stays open. Verified with a
  script: fresh connections return the same number after several writes.
  Fix: open one connection before the loop and poll on it. Also check the
  frontend for a fallback that hides the problem.
  Test: write from a second connection, assert an `update` event is emitted.

- [ ] **A2. Transaction helper; stop running multi-statement writes in
  autocommit.** `delete_entity`, `create_entity` (and the `manual_*` write
  paths, check each) have no `BEGIN`. A crash or lock error mid-way leaves a
  half-applied change. Add `transaction(conn)` context manager in `core/db.py`
  (BEGIN … COMMIT, ROLLBACK on exception), use it everywhere writes span more
  than one statement. Replace the existing manual BEGIN/COMMIT/ROLLBACK blocks
  with it (writes.py, story_import.py).
  Test: inject a failure mid-delete / mid-create, assert nothing persisted.

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
| — | — | — | — | none yet |

## 6. Session notes

- 2026-11-16 — Session 1: audit read, code reviewed (db.py, story_admin,
  delete_entity, drafts.commit, story_import, version tokens, SSE route, chat
  store), baseline recorded, this file created. No patches produced yet.
  Suggested start: A1, then A2.

## 7. Things that are fine, leave alone

WAL mode and `busy_timeout`; `Connection.backup()` for snapshots; FTS5
external-content table with its three triggers; fractional `order_key`;
short-lived connections; snapshots before import / purge / project delete; the
separate `chat.db` (chat is not story data); the existing test coverage.
