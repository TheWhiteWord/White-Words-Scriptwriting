# T8 — Executor: ordering, dry run, apply, stale-plan guard, parent recording

Spec: `../spec-draft-versioning.md` §7.7 (plan/dry run/apply), §7.8 (where the target
lives), §7.9 (what a merge records), §4.5 (locking), §9 (`execute.py`), §13 T8,
§15 (merge tests).
Branch: `draft-versioning`.
Baseline: `1967 passed, 1 failed` on this branch before starting (the known
`test_no_hermes_imports`).

Status: in progress.

## Objective

A plan is a description; this task makes it happen. Three things:

1. **Order.** §7.7.2's order — restores → edits that release roles → deletes → creates
   → other edits → reorders — applied by calling the per-op dispatcher directly.
   `sorted_ops` cannot be reused: it puts every create before every delete, and a
   Replace or a Theirs-swap needs the old holder to lose a singular role first.
2. **Dry run and apply.** The dry run replays the whole plan with the real validators
   against a scratch copy of the target and maps each refusal back to the plan item or
   decision that produced it (§7.7.3). Apply takes a snapshot of the target, then runs
   the ops in one transaction, all or none (§7.7.4). Both stay off while a decision is
   open.
3. **Guards and bookkeeping.** A plan carries the target's fingerprint from plan time;
   apply refuses when it no longer matches, and the caller re-plans. A complete merge
   records its source as a pending second parent (§7.9); a cherry-pick records none.

Out of scope (later tasks): persisting a session (T9), routes (T10), agent tools (T11),
any UI.

## Verified before starting

Every row is a probe on this branch, not a reading of the spec.

| # | Claim | Evidence |
|---|---|---|
| 1 | The plan already emits ops in §7.7.2's order, then strips the ordering field | `plan._build`: sorts on `_phase` via `_order_key`, then `op.pop("_phase")`. Order is in list order only. |
| 2 | `apply_op` covers `create`/`edit`/`delete`/`reorder`/`purge` and **falls through to `reorder` for anything else** | `drafts.py:692`. A `restore` op through it would be dispatched as a reorder. The executor dispatches `restore` itself. |
| 3 | `trash.restore` opens its OWN connection and takes its own transaction; there is no `conn` parameter | `trash.py:1014`. Inside the executor's transaction this is a second writer → `database is locked`. |
| 4 | `restore` returns refusals as dicts (`{"error", "code": "restore_needs_decision", "collisions"}`) and never raises for a refused write | `trash.py:1090`. Same contract `apply_op` has through `_call`. |
| 5 | `apply_op` funnels a raise into `{"error": …}` and returns it | `drafts.py:759 _call`. So neither dispatch path raises. |
| 6 | `plan()` returns `{items, decisions, open, ops, ready}` — no fingerprint | `plan.py:152`. §7.7.4 says "the plan stores the target's fingerprint", so this task adds it. |
| 7 | An op carries no provenance: nothing on it names the item or decision it came from | `plan.py` emit sites. §7.7.3 requires mapping a failure back to its decision; a D4 `theirs` release acts on the *holder* scene, so matching on `(type, id)` maps it to nothing. |
| 8 | The planner gates Apply on `ready`, and `ops` is the *default* plan even when `ready` is false | `plan.py:152`; T7 Notes. An executor that ignores `ready` silently drops content. |
| 9 | `store.save_snapshot` takes the history lock and opens its own `story.db`; it refuses when the head's fingerprint equals its base's | `store.py:497`. Two consequences: it cannot run inside the executor's live transaction (deadlock), and a head identical to its base has no draft to take. |
| 10 | `store.head_state` returns the base draft and a `changed` flag; with no manifest it returns `branch: None` | `store.py:282`. Adoption has to happen first or a fresh project takes no snapshot. |
| 11 | `branches.pending_merge_parents` exists and `save_snapshot` turns it into a second `snapshot_parents` row, then clears it | `store.py:543`. The executor appends to the column; it must not insert a parent row itself. |
| 12 | `fingerprint.of_conn(conn)` exists | `fingerprint.py:41`. So the stale check can run on the same connection, inside the transaction, with no second open. |
| 13 | `db.transaction` starts `BEGIN IMMEDIATE` and becomes a SAVEPOINT when already inside one | `db.py:267`. Nested `restore`/`reorder` inside the executor's transaction are safe once they are handed `conn`. |
| 14 | `reorder` already accepts `project_path=None` with a `conn` | `writes.py:1009`, T2. The precedent for `restore` gaining `conn`. |

## Decisions

### D-T8-A — §7.8's non-current-branch target is T9's (settled, owner)

§7.8's second half — merge into another branch's parked head: copy to scratch, apply,
write back — is not in T8's task line and needs a branch-addressed pre-merge snapshot
(`save_snapshot` only freezes the live database). **Decision (owner):** the executor
takes a project path and covers the live database only; the parked-head target and the
branch-addressed snapshot land in T9, which owns `target_branch_id`. Recorded as a T9
finding below.

### Settled without asking

- **`trash.restore` gains `conn=None`**, exactly as `reorder` did (T2). Without it the
  executor's single transaction is impossible. Minimal diff: the same
  `own_conn`/conditional-close shape.
- **The executor preserves the plan's op order.** It does not re-sort: the plan's order
  IS §7.7.2's, and re-sorting by `OP_ORDER` would put creates before the role release.
