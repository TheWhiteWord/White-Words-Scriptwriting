# Phase E — consistency and integrity of the database layer

Task file for the implementing agent. Written after a code review of `dev` at
commit `726d57c` (2026-11-20). Python 3.11+, SQLite, FastAPI. Everything below was
checked against that code; where I give a line number it is only a hint — find
things by **function name**, line numbers drift.

---

## Note to the project owner (the agent can skip this box)

I investigated before writing, and **three of the original E-items change shape**:

| Original item | What the code showed | What this file does instead |
|---|---|---|
| **E1** replace the three hash tokens with a `rev` column | The defect is not "hash vs counter". It is that every save does *check the token, close the connection, then write in a separate transaction*, so the check is not atomic with the write. A `rev` column needs a migration, triggers (or touching every writer — the exact mistake class that hid in D1), and would conflict on no-op writes. The hash tokens are content-aware, which is a *good* property (a scene-title edit does not conflict a reorder). | **T4**: keep the tokens, share one hashing helper, and make the check happen **inside the write transaction**. No `rev` column. (Appendix B says what the alternative would cost, if you disagree.) |
| **E2** atomic draft commit | The plumbing exists (`transaction()` already nests as a SAVEPOINT). The hard part is that **seven validators open their own connection**, so inside one atomic commit a later op could not see an earlier op's uncommitted create. Also `dry_run` calls `commit()` on a DB *copy*, and a `purge` op opens its own connection. | **T3** (pure plumbing, no behaviour change) comes first and is the prerequisite for both E1 and E2; **T5** is the atomic commit itself. |
| **E3b** foreign keys with `ON DELETE CASCADE` | There are **no foreign keys declared at all** (though `get_db` already sets `foreign_keys=ON`). Adding them means rebuilding `sections`, which has an external-content FTS5 index and three triggers tied to its `rowid`, plus the `live_relations` view. High risk, low value: `hard_delete` already deletes in the right order. | **T1**: a read-only *orphan checker* plus tests. It gives the safety of FKs without the migration, and it becomes the safety net for T3–T5. Real FKs only as Appendix B. |
| **E3c** UTC timestamps | ~10 producers; the stamp `deleted_at` is both compared (purge cutoff) and matched by equality ("deleted together"). Real but low value. | **T7**, **optional**, last. Fine to skip; record the decision. |

Effort/risk, in the order I recommend:

| Task | Covers | Size | Risk | Needs your decision? |
|---|---|---|---|---|
| T1 orphan checker | E3b | S | none | no |
| T2 indexes | E3a | S | low | no |
| T3 connection plumbing | E2 (part 1) | M | medium (wide, mechanical) | no |
| T4 atomic version checks | E1 | M | medium | **only if you want the `rev` column** |
| T5 atomic draft commit | E2 (part 2) | L | **high** | no |
| T6 draft status, one source | E3d | S | low | no |
| T7 UTC timestamps | E3c | M | low–medium | **owner said yes** (done; the conversion run is the owner's step) |

None of this is an emergency. The race in E1 needs two writers within milliseconds; the
partial-commit state in E2 has a working recovery path today. This phase is about
correctness and simplicity, so **do not rush it**: a slow, verified T3 is worth more than
a fast T5.

---

# Part 0 — How to work through this file

1. **Read Parts 0–3 completely before touching code.** Then do the tasks in Part 4
   **in the order given**, one at a time. Each task is self-contained: goal, why,
   what the code looks like now, the design, steps, gotchas, tests, and a
   "done when" checklist.
2. **One task = one git branch = one commit** (amend while iterating). Do not
   start task N+1 until task N's checklist is fully ticked and the full test suite
   is at baseline (Part 1.1).
3. **After each task**, fill in its row in the Progress log (Part 6) and note
   anything surprising in "Discoveries".
4. **If the code contradicts this file, stop.** Do not guess. Write the
   discrepancy in "Discoveries", take the *safer* reading (the one that changes
   less), and, if it changes the design of the task, ask the human before going on.
5. **Stop and ask the human** (do not decide alone) when:
   - an existing test must be *deleted* or has to be *loosened* to pass;
   - you must change a JSON key, status code, or tool-result key listed in
     Part 2.4 ("interfaces that must not change");
   - a task needs a schema change that Part 4 does not mention;
   - you are about to touch more than the files the task lists;
   - the suite shows a failure that is not the known baseline failure and you
     cannot explain it within two attempts.
6. **You are trusted to work alone inside these rules.** Small decisions
   (naming, where a helper lives, how to split a function) are yours. Follow the
   existing style of the file you are in.

---

# Part 1 — Ground rules (non-negotiable)

## 1.1 Environment and the test baseline

Run from the repository root, with the project installed (`pip install -e .`):

```bash
python -m pytest tests -q -p no:cacheprovider > /tmp/run.txt 2>&1
grep -E '^FAILED' /tmp/run.txt | sed 's/ - .*//' > /tmp/fails.txt
cat /tmp/fails.txt; tail -1 /tmp/run.txt
```

**Expected baseline at the time of writing: `1602 passed, 1 failed`**, and the one
failure is exactly `tests/test_no_hermes_imports.py::test_no_hermes_imports`. It is
known and unrelated; leave it alone. Run this **before you start** and write the
number in the Progress log. Every task must end at *baseline + the tests you added*,
with that same single failure.

If tests fail with certificate errors or `Errno 2` in a sandbox, `SSL_CERT_FILE`
may point at a missing file; unset it or point it at a real CA bundle.

## 1.2 Git

- Branch per task: `e-t3-connection-plumbing`, etc. Start from the latest `dev`.
- Commit message: a one-line summary, a blank line, then *why* (the problem), *what*
  (bulleted), and the test count. Mention every contract or doc change.
- **Never chain the test run into the commit.** `pytest | tail && git commit`
  commits even when pytest fails, because `tail` succeeds. Use the file pattern
  in 1.1 and compare the failure list explicitly:

  ```bash
  test "$(cat /tmp/fails.txt)" = "FAILED tests/test_no_hermes_imports.py::test_no_hermes_imports" \
    && git add -A && git commit
  ```
- Never commit a half-working state "to save progress" onto the task branch; use
  `git stash` for that.

## 1.3 Database rules (each exists because something already went wrong)

**DB-1 — Always `get_db(project_path)`.** Never a bare `sqlite3.connect` in
application code: it skips the schema upgrade, so a view or index added by a
migration may not exist yet (`no such table: live_relations`). *Tests* may use a bare
connect to look at the file.

**DB-2 — Transactions only through `with transaction(conn):`** (`core/db.py`).
Never type `BEGIN`, `COMMIT` or `ROLLBACK` by hand. The connection is in
autocommit mode (`isolation_level=None`), so every statement outside a
`transaction` is its own commit. `transaction()` starts with `BEGIN IMMEDIATE`
(takes the write lock up front) and, if one is already open on that connection,
becomes a `SAVEPOINT` instead — so it **nests safely**. An exception inside the
block rolls the block back.

**DB-3 — A write that may run inside someone else's transaction must use the
connection it was given for *every* read and write.** Why: the database is in WAL
mode. A *second* connection sees only what was committed before the outer
transaction began, so it cannot see the outer transaction's new rows (validation
fails wrongly), and a second *writer* waits for the lock for `busy_timeout`
(3000 ms) and then raises `database is locked`. This is the single biggest danger of
T3–T5.

**DB-4 — Readers go through the hiding layer.**
- Relations are read from the `live_relations` view, never the `relations` table
  (a source-scan test enforces this).
- References to deleted entities in `extra` and in `location_id` / `parent_id` are
  hidden by `core/references.py` (`dead_ids`, `live_extra`, `live_column`).
- **A new reader must be added to `tests/twin_helpers.everything_a_reader_can_say()`**
  — that is the only test that covers it.

**DB-5 — Schema changes.** The schema has a baseline (`BASELINE_VERSION = 5` in
`core/db.py`; `chat/store.py` has its own `CHAT_BASELINE = 1`). Every change from
now on is **appended after the baseline**: add a function to `SCHEMA_MIGRATIONS`
**and** update `SCHEMA_SQL` for fresh databases. Never edit an existing migration
(it is a frozen record). Entry *k* upgrades `BASELINE+k → BASELINE+k+1`;
`LATEST_VERSION = BASELINE_VERSION + len(SCHEMA_MIGRATIONS)`. The live database is
upgraded by opening it (`get_db`); never edit it by hand. A file below the
baseline, or one with tables but no version, is refused. The app has not shipped,
so the baseline is the only schema there is: `SCHEMA_MIGRATIONS` is empty and the
machinery (`apply_migrations`, the version gate) stays for the first real change.
Test a
migration on (a) a new project and (b) a database stamped one version lower,
using a test-only migration monkeypatched onto the list (see
`tests/test_schema_migrations.py`); no legacy shapes. Beware: SQLite re-validates
views on `ALTER TABLE`, so any table rebuild must drop and recreate
`live_relations` — a view over a missing table breaks every later
`ALTER TABLE ... RENAME` (the lesson is kept as a comment in `SCHEMA_SQL`).

**DB-6 — Observable contracts do not change silently** (Part 2.4). If one must, you
update: the tests, the agent-facing text (`tasks/task_30/skill/references/**`
and the `SCHEMA` description strings in `tools/*.py`), and you list it in the
commit message. The frontend cannot be run here; assume nothing about it beyond
Part 2.4.

## 1.4 Testing rules

**TR-1 — Test first for behaviour changes.** Write the test, watch it fail *for the
right reason*, then change the code.

**TR-2 — Mutation-check every new behaviour test.** Temporarily undo the fix and
confirm the test fails; then restore. Procedure: copy the file to `/tmp`, edit
with a script that **asserts the pattern matches exactly once**, run the test,
copy the file back, and `git diff --stat` to prove the tree is clean. A test that
passes both with and without the fix proves nothing. Run mutation loops in the
**foreground** — a background process dies when the tool's shell ends and can leave
a mutated file behind.

**TR-3 — No fragile assertions.** No byte offsets, no exact timestamps, no
`sleep`-based races. Assert through public functions. For "the database is
byte-for-byte as before", use `tests/twin_helpers.snapshot(project_path)`.

