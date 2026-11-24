## T2b — Baseline: drop legacy-database support (insert between T2 and T3)

**Size M · Risk low–medium · Mostly DELETION · One new standalone script.**

### Owner decision (this changes an assumption in the rest of this file)
The application has not shipped. There is **one** database that matters — the owner's
live one. The test fixture has no committed database (`tests/fixtures/save-the-children`
contains Markdown only; every test builds its database by importing it). So no legacy
database exists once the live one is upgraded, and **code and tests that exist only to
open legacy databases should be removed.**

This overrides, from here on:
- DB-5's requirement to test against "the legacy partial database";
- T2's "table-exists guard" advice (it stays in `_m5` only until this task removes it);
- any rule elsewhere in this file about tolerating databases from older builds.

### What to KEEP (this is not legacy — do not delete it)
- The **versioned, append-only migration runner** (`SCHEMA_MIGRATIONS`, `apply_migrations`,
  `PRAGMA user_version`). Every future schema change goes through it.
- **Migrate-on-open** in `get_db`. The live database will be one migration behind every time
  a task changes the schema, and restoring a backup taken at an earlier version (C4) is a
  normal path that needs it.
- `SCHEMA_SQL` with `IF NOT EXISTS` (it runs on every `create_schema`, including over
  existing tables).
- `deleted_together`, soft delete, `live_relations`, `references.py`, drafts idempotence:
  all current behaviour, none of it legacy.

### Goal
The code supports **exactly one starting point** — the current schema — plus the mechanism
to move forward from it.

### Part 1 — Upgrade the live database once (standalone script, outside the package)

Create `tasks/task_40/upgrade_live_db.py`. It is a one-off tool, not imported by the app.

```
usage: python tasks/task_40/upgrade_live_db.py PROJECT_DIR [--apply]
```
Without `--apply` it works on a **temporary copy** and only reports. With `--apply` it
works on the real project, **after** taking a backup it prints the path of.

Steps, in order:
1. Print `PRAGMA user_version` and row counts of `entities`, `relations`, `sections`,
   `revisions`, `drafts`.
2. Copy the database file with the SQLite backup API (`sqlite3.Connection.backup`) — never
   `shutil.copy` a WAL database. In `--apply` mode this copy is the safety backup.
3. Open it through `get_db(project_dir)` — this runs every migration (`_m1`…`_m5`).
4. **Data fixes the migrations cannot do:**
   - Rows with `is_deleted=1` and `deleted_at IS NULL` (deleted by an earlier build): give
     them **one shared stamp** (the current time, `datetime.now().isoformat(timespec="seconds")`).
     One shared value keeps a deleted parent and its deleted children "deleted together", and
     the 30-day purge floor protects them.
   - Anything else the report below shows that needs it — **ask the human** rather than
     invent a fix.
5. Run `core.integrity.find_orphans(conn)` (T1) and `PRAGMA integrity_check`. Print both.
6. Print the row counts again and a diff line per table. **Counts of `entities`,
   `relations`, `sections`, `revisions` must be unchanged** (the stamp fix touches values,
   not rows). If a count changed, stop: do not `--apply`; tell the human.
7. Exit non-zero if `find_orphans` is non-empty or `integrity_check` is not `ok`.

**Procedure (the human runs this, or the agent does and reports):**
1. Run without `--apply` on the live project. Read the report.
2. If clean: run with `--apply`. Keep the backup file until the whole of Phase E is done.
3. Confirm the app opens the project and the dashboard loads.

**Do not start Part 2 until the live database reports `user_version = 5`, zero orphans, and
`integrity_check = ok`.**

### Part 2 — Make the current schema the baseline

1. **`core/db.py`.** Introduce `BASELINE_VERSION = 5`. Replace the history (`_m1`…`_m5`) by the
   baseline concept; `SCHEMA_MIGRATIONS` becomes **empty**. The next real change will be
   appended as the first entry and takes the database from version 5 to 6. Define
   `LATEST_VERSION = BASELINE_VERSION + len(SCHEMA_MIGRATIONS)` and make `apply_migrations`
   use it (migration at list position *k* upgrades *BASELINE+k → BASELINE+k+1*). Update
   everything that used `len(SCHEMA_MIGRATIONS)` or `LATEST`.
   - A database stamped **lower than the baseline**, or a file that **has tables but no
     version**, must raise a clear error, e.g.
     `"This database is older than this build supports (version N). Run tasks/task_40/upgrade_live_db.py."`
     — never silently open or half-upgrade it.
   - A file with **no tables** is a new project: `create_schema` stamps it `LATEST_VERSION`.
     Keep that path.
