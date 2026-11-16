# PATCHES NOTES

## PHASE 1

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