**TR-4 — Concurrency tests are deterministic or they are not written.** See the
recipe in T4.

**TR-5 — Patching scripts assert one match.** A pattern can match twice. Always
`assert text.count(old) == 1` before replacing.

**TR-6 — A failing existing test is information, not an obstacle.** Decide which it
is: (a) it **encodes the old behaviour you are deliberately changing** → rewrite it
and say why in a comment; or (b) it **found a real regression** → fix the code.
Never delete a test or loosen an assertion just to get green (ask the human, rule
0.5).

**TR-7 — Use the existing test helpers**: `tests/conftest.py` (`fixture_path`,
`vault`…), `tests/twin_helpers.py` (`build`, `sql`, `snapshot`, the reader battery).
Look at `tests/test_live_references.py` and `tests/test_purge_approval.py` for the
house style.

## 1.5 Code conventions

- Comments and docstrings explain **why**, briefly. Match the density of
  `core/writes.py` and `core/references.py`.
- **Prefer deleting code to adding it.** When you replace something, remove it, its
  stale comments, its tests' stale comments, and its mention in agent-facing docs.
- Raise the exception types the module already uses (`ValueError` in `writes`,
  `DraftError` in `drafts`, `EntityConflict` / `StructureConflict` /
  `ScriptConflict` in the manual modules). Do not invent new ones unless a task says so.
- `from __future__ import annotations` at the top of new modules; type hints in the
  repo's light style (`dict | None`).
- No new third-party dependencies.
- Keep diffs small. **Do not re-indent a large function** to wrap it in a `with`;
  change the two lines that acquire and release the connection instead (T3 shows how).

## 1.6 Scope discipline

Do the task, only the task. If you notice an unrelated bug or an improvement, write
it in "Discoveries" and move on. If a task "needs" an unrelated fix to pass, that is
rule 0.5: ask.

---

# Part 2 — Map of the system (what you need to know)

## 2.1 The pieces

| Piece | Where | What it is |
|---|---|---|
| Connection + transaction | `core/db.py` `get_db`, `transaction`, `SCHEMA_SQL`, `SCHEMA_MIGRATIONS` | WAL, `busy_timeout=3000`, `foreign_keys=ON`, autocommit. Migrations stamp `PRAGMA user_version`. |
| Write functions | `core/writes.py` | `create_entity`, `edit_entity`, `delete_entity` (flag only), `reorder`, `current_values`, `validate_value`, `create_project`. |
| Validators | `core/entity.py` | `check_references`, `validate_scene_*`, `validate_beat_references`… |
| Soft delete | flag `is_deleted` + `deleted_at`; **nothing else changes** on delete | Readers hide the rest: view `live_relations`; `core/references.py`. Restore clears the flag. Purge is the only irreversible op (`core/trash.py`). |
| Drafts | `core/drafts.py`, `tools/story_draft.py`, `app/routes/drafts.py` | The agent *stages* ops; the person approves on a card; `commit()` applies them. |
| Manual (web) editing | `core/manual_entities.py`, `core/manual_structure.py`, `core/manual_edits.py`, routes in `app/routes/entities.py` and `scripts.py` | Form save, structure reorder, script editor. Each has a **version token** (see 2.3). |
| Tests | `tests/` | ~1600 tests. `tests/twin_helpers.py` is the key shared module. |

## 2.2 The save flows today (this is what T3–T5 change)

**Entity form** — `PUT /api/projects/{slug}/entities/{etype}/{eid}` →
`manual_entities.edit_form_entity`:
`load_entity` (opens a connection, reads, closes) → compare `base_version` →
validate → `writes.edit_entity` (its own connection, its own transaction) →
`_write_sheet` (another connection, another transaction). *Three separate
transactions; the check is in none of them.*

**Structure reorder** — `POST .../structure/apply` → `manual_structure.apply`:
`load_tree` → compare `base_version` → a series of `writes.edit_entity` calls.

**Script editor** — `PUT .../scenes/{id}/script` → `manual_edits.save_scene_script`:
state read → compare `base_hash` → `writes.edit_entity`.

**Agent** — `tools/story_draft.py` stages; the web approve route (or the tool)
calls `drafts.commit`, which applies **each op in its own transaction**, then marks
the draft committed in **yet another** transaction. A failure part-way leaves earlier
ops landed and the draft kept for a re-stage.

Plain `def` FastAPI route handlers run in a thread pool, so two saves in the same
process can genuinely overlap; the agent's MCP server is a separate process. Both
write the same SQLite file.

## 2.3 The three version tokens

| Where | Function | What it hashes |
|---|---|---|
| entity form | `manual_entities._version(values, sections)` | `{"v": values, "s": sections}` → sha256[:16] |
| structure | `manual_structure._version(tree)` | the ids and order of acts / sequences / scenes → sha256[:16] |
| script editor | `manual_edits.content_hash(state)` | the heading fields + raw content → hash |

They are opaque strings the browser stores and sends back. They are **content-aware**:
re-saving identical content does not conflict, and the structure token ignores titles.
Keep that.

## 2.4 Interfaces that must not change

| Contract | Detail |
|---|---|
| Entity form save | request field `base_version`; on conflict HTTP **409** `{"error": {"code": "conflict", "message", "current_version"}}` |
| Structure apply | request field `base_version`; 409 conflict with `current_version` |
| Script save | request field `base_hash`; 409 conflict with `current_hash` |
| Draft approve | the route reads `result["success"]`, `result["failed"]`, `result["committed"]`; the card status it stores is `"failed"` or `"committed"`; a missing/finished draft is 409 `stale_draft` |
| Tool results to the agent | `story_draft` results keep `success`, `draft_id`, `preview_md`, `committed`, `failed`, `draft_kept`, `already_committed` |
| Exceptions | `EntityConflict.current_version`, `StructureConflict.current_version`, `ScriptConflict.current_hash` |

Frontend files that depend on these: `web/js/forms/entity-form.js`,
`web/js/views/reorder.js`, `web/js/script-editor/editor.js`.

---

# Part 3 — Findings that shape the tasks

1. **`transaction()` already nests** (SAVEPOINT) and starts `BEGIN IMMEDIATE`. E2's
   foundation exists.
2. **Functions that open their own connection** (verified by AST scan). T3's exact
   worklist:
   - `core/writes.py`: `create_entity`, `edit_entity`, `current_values`,
     `delete_entity`, `reorder`, `validate_value` (and `create_project`, which does
     not need to change).
   - `core/entity.py`: `validate_scene_act_id`, `validate_scene_location`,
     `check_references`, `validate_scene_beats`, `validate_beat_references`,
     `validate_scene_value_turns`. (`validate_scene_plot_roles` **already takes
     `conn`** — copy its pattern; its docstring explains the need: "read rows its
     own transaction has written but not committed".)
   - `core/manual_entities.py`: `load_entity`, `check_entity`, `_write_sheet`,
     `create_form_entity`, `edit_form_entity`, `delete_preview`.
   - `core/manual_edits.py`: `load_scene_script`, `check_scene_script`,
     `save_scene_script`.
   - `core/manual_structure.py`: `load_tree`, `apply`.
3. **`edit_entity` validates before it opens its transaction.** Inside the
   function the read-then-write gap exists even for a single edit.
4. **`dry_run` replays `commit()` on a *copy* of the database** (a full copy per
   stage). It also runs a `purge` op on that copy. Do **not** change `dry_run` in
   this phase.
5. **A `purge` op opens its own connection and takes a backup.** It must never run
   inside the shared transaction of T5 (it would wait 3 s for the lock, then fail).
   `validate_ops` already guarantees a purge draft contains *only* purge ops, so
   T5 keeps the old per-op path for those.
6. **The fixture database is clean** (no orphan rows, no dangling relations), so a
   checker can start strict. Real user databases may differ; the checker only
   *reports*.
7. **Indexes missing for three common lookups** (query plans show full scans):
   `relations` by `to_id`; `entities` by `parent_id`; `entities` by `type`. And the
   set of deleted ids (`WHERE is_deleted=1`) is read constantly by the hiding layer.
8. **Draft status lives in two places**: the `drafts` table (truth) and a `status`
   field inside the chat message's draft snapshot (a display copy that goes stale if
   the agent commits via the tool, or a commit fails).
9. **Timestamp producers** (`datetime.now()` etc.) exist in roughly ten places;
   build the inventory yourself in T7.

---

# Part 4 — The tasks

Common closing steps for **every** task (referred to below as "the close-out"):

1. Full suite at baseline + your new tests, only the known failure (1.1).
2. Every new behaviour test mutation-checked (TR-2); `git diff --stat` clean afterwards.
3. Search for stale text: `grep -rn` the old behaviour's keywords in `src/`, `tests/`,
   `tasks/task_30/skill/` — fix what you find (agent-facing docs especially).
4. Commit with the message template; update the Progress log.

---

## T1 — Orphan checker (original E3b, the safe part)

**Size S · Risk none · No schema change.**

### Goal
A read-only function that finds rows pointing at things that do not exist, plus tests
that use it as an oracle after every kind of write. This replaces "add foreign keys":
the same protection, no table rebuild.

### Why
There are no declared foreign keys. `hard_delete` removes rows in the right order, but
nothing *checks* that no operation ever leaves a section, revision, or relation behind.
T3–T5 change how writes are grouped; this is the net under them.

### Design
New module `core/integrity.py`:

```python
def find_orphans(conn) -> dict[str, list]:
    """Rows that point at something that is not there. Empty dict = clean."""
```

Report only non-empty categories. Checks (all plain SQL, all read-only):

| key | rule |
|---|---|
| `sections` | `entity_id` not in `entities.id` |
| `revisions` | `entity_id` not in `entities.id` |
| `relations_from` | `from_id` not in `entities.id` |
| `relations_to` | `to_id` not in `entities.id` |
| `parent_id` | non-empty `parent_id` not in `entities.id` |
| `location_id` | non-empty `location_id` not in `entities.id` |

**Important:** a row that is *flagged deleted* still exists, so a reference to it is
**not** an orphan. Only a reference to a *missing row* is. (A live "grandchild" whose
parent is in the trash is legitimate.)