2. **Remove the legacy branches.** Search and delete, with their docstrings and comments:
   - the "unstamped" handling in `core/trash.py` (`deleted_together` uses `deleted_at IS ?`
     only so a NULL stamp matches NULL — it becomes a plain `deleted_at = ?`);
   - the "rows with no `deleted_at` (deleted by an earlier build)" listing branch in
     `tools/story_admin.py` (`list_deleted`) and its mention in the tool description;
   - `deleted_at IS NOT NULL` filters whose only purpose was to skip unstamped rows (only if
     removing them changes no result for stamped rows);
   - comments mentioning "earlier build", "old database", "never stamped" that are no longer true.
   Do **not** touch `get_db`'s migrate-on-open call.
3. **Tests.**
   - Delete `tests/test_legacy_db_migration.py`.
   - Rewrite `tests/test_schema_migrations.py` to test the **mechanism**, not history: a new
     project is stamped `LATEST_VERSION`; with a **test-only migration** monkeypatched onto
     `SCHEMA_MIGRATIONS` (e.g. creating a throwaway table), a database stamped one version lower
     is upgraded on open, keeps every row, and is stamped; running it twice changes nothing; a
     failing migration leaves the database at its old version; a database **below the baseline**
     raises the clear error; a file with tables and no version raises it too.
   - The legacy-shaped fixtures that T2 edited (`_legacy_project` and the two sites in
     `test_live_relations.py`) are now unnecessary: replace each by a project built the normal
     way (`create_project` / `twin_helpers.build`). If a test only existed to exercise a legacy
     shape, delete it and say so in the commit.
   - `tests/test_backups.py`: keep tests that restore a backup taken at the **current** schema;
     replace the ones that fabricate an old version with **one** test using the test-only
     migration (a backup one version behind is upgraded when restored). Delete the rest.
   - Search the remaining files for `user_version`, `legacy`, `unstamped`, `stamped`
     (`test_soft_delete`, `test_drafts`, `test_manual_structure`, `test_manual_entities_phase2`,
     `test_revisions`, `test_delete_stamps`, `test_purge_one`, `test_periodic_backup`) and apply the
     same rule to each hit: keep it if it tests current behaviour, delete or simplify it if it tests
     legacy support.
4. **This file.** Update DB-5: migration tests are (a) a new project and (b) a database one
   version behind, using a test-only migration; no legacy shapes. Add the rule: *every schema
   change from now on is appended after the baseline; the live database is upgraded by opening
   it; never edit it by hand.*

### Gotchas
- **Backups from before the baseline become unopenable.** The live project's `.story/backups`
  may contain files at versions below 5. After Part 1 succeeds, either delete them or run the
  script on a copy of each you care about. Say which in Discoveries.
- Do not delete `_m4`'s lesson — keep the sentence "a view over a missing table breaks later
  `ALTER TABLE`" as a comment next to the `live_relations` view in `SCHEMA_SQL`.
- The suite count **will go down** (tests deleted). That is expected: record the new baseline
  and the reason in the Progress log.
- Anything that fails for a reason that is not a deleted legacy test is a real regression: stop.

### Done when
- [x] Script exists; run on a copy, then on the live project with `--apply`; live DB at
      version 5, zero orphans, `integrity_check ok`, row counts unchanged. Backup path recorded.
- [x] `BASELINE_VERSION`, empty `SCHEMA_MIGRATIONS`, clear error for older databases.
- [x] Unstamped-row branches and the stale comments removed.
- [x] `test_legacy_db_migration.py` deleted; `test_schema_migrations.py` tests the mechanism;
      T2's legacy-shape fixtures replaced by normally-built projects.
- [x] `git diff --stat` shows **more lines deleted than added**; the new test baseline and the
      reason are in the Progress log.
- [x] Close-out. Then continue with T3.

### If T7 (UTC timestamps) is ever done
This task makes it simpler: extend the one-off script to convert the live database's stored
stamps once, and no code needs a "tolerate naive timestamps" path.

### Close-out (2026-11-21)
Done on branch `e-t2b-baseline`. Suite: **1619 passed, 1 failed** (the pre-existing
`test_no_hermes_imports`); baseline down from 1629 because legacy-only tests were deleted
(whole `test_legacy_db_migration.py` + legacy-shape tests in 9 files), replaced by mechanism
tests. 8 mutations verified caught. Code diff: 342 insertions / 612 deletions. Live DB at
version 5, zero orphans, `integrity_check ok`; safety backup
`.story/pre-t2b-upgrade-20261121_132138.db`. Details and surprises: main file, Progress log
and Discoveries (T2b entries). DB-5 rewritten; T2 marked superseded in part.
