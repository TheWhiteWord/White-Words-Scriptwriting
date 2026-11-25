# T0 — Branch off `dev`; ruff config; apply formatting

Spec: `../spec-draft-versioning.md` §13 T0, appendix "Formatting".
Branch: `draft-versioning` (off `dev` @ `610cf06`).

## Objective

Stand up the branch this feature is built on, make the formatter deterministic
(the same tree formats the same way on every machine), and land the resulting
mechanical diff as its own commit so every later task's diff is readable.

Out of scope by decision: fixing the lint backlog. `ruff format` is mechanical;
`ruff check` findings stay for a later commit.

## Verified before starting

| Claim | Evidence |
|---|---|
| Baseline is green apart from one known failure | `1744 passed, 1 failed` (`test_no_hermes_imports`) |
| A `[tool.ruff]` block already exists | `pyproject.toml`: `line-length=100`, `target-version=py311`, `select=["E","F"]` |
| Ruff is neither installed nor pinned | absent from `.venv`, absent from the `dev` extra |
| `ruff format` touches most of the tree | 170 of 206 files, 14271 insertions |
| Format output is version-dependent | 0.15.8 and 0.17.6 disagree on 6 files after formatting |
| Format does not change agent-facing payloads | `build_registry()` JSON byte-identical before/after |
| Format leaves 263 lint findings | E501 127, F401 88, F841 13, E402 12, E741 10, E712 7, F811 2, E731 2, F541 1, F402 1 |
| 113 of the remaining E501s are string literals | unsplittable by the formatter; no config value fixes them |

## Decisions taken

- **Branch name**: `draft-versioning`.
- **Pin ruff**: `ruff==0.15.8` in the `dev` extra. Unpinned, the format commit is
  not reproducible — a second machine on a newer ruff would reformat 6 files the
  first machine left alone, and every later diff would carry that noise.
- **Scope**: format only. The T0 commit is the format; the lint backlog is a
  separate later commit.

## Tasks

- [ ] Create branch `draft-versioning` off `dev`.
- [ ] Commit the spec and task records on the branch before any reformat, so the
      pre-format tree stays reachable by `git checkout <sha> -- <path>`.
- [ ] `pyproject.toml`: pin `ruff==0.15.8` in the `dev` extra.
- [ ] `pyproject.toml`: exclude `tasks/` from ruff. It holds historical task
      artefacts — the same reason `testpaths` already leaves it uncollected.
      Keeps 7 one-off scripts and 83 plan documents out of the format diff.
- [ ] `ruff format src tests` — its own commit, nothing else in it.
- [ ] Verify the suite still reports `1744 passed, 1 failed` with the same
      single failure.
- [ ] Verify `ruff format --check src tests` is clean and stays clean when run
      again with the pinned version.
- [ ] Verify `ruff format --check .` does not touch `tasks/`.

## Final Brief

_(appended on completion)_