Optional seventh check: the full-text index agrees with `sections`. FTS5 offers
`INSERT INTO sections_fts(sections_fts) VALUES('integrity-check')`, which raises if
the index is out of step. Wrap it in `try/except sqlite3.DatabaseError` and report
`fts` when it raises. Skip this check if it proves flaky (note it in Discoveries).

### Steps
1. Write `core/integrity.py` and `tests/test_integrity.py`.
2. Add a helper to `tests/twin_helpers.py`:
   ```python
   def assert_no_orphans(project_path):
       conn = sqlite3.connect(str(project_path / ".story" / "story.db"))
       try:
           assert find_orphans(conn) == {}
       finally:
           conn.close()
   ```
3. Tests:
   - clean freshly-imported fixture → `{}`;
   - one test per category on a hand-broken database (insert the bad row with plain
     SQL, assert the right key appears, and nothing else);
   - a flagged-deleted parent is **not** reported;
   - **scenario matrix** (parametrize) — after each of these `assert_no_orphans`:
     delete + restore of a character / scene / plot / location / world; targeted
     purge (`core.trash.purge_deleted`); bulk purge with `older_than_days=0`; create
     then edit then delete via `writes`; a draft commit; a full re-import.
4. If a scenario reports orphans, **that is a real bug**: stop, put it in
   Discoveries, tell the human. Do not "fix" it in this task unless the fix is one
   line and obviously right.

### Gotchas
- Use `NOT IN (SELECT id FROM entities)`; remember `NULL` in a `NOT IN` list makes the
  whole comparison unknown — `entities.id` is a primary key, so it is never NULL; the
  *referencing* column may be NULL or `''`, so guard those two for `parent_id` and
  `location_id`.
- Do not wire the checker into any tool or route. It is test infrastructure.

### Mutation check
Make `hard_delete` (in `core/trash.py`) skip the `sections` delete; the purge scenario
must now fail with a `sections` orphan. Restore.

### Done when
- [x] `core/integrity.py` + `tests/test_integrity.py` (clean, six categories, grandchild
      case, scenario matrix) pass. *(FTS check kept, with `rank=1` — see Discoveries.)*