- **Ops gain a `source` key** — the item or decision key that produced them. §7.7.3's
  mapping needs it, and nothing else can reconstruct it for a release op.
- **`plan()` returns the target's fingerprint.** §7.7.4 says the plan stores it, and a
  parameter the caller can forget is a guard that will be forgotten.
- **Both executor entry points take the planner's return**, not a bare op list: `apply`
  must see `ready`, and one input shape is one thing to pass.
- **The pre-merge snapshot is a normal history draft** (`save_snapshot`), taken *before*
  the run and *before* any parent is recorded. When the head equals its base, the base
  draft is that exact state and is reported instead of a duplicate.
- **`parent_source` is one parameter, not a `complete` flag plus an id.** Passing a
  source IS the declaration §7.9 asks for; a cherry-pick passes nothing.

## Tasks

- [x] `core/trash.py`: `restore(..., conn=None)` — the `own_conn` shape `reorder` uses.
- [x] `core/history/plan.py`: stamp `source` on every emitted op.
- [x] `core/history/plan.py`: return `fingerprint` of the plan's target.
- [x] `core/history/store.py`: `record_pending_parent(project_path, snapshot_id)`.
- [x] `core/history/execute.py`: `dry_run(project_path, planned)` — scratch copy, real
      validators, failure mapped to its `source`.
- [x] `core/history/execute.py`: `apply(project_path, planned, *, parent_source=None,
      label=…)` — not-ready and stale-plan refusals, pre-merge draft, one transaction,
      all or none, pending parent on success.
- [x] `core/history/execute.py`: `_run` / `_apply_one` — §7.7.2 dispatch, `restore` included.
- [x] `tests/test_history_execute.py`: order preserved (release before create), restore
      op inside the transaction, all-or-none rollback, dry run clean and refused with
      `source`, stale refusal with nothing written, not-ready refusal, pre-merge draft,
      no duplicate draft when unchanged, complete merge writes the pending parent and
      the next save turns it into a second parent row, cherry-pick records none,
      a refused merge records no parent.
- [x] Suite green against the `1967 passed, 1 failed` baseline; `ruff format --check` and
      `ruff check` clean on every touched file.

## Final Brief

**What the executor is.** Two functions in `core/history/execute.py`:
`dry_run(project_path, planned)` → `{status: "clean"|"refused", failures, ready}`, and
`apply(project_path, planned, *, parent_source=None, label=…)` →
`{status: "applied"|"refused"|"blocked", applied, baseline, parents}`. Both take the
planner's own return value, so `ready` and the fingerprint cannot be forgotten.

**Order.** `_run` walks `planned["ops"]` as given and never sorts. §7.7.2's order is
already in the list (`plan._build` sorts on `_phase`), and re-sorting by `OP_ORDER`
puts creates before deletes — mutation-verified: swapping in `drafts.sorted_ops` makes
the D4 Theirs-swap fail to apply.

**Refusals are data.** `blocked` (an unanswered non-optional decision, with its `open`
keys), `refused`/`stale_plan`, and `refused`/`failures` where each failure names the
op, the core's own error string, the plan `item`, and the `decision`. The item is
looked up through the op's new `source` tag — a release op edits the scene that
*holds* a role while its decision is about the scene *arriving*, so the op's own id
names the wrong item.

**All or none.** `apply` holds the manifest lock (§4.5) for the whole operation, takes
the restore point inside it, then runs every op in one content transaction with a
second fingerprint check. A refused op raises out of that transaction and every earlier
op rolls back with it. `_run` stops at the first failure on purpose: later ops were
planned against a state where the failed one had landed.

**Restore point.** `store.restore_point(project_path, conn, label)` — a normal history
draft labelled "Before merge", or the existing draft when the head already equals it
(no duplicate draft). It runs on the executor's manifest connection; taking the lock
twice deadlocks, which a mutation confirmed.

**Parentage (§7.9).** `parent_source` is a snapshot id and passing one IS the "complete
merge" declaration: `store.record_pending_parent` appends it to
`branches.pending_merge_parents` and the next `save_snapshot` turns it into a second
`snapshot_parents` row. A cherry-pick passes nothing and records nothing. A **refused**
merge records nothing either — that gap was found by a mutation surviving and now has
its own test.

**Suite.** 1985 passed, 1 failed — the baseline's `test_no_hermes_imports`, unchanged.
1967 → 1985 is 18 new executor tests. Run as two chunks, because one `pytest tests/`
invocation wedges in the host's ext4 journal (`jbd2_log_wait_commit`) — the clean T7
baseline does the same, so it is the environment; see the T8 environment note in
`Notes.md`.

**Mutations that fail a test.** Re-sorting the ops, `restore` without the caller's
connection, dropping the stale guard, ignoring `ready`, recording the parent before the
run, and recording the parent on a second manifest connection. Six, all killed.

**Deliberate ceilings.**

- The dry run copies the target with the backup API and replays there — a full copy per
  preview, the same cost the drafts flow pays (F6). Text data; fine at this size.
- `_stale` compares fingerprints, not row counts: it says the target moved, not what
  moved. §7.7.4 asks exactly that.
- `apply` on an unchanged head reports the base draft as the baseline instead of
  writing a second identical draft; the restore point is that draft either way.

**Not in this task.** §7.8's other target — another branch's parked head — is T9's, by
owner decision (D-T8-A). Nothing persists a session (T9), no route (T10), no agent tool
(T11).

