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

- [x] Create branch `draft-versioning` off `dev`.
- [x] Commit the spec and task records on the branch before any reformat, so the
      pre-format tree stays reachable by `git checkout <sha> -- <path>`.
- [x] `pyproject.toml`: pin `ruff==0.15.8` in the `dev` extra.
- [x] `pyproject.toml`: exclude `tasks/` from ruff. It holds historical task
      artefacts — the same reason `testpaths` already leaves it uncollected.
      Keeps 7 one-off scripts and 83 plan documents out of the format diff.
- [x] `ruff format src tests` — its own commit, nothing else in it.
- [x] Verify the suite still reports `1744 passed, 1 failed` with the same
      single failure.
- [x] Verify `ruff format --check src tests` is clean and stays clean when run
      again with the pinned version.
- [x] Verify `ruff format --check .` does not touch `tasks/`.

## Final Brief

Branch `draft-versioning`, three commits off `dev` @ `610cf06`:

| Commit | Contents |
|---|---|
| `323c49c` | Spec, `Notes.md`, this task file. First on the branch so the pre-format tree is reachable. |
| `d2d2563` | `pyproject.toml`: `ruff==0.15.8` in the `dev` extra; `exclude = ["tasks"]`. |
| `cc52032` | `ruff format` over 170 files. Mechanical only. |

**Verification, as run.**

- Suite before: `1744 passed, 1 failed`. After: `1744 passed, 1 failed` — the
  same `test_no_hermes_imports`, 166s.
- `ruff format --check .` → `177 files already formatted`, on a second run after
  reinstalling from `.[dev]`.
- `ruff format --check .` lists no `.md` and no `tasks/` path; `ruff check .`
  reports 0 findings under `tasks/`.
- `build_registry()` dumped to JSON before and after: byte-identical, so no
  agent-facing tool schema moved.
- `git show --stat cc52032` touches 0 markdown or `tasks/` files.

**What was deliberately not done.** 263 `ruff check` findings remain (E501 127,
F401 88, F841 13, E402 12, E741 10, E712 7, F811 2, E731 2, F541 1, F402 1) and
belong to a later lint-backlog commit. 113 of the E501s are string literals the
formatter cannot split, so that commit will need either an `E501` ignore or 113
hand edits — a decision for then, recorded in `Notes.md`.

**One caveat for whoever runs this next.** `ruff check tasks` on the command
line still lints that folder: `exclude` governs discovery from `.`, not an
explicitly named path.

