# Draft dry run — implementation plan

Spec: `draft_dry_run_spec.md`. Paths below are relative to `src/story_architect/`.
Three phases, in order. Phase 1 lands the replay; Phase 2 makes the verdict
reach the agent and the card; Phase 3 proves nothing was left behind. The order
matters: the response field must exist before the agent-facing wording and the
card have anything to carry.

## Comment hygiene

When editing a file, delete comments that only record history — "was X, now Y",
"used to", "this used to be", phase and issue references ("B12", "D1a"), and
"restored/rewritten after <incident>". State only what the code does now. Keep a
comment only when it explains a non-obvious *why* (a constraint, an invariant,
a trap). If a comment describes a change, it is a line in the git log, not a
comment.

For this change specifically:

- A comment may say **why** the copy uses SQLite's backup API (WAL) and **why**
  the temp dir is outside the project (the promise that staging leaves no
  footprint). Those are invariants.
- A comment may not say "stage used to skip validation, now it replays" or
  reference this task.
- Do not describe the three verdict states in a comment; the `status` values say
  it.

## Code practices

- **The dry run adds no rule.** It calls the existing `commit()`. Never
  re-implement op ordering or any validator — if a check is needed, it already
  lives there. A second copy of a rule is what this codebase keeps removing.
- **One helper, no more.** `dry_run()` in `core/drafts.py`. The card gate is
  one condition in `on_call_tool`. No snapshot helper, no class, no config
  flag, no registry, no options object.
- **Copy with SQLite's backup API**, never `shutil.copy`: the database runs in
  WAL mode, so a plain file copy can miss recent commits.
- **Temp dir outside the project, removed on every path.**
  `with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:`. The
  copy is gone before `stage` returns — a refused batch leaves nothing to retry
  against, so a re-stage makes a fresh copy. A leaked directory, or a file
  written inside `.story/`, breaks the feature's whole promise.
- **Staging must not fail because the replay could not run.** The draft row is
  already written at that point; report `{"status": "unavailable", ...}`
  instead of raising.
- **Match the surrounding idiom.** Local imports inside functions
  (`from .db import get_db` at `core/drafts.py:348`), plain dicts in responses,
  `ValueError` for a refusal, terse prose.
- **Every branch leaves a runnable check.** Three outcomes — `clean`,
  `refused`, `unavailable` — each gets a test.

Out of scope, deliberately: `app/mcp_server.py:83` writes
`/tmp/draft_debug.txt` on every draft call. That is a pre-existing debug
write, unrelated to this change — leave it alone (worth its own ticket).

## Phase 1 — The replay

**Goal:** staging reports whether the batch would commit, and touches nothing.

Checklist:
- [ ] `core/drafts.py` — add `dry_run(project_path, draft_id)`. Open a throwaway
      dir with `tempfile.TemporaryDirectory(ignore_cleanup_errors=True)` and
      create `<tmp>/.story/` inside it (a raw `sqlite3.connect` does not make
      parents), copy `<project>/.story/story.db` to `<tmp>/.story/story.db`
      through `Connection.backup()`, then `try: result = commit(Path(tmp),
      draft_id)` with `except Exception:` → `{"status": "unavailable",
      "error": ...}`. The context manager removes the dir on every path. Map the
      outcome to
      `{"status": "clean"}`,
      `{"status": "refused", "failed_op": result["failed"]["op"], "error": result["failed"]["error"]}`,
      or `{"status": "unavailable", "error": ...}` when the copy or the replay
      failed. The function does not raise.
- [ ] `core/drafts.py:195-253` — `stage()`: after the draft row is written, set
      `result["dry_run"] = dry_run(project_path, new_id)`. Nothing else in the
      response changes.
- [ ] `core/drafts.py` — bring the module docstring and `stage`'s in line with
      the replay: `commit_draft` is `commit`, and the dry run dispatches into
      `core.writes` on the copy, so it is the project's tables that go
      untouched.
- [ ] `tests/test_draft_dry_run.py` — new file, using the `fixture_path`
      fixture and `test_drafts._counts`:
      - a batch whose scene takes a `climax` another scene holds →
        `status == "refused"`, and the error names the plot, the role and the
        scene that already holds it;
      - a batch where one edit clears the `climax` and a later edit gives it to
        another scene → `status == "clean"` (the case a committed-state check
        would get wrong);
      - the real project is untouched: `_counts` identical, and the set of
        files under the project tree identical;
      - the copy is untouched by the replay apart from the database: its file
        set afterwards is still only `.story/story.db` (+ `-wal`/`-shm`), the
        assertion that makes a future file-writing write path loud;
      - the temp dir is gone afterwards on the clean, refused and exception
        paths (patch `tempfile.TemporaryDirectory` to record its dirs, assert
        none survive the call);
      - `commit()` on the refused draft still fails with the same message.

**Gate:**
```
.venv/bin/python -m pytest tests/test_draft_dry_run.py tests/test_drafts.py -q
```
Plus the probe: stage the refused batch against a scratch project and confirm
the `dry_run` verdict matches the message `commit` produces for the same draft.

## Phase 2 — The verdict reaches the agent

**Goal:** the agent knows before presenting the card; the card appears only for
a clean stage, so the user never sees a verdict.

Checklist:
- [ ] `tools/story_draft.py:118-121` — SCHEMA description: report `validation`
      **and** `dry_run`; `"refused"` means fix and re-stage, or relay the
      conflict when it is a story decision; `"unavailable"` means the replay
      could not run — relay the `error`.
- [ ] `app/mcp_server.py:80-107` — publish the card only when the stage result
      carries a `dry_run` with `status == "clean"`. A `refused` or `unavailable`
      stage publishes nothing. A result with no `dry_run` (a `commit` call)
      keeps the existing behaviour. No verdict is added to `warnings`.
- [ ] Tests: a clean stage publishes, a refused stage publishes nothing, an
      unavailable stage publishes nothing; the `story_draft` description
      mentions `dry_run`.

**Gate:**
```
.venv/bin/python -m pytest tests/test_draft_dry_run.py tests/test_story_draft_tool.py -q
```

## Phase 3 — Cleanup

**Goal:** nothing the change made unused is left behind, and the whole suite is
green.

Checklist:
- [ ] Grep for leftovers: `dry_run` appears only in `core/drafts.py`,
      `tools/story_draft.py`, `app/mcp_server.py` and the new test — ignoring
      the pre-existing uses in `core/writes.py:794` and `tools/story_import.py`
      (`current_values` and the import flag); no debug writes, no stray
      `print`, no leftover temp paths in the repo.
- [ ] Confirm `commit()` is byte-for-byte unchanged and still the enforcer
      (the Phase 1 backstop test pins this).
- [ ] Confirm every new import is used and every new branch is covered.
- [ ] Full suite (two failures pre-date this change and are not theirs to fix:
      `tests/test_no_hermes_imports.py`, `tasks/task_30/test_skill_references.py`):
      ```
      .venv/bin/python -m pytest -q
      ```
- [ ] Re-run the probes from Phase 1 and Phase 2 against a scratch project and
      confirm the outputs named in the gates.

**Gate:** the full suite shows no new failures and every grep above returns
nothing attributable to this change.