- [x] Mutation check done. · [x] Close-out. *(DB-4 source scan needed a named exemption
      for the checker's raw reads — owner approved; see Discoveries.)*

---

## T2 — Indexes (original E3a)

**Size S · Risk low · Schema change: migration 5, additive only.**

> **Superseded in part by T2b (baseline).** `_m5_indexes` and the legacy-shape
> fixtures no longer exist: the four index statements live in `SCHEMA_SQL` only,
> and the migration mechanism is tested with a test-only migration. The design,
> evidence and plan tests below remain the record of what was added and why.

### Goal
Add the indexes the query plans show missing, with proof that SQLite uses them.

### Evidence (reproduce it first)
```sql
EXPLAIN QUERY PLAN SELECT from_id FROM relations WHERE to_id='x' AND kind='character_scene';
  -- SCAN relations USING COVERING INDEX sqlite_autoindex_relations_1   (full scan)
EXPLAIN QUERY PLAN SELECT id FROM entities WHERE parent_id='x' AND is_deleted=0;   -- SCAN entities
EXPLAIN QUERY PLAN SELECT id FROM entities WHERE type='scene'  AND is_deleted=0;   -- SCAN entities
```
The primary key on `relations` is `(from_id, to_id, kind)`, which serves lookups by
`from_id` but not by `to_id`.

### Design
Migration 5, `_m5_indexes`, appended to `SCHEMA_MIGRATIONS`, and the same statements
added to `SCHEMA_SQL`:

```sql
CREATE INDEX IF NOT EXISTS idx_relations_to      ON relations(to_id, kind);
CREATE INDEX IF NOT EXISTS idx_entities_type     ON entities(type, is_deleted);
CREATE INDEX IF NOT EXISTS idx_entities_parent   ON entities(parent_id);
CREATE INDEX IF NOT EXISTS idx_entities_deleted  ON entities(id) WHERE is_deleted=1;
```
The last is a **partial index**: it holds only the (few) deleted rows, so
`SELECT id FROM entities WHERE is_deleted=1` — which the `live_relations` view and
`dead_ids()` run constantly — becomes a tiny scan.

### Steps
1. Write `_m5_indexes(conn)` with the **table-exists guard** (copy the `have = {…}`
   pattern from `_m4_live_relations_view`; skip a statement if its table is missing).
   Write the docstring like `_m4`'s ("written out in full: a migration is a frozen
   record").
2. Append it to `SCHEMA_MIGRATIONS`; add the four statements to `SCHEMA_SQL`.
3. `grep -rn "user_version\|== 4" tests/` and fix any test that hard-codes the
   latest version (most use `len(SCHEMA_MIGRATIONS)`/`LATEST`; check each).
4. Tests in `tests/test_schema_migrations.py` (or a new `tests/test_indexes.py`):
   - a new project has all four indexes;
   - a database stamped `user_version=4` gains them on open and keeps all rows;
   - the legacy partial database (no `relations`) still migrates without error (guard);
   - **query-plan tests**: for each of the three lookups above plus
     `SELECT id FROM entities WHERE is_deleted=1`, `EXPLAIN QUERY PLAN` must mention
     the new index by name (`assert "idx_relations_to" in plan_text`). Join the
     plan rows into one string; plan wording varies between SQLite versions, so
     assert on the *index name* only.
5. Measure once, for the commit message: build a synthetic project of ~5,000
   entities and ~15,000 relations (a loop of inserts is fine), time the three
   lookups before and after. You are not asserting timings in tests — just
   recording that it helps.

### Gotchas
- Never edit `_m1`–`_m4`. Never renumber.
- A new database is stamped with the latest version by `create_schema`, so migrations
  never run on it — which is why `SCHEMA_SQL` must also contain the indexes.
- `CREATE INDEX` on a populated table takes a moment and a write lock; migrations
  already run inside the open path, which is fine at this size.
- Do not index `live_relations` (a view cannot be indexed; it uses the table's indexes).

### Owner notes (added after T1)

- The partial index only works with a literal. `idx_entities_deleted` (`WHERE is_deleted=1`)
  is used only when the query contains the literal `is_deleted=1`. A parameterised
  `is_deleted = ?` cannot use it. `dead_ids()` and the `live_relations` view use the literal,
  so they will benefit. If the query-plan test shows the index isn't used, check the query's
  wording before suspecting the index.
- Test the plan on a realistic table. Run the plan tests on a table with a few thousand rows.
  On a tiny table SQLite sometimes prefers a scan even when an index exists, which can make
  a plan test flaky.
- Number the migration 5. Use `_m5_indexes` with the table-exists guard, and add the same
  statements to `SCHEMA_SQL`.

### Mutation check
Delete one statement from `SCHEMA_SQL`: the "new project has the index" test fails.
Delete one from `_m5`: the "old database gains it" test fails.

### Done when
- [x] Migration 5 + `SCHEMA_SQL` + the four tests above. *(Legacy-shape fixtures edited —
      owner-approved; see Discoveries.)* · [x] Query-plan tests name the
      indexes. · [x] Timing noted in the commit message. · [x] Close-out.

---

## T3 — Connection plumbing (original E2, part 1)

**Size M · Risk medium (wide, mechanical) · No schema change · NO behaviour change.**

### Goal
Every write function and every validator it calls can run on a connection supplied
by the caller. When no connection is supplied they behave **exactly** as today.

### Why
T4 (atomic version checks) and T5 (atomic draft commit) both need one outer
transaction in which later steps can see earlier steps' uncommitted rows (rule DB-3).

### The pattern (one small helper, then repeat)
Add to `core/db.py`:

```python
from contextlib import contextmanager

@contextmanager
def use_connection(project_path, conn=None):
    """Yield `conn` if the caller supplied one — the caller owns it, so do not
    close it and do not commit or roll it back here — otherwise open one with
    get_db and close it on exit."""
    if conn is not None:
        yield conn
        return
    own = get_db(project_path)
    try:
        yield own
    finally:
        own.close()
```

**For the small validators** (`validate_scene_location` etc.): add a keyword-only
`conn=None` as the **last** parameter, and wrap the body:

```python
def validate_scene_location(project_path, location_id, *, conn=None):
    with use_connection(project_path, conn) as c:
        ...                       # use `c` instead of the old local conn
```

**For the big functions** (`edit_entity`, `create_entity`, `delete_entity`,
`reorder`): do **not** re-indent them. They already look like:

```python
conn = get_db(project_path)
try:
    ... long body ...
finally:
    conn.close()
```
Change only the two acquisition/release points:

```python
own_conn = conn is None
if own_conn:
    conn = get_db(project_path)
try:
    ... body unchanged ...
finally:
    if own_conn:
        conn.close()
```
and add `conn=None` to the signature. Inside, **pass `conn=conn` to every validator and
helper the body calls** (`check_references`, `validate_scene_*`, `validate_beat_*`,
`validate_value`, `current_values`, revisions helpers…).

`validate_scene_plot_roles` already has a `conn` parameter — leave its signature alone,
and make sure callers pass it.

### Steps
1. Read `validate_scene_plot_roles` and `create_entity` fully first; you are
   extending an existing idea.
2. Add `use_connection`. Do the validators in `core/entity.py` (six functions), then
   `core/writes.py` (`current_values`, `validate_value`, `create_entity`,
   `edit_entity`, `delete_entity`, `reorder`), then `manual_entities` (`load_entity`,
   `check_entity`, `_write_sheet`), `manual_edits` (`load_scene_script`, and the
   state-reading helper it uses), `manual_structure` (`load_tree`).
   **Do not** touch `create_project`, `trash.purge_deleted`, `story_import`, or
   `revisions.restore_revision`.
3. `create_entity` calls `has_schema(conn)` / `create_schema(conn)` on its connection —
   fine to do inside an outer transaction (DDL is transactional in SQLite), but keep
   that block as is.
4. After **each file**, run the targeted tests for that area, then the full suite at the
   end. The suite must pass **without any test changes**. If an existing test breaks, you
   changed behaviour; undo and find out why (rule 0.5 if you cannot).
5. Grep to prove nothing was missed: in `core/writes.py` and `core/entity.py` every
   `get_db(` call must now sit behind `own_conn`/`use_connection`.

### Tests to add (`tests/test_connection_plumbing.py`)
- **A later step sees an earlier step's uncommitted row.** Open one connection, begin
  `transaction(conn)`, `create_entity(..., conn=conn)` a character, then
  `create_entity(..., conn=conn)` a relationship that names that character. Both must
  succeed. (Without the plumbing the second fails: the validator's own connection cannot
  see the character.)
- **Nothing opens a hidden connection.** Same scenario, but first monkeypatch
  `story_architect.core.db.get_db` to raise. Late imports (`from .db import get_db`
  inside functions) resolve through that attribute, so any function that still opens its
  own connection blows up. Module-level imports (e.g. at the top of `manual_entities`)
  are separate names: patch those modules' `get_db` too.
- **Ownership:** when you pass a connection, it is still open and usable afterwards;
  when you do not, no connection leaks (use a counter around a patched `get_db`).
- **Rollback reaches everything:** inside `transaction(conn)`, create two entities via
  `conn=conn`, then raise; afterwards neither exists.

### Gotchas
- Late imports: many functions do `from .db import get_db, transaction` *inside* the
  function. Keep that style where it exists.
- A function that returns a "success" dict must still do so; only the connection
  handling changes.
- `edit_entity` reads a lot **before** its `with transaction(conn):`. Leave the order alone
  in this task — T4 deals with it. Plumbing only.
- If you find a function not on the list that also opens a connection during a write,
  add it and note it in Discoveries.

### Done when
- [x] Every function in Part 3.2 takes `conn=None`; behaviour unchanged. **Deviation
      (owner-approved 2026-11-21):** four stubs pinned the old write signatures and broke
      on the `conn` keyword (TypeError, not an assertion) — `test_manual_entities.py:221`,
      `test_manual_scene_editors.py:200/211/266`; their signatures now accept and forward
      `conn=None`, every assertion untouched (Discoveries).
- [x] The four new tests pass and are mutation-checked: six mutations, each caught by the
      expected test(s) — location validator ignores conn → `[location]`; `check_references`
      ignores conn → `[plot]`; value-turn validator ignores conn → `[value-turns]`;
      `create_entity`/`edit_entity` ignore conn → rollback + hidden-connection;
      `use_connection` closes the supplied conn → ownership. Full table in the Progress log.
- [x] Close-out: full suite **1625 passed + 1 failed** (baseline 1619 + 6 new; the same
      known `test_no_hermes_imports` env failure); grep proves every `get_db(` in
      writes/entity sits behind `own_conn`/`use_connection` (or is `create_project`);
      stale-text sweep clean; commit on `e-t3-connection-plumbing`.

---

## T4 — Atomic version checks and one hashing helper (original E1)

**Size M · Risk medium · No schema change · Contract unchanged (Part 2.4).**

### Goal
Make the "has this changed since you loaded it?" check **atomic with the write**, and
share one hashing function between the three tokens.

### The bug, exactly
`edit_form_entity` does: read → compare token → **(connection closed)** → write in a new
transaction. If the agent commits between the compare and the write, the person's save
silently overwrites it (only the fields they changed, but still). The fix is not a
different token; it is to hold the write lock from *before the check* until *after the
write*.

### Design
1. `core/versions.py` (new, tiny):
   ```python
   def token(payload) -> str:
       """Opaque 16-hex-digit fingerprint of what a person was shown."""
       blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
       return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
   ```
   Each of the three modules keeps deciding **what** it hashes (do not change the
   payloads' meaning) and calls `token(...)`. The entity and structure tokens are
   already `sha256[:16]`; check how `content_hash` finishes and make all three use
   `token`. The token *values* may change — they are opaque and short-lived — but
   run the suite to see if any test pins a value or a length.
2. **Entity form** (`edit_form_entity`):
   ```python
   conn = get_db(project_path)
   try:
       with transaction(conn):                       # write lock taken here
           current = load_entity(project_path, entity_type, entity_id, conn=conn)
           if base_version != current["version"]:
               raise EntityConflict(..., current_version=current["version"])
           ...                                       # validation, using conn
           result = edit_entity(..., conn=conn)
           _write_sheet(..., conn=conn)
   finally:
       conn.close()
   ```
   Everything the function does today, in the same order, **inside one transaction**.
   Raising inside the `with` rolls everything back, which also fixes the partial state
   "the scene was saved but the beats were not".
3. **Structure** (`manual_structure.apply`) and **script** (`manual_edits.save_scene_script`):
   same shape — open `transaction(conn)` first, load state with `conn=conn`, compare the
   token, then perform the writes with `conn=conn`, all inside.
4. **User-facing messages that describe partial saves become false.** Search for them
   (`grep -rn "was saved, but\|Stopped after\|were not" src/`) and rewrite: after this
   task a failed save changes **nothing**. Keep the same exception types and HTTP
   statuses.

### Steps
1. Read the three save paths completely (`edit_form_entity`, `manual_structure.apply`,
   `save_scene_script`) and `_write_sheet`.
2. Add `core/versions.py`; switch the three token functions to it. Run the suite.
3. Restructure the form save as above. Run `tests/test_manual_entities*.py`.
4. Do the same for structure, then script.
5. Fix the partial-save messages (and their tests).

### The deterministic race test (this is the important one)
You cannot reliably *produce* the old race with threads, so test the **guarantee** that
removes it: *while a save is between its check and its write, nobody else can commit.*

```python
def test_nobody_can_commit_between_the_check_and_the_write(project, monkeypatch):
    seen = {}
    real_edit = writes.edit_entity

    def edit_with_a_competitor(*a, **kw):
        # We are now inside the save's transaction. Try to commit from ANOTHER connection.
        other = sqlite3.connect(str(db_path(project)), isolation_level=None)
        other.execute("PRAGMA busy_timeout=50")
        try:
            other.execute("UPDATE entities SET one_sentence='sneaky' WHERE id='kael'")
            seen["outcome"] = "committed"
        except sqlite3.OperationalError as e:
            seen["outcome"] = str(e)                       # "database is locked"
        finally:
            other.close()
        return real_edit(*a, **kw)

    monkeypatch.setattr(writes, "edit_entity", edit_with_a_competitor)  # patch where it is *looked up*
    ... perform a normal form save ...
    assert "locked" in seen["outcome"]
```
Patch the name in the module that **calls** it (`manual_entities`), not only in `writes`.
Write one such test per save path. **Mutation check:** change the save back to
"check outside the transaction" — `seen["outcome"]` becomes `"committed"` and the test
fails.

Plus the ordinary conflict tests must still pass unchanged: load → another writer
changes it → save with the old token → `EntityConflict` (HTTP 409 with `current_version`).

### Gotchas
- `load_entity` computes the token from the **hidden-references-filtered** values; keep it
  that way (deleting a character a relationship names *should* conflict an open form).
- `BEGIN IMMEDIATE` makes a second saver wait up to `busy_timeout` and then proceed — it
  then sees the new state and conflicts correctly. Do not add retries.
- Validation errors are raised **inside** the `with transaction`; that is intended (rollback
  of nothing).
- `edit_entity` still has its own validation-before-transaction ordering; because the
  caller's transaction is already open, its internal `with transaction` is just a savepoint
  and the gap is closed. You do not need to restructure `edit_entity`.
- The browser sees exactly the same JSON as before (Part 2.4). If a JSON key or status
  changes, you went too far.

### Done when
- [x] `core/versions.py` used by all three. · [x] The three saves run in one transaction
      with the check inside. · [x] One "nobody can commit in between" test per path, each
      mutation-checked. *(Plus structure and create rollback tests; 6 mutations, exact failure
      sets — Progress log.)* · [x] Partial-save wording and tests updated. *(Owner-approved
      follow-up wrapped the create path too — see Discoveries.)* · [x] 409 bodies unchanged.
      · [x] Close-out.

---

## T5 — Atomic draft commit (original E2, part 2)

**Size L · Risk HIGH · No schema change · Depends on T3 (and benefits from T1, T4).**

### Goal
Applying a draft either lands **all** its ops or **none**, and marking the draft
committed happens in the same transaction.

### Why
Today each op is its own transaction and the "committed" mark is a separate one. A crash
between them leaves ops landed with the draft still "open"; re-committing then fails on
the creates. A mid-way failure leaves a mixture and a "re-stage the remainder" dance.

### Design
In `core/drafts.py`:

```python
def commit(project_path, draft_id):
    ... load the row, the idempotent already_committed path (KEEP, unchanged) ...
    ops = sorted(...)                          # unchanged ordering

    if all(op["op"] == "purge" for op in ops):            # see Gotcha 1
        return _commit_one_by_one(...)                     # the old path, for purge drafts only

    conn = get_db(project_path)
    try:
        try:
            with transaction(conn):
                landed = []
                for op in ops:
                    result = _dispatch(project_path, op, conn=conn)
                    if result.get("error") or result.get("success") is False:
                        raise _OpFailed(op, result)        # aborts the WHOLE transaction
                    landed.append(...)
                _mark_committed(conn, draft_id, landed)    # same transaction
        except _OpFailed as failure:
            return _failure_report(draft, failure)         # nothing landed
    finally:
        conn.close()
    return _success_report(...)
```
- `_OpFailed` is a private exception local to `drafts.py`.
- `_dispatch` gains `conn` and passes it to the write function it calls.
- On failure the draft row is untouched (still open) — exactly the current `draft_kept`
  behaviour, minus the half-written state.
- **Report shape:** keep `success`, `committed`, `failed`, `draft_id`, `draft_kept`,
  `preview_md`, `message`. On failure `committed` is **always `[]`** now, and `message`
  must say plainly: *nothing was changed; change N failed (…); fix it and re-stage — the
  draft is kept.* Delete the "0 of N written, then it stopped / re-stage the remainder"
  wording and any code that only existed to support partial landing.

### Steps
1. Read `commit`, `_dispatch`, `_call`, `_commit_report`, the helper that sorts ops by
   `OP_ORDER`, and `dry_run` completely. Read `tests/test_drafts*.py` to see what is pinned.
2. Thread `conn` through `_dispatch` for create/edit/delete/reorder (T3 made the write
   functions accept it). Keep `_call` (it turns exceptions into `{"error": …}`).
3. Write the atomic path and the purge-only path. Keep **`already_committed`**
   idempotence and the receipt pruning exactly as they are.
4. Update `_failure_report`/message text.
5. Run the draft tests; **classify each failure** (TR-6): tests that pinned *partial
   landing* (a few, in `test_drafts.py`, `test_story_draft_tool.py`,
   `test_draft_dry_run.py`) encode the old behaviour — rewrite them to assert *nothing
   landed*. Anything else failing is a regression: fix the code.
6. **Agent-facing docs:** grep `tasks/task_30/skill/` and `tools/story_draft.py` for
   "partial", "remainder", "stopped", "draft_kept", "resume" and update them. (This was the
   lesson of D2: the skill reference had been teaching a behaviour that no longer existed.)
7. Add an orphan check (`assert_no_orphans`) to the new tests.

### Tests to add (`tests/test_draft_atomic.py`)
- Two creates where the second references the first (character, then a relationship naming
  it) commit together. (This is the DB-3 case; it only passes because of T3.)
- **Nothing lands when op K fails:** a draft whose third op is invalid → `success False`,
  `committed == []`, and `twin_helpers.snapshot` equals the snapshot taken before; the draft
  is still open and listed.
- After a failed commit, fix the draft (re-stage with the same id) and commit: it lands.
- **Crash safety:** make `_mark_committed` raise (monkeypatch); afterwards nothing landed
  *and* the draft is still open — the old code left the ops landed.
- **Idempotence:** commit twice → second result has `already_committed True`, no second write.
- **Purge drafts keep the old path:** commit a purge-only draft with `trashed` items; it
  works and takes a backup (so it was *not* run inside the shared transaction). Mutation:
  force purge drafts through the atomic path → this test fails with `database is locked`.
- `tests/test_purge_approval.py` must pass **unchanged**.
- The web approve route's contract (Part 2.4) is unchanged: add or keep a route test that
  a failed commit returns `status: "failed"` and a succeeded one `"committed"`.

### Gotchas
1. **Purge.** A purge op opens its own connection and a backup connection; inside the
   atomic transaction it would deadlock for 3 s then fail. Route purge-only drafts to the
   per-op path. `validate_ops` already forbids mixing purge with other ops — *rely on that,
   and test it still holds.*
2. **`dry_run`** runs `commit` on a copy in a temp dir. It must keep working untouched; it
   is a good extra test of your code (the copy is a different project path/connection).
3. **Validators inside the transaction** must use `conn` (T3). If a test fails with a
   "not found" for something an earlier op created, a validator is still opening its own
   connection — find it with the `get_db`-patching trick from T3.
4. **Exceptions vs error dicts.** Some write paths return `{"error": …}` instead of
   raising. Treat both as failure. `_call` already converts exceptions to dicts.
5. **Savepoints and partial success of one op.** If a single write function fails after
   writing some rows, its own `with transaction` (a savepoint) rolls that back; the outer
   rollback then discards everything else. You do not need extra cleanup code.
6. **Lock hold time.** The whole draft now holds the write lock. Drafts are small; do not
   add sleeps or network/file work inside the loop.
7. Backups: `story_import`/`create_backup` are not part of a normal draft; do not add one
   here.

### Owner clarification (added after T1)

The T1 finding that `commit()` returns `committed: True` on success but a truthy list on
partial failure is a real inconsistency. In T5, keep the success shape as it is, and make
a failure return `committed == []`. Don't try to unify the two shapes unless the approve
route needs it. The route keys off `failed` and `success`, and the frontend contract
matters more than tidying the key. The trap about asserting only that `committed` is
truthy is worth keeping in T5's tests: assert `success` and the exact `applied` list.

### Done when
- [x] Atomic path + purge path + idempotence kept. · [x] Report shape per Part 2.4; message
      says nothing changed. · [x] Old partial-landing tests rewritten (not deleted) with
      comments. · [x] New tests above, each mutation-checked. · [x] Skill/tool docs updated.
      · [x] `assert_no_orphans` used. · [x] Close-out.

---

## T6 — Draft status, one source of truth (original E3d)

**Size S–M · Risk low · No schema change (see option).**

### Goal
The chat card's status must never disagree with the draft's real status.

### Why
The `drafts` table holds the truth. The chat message holds a *display copy* of the draft
with a `status`. It goes stale when the agent commits through the tool (the card still says
"open"), when a draft is discarded or re-staged, and after a failed approve.

### Design: reconcile at read time
When a conversation is loaded for the UI, **overlay the status from the table** onto each
draft snapshot in its messages; never trust the stored copy for status.

| snapshot says | table row | show |
|---|---|---|
| `open` or `failed` | `open` | keep the snapshot's value (so a "failed" card keeps its error) |
| `open` or `failed` | `committed` | `committed` |
| `open` or `failed` | no row | `discarded` |
| `committed` / `discarded` | anything | keep (terminal; receipts are pruned after 30 days, so a missing row is normal) |

Put the rule in one function in `core/drafts.py` (`reconcile_status(project_path, snapshot)`
or a batch version taking many ids and doing one query), and call it where the chat
conversation is served to the frontend — find it with `grep -rn "drafts" src/story_architect/chat src/story_architect/app/routes/chat.py`.

### Steps
1. Find where snapshots are written (stage, approve, reject) and read (conversation
   load). Note them in Discoveries.
2. Implement the overlay as a pure function over (snapshot, table status) + a thin DB
   lookup, so the table above is unit-testable without a database.
3. Tests: one per row of the table; the agent commits via the tool while the snapshot says
   `open` → UI shows `committed`; discard → `discarded`; a failed approve (T5) keeps
   `failed` with its error.
4. Do **not** change what the approve/reject routes return (Part 2.4).

### Gotchas
- Do one query for all drafts in a conversation, not one per message.
- The frontend only reads `status` and `error`; do not rename them.

### Done when
- [x] Overlay function + six table-row tests. · [x] Conversation load uses it. · [x] No route
      contract change. · [x] Close-out.

---

## T7 — UTC timestamps (original E3c) — **OPTIONAL, do last**

**Size M · Risk low–medium · Needs the owner's yes/no.**

### Should you do it?
Local-time naive timestamps matter only if the machine's timezone or DST changes between
writes, or the vault is shared across timezones. If the owner has not said "do it", **write
"skipped — not needed" in the Progress log and stop.** If they have:

### Goal
All *stored* timestamps are timezone-aware UTC, produced by one helper.

### Step 0 — build the inventory (required before any edit)
```bash
grep -rn --include=*.py -E "datetime\.(now|utcnow)|time\.time\(\)|timezone|\.isoformat\(|strftime" src | grep -v "/web/"
```
Make a table: **file:line · what it stamps · stored? · compared or matched? · who reads it**.
Known to matter: `deleted_at` (written in `delete_entity`; **compared** by `purge_cutoff` in
`core/trash.py`; **matched by equality** in `deleted_together`), draft `created_at` and its
30-day receipt pruning, revision `replaced_at`, backups. The chat store already uses UTC.

### Design
Two moves, in this order (T2b made this simple: one starting point, no mixed
formats in code):

1. **Convert the stored stamps once.** Extend `tasks/task_40/upgrade_live_db.py`
   (the T2b one-off script): every naive stamp in the columns the inventory
   names (`deleted_at`, draft `created_at`, revision `replaced_at`, …) is read
   as local time and rewritten as aware UTC. Same procedure as T2b — backup
   first, dry run on a copy, row counts unchanged — and the safety backup path
   recorded.
2. **One producer**, `core/clock.py`:
```python
def now_iso() -> str:
    """UTC, whole seconds, with an explicit offset: '2026-11-20T09:15:00+00:00'."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def parse(ts: str) -> datetime:
    """Parse a stored stamp. A naive one raises: the conversion already ran,
    so naive input means unconverted data, not a format to tolerate."""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        raise ValueError(f"naive timestamp in the database: {ts!r}")
    return dt
```
Every stored stamp is produced by `now_iso()`; every date arithmetic goes
through `parse`. Python is 3.11+, so `fromisoformat` accepts offsets.

### Rules that keep it safe
- All stamps share one format, so text comparison and `deleted_together`
  equality are exact. Compute `now_iso()` **once per delete**, as the code does
  now, so all rows of one delete carry the same string.
- Run the conversion on the live project before the new producer lands there;
  after it, no code path tolerates a naive stamp — `parse` raises instead.
- The chat store already uses UTC; leave it alone.

### Tests
`now_iso` shape; `parse` of an aware stamp, of garbage, and of a naive stamp
(raises); purge cutoff and receipt pruning on converted stamps; "deleted
together" still groups. The conversion itself: run the script on a copy and
verify every stamp parses aware and the row counts are unchanged.

### Done when
- [x] Inventory table in the commit message. · [x] **Conversion run on the live
      project — DONE 2026-11-22: 6 `drafts.created_at` stamps converted
      (report first, then `--apply`), safety backup
      `projects/browser-verification-test/.story/pre-t7-utc-20261122_234933.db`;
      row counts unchanged, zero orphans, integrity ok.** · [x] then one producer
      helper for all stored stamps. · [x] No naive-tolerance path anywhere. ·
      [x] Close-out.

---

# Part 5 — Troubleshooting

| Symptom | Almost certainly |
|---|---|
| `database is locked` after 3 s | A second *writer* connection while an outer transaction is open (DB-3). Find the function that still calls `get_db` inside the transaction. |
| A validator says "X not found" for something an earlier step in the same transaction created | That validator opens its own connection (cannot see uncommitted rows). Thread `conn` through it. |
| `cannot start a transaction within a transaction` | Someone typed `BEGIN` by hand. Use `with transaction(conn)`. |
| `no such table: live_relations` / missing index | A bare `sqlite3.connect` in app code (DB-1) or a migration that did not run. |
| Passes alone, fails in the full suite | Shared state: a module-level cache, or a monkeypatch not undone. Use `monkeypatch` (auto-undo), not manual assignment. |
| A test of yours passes with *and* without the fix | It tests nothing (TR-2). Rewrite it. |
| An old test now fails | TR-6: encodes old behaviour or caught a regression. Decide, and say which in your commit. |
| `git diff --stat` shows a file you did not mean to change | A mutation run was interrupted. `git checkout -- <file>` after confirming it is only the mutation. |

---

# Part 6 — Progress log and discoveries (the agent fills this in)

Baseline at start: `1602 passed, 1 failed` (expected `1602 passed, 1 failed`).

| Task | Status | Commit | Tests after | Notes |
|---|---|---|---|---|
| T1 orphan checker | done | `e-t1-orphan-checker` (branch tip) | 1622 passed, 1 failed | +20 tests, 8 mutations verified; FTS check needs `rank=1`; source-scan exemption owner-approved |
| T2 indexes | done | `e-t2-indexes` (branch tip) | 1629 passed, 1 failed | +7 tests, 5 mutations verified; owner-approved legacy-shape edits in 3 test files (Discoveries) |
| T2b baseline (drop legacy support) | done | `e-t2b-baseline` (branch tip) | 1619 passed, 1 failed | −10 net: legacy-only tests deleted, mechanism tests added; 8 mutations verified; live DB upgraded 0→5; code diff 342 insertions / 612 deletions (Discoveries) |
| T3 connection plumbing | done | `e-t3-connection-plumbing` (branch tip) | 1625 passed, 1 failed | +6 tests (uncommitted-row visibility ×3 parametrized, hidden-connection, ownership, rollback); 6 mutations verified (M1→[location], M2→[plot], M3→[value-turns], M4→all 6, M5→rollback+ownership+hidden, M6→5); 4 stub signatures updated owner-approved; `plan`/`delete_form_entity` added to the worklist (Discoveries) |
| T4 atomic version checks | done | `e-t4-atomic-version-checks` (branch tip) | 1630 passed, 1 failed | +5 tests (3 race guarantees, structure rollback, create rollback); 1 partial-landing test rewritten (TR-6a); 6 mutations verified (M1→[form-race, beats], M2→[structure-race, structure-rollback], M3→[script-race], M4→[structure-rollback], M5→[beats, create], M6→[create]); owner-approved follow-up wrapped the create path too, deleting `saved_scene` (Discoveries) |
| T5 atomic draft commit | done | `e-t5-atomic-draft-commit` (branch tip) | 1650 passed, 1 failed | +20 tests (`test_draft_atomic.py`); 4 partial-landing tests rewritten (TR-6a); 11 mutations verified (M1→15 tests, M2→9, M3→crash test, M4→11, M4b→success-False, M5→4 incl. `database is locked`, M6→2, M7→2, M8→2, M9→crash test, M10→purge test); purge-only drafts keep the per-op path; non-op failures also returned as reports (Discoveries) |
| T6 draft status | done | `e-t6-draft-status` (branch tip) | 1675 passed, 1 failed | +25 tests (`test_draft_status_overlay.py`: 12 rule cases, 8 against a real DB, 4 through the routes); 9 mutations verified (a→6, b→4, c→2, d→3, e→query-count, f→query-count, g→input-not-mutated, h→2, i→2); no route contract change; no schema change |
| T7 UTC (optional) | done | `e-t7-utc-timestamps` (branch tip) | 1720 passed, 1 failed | +45 tests (`test_utc_stamps.py` 21, `test_utc_conversion.py` 24); 27 mutations verified (C1–C13 clock/producers, S1–S14 script; two survived at first — S8, S14 — and were fixed by strengthening tests); no existing test needed a change; conversion run on the live project 2026-11-22 (6 stamps, backup `pre-t7-utc-20261122_234933.db`) |

**Discoveries** (anything surprising, any bug you saw but did not fix, any place the code
contradicted this file):

- **T1: the FTS snippet in this file is inert as written.** For an external-content
  FTS5 table, `INSERT INTO sections_fts(sections_fts) VALUES('integrity-check')` only
  checks the index's internal structure; the comparison against `sections` happens
  only with `rank=1` (sqlite.org/fts5.html §6.7). Probed all three desync classes
  (missing index entry, stale entry, token mismatch): the bare form reads clean on
  all three, `rank=1` raises on all three. The checker uses
  `INSERT INTO sections_fts(sections_fts, rank) VALUES('integrity-check', 1)`;
  mutation M5 pins it. Not flaky — kept. Version history (checked against the
  SQLite source, not memory): the rank opt-in arrived in **3.34.0** (check-in
  `7548ab20e6`, 2020-09-21), not 3.44 — 3.44.0 is when PRAGMA integrity_check
  gained `xIntegrity`. Before 3.34 the rank value is ignored and the check
  ALWAYS compares content, so the rank=1 statement is safe on older SQLite too
  (no false `fts` report possible); no version gate needed.
- **T1: DB-4's source scan contradicted T1's design.** `test_live_relations.py::
  test_every_read_of_relations_goes_through_the_view` whitelisted only `core/db.py`
  for raw `FROM relations` reads, which the checker's design requires. Reading via
  `live_relations` would miss a dangling reference whose other end is in the trash
  (the view hides that row). Owner approved a named exemption: the whitelist now
  includes `core/integrity.py` (2 reads) with the reason in the docstring; the guard
  is unchanged for every other file.
- **T1: the checker is deliberately outside the hiding layer and the twin battery.**
  `find_orphans` is an oracle over the raw tables, not a data reader: it must see
  flagged-deleted rows as existing. It is not added to `everything_a_reader_can_say`
  (DB-4's reader rule targets readers that hide references).
- **T1: a partial draft landing reads as success.** `drafts.commit` returns
  `committed: True` + `applied: [...]` on success but `committed: [landed ops]` +
  `failed: {...}` on a mid-way stop — a truthy-`committed` assert passes on both.
  The draft scenario first used `status` in a character edit (copied from a
  shape-only op in `test_purge_approval.py`); commit refused it and only the create
  landed. Fixed to a valid field and `assert success and len(applied) == 3`.
  Owner ruling for T5: keep the success shape, failure returns `committed == []`,
  no unification (see T5's owner clarification).
- **T1: no orphans in any scenario.** All ten write scenarios (delete+restore of
  character/scene/plot/location/world, targeted purge, bulk purge `older_than_days=0`,
  create-edit-delete, draft commit, full re-import) leave the database clean.
- **T2: "SCHEMA_SQL only runs on fresh databases" is false.** `create_schema`
  executes it unconditionally, also over pre-existing tables, and three
  existing tests pinned a legacy `entities` with only `(id, type, name)`:
  that shape cannot carry the new indexes (probed: `create_schema` raises
  `no such column: is_deleted`; `_m5` raises `no such column: parent_id`).
  Owner ruling: keep the briefed layout (four statements in SCHEMA_SQL +
  table-exists-guarded `_m5`) and give the legacy fixtures the full
  pre-soft-delete column set — the shape `test_soft_delete.py` already used.
  Edited: `test_schema_migrations._legacy_project`, `test_live_relations`
  (two sites), and `test_legacy_db_migration` (a third site of the same
  shape, found by grep — same approved class). No assertion loosened; `_m5`
  keeps the briefed table guard, no column guard.
- **T2: the type index barely helps when the queried type dominates the
  table.** On the synthetic 5000-entity / 15000-relation DB (300 runs each,
  before → after): relations by to_id 121.6 → 1.6 ms; parent_id 39.8 →
  1.6 ms; deleted-id set 37.4 → 3.2 ms; `type='scene'` (half the rows)
  166.3 → 148.4 ms, while the selective `type='plot'` went 44.3 → 6.8 ms.
  The owner note on the partial index held: the plan test uses the literal
  `is_deleted=1` and the plan names `idx_entities_deleted`.
- **T2b: live database upgraded once, 0 → 5.** `tasks/task_40/upgrade_live_db.py`
  run on the live project (`browser-verification-test`) with `--apply`: safety
  backup `.story/pre-t2b-upgrade-20261121_132138.db` (kept until Phase E ends);
  rows with `is_deleted=1, deleted_at NULL` got one shared stamp; counts
  unchanged (entities 42, relations 23, sections 244, revisions 0, drafts 6);
  `find_orphans` empty, `integrity_check ok`; dashboard loads clean.
- **T2b: pre-baseline snapshots deleted with owner approval.** The live `.story/`
  held seven old snapshots (`story_20261020_*.db`, `story_20261113_*.db`), all at
  version 0 and unopenable by this build; the owner approved deletion and they
  are gone (first recorded as eight — a miscount, corrected). The safety backup
  above is version 0 by design — it is the pre-upgrade original, kept until
  Phase E ends.
- **T2b: the fixture premise held for committed content only.**
  `tests/fixtures/save-the-children/.story/` had two UNTRACKED local artifacts
  from Oct 27 (`story.db` at version 0 plus one old snapshot) left by a
  pre-versioning test run; the baseline refusal turned them into 700+ fixture
  errors. Removed — every test builds its DB by importing the Markdown;
  `memory.md` is the only committed `.story` file.
- **T2b: regression caught and fixed — get_db's new-file path.** The first
  baseline rewrite dropped `get_db`'s create-schema-on-a-file-with-no-tables
  branch; `test_transaction` (opens a scratch dir twice) caught it. Restored
  per the side-task's "keep that path".
- **T2b: test-only migrations need an explicit stamp.** `create_schema` stamps
  `LATEST_VERSION` at call time, so a project built under a patched LATEST is
  current, not one behind: the one-behind tests stamp `BASELINE_VERSION`
  explicitly after building. Fixture order matters too — `twin.build` opens the
  DB during import, so a patch applied before the build runs the step early
  (the reader-loop test undoes that upgrade before calling the reader).
- **T2b: two mutation checks initially named the wrong tests.** The
  `purge_eligible` flag is computed in `story_admin` (`r[3] <= cutoff`), not in
  `trash.select_for_purge` — the age-floor mutation is caught by
  `test_story_admin.TestPurge`; the stamp-grouping mutation by
  `test_list_deleted`'s own-entry test, not by restore/purge behaviour. All 8
  mutations verified caught with the right tests.
- **T2b close-out audit: T3–T7 checked for the legacy trap.** T3–T6 carry no
  legacy-tolerance instructions (T5's purge-only "old path" is current
  behaviour, not legacy support). T7 did — "tolerate both formats forever",
  naive-stamp parsing, mixed-format tests — and was rewritten: the one-off
  script converts stored stamps once, `clock.parse` raises on naive input, no
  mixed-format code path. T2's historical section stays under its superseded
  banner.
- **T3: four test stubs pinned the old write signatures (owner-approved edit,
  2026-11-21).** `test_manual_entities.py:221` and
  `test_manual_scene_editors.py:200/211/266` monkeypatch `writes.edit_entity` /
  `writes.create_entity` with fixed-arity lambdas; the uniform `conn=conn`
  threading broke them with `TypeError: unexpected keyword argument 'conn'` —
  a signature pin, not a behaviour assertion. Owner chose updating the four
  stub signatures (accept + forward `conn=None`) over conditional `**kwargs`
  at the call sites (a compatibility shim the repo rules forbid). Every
  assertion is untouched; the full suite confirms no behaviour change.
- **T3: the worklist missed two functions on the call chains.**
  `manual_structure.apply` calls `plan`, and `manual_entities.delete_form_entity`
  calls `delete_preview` + `delete_entity`; both now take `conn=None` too
  (the gotcha "add it and note it in Discoveries" clause).
- **T3: the briefed relationship example cannot fail pre-plumbing.** Creating
  a relationship does not validate its character references at all — a
  relationship naming two nonexistent characters was created both before and
  after the plumbing (that gap is DB-2 / T4's, untouched here). The
  visibility test therefore uses three scenarios whose validators DO read
  references: scene→location, plot→character, scene value-turn→value entity.
  Pre-plumbing probes: the location and plot creates were REFUSED
  ("Location not found: newloc", "Character not found: newchar"); post-plumbing
  on one connection both succeed.
- **T3: multi-block functions keep the parameter intact.** Where a function
  reads on its own connection in an early block and writes later
  (`create_form_entity`, `edit_form_entity`, `_write_sheet`,
  `save_scene_script`, `apply`), the read block uses a block-local connection
  (`block_conn`) so the original `conn` argument — None or the caller's —
  flows unchanged into the downstream write calls. Reassigning and closing
  the parameter would hand a CLOSED connection to the next callee.
- **T3: mutation runs need `PYTHONDONTWRITEBYTECODE=1`.** A same-length source
  mutation written within the same mtime second as the previous restore
  reuses the stale `.pyc`: M2's first run actually executed M1's bytecode and
  reported M1's failures. With bytecode writing disabled all six mutations
  attributed correctly (worktree at HEAD + plumbed sources, restored after
  each run; worktree removed afterwards).
- **T4: the token values did not change.** Entity and script tokens already
  used `token`'s exact serialization; the structure token moved from
  `json.dumps(flat)` to `sort_keys=True, ensure_ascii=False`, which is
  byte-identical for lists of ASCII slugs. Grep confirmed no test pins a token
  value or length — they pin equality/inequality and conflict behaviour.
- **T4 follow-up (owner-approved): `create_form_entity` is now one transaction
  too.** Asked whether a hidden reason kept it create-then-beats; a probe on a
  throwaway project found none: (A) crash after create inside an outer
  transaction rolls scene+beats back; (B) a beats refusal rolls the scene back;
  (C) the one real hazard — `create_schema`'s `executescript` silently commits
  a pending transaction — is unreachable, because `get_db` already creates the
  schema on a table-less file, so `has_schema` is always True inside
  `create_entity`; (D) the success path commits normally. `value_focus` (the
  one own-connection reader left in the final load) is read-only, and its
  stale-snapshot read is vacuous on creates: a new plot/act/sequence cannot
  have value turns yet, and `project` cannot be created from the form. The
  wrap deleted the `saved_scene` parameter and the last partial-save message:
  `_write_sheet` now always says "Nothing was saved: …". One new test
  (`test_create_failure_lands_nothing`), mutation M6 verified; the wording
  mutation M5 now covers both beats tests.
- **T4: one partial-landing test rewritten, not deleted (TR-6a).**
  `test_manual_scene_editors.py::test_scene_saved_but_beats_failed_says_which`
  pinned the old behaviour twice — the partial message AND the scene edit
  surviving the beats failure (`one_sentence == "Saved."`). T4 step 5 directs
  updating these tests. It is now `test_beats_failure_saves_nothing`: message
  says nothing was saved, the scene edit is rolled back, no beats record
  exists, and the version token is unchanged.
- **T4: the fixture has one act and one sequence.** A pure within-sequence
  reorder only calls `reorder`, so the structure race test creates a second
  sequence and moves a scene ACROSS sequences — that move goes through
  `edit_entity`, the same seam the other two race tests watch. The structure
  rollback test moves two scenes and fails the second `edit_entity` call: the
  first move must not survive it.
- **T4: `edit_entity`'s validation-before-transaction order was left alone**,
  as briefed: with the caller's transaction already open its internal
  `with transaction` is a savepoint, so the read-then-write gap is closed
  without restructuring it.

- **T5: a draft now lands all ops or none, with the mark in the same transaction.**
  `commit` runs every op and `_mark_committed` on one connection in one
  `transaction`; `_dispatch` hands each write function `conn`. A refusal is
  `result.get("error") or result.get("success") is False` (raised errors reach
  that check through `_call`). `_OpFailed` is private to `drafts.py`. The
  `already_committed` replay and the receipt pruning are unchanged (pruning moved
  verbatim into `_mark_committed`). `dry_run`, `validate_ops`, the approve route
  and `test_purge_approval.py` needed no change.
- **T5: a failure that is not an op's fault is also returned, not raised.** The
  brief caught only `_OpFailed`. A lock that cannot be taken within 3 s, a failed
  COMMIT, or a failed mark would have escaped `commit` as a raw exception (a 500
  from the approve route); the old per-op code turned those into a failure report
  through `_call`. A second `except Exception` returns the same report shape
  (`failed.op == "save the draft"`, message "Nothing was changed … commit it
  again"). Mutation M9 pins it.
- **T5: a multi-purge draft can still partly land — the one place `committed`
  is not always `[]`.** `validate_ops` forbids mixing a purge with other ops but
  allows several purges. Each purge is its own transaction (it takes a backup)
  and cannot be undone, so if purge 2 fails purge 1 stays done. For that case
  only, `committed` lists what was purged and the message says so (tested:
  `test_a_draft_with_several_purges_says_truthfully_what_was_done`). Not changed
  here: `story_admin` stages exactly one purge. **Recommendation:** a later task
  limits a purge draft to one op; `_commit_purges`'s landed-list branch and the
  "Partly done" report then disappear.
- **T5: four old tests pinned partial landing — all class (a), none a regression.**
  `test_drafts.py` ×2 (`..._names_what_landed` → `..._lands_nothing`;
  `..._refuses_the_op_that_already_landed` → `..._fails_the_same_way_again`),
  `test_story_draft_tool.py` ×1, `test_draft_preview.py` ×1 ("Partly saved" →
  "Not saved … Nothing was changed"). `test_draft_dry_run.py` needed none.
- **T5: the briefed relationship example does not discriminate** (same finding as
  T3): a relationship's characters are not validated, so it passes with or without
  the shared connection. It is kept as briefed; location→scene and character→plot
  are the pairs that fail when `conn` is not passed (M1).
- **T5: the skill reference was teaching the old behaviour.**
  `staging-changes.md` had a section "A failed commit may have partly landed"
  (resume by re-staging the remainder). Rewritten as "A commit lands everything or
  nothing". `tools/story_draft.py` gained "all of it or none of it" in the commit
  description. Not changed, flagged: `craft/scene-design.md` still says to "create
  the location and commit it first" — now unnecessary within one draft, but
  over-cautious rather than false.
- **T5: residual race, not a regression.** `commit` reads the draft's status
  before opening the transaction. Two commits of the same open draft at nearly the
  same moment (web approve + agent tool) can both pass that check; the second then
  fails on "already exists" for a draft that actually landed. Re-checking status
  inside the transaction would close it. Left alone per scope.
- **T5: mutation runs.** M1 (`conn` dropped) and M5 (purge through the atomic
  path) make every failing test wait out the 3 s lock timeout; run them one per
  call under `timeout`. A run killed mid-mutation can leave a mutated source file:
  keep a known-good copy and `cmp` after every run.
- **T6: where snapshots live.** Written: created with status `open` in
  `app/mcp_server.py` (on a clean dry run), carried by `DraftEvent` and stored on
  the chat message's `drafts` column by `chat/service.py`; rewritten by the approve
  and reject routes in `app/routes/drafts.py` (`committed`, `failed` + `error`,
  `discarded`). Read: `chat/store.get_conversation`, whose callers are the UI route
  `routes/chat.py::get_conv`, the approve/reject routes (which REWRITE cards), the
  retry route and `chat/service.py`.
- **T6: the overlay is at serve time in the route, not in the store.** Putting it in
  `get_conversation` would have leaked display values into the approve/reject
  rewrite path. `reconcile_snapshots` returns copies and never writes; a test pins
  that the stored card is still `open` after the conversation is served.
- **T6: the rule is `drafts.reconcile_status` (pure); `reconcile_snapshots` is the
  thin lookup.** One `SELECT … WHERE id IN (…)` for all cards, none when no card is
  `open`/`failed`. Only `status` is replaced; `error` and everything else survive.
  Two cards of one id (a re-stage can leave two) each follow their own snapshot.
  A status the rule does not know, and an unknown table value, are left as they are.
- **T6: known limit of the briefed table — a stale `open` card plus a pruned
  receipt reads `discarded`.** If the agent commits through the tool and the
  conversation is not loaded again until after `RECEIPT_DAYS` (30), the row is gone
  and the card cannot be told from a discarded one. The table has no better answer;
  an approve through the UI writes `committed` into the card and is unaffected.
- **T6: status only.** A re-staged draft keeps its id, so an older card for it can
  show stale `changes`/`summary`; T6 corrects status, as briefed, not content.
- **T6: not fixed, seen in passing.** `app/mcp_server.py` writes
  `/tmp/draft_debug.txt` on every staged draft (a leftover debug line).
- **T7: how to run the conversion (owner step, do this BEFORE starting the app on
  the new code).** Stop the app and any agent. Then, with the project venv:
  `python tasks/task_40/upgrade_live_db.py <ROOT> --all --tz <your zone>` (report:
  changes nothing, prints the zone it assumed and sample conversions), check the
  samples, then the same line with `--apply`. `--all` covers every project under
  `<ROOT>/projects/`, every trashed project, and every `.story-trash/*/deleted.json`;
  it reports on everything first and writes nothing unless all of it is readable.
  For a single project: `<PROJECT_DIR>` without `--all`. Each database gets a safety
  backup `.story/pre-t7-utc-<time>.db` (the path is printed — record it here);
  keep it until you are sure. `--tz` is the zone the machine was in when the
  stamps were written (default: the machine's own zone, with summer time applied
  per date). Safe to run twice. If the new code runs first, nothing breaks loudly —
  stamps are compared as text, so old naive ones are simply off by the zone offset
  (hours) in the 30-day windows — but then run the conversion anyway.
  **RUN 2026-11-22:** root `/mnt/AI/TWW/hermes-story-architect`, `--tz Europe/Rome`,
  1 project DB, 0 trash records. Report first (nothing changed), then `--apply`:
  6 `drafts.created_at` stamps converted (all winter, UTC+1); `entities.deleted_at`
  and `revisions.replaced_at` were empty. Row counts unchanged (42/23/244/0/6),
  zero orphans, integrity ok. Safety backup kept at
  `projects/browser-verification-test/.story/pre-t7-utc-20261122_234933.db`.
- **T7: inventory (Step 0).** Stored = written to a database/file and read back.

  | file · what | stored? | compared / matched? | read by | now |
  |---|---|---|---|---|
  | `core/writes.py` `delete_entity` · `deleted_at` (parent + children, one string) | DB | `<=` cutoff (text); `=` in `deleted_together` | trash list, purge, restore | `clock.now_iso()` |
  | `core/revisions.py` · `replaced_at` | DB | no | revision list/get/restore (display) | `clock.now_iso()` |
  | `core/drafts.py` `stage` · `created_at` | DB | `<` cutoff in receipt pruning | `list_drafts`, approve card | `clock.now_iso()` |
  | `core/drafts.py` `_mark_committed` · the 30-day cutoff | — | against `created_at` (text) | — | `clock.ago_iso()` |
  | `core/trash.py` `purge_cutoff` · the age-floor cutoff | — | against `deleted_at` (text) | purge, preview, list | `clock.ago_iso()` |
  | `tools/story_admin.py` `delete_project` · `deleted.json` `deleted_at` | file | sorted as text, newest first | list/restore trashed projects | `clock.now_iso("microseconds")` (full precision kept on purpose) |
  | `app/mcp_server.py` · the chat card's `created_at` | chat DB (JSON) | no | UI (not displayed) | `clock.now_iso()` |
  | `chat/store.py` · conversation/message stamps | chat DB | ordering | UI | already UTC; untouched |
  | `core/backups.py` · backup `created_at` (read from the FILE NAME), periodic-backup interval | name | `now - taken` (both local) | backup list, periodic backup | **unchanged** (below) |
  | `core/db.py`, `core/drafts.py` (draft id), `tools/story_admin.py` (trash folder) · `strftime` labels | names | no | people | **unchanged** (below) |
  | `app/server.py`, `adapters/hermes/gateway.py` · `time.time()` | no | heartbeat / timeouts | — | not a stored stamp |

- **T7: backup file names stay local time (decision; veto if you disagree).** The
  brief lists backups as "known to matter", but their time is in the FILE NAME
  (`story_20261120_091500.db`), not a database column. Switching new names to UTC
  would put two zones in one folder, and `list_backups` sorts and prunes by that
  time: a new backup taken at UTC (1–2 hours behind Rome) could sort as OLDER than
  one taken just before it, so pruning could keep the wrong ones. The only risk
  left is the 24-hour periodic-backup interval being an hour off across a DST
  change, which is harmless. `LOCAL_TIME_ALLOWED` in `test_utc_stamps.py` records
  each such exemption and its reason, and a test fails if one stops being needed.
- **T7: the brief's helper was extended in three small ways.** `now_iso(timespec=)`
  because the project-trash stamp is full precision on purpose ("two deletes in one
  second must still sort newest-first") and must be fixed width; `ago_iso(days)`
  because the purge cutoff and the receipt cutoff are stamps compared as text and
  were two hand-written copies of the same arithmetic; `STORED_STAMPS`, the one list
  of stamp columns, walked by the conversion and guarded by a test that fails if the
  schema gains a `*_at` column that is not listed.
- **T7: `clock.parse` has no production caller.** Nothing in the app parses a stored
  stamp — every comparison is text, which is exactly why one format matters. So
  "naive means unconverted data" is enforced where parsing happens: by the conversion
  script's own post-check, and by tests. A naive stamp that appeared in a database
  later would not raise at runtime; it would compare as text, hours off. Cheap
  hardening if wanted: run the script's report mode (it fails on any non-aware stamp)
  from time to time, or add a "naive stamps" category to `find_orphans`.
- **T7: the conversion is wider than the brief's one project.** The brief says
  `deleted_at`, draft `created_at`, `revisions.replaced_at` of the live project. A
  trashed project's database comes back with naive stamps when restored, other
  projects under `projects/` have their own, and `deleted.json` records are stored
  stamps outside any database; the script covers all of them with `--all`. T2b's
  version of this script wrote its data fix as naive local time; it now stamps with
  `clock.now_iso()`, and conversion + verification are one transaction (T2b's
  version was not).
- **T7: existing test fixtures still hand-write naive stamps** (`'2020-01-01T00:00:00'`
  in about a dozen places in `test_purge_one`, `test_list_deleted`, `test_delete_stamps`,
  `test_purge_approval`, `test_story_admin`, `test_write_atomicity`, `test_backups`).
  They still pass, because the code compares as text and the stamps are far from the
  cutoff, and rule 0.5 says not to edit tests that do not need it. They describe data
  that can no longer exist. Recommendation: leave them.
- **T7: known leftover.** Chat cards already stored in the chat database keep their old
  naive `created_at` in the JSON display copy. Nothing parses or displays it.
- **Post-T7: the live project was in the wrong root, and T2b had made it unopenable.**
  The app and the agent tools both resolve the root independently (`--root` /
  `STORY_ARCHITECT_ROOT` / `~/.config/story-architect/config.toml` / `DEFAULT_ROOT`
  for the app; `resolve_root` → `load_plugin_config()` for the tools, which returns
  `{}`, so also `DEFAULT_ROOT`). Neither reads the other's config, and the desktop
  launcher passes no `--root` — so both silently serve `~/story-architect`, whose
  only project is the seeded `demo`. That `demo` is the **newer** copy (49 entities,
  299 sections, drafts to 2026-11-15); the `browser-verification-test` under
  `/media/theww/AI/TWW/hermes-story-architect` is a strict subset of it (42/244,
  drafts to 2026-10-20) and is not the working project. It stopped opening because
  T2b raised the baseline to 5 and `demo` is at 4 — T2b's premise ("there is one
  database that matters") was false. The baseline went to 4 with the frozen 4→5
  index step reinstated so `demo` opened, then **went back to 5** once `demo` was
  the only database and had been converted: the app has not shipped, so the
  baseline is the only schema there is and no legacy step is carried. The
  migrate-on-open machinery stays for the first real schema change. **`demo`
  holds naive stamps** (26 `drafts.created_at`, 6 `entities.deleted_at`); the
  conversion was run on it (2026-11-23, `--tz Europe/Rome`, 32 stamps, backup
  `pre-t7-utc-20261123_004452.db`), and the stale media-root copy was then deleted
  (tarball in `~/story-architect/.trash-backup/`). `demo` is now the only project
  on disk.

---

# Appendix A — The database ideas you need, in plain words

- **WAL mode.** Readers and one writer can work at the same time. A reader sees a
  *snapshot*: the data as it was when its read began. It never sees another connection's
  uncommitted changes.
- **Write lock.** Only one connection can write at a time. `BEGIN IMMEDIATE` takes the lock
  at the start of a transaction; a second writer waits up to `busy_timeout` (3 s here), then
  raises `database is locked`.
- **Autocommit.** `get_db` connections are in autocommit mode: each statement outside a
  `transaction` block commits by itself. So "two writes in a row" are *two* transactions
  unless you wrap them.
- **SAVEPOINT.** A nested "mini-transaction". `transaction()` uses one when you are already
  inside a transaction, so inner code can roll back its own part while the outer one
  decides the final outcome.
- **Why one connection per transaction.** Savepoints and the write lock belong to a
  *connection*. Work done through a different connection is a different transaction, with
  its own snapshot — which is the whole reason for T3.
- **View.** A saved query that looks like a table (`live_relations`). **Index.** A
  lookup structure that makes `WHERE` on those columns fast.

# Appendix B — If the owner insists on the alternatives

**A `rev` column instead of content tokens.** Needs: a migration adding `rev INTEGER NOT
NULL DEFAULT 0` to `entities`; `AFTER UPDATE` triggers on `entities` (when `OLD.rev =
NEW.rev`, with recursive triggers left **off**) and `AFTER INSERT/UPDATE/DELETE` triggers on
`sections` and `relations` that bump the owning entity — triggers, not application code,
because *a single writer that forgets to bump causes silent lost updates*, the same class of
mistake D1 had; a decision per relation kind about which side's form shows it (else false
conflicts); a separate project-level counter for the structure tree, bumped only by changes
to `order_key`, `parent_id`, `is_deleted` or inserts of act/sequence/scene rows; and a plan
for no-op writes (they would bump). T4's atomic check is still required, so do T4 first.

**Real foreign keys.** `get_db` already sets `foreign_keys=ON`, so declared FKs are enforced
on every connection at once. A safe migration: take a backup; for `sections`, `revisions`
and `relations` create `*_new` with `REFERENCES entities(id) ON DELETE CASCADE`, copy rows,
drop, rename; **recreate** the three `sections_fts` triggers and rebuild the index
(`INSERT INTO sections_fts(sections_fts) VALUES('rebuild')`); **drop and recreate
`live_relations`** around any rename; run `PRAGMA foreign_key_check` and refuse to migrate if
it reports rows (real databases may hold dangling relations the fixture does not); then
simplify `hard_delete`. Because soft delete flags rows instead of deleting them, cascades
only ever fire on purge — so the gain is small. T1's checker gives most of the benefit.
