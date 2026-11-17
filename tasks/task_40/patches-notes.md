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

