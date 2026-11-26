# T9 — Persistent merge sessions

Spec: `../spec-draft-versioning.md` §4.2 (`merge_sessions`), §7.1 (source), §7.7
(plan/preview/apply), §7.8 (where the target lives), §7.9 (what a merge records),
§9 (`session.py`), §13 T9.
Branch: `draft-versioning`.
Baseline: `1744 passed, 1 failed` + the seven history files' 209 passed = `1953 passed,
1 failed`, the known `test_no_hermes_imports`.

Status: in progress.

## Objective

A plan is currently a value in memory: plan, preview, apply all happen in one call.
This task makes the *session* the thing that persists — the selection, the decisions
already answered, the base it was computed from, and the target's fingerprint at plan
time — so a merge can be worked on over several requests (and by the agent, T11)
without re-answering what was already settled.

Three parts:

1. **`session.py`**: create, read, update (selection, one decision), preview, apply,
   discard — over the `merge_sessions` table T3 created and left empty. Every read
   re-plans from the stored selection and decisions, so the stored plan can never
   disagree with what apply would do.
2. **A source is a draft or another branch's head** (§7.1). The second needs the head
   read as a project path, and its unsaved changes are exactly what makes a *complete*
   merge undeclarable for it.
3. **A target is the live head or another branch's parked head** (§7.8, deferred from
   T8): copy the head to a scratch project, apply there, write back — with the
   branch-addressed pre-merge draft that `store.save_snapshot` cannot take.

## Verified before starting

Every row is a probe on this branch, not a reading of the spec.

| # | Claim | Evidence |
|---|---|---|
| 1 | `merge_sessions` exists, empty, and `history.db` is at `BASELINE = 1` with `MIGRATIONS = []` | `store.py:71`, `:85`. So a session is a row write, never a migration. |
| 2 | `plan()` takes three project **paths** and returns `{items, decisions, open, ops, ready, fingerprint}` | `plan.py:115`. A re-plan is one call; nothing has to be cached on the row. |
| 3 | `execute.apply` takes a project path and covers the live database only | `execute.py:77`; T8 decision D-T8-A. |
| 4 | Calling `execute.apply` on a scratch copy of a parked head **adopts it as a new project**: the scratch gains `history.db` + `history/`, `baseline.created` is False, and the real branch gets no draft | probed: `apply-to-scratch: applied baseline: Draft 1`, `scratch gained history.db: True`, real manifest unchanged. The T8 note's trap, reproduced. |
| 5 | `execute._run(scratch, planned)` writes only content: no `history.db`, no restore point, no lock | probed: `_run failures: []`, `_run scratch history.db: False`, `_run kael: Kael` |
| 6 | A scratch written by `_run` read with the backup API and parked back over the head lands the change | probed: `written back kael: ('Side Name',)`, and the untouched head still reads `('Kael',)` |
| 7 | `store._park` reads its source `immutable=1`, which **ignores an un-checkpointed `-wal`** | probed with a second connection open: live sees `['before', 'committed-by-other']`, the parked copy sees `['before']`. A switch in that window loses committed writes. |
| 8 | `store._freeze(source=…)` is the only other reader of a live database file and has the same defect (`_open_read`) | `store.py:388-402`; `_open_read` at `:355`. |
| 9 | `_open_read` on a **frozen** draft is correct: a snapshot is written by `_write_atomic` and closed, so it never has a `-wal` | `store.py:360`; `_write_atomic` closes `out` before `os.replace`. |
| 10 | A `mode=ro` (non-immutable) read of a 0444 draft works and leaves `-wal`/`-shm` beside it | probed: `ro OK rows 1`, dir gains `snap.db-shm`, `snap.db-wal`. So the fix must keep `immutable` for drafts and use `mode=ro` for live databases. |
| 11 | `record_pending_parent` writes to the **current** branch (`_adopt`) | `store.py:598`. A merge into another branch needs it addressed by id. |
| 12 | `_save` reads the live database in three places (freeze, fingerprint, version/counts) and always writes `_adopt`'s branch | `store.py:497-551`. Freezing a parked head needs all four parameterised. |
| 13 | `branches.base_snapshot_id` of another branch is live: `branch_from` sets it, `_save` moves it | `store.py:611`, `:544`. |
| 14 | `store.merge_base(project, target_draft, source_draft)` returns `{base, imprecise}` and raises `No such draft` for a foreign id | `store.py:299`; test pinned. |
| 15 | `view.project_view` copies a draft with `backup()` into a temp project; the copy is deleted with the block | `view.py:27`. The shape a head view needs too. |
| 16 | `_save`'s "nothing changed" guard compares the head's fingerprint against its base draft | `store.py:503`. For a head that IS the base draft it would refuse — correct for `save_head_snapshot`. |
| 17 | `core/history/session.py` will need a timestamp for a session id, so it must be registered in `LOCAL_TIME_ALLOWED` | `tests/test_utc_stamps.py:275`; `store.py` is registered for the same reason. |

## Decisions

### Settled by owner

- **A source is any draft, or another branch's head** (§7.1), and a **complete** merge
  from an unsaved head is refused with "save that branch's draft first". "Everything in
  it is accounted for" cannot be claimed for changes that have no draft, so the
  declaration is only available for a source that is a draft.
- **The `_park` `-wal` defect is fixed in this task**, in its own commit with its own
  test (finding 7). It is a data-loss path on the branch-switch that this feature
  already ships, and this task reuses the primitive for its write-back.

### Settled without asking

- **Every read re-plans.** The row stores the *inputs* (selection, decisions, base,
  fingerprint), never the op list. A stored plan can disagree with the code that made
  it; the inputs cannot. Cost is one `materialize` per side, which T6 already pays.
- **`target_fingerprint` is stamped once, at `start`.** §7.7.4 wants a stale plan
  refused, not silently re-based. A refusal tells the caller to start a new session
  with the same selection and decisions — both are on the row, so `show` returns them.
  No "refresh" operation: refreshing the fingerprint *is* re-planning.
- **`session.apply` never calls `execute.apply` on a scratch copy.** That path adopts
  the copy (finding 4). The parked-target path uses `_run` and its own restore point;
  the live path delegates to `execute.apply` unchanged.
- **`_park` gains `frozen=`** rather than one reader for both: a draft must keep
  `immutable` (finding 10 — `mode=ro` leaves debris beside a frozen file), a live
  database must not (finding 7).
- **`store.save_head_snapshot(..., head_path=…)`** accepts an already-made copy, so a
  parked-target apply copies the head once: freeze the draft from the copy, run the ops
  on it, write it back.

## Tasks

- [ ] `store.py`: `_open_live()` (`mode=ro`, no `immutable`) and `_park(..., frozen=False)`;
      `_freeze(source=…)` through the same reader. Own commit, with the `-wal` test.
- [ ] `store.py`: `_save(..., branch=None, head=None)` — freeze from `head` when given and
      write `branch`; `restore_point(..., branch_id=None, head=None)` passing them through
      (its "unchanged head reuses its base draft" rule is what a parked target needs).
- [ ] `store.py`: `get_branch(project_path, branch_id=None)` (None: the current branch) and
      `record_pending_parent(..., branch_id=None)`.
- [ ] `view.py`: `head_view(project_path, branch_id)` — a parked head as a project path,
      refusing the current branch and a missing file.
- [ ] `session.py`: `start`, `show`, `set_selection`, `set_decision`, `preview`, `apply`,
      `discard`; source refs `{"kind": "snapshot"|"branch", "id", "imprecise"}`; `complete`
      only for a draft source.
- [ ] `session.apply` live target → `execute.apply` with the session's fingerprint.
- [ ] `session.apply` parked target → one manifest lock: copy head → scratch, restore point
      from that copy, `_run` there, write back with `_park`, record the parent.
- [ ] `tests/test_history_session.py`: row round-trip, a decision set before planning,
      selection narrowing, preview writes nothing, apply marks the row, twice refused,
      blocked on an open decision, stale refused, draft source complete-merge parent,
      head source (cherry-pick applies, complete refused), parked target end to end
      (write-back, branch draft, **no `history.db` in the scratch**), discard.
- [ ] `tests/test_history_store.py`: a committed write that is still in `story.db-wal`
      survives a park (a second connection open across it).
- [ ] `tests/test_utc_stamps.py`: register `core/history/session.py`.
- [ ] Suite green against the `1953 passed, 1 failed` baseline; `ruff format --check`
      and `ruff check` clean on every touched file.

## Final Brief

(filled at close-out)
