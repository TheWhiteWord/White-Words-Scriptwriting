# T2 — Extract `load_database_in_place`; make `apply_op` public

Spec: `../spec-draft-versioning.md` §4.3 (switch branch), §7.7 (execution order), §13 T2, §14-D.
Branch: `draft-versioning`.
Baseline: `1770 passed, 1 failed` on this branch before starting (the known
`test_no_hermes_imports` failure from T0; T1 took 1744 → 1770).

## Objective

Two seams must exist before anything in `core/history/` can be built, and both
are pure refactors:

1. `restore_backup` copies a validated backup **into the live database in place**
   (SQLite backup API, not a file swap). §4.3's branch switch needs exactly that
   copy with a different source and a different safety label.
2. §7.7's executor cannot use `sorted_ops` — creates before deletes makes
   Replace and Theirs-swap impossible. It needs the per-op dispatcher directly,
   so `_dispatch` becomes `apply_op`.

No behaviour change: `restore_backup` keeps its validation, refusal order and
return shape; `commit` keeps calling the same function under its new name.

## Verified before starting

| Claim | Evidence |
|---|---|
| The in-place copy is 8 lines inside `restore_backup`, interleaved with validation | `core/backups.py`, `restore_backup` |
| Every restore caller goes through `tools/story_backup.py:88`; there is one entry point | grep `restore_backup` over `src` |
| `_dispatch` has exactly two callers, both inside `commit`/`_commit_purges` | `core/drafts.py:485`, `core/drafts.py:542` |
| Nothing outside `core/drafts.py` imports `_dispatch` — rename is internal | grep over `tests/`, `tools/`, `app/`, `web/`: 0 hits |
| `_call` funnels a raise into `{"error": …}`, which is what the commit loop keys on | `core/drafts.py`, `_call` |
| `create_backup(label=…)` slugifies and rejects a label with no letter or digit | `core/backups.py`, `slugify_label` |
| The page-size comparison sits **before** the safety backup today | `restore_backup`: `PRAGMA page_size` compare, then `create_backup(... "before-restore" …)` |

## Decisions taken

- **The loader owns the safety backup.** It takes `safety_label` and returns the
  backup path; `restore_backup` passes `"before-restore"`, T3's switch will pass
  `"before-switch"`. Reason: today the page-size refusal happens *before* the
  safety backup, so a loader-plus-copy-only split would either change the
  refusal order (leaving a `before-restore` backup a refusal does not leave
  today) or force T3 to repeat both steps. One seam, no duplication.
  *(Recommendation applied after the clarify timed out; say so and I will move
  the backup back into `restore_backup`.)*
- **Refusal strings stay byte-identical** in this task, including the two that
  now live in a generic loader and still say "restored in place" / "after the
  restore". Rewording them is observable behaviour, which T2 is not allowed to
  change; they are recorded in `Notes.md` under T3 so the switch rewords them
  rather than shipping the wrong word.
- **Branch**: continue on `draft-versioning` (T0/T1 already committed there).
  *(Same timed-out clarify; `dev` has none of the branch's work.)*

## Tasks

- [x] `core/backups.py`: `load_database_in_place(project_path, source, *, safety_label="before-restore") -> str` — refuses a live database that does not exist, refuses a page-size mismatch, takes the safety backup, copies `source` in with the backup API, migrates the copy forward, re-checks integrity, returns the safety backup's path. Reads the source read-only/immutable so no `-wal` appears beside it.
- [x] `core/backups.py`: `restore_backup` keeps name check, source validation and the result dict; the in-place block is replaced by one call to the loader. The paragraph explaining *why* the copy is in place moves with the code.
- [x] `core/drafts.py`: `_dispatch` → `apply_op`; its docstring states the contract (public, takes `conn`, `purge` never gets one) without pointing at a module that does not exist yet. Both call sites updated.
- [x] `tests/test_backups.py`: the loader copies a backup's contents into the live database, a second connection already open sees the new data, and the safety backup carries the label it was given.
- [x] `tests/test_drafts.py`: `apply_op` applies an op through a caller's `conn` inside the caller's transaction (rolled back by the caller leaves nothing), and returns the error dict (not a raise) when a write is refused.
- [x] Suite still `1770 passed, 1 failed` plus the new tests: **1774 passed, 1 failed** (4 new; the failure is the known `test_no_hermes_imports`).

## Final Brief

**What T2 changes.** Two seams, no behaviour.

*`load_database_in_place`* (`core/backups.py`). `restore_backup` did three
things in one function: check the source, copy it into the live database in
place, then report. The copy is now its own function and takes any already
checked file, which is what §4.3's branch switch needs. The loader owns exactly
the failures the copy itself can produce: no live database to copy into, a page
size the live database cannot take, and the state after the copy (migrated
forward, integrity re-checked). Source validation — readable, undamaged, has an
`entities` table, schema version between the baseline and the latest — stays in
`restore_backup`, because that is a statement about a *backup*, not about a copy.

The safety backup lives in the loader and takes `safety_label`: `"before-restore"`
from `restore_backup`, `"before-switch"` from T3. It is taken after the page-size
refusal, which is the order that existed before the split — verified by probe: a
page-size refusal still leaves no safety backup behind.

*`apply_op`* (`core/drafts.py`). `_dispatch` renamed. §7.7's executor orders ops
by its own rules and cannot use `sorted_ops` (creates before deletes makes
Replace and Theirs-swap unwritable), so it calls the per-op dispatcher directly.
The rename is the whole change: same body, same `conn` contract, same
`{"error": …}`-instead-of-raise behaviour, both existing call sites updated.
`OP_ORDER` and `sorted_ops` are untouched, so the agent's `story_draft` schema
(T11) does not move.

**Verification, as run.**

- `tests/test_backups.py` +2: the loader copies a backup into the live database
  and a second connection already open sees it; the safety backup carries the
  label it was given; a page-size mismatch is refused **before** any safety
  backup exists.
- `tests/test_drafts.py` +2: `apply_op` writes inside the caller's transaction
  and the caller's rollback removes it; a refused write comes back as
  `{"error": "ValueError: Entity not found: …"}`, not a raise.
- Probe against the fixture: `restore_backup` with a page-size-mismatched
  backup refuses and leaves `[]` labelled backups — the pre-split ordering.
- Full suite: **1774 passed, 1 failed** — baseline 1770 plus 4 new, same single
  known failure (`test_no_hermes_imports`).
- `ruff format --check src tests` clean.

**Deliberately not done.** The two loader strings that still say "restored in
place" / "after the restore" are left byte-identical: rewording them changes
user-visible output, and T3 is the task that makes a non-backup source reach
them. Recorded in `Notes.md` under T3 so the switch rewords both and updates
`tests/test_backups.py` in its own commit.
