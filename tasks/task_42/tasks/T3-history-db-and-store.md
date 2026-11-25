# T3 — `history.db` and `store.py`

Spec: `../spec-draft-versioning.md` §4.1–4.5, §7.9, §13 T3, §2 non-goals.
Branch: `draft-versioning`.
Baseline: `1774 passed, 1 failed` on this branch before starting (the known
`test_no_hermes_imports`; same count T2 recorded).

## Objective

The manifest and the operations that keep it true. After T3 a project can save
the current state as a frozen snapshot, branch from any snapshot, switch between
branches, rename and delete branches, and delete snapshots — each leaving
`story.db`, `history.db` and the files on disk in a state the next reader can
trust. Existing projects adopt themselves on first touch; nothing to migrate.

Out of scope (later tasks): `ProjectView`, reading a snapshot as a project
(T4); diff (T6); merge sessions (T8/T9); HTTP (T10); agent tools (T11).

## Verified before starting

| Claim | Evidence |
|---|---|
| Suite is green on this branch | `.venv/bin/python -m pytest -q` → `1774 passed, 1 failed`, the known `test_no_hermes_imports` |
| `backup_database` already gives a WAL-safe copy under a `.partial` name, renamed on success | `core/db.py:312` — `Connection.backup()`, `mkstemp`, `os.replace` |
| A backup written by it comes out as ONE file: no `-wal`/`-shm` left beside it | probe: after `backup_database` + `DELETE FROM drafts` + `VACUUM`, the snapshot dir held only `snap_*.db`, and an `immutable=1` read created nothing |
| The live DB's page size is 4096 and a copy keeps it, so the loader's page-size refusal cannot fire on a switch | probe: live `(4096, 'delete')`, copy `(4096, 'delete')` |
| `load_database_in_place` does not validate its source | `core/backups.py:159` — source checks live in `restore_backup` only (recorded in T2's Notes entry) |
| `load_database_in_place` **always** takes an automatic backup | `core/backups.py:202`; `create_backup(label=None)` still writes the file |
| Every automatic backup shares one 20-slot cap, label or not | `core/backups.py:144` `prune_automatic_backups` filters on `kind`, never on `label` |
| The two "restored in place" strings are pinned only by `match="page size"` | `tests/test_backups.py:314,413` — **Notes.md is wrong** that two assertions pin the rest of the wording |
| Open staged drafts are `status='open'` rows in `story.db` | `core/drafts.py:328`; `commit` flips to `'committed'` at `:586` |
| No fixture entity stores a computed field or a relation-backed field in its own `extra` | probe over all 26 fixture entities, per type against `ENTITY_SCHEMAS[type]` — zero on both counts |
| `versions.token` is the repo's one "canonical payload → short sha256" function | `core/versions.py:15`; its docstring says the caller decides *what* to hash |
| `FROM live_relations` does **not** count as a raw `relations` read | the registry's pattern is `(?<!DELETE )\b(?:FROM\|JOIN)\s+relations\b`; `_` is a word char, so `live_relations` never matches — the fingerprint can read the view freely (`tests/test_live_relations.py:328`) |
| A new file may not call `datetime.now`/`.isoformat` | `tests/test_utc_stamps.py:283` scans every `src/**/*.py`; a file that does must be added to `LOCAL_TIME_ALLOWED` with a reason |
| One process writes `story.db`: the server (`uvicorn.run` single-process, `app/launcher.py:122`); every other `sqlite3.connect` in `src/` is a short read or the same process | grep over `src/` — `services.py`, `story_resolve.py`, `value_focus.py`, `db.py:1139` are reads |
| A partial unique index can hold "exactly one current branch" | SQLite supports `CREATE UNIQUE INDEX ... WHERE`; the schema already uses one (`idx_entities_deleted`) |

## Decisions taken

- **§14-I settled: no non-app writer.** The server runs one process and every
  other connection in `src/` is a read. The switch's in-place copy is therefore
  as safe as `restore_backup` already is, and the history lock is what serialises
  two operations in that one process.
- **The switch parks, it does not also back up (owner decision).** §4.3 asks for
  a safety backup *and* a park. The park is byte-for-byte the pre-switch state
  and is addressable by branch name, while a `before-switch` automatic backup
  would evict a daily one — the 20-slot cap counts every `automatic` regardless
  of label, and `before-restore` copies already do this. So `switch` passes no
  safety label: the loader grows `safety_label=None` meaning "copy only". Undo is
  switching back, the one operation this feature exists to provide.
- **Snapshots are `chmod 0444`** (§4.3, owner decision). One `os.chmod` at save
  time makes a future write-open fail loudly instead of silently rewriting a
  frozen draft. Deletion is unaffected — the directory grants that.
- **Switch refuses while the head has open drafts** (owner decision). A staged
  draft lives in `story.db` and is deliberately not part of a snapshot (§4.3), so
  switching would destroy it with no record. The refusal names the open draft ids.
  The parked head keeps its drafts, so switching back brings them back; only the
  destructive direction is refused. Carrying them to the target is not an option:
  the ops were validated against the old head's ids and state.
- **Branch ids are slugged from the name and stay fixed across a rename**
  (name is the label, §4.3). `heads/<branch_id>.db` then reads as
  `heads/main.db`, and adoption gives the first branch id `main`.
- **Snapshot ids are `s-<stamp>[-n]`, generated against the manifest** — the
  `new_draft_id` shape (§4.2 names the precedent). The file is named for the id.
- **A `heads/<branch>.db` is removed once that branch becomes current.** It is
  the parked head of a *non-current* branch (§4.1); leaving it behind would let a
  later switch load a stale copy.
- **`baseline_snapshot` is the single delete guard for snapshots.** §4.3 names
  "the branch's open head and a branch's `base_snapshot_id`"; a head is a file,
  never a snapshot row, so the row-level guard is exactly "some branch's
  `base_snapshot_id`".
- **`pending_merge_parents` is written by save.** §7.9 says the next *Save draft*
  turns them into `snapshot_parents` rows. The column is this task's schema and
  save is the only writer of `snapshot_parents`, so the four lines live here;
  nothing sets the column until T8.

## Tasks

- [x] `core/history/__init__.py` + `core/history/store.py`: `history.db` schema
      (§4.2 verbatim), `connect()` following the `chat.db` pattern (own
      `BASELINE`, `MIGRATIONS`, `LATEST`, `apply_migrations`), `busy_timeout`,
      and a partial unique index for "exactly one current branch".
- [x] `core/history/store.py`: paths — `.story/history.db`,
      `.story/history/snapshots/<snapshot_id>.db`, `.story/history/heads/<branch_id>.db`.
- [x] `core/history/fingerprint.py`: `of_project(project_path) -> str` over live
      entities (columns minus `order_key`/`is_deleted`/`deleted_at`, `extra`
      minus computed keys), their sections, live relations, and the per-parent
      child order as id lists; via `versions.token`.
- [x] `core/history/store.py`: `_adopt(conn, project_path)` — first touch creates
      branch `main` and snapshot "Draft 1" from the current state.
- [x] `core/history/store.py`: `save_snapshot(project_path, label=None, note=None)`
      — refuse when the head fingerprint equals the base snapshot's; copy to
      `snapshots/<id>.db`, `DELETE FROM drafts`, `VACUUM`, `chmod 0444`; insert
      the snapshot and its parents (base + `pending_merge_parents`, then clear
      it); move `base_snapshot_id`.
- [x] `core/history/store.py`: `branch_from(project_path, snapshot_id, name)` —
      new branch, head parked as a copy of that snapshot.
- [x] `core/history/store.py`: `switch(project_path, branch_id)` — refuse on open
      drafts; park the live DB as `heads/<current>.db`; `load_database_in_place`
      with no safety backup; drop the target's parked head; update `is_current`.
- [x] `core/history/store.py`: `rename_branch`, `delete_branch` (reachability-
      pruned snapshots and files), `delete_snapshot` (re-parent children to the
      snapshot's parents in order, then remove rows and file).
- [x] `core/history/store.py`: `list_branches(project_path)` — branches, snapshots
      with parents, `is_current`, head state for the graph.
- [x] `core/backups.py`: `safety_label=None` copies without taking a backup;
      source validation extracted to `check_source` so a branch's parked head is
      checked by the same rules a backup is; the two strings that still said
      "restored in place" / "after the restore" reworded neutrally.
- [x] `tests/test_history_store.py`: save/branch/switch/rename/delete, adoption,
      fingerprint guard, immutability (mode + unchanged bytes), re-parenting,
      reachability, open-draft refusal, parked-head cleanup, schema-version
      refusal, `.partial` crash safety — **42 tests**.
- [x] `tests/test_utc_stamps.py`: `core/history/store.py` added to
      `LOCAL_TIME_ALLOWED` — a snapshot id's timestamp is an identifier, like a
      draft id's.
- [x] Suite still `1774 passed, 1 failed` plus the new tests; `ruff format` clean.

## Final Brief

**What T3 changes.** The manifest and the operations that keep it true, with no
reading path yet (T4's `ProjectView`) and no UI (T10/T13).

*`core/history/store.py`.* `history.db` holds `branches`, `snapshots`,
`snapshot_parents` and (empty, for T9) `merge_sessions`, shaped exactly as §4.2.
It is its own file with its own baseline and migration list, following `chat.db`:
it cannot live in `story.db`, which is overwritten on every switch. A partial
unique index holds "exactly one branch is current" in the database rather than in
whatever code remembers to keep it true.

Adoption is lazy: the first call that touches history writes down the state it
finds as branch `main` + "Draft 1". A pre-feature project needs no migration
because it already has exactly the state that becomes Draft 1 — there is nothing
to convert.

`save_snapshot` refuses when the live fingerprint equals the base draft's, then
copies through SQLite's backup API under a `.partial` name, drops the staged
proposals (they belong to the head they were made on), vacuums, renames, and
`chmod 0444`s the result. Its parents are the base plus any
`pending_merge_parents` §7.9 left, cleared in the same transaction.

`switch` parks the live database as the outgoing branch's head — that copy IS the
pre-switch state — then copies the target's parked head in through
`load_database_in_place`, and removes the parked file because the head is live
now. `branch_from` parks a copy of the draft it grows from, so a new branch is
switchable immediately. `delete_branch` prunes by **reachability** (walk parents
from every branch's saved draft), not by ownership, which is what keeps a draft a
merge brought into another branch. `delete_snapshot` re-attaches children to the
draft's own parents, keeping their order.

*`core/history/fingerprint.py`.* SHA-256 over live entities (columns minus
`order_key`/`is_deleted`/`deleted_at`, `extra` minus computed fields), their
sections, live relations, and the per-parent child order as id lists. Order is
serialized as the id list, never the key values, so renumbering without
reordering is not a change — the two live siblings that can already share an
`order_key` (F13/T1) would otherwise diff as equal.

*`core/backups.py`.* `load_database_in_place` gains `safety_label=None` (copy,
take no backup) and the source validation is extracted to `check_source`, so a
branch's parked head is checked by the same rules a backup is — the loader
deliberately does not validate, and switch would otherwise ship the gap T2
recorded. The two strings that said "restored in place" / "after the restore" now
speak of a copy; both `tests/test_backups.py` assertions pin only `"page size"`,
so the reword cost no test change (**Notes.md was wrong about this** — corrected
below).

**Verification, as run.**

- `tests/test_history_store.py`, 42 tests: adoption once and only once; the
  fingerprint's five invariants (stable, edit moves it, renumbering does not,
  reordering does, a trashed row's own content does not, delete+restore returns
  to the same hash); save refused when unchanged, freezes the state, is 0444,
  survives later edits, carries no staged proposals, records its parent, takes no
  backup, and leaves no file when the rename fails; branch parks a real database
  and its id survives a rename; switch carries the other head, parks the outgoing
  one and keeps exactly one, claims one current branch, takes no backup, refuses
  on open drafts / already-current / no parked head / a newer schema; delete
  re-parents children, refuses a branch's latest draft, prunes unreachable
  drafts but keeps a merge-linked one, refuses the current branch; the manifest
  is its own file at its own version and the unique index refuses a second
  current branch.
- `tests/test_utc_stamps.py` +1 registry entry, with the reason. Verified by the
  suite: without it, the stamp guard fails naming the new file.
- Full suite: **1816 passed, 1 failed** — baseline 1774 plus 42 new, same single
  known failure (`test_no_hermes_imports`).
- `ruff format --check src tests` clean; `ruff check` clean on every touched file.
- End to end on the fixture: `.story/` ends with `history.db`,
  `history/snapshots/s-*.db` at `0o444`, and exactly one
  `history/heads/<branch>.db` for the branch that is not current — §4.1's layout.

**Deliberate simplifications.**

- **No safety backup on switch** (owner decision, recorded above). One
  `safety_label=None` argument, no new code.
- **`chmod 0444` rather than a write-blocked connection.** One line, and it fails
  the failure mode that matters.
- **Snapshot ids use local time in the name**, like a draft id or a backup file
  name — an identifier, not a stamp. Registered in `LOCAL_TIME_ALLOWED` with that
  reason rather than pretending otherwise.
- **T7's merge session table is created here and left empty.** §4.2 lists it in
  this schema; creating it now costs nothing and T9 would otherwise migrate.

**One finding for T4.** SQLite creates `-wal`/`-shm` *before* it discovers a file
is read-only, so any bug that opens a draft read-write leaves two empty files
beside a frozen draft. `_drop_sidecars` sweeps them on every write, and
`tests/test_history_store.py` pins it. `ProjectView` must copy a draft out rather
than open it, or it will re-create exactly this debris — and a `-wal` beside a
snapshot is what would make a later reader see a stale view of it.

**One finding for T8.** `switch` refuses on any `status='open'` draft. The merge
executor applies its plan inside one transaction on the live database, so it does
not need a switch; but if T8 ever sequences a switch after a merge, it must land
after the commit, not inside it.

