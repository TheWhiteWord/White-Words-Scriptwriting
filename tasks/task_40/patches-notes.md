# PATCHES NOTES

## Phase A — Bugs 

### A1. Live-update stream never fires

**The bug.** SQLite tells you "someone else changed the database" through a counter, but that counter only moves on a connection that stays open. The old code opened a brand-new connection every second, so it never saw a change. I checked this against a real running server. After a write from another process, the original code sent the browser nothing, and the fixed code sent the update event. The frontend had no fallback, so the banner never showed.

**The fix.** One connection is now kept open for the life of the stream. It also notices if the database file gets swapped, for example when a backup is restored later in C4. And it never creates an empty database file just by watching one.

### A2. Transaction helper; stop running multi-statement writes in autocommit.

**One correction to my review.** I said `create_entity` and the `manual_*` modules had no transaction, and that was wrong. Five functions already wrapped their writes in a hand-written `BEGIN … COMMIT` with a swallowed `ROLLBACK`: `create_project`, `create_entity`, `edit_entity`, `reorder` and the import handler. The `manual_*` modules call those functions, so they were covered too. The real problems were different:

- **Copy-paste.** That block was copied five times.
- **Three unprotected operations.** `delete_entity`, purge and restore ran several writes with no transaction at all.

**What changed**
- **One helper.** `core.db.transaction(conn)` replaces all five hand-written blocks. It commits on exit, rolls back on any error without hiding the original error, and works when nested. Nesting isn't needed yet, but E2 will need it.
- **Delete, purge and restore are now all-or-nothing.** `delete_entity`'s check for child scenes now runs in the same transaction as its writes, so a scene can't be added in between.
- **`BEGIN IMMEDIATE` instead of a plain `BEGIN`.** I tested this directly. With a plain `BEGIN`, a read-then-write block fails instantly with "database is locked" if another writer commits in between, and your 3-second timeout doesn't help. With `IMMEDIATE` the second writer waits its turn. This can happen for real because the web UI and the agent can both write to a project.
- **A bug in import is fixed.** If anything failed before its `BEGIN`, such as the safety backup, the cleanup raised "cannot rollback — no transaction is active" and the tool crashed. It now returns the intended error message.

**Evidence.**
- **Atomicity tests.** I forced the last step of delete, purge, restore and import to fail. Against your original code, 4 of those 6 tests fail: delete, purge and restore left the database half-changed, and the import crash showed up. With the patch they pass.
- **Concurrency tests.** Two tests fail if the helper uses a plain `BEGIN`, so they will catch anyone reverting it.
- **Size.** The diff looks big because of re-indentation, but ignoring whitespace it is about +94/−64 lines of source. I reviewed it with `git diff -w`.

**Left alone on purpose.** The chat store already uses Python's built-in transactions correctly. The draft commit stays as it is until E2, and I fixed a stale comment there that said `create_entity` ran in autocommit.

## Phase B — Foundations

### B1. Schema versioning with `PRAGMA user_version`

**What was wrong.** Every time the app opened `story.db`, it re-checked the table layout with four catalogue queries and added missing columns. `chat.db` did the same with its own loop. Nothing recorded which upgrades a database had already had.

**What it does now.** This is the standard SQLite pattern:
- **A version number in the file.** Each database stores a version number, `PRAGMA user_version`. A list of upgrade steps, `SCHEMA_MIGRATIONS`, is the schema history, and opening a current database runs nothing.
- **Your existing databases.** They have no version number yet. On first open they run the two old repairs once (both are no-ops on your data) and get stamped.
- **Two programs opening an old file together.** It's upgraded once, not twice.
- **A failed step.** It undoes everything, including the version number.
- **Restored backups.** Backups keep their version, so a restored old backup is upgraded when opened. This matters for C4.
- **`chat.db`.** It uses the same runner.

**How I checked it.**
- **Real old databases.** I rebuilt databases from your repo's own history, from before soft delete and from before `drafts.status`, and opened them with the new code. Your data was kept, and the missing columns were added.
- **Mutation checks.** I broke two protections on purpose. One of my tests didn't catch the missing race protection, so I rewrote it, and it now does.
- **Speed.** Opening a connection went from about 227 µs to about 189 µs. It's a small saving and not the reason for the change.

**Two things to know**
- **A test changed.** `test_drafts.py::test_a_database_with_the_old_drafts_table_still_works` failed after the change. It put an old-shaped table into a file stamped "current", which the old repair-every-open code happened to fix. A stamped file is trusted by design, and that state can't occur in real use. I changed the test to build an unstamped legacy file, which is what the test was trying to prove.
- **A decision for you.** If a database has a *newer* version than the running app knows, the app now refuses to open it with a clear message instead of carrying on. The risk is that if you switch to an older branch after a newer one has upgraded a database, it won't open until you update or restore a backup. I think refusing is the safer choice. If you'd rather it only warn, that's a small change. It's recorded in §4 of the task file.

