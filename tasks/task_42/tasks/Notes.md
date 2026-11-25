# Task 42 — Notes

Cross-task record for draft versioning, branching, diff and merge.
One section per task. Each task reads every earlier section before it starts,
and writes its findings into the sections of the tasks they affect.

Rules for entries: a finding is a fact about the code or the spec that a later
task would otherwise have to rediscover. State the fact, where it was verified,
and what it changes. No narration.

---

## T0 — Branch off `dev`, ruff config, formatting

### Findings
- Baseline at `dev` @ `610cf06`: `1744 passed, 1 failed`. The failure is
  `tests/test_no_hermes_imports.py::test_no_hermes_imports` — `app/server.py`
  mentions `adapters.hermes.chat_backend` in a local import. Pre-existing, by
  owner decision not this feature's concern. Every boundary check in later
  tasks compares against **1744 passed / 1 failed**; a count that moves down is
  a regression.
- `build_registry()` output is byte-identical before and after the reformat, so
  no agent-facing tool schema changed. Verified by dumping the registry to JSON
  on both trees and diffing.
- `ruff format` **also rewrites Python code fences inside `.md` files**: 83
  documents under `tasks/` would be reformatted. `tasks/` is excluded from ruff
  for this reason.

### Deviations
- The spec's T0 line reads "`ruff` config; apply formatting". A `[tool.ruff]`
  block already existed at `dev` (`line-length=100`, `target-version=py311`,
  `select=["E","F"]`); T0 therefore adds only the pin and the `tasks/` exclude,
  rather than introducing a config.
- Scope of the `ruff` work is format only, by owner decision. 263 `ruff check`
  findings remain after formatting and are **not** this task's. A later commit
  owns them.

### Issues
- Ruff was neither installed nor pinned at `dev`, so `ruff format` was not
  reproducible: 0.15.8 and 0.17.6 reformat a different set of 6 files. Pinned to
  `0.15.8` in the `dev` extra. A future ruff upgrade is its own commit with its
  own reformat, not a side effect of an unrelated task.
- Of the 263 remaining findings, 113 of the 127 `E501`s are string literals
  (prompt text, SQL, regexes) that the formatter cannot split. Adding `E501` to
  the ignore list is the standing ruff guidance when the formatter owns line
  length; not done here, since it belongs with the lint-backlog commit.
- Three `F841` findings in `src/` are worth reading, not deleting:
  `core/db.py:857 plot_scopes`, `chat/service.py:191 cancelled`,
  `adapters/hermes/setup.py:332 gateway_ok`. Each is assigned and never read;
  two of the three read like an unimplemented check. Carry them to the
  lint-backlog commit with this note.

---

## T1 — Restore guard

### Findings
### Deviations
### Issues

---

## T2 — `load_database_in_place`, `apply_op` public

### Findings
### Deviations
### Issues

---

## T3 — `history.db` and `store.py`

### Findings
### Deviations
### Issues

---

## T4 — `ProjectView` and the logical entity

### Findings
### Deviations
### Issues

---

## T5 — `refmap`

### Findings
### Deviations
### Issues

---

## T6 — Diff

### Findings
### Deviations
### Issues

---

## T7 — Planner

### Findings
### Deviations
### Issues

---

## T8 — Executor

### Findings
### Deviations
### Issues

---

## T9 — Persistent merge sessions

### Findings
### Deviations
### Issues

---

## T10 — HTTP routes

### Findings
### Deviations
### Issues

---

## T11 — Agent tools

### Findings
### Deviations
### Issues

---

## T12 — Agent approval card

### Findings
### Deviations
### Issues

---

## T13 — UI

### Findings
### Deviations
### Issues