**Noticed but left alone.** Four places (`services.py`, `story_load.py`, `story_resolve.py`, `value_focus.py`) open `story.db` directly and skip `get_db`, and `chat.db` has no timeout settings. These are listed under B1 in the task file as candidates for E3.

The task file also has a short recipe for adding a schema change from now on, and it marks A2 as applied.

### B2. Backup helper cleanup.

**04, B2: one backup function.**
- **Name and write.** `backup_database` now reserves its file name with Python's `tempfile.mkstemp`. It writes the snapshot as `.partial` and renames it to `.db` only when it's complete, and a failed backup is deleted. `delete_project` uses the same function with a different folder, and the second naming loop is gone.
- **A silent bug fixed.** The old "check the name, then use it" loop lost or duplicated backups in 9 of 40 rounds with 8 backups at once. The new code had 0 of 40. Eight at once is artificial, but two at once from the UI and the agent is plausible.

## Phase C — Features a writing app is expected to have

### C1. Trash: list deleted entities
**05, C1: a trash list.** `story_admin(action="list_deleted")` shows every deleted item, newest first. For each it gives the type and id that restore needs, when it was deleted, and whether a purge would remove it. A scene deleted together with its beats appears as one entry with "includes". Items deleted before `deleted_at` existed are listed too, and the bulk purge could never see those.

I also found a real problem in existing code while writing the C1 tests, and I left it for D1. When you delete a parent, `delete_entity` re-stamps children that were already in the trash. Their own deletion time is overwritten, restoring the parent brings them back, and the confirmation preview lists them as "would delete". There's also a lead about grandchildren being orphaned, which I only saw with a made-up test case. Both are written up under D1.

### C2. Delete a single item forever.

**06, C2: delete one item forever.** `purge` with a `target` removes exactly that item, plus what was deleted with it, and leaves the rest of the trash alone. It needs the same confirmation and takes a backup first. It refuses anything that isn't already in the trash, an unknown id, or a wrong type. It also clears links from remaining trashed items that pointed at what was removed, which the bulk purge now does too.

Two things for you to review:
- **A decision for you.** A named delete-forever skips the 30-day wait, because naming one item isn't a bulk tidy-up. It still needs the confirmation phrase and takes a backup. If you'd like the wait kept, it's a one-line change, and it's recorded in §4.
- **A contract change.** A `target` on `purge` used to be silently ignored, and the call wiped everything old enough. Now it means "just this one". `tests/test_purge.py`'s helper sent a target on every call, so it now sends one for `restore` only. That's the only existing test I changed.

I caught two gaps in my own tests during mutation checking and fixed them. In one, the mutation text wasn't found, so it had silently tested unmodified code.

## C3. Scene revision history.

**What it does.** Until now, saving a scene replaced its text for good. Now every save keeps the text it replaced. It's one hook inside `edit_entity`, and I confirmed that both the agent's draft commits and the script editor's Save go through it. The kept copy is written in the same transaction as the overwrite, so a failed save can't leave a stray revision.

- **Restoring.** Restoring an old version is an ordinary edit, so the text it replaces is kept too. Restoring twice takes you back where you started. It refuses a locked scene or another entity's revision.
- **Where you reach it.** There are two new `story_admin` actions, `list_revisions` and `restore_revision`. For now they're agent-facing, so you'd say "put back the version of scene X from this morning". There's no web history panel yet, but `core/revisions.py` has what a route or button would call.
- **Details.**
  - A revision shows when the text stopped being current, the summary of the edit that replaced it, its length, and a one-line preview.
  - Soft delete keeps the history. Purge removes it with the entity. A Markdown re-import leaves it alone.
  - Nothing is kept when the text is identical or the old text is empty.
  - It covers section text only, not fields like heading parts, cast or status.
- **Decisions I made (recorded in §4).** I keep the last 50 versions per section, not the 20 in the plan, because the editor saves on demand and a habitual Ctrl+S would burn through 20 in one sitting. Say if you want a different number; it's one constant. I also kept the "only when the text changed" rule from the plan.

**How I checked it.** I broke six rules on purpose, one at a time. Examples: the hook removed, retention pruning the wrong rows, locked scenes allowed, purge leaving history behind. Each break made a test fail. I also found a test of mine with an assertion that could never fail (it ended in `or True`) and fixed it.

**One finding for later.** The scene lock is enforced only in the UI's save path, not at the write boundary. An agent edit through `story_draft` isn't stopped by a locked scene. I didn't change that, but it's recorded in the task file for the D-phase discussion.