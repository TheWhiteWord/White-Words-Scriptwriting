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
- [x] `core/drafts.py` — add `dry_run(project_path, draft_id)`. Open a throwaway
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
- [x] `core/drafts.py:195-253` — `stage()`: after the draft row is written, set
      `result["dry_run"] = dry_run(project_path, new_id)`. Nothing else in the
      response changes.
- [x] `core/drafts.py` — bring the module docstring and `stage`'s in line with
      the replay: `commit_draft` is `commit`, and the dry run dispatches into
      `core.writes` on the copy, so it is the project's tables that go
      untouched.
- [x] `tests/test_draft_dry_run.py` — new file, using the `fixture_path`
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
- [x] `tools/story_draft.py:118-121` — SCHEMA description: report `validation`
      **and** `dry_run`; `"refused"` means fix and re-stage, or relay the
      conflict when it is a story decision; `"unavailable"` means the replay
      could not run — relay the `error`.
- [x] `app/mcp_server.py:80-107` — publish the card only when the stage result
      carries a `dry_run` with `status == "clean"`. A `refused` or `unavailable`
      stage publishes nothing. A result with no `dry_run` (a `commit` call)
      keeps the existing behaviour. No verdict is added to `warnings`.
- [x] Tests: a clean stage publishes, a refused stage publishes nothing, an
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
- [x] Grep for leftovers: `dry_run` appears only in `core/drafts.py`,
      `tools/story_draft.py`, `app/mcp_server.py` and the new test — ignoring
      the pre-existing uses in `core/writes.py:794` and `tools/story_import.py`
      (`current_values` and the import flag); no debug writes, no stray
      `print`, no leftover temp paths in the repo.
- [x] Confirm `commit()` is byte-for-byte unchanged and still the enforcer
      (the Phase 1 backstop test pins this).
- [x] Confirm every new import is used and every new branch is covered.
- [x] Full suite (two failures pre-date this change and are not theirs to fix:
      `tests/test_no_hermes_imports.py`, `tasks/task_30/test_skill_references.py`):
      ```
      .venv/bin/python -m pytest -q
      ```
- [x] Re-run the probes from Phase 1 and Phase 2 against a scratch project and
      confirm the outputs named in the gates.

**Gate:** the full suite shows no new failures and every grep above returns
nothing attributable to this change.

## Phase 2 brief — the verdict reaches the agent

**Summary.** The verdict now reaches the agent through two channels and the
card is gated on it. `story_draft`'s SCHEMA description names `dry_run.status`
and what each of the three values means (`src/story_architect/tools/story_draft.py:120-123`).
`on_call_tool` publishes an approval card only when the result carries a
`dry_run` whose status is `clean`; a `refused` or `unavailable` stage, and any
result without a `dry_run`, returns the tool text without touching the bus
(`src/story_architect/app/mcp_server.py:89-91`). No verdict was added to
`warnings`: the card still renders exactly `validation`, as before.

**Deviations.**

- **A pre-existing bug was suppressed, not preserved.** The plan's third item
  said "a result with no `dry_run` (a `commit` call) keeps the existing
  behaviour" — but that behaviour was wrong. The gate was
  `isinstance(obj, dict) and "draft_id" in obj`, and a commit response carries
  `draft_id`, so **every commit published an empty card**: `status: "open"`,
  no summary, no changes. Confirmed by probe before editing. With the strict
  `dry_run`-clean gate, that path is unreachable, so nothing is lost; the
  "existing behaviour" clause is satisfied vacuously. A test pins it.
- **`tests/test_story_describe.py::test_no_description_promises_a_missing_parameter`
  conflicted with the checklist.** It asserts the string `dry_run` appears in
  no tool description. It was written for a real bug — `story_import`
  advertised a flag its schema lacked — but it cannot distinguish an input
  parameter from a response field, and Phase 2 requires `story_draft` to name
  its own response field. Scoped the guard with a named exemption for
  `story_draft`/`dry_run`, stating why in the comment, rather than rewording
  the agent contract around a guard. The other three claims are untouched.
  (Clarification asked; no answer, so the narrower fix was taken.)
- **`props` deleted at `tests/test_story_describe.py:44`** — already unused
  before this change.
- **The card gate is tested by driving `on_call_tool` directly**, via
  `server.get_request_handler("tools/call").handler`, patching
  `mcp_server._publish_bus`. No repo test drove this handler before, and the
  surrounding MCP transport is not part of the decision under test.
- **Loop hygiene in that test.** `asyncio.run` closes the loop it creates, and
  every other chat test calls `get_event_loop()` afterwards — the first cut
  broke all five `test_chat_core.py` tests whenever the full suite ran. The
  test now reuses the ambient loop, creating one only if none exists, and never
  closes it.

**Contract changes.** Two, both intended:

- `story_draft`'s agent-facing description gains the `dry_run.status` contract
  (spec change #3).
- A `commit` call no longer emits a phantom `status: "open"` card on the bus.
  This is a user-visible fix, not a spec change: previously the agent's commit
  put an empty, unapprovable proposal card on screen alongside the real
  `✅ Committed` report.

**Verification.**

- Gate: `pytest tests/test_draft_dry_run.py tests/test_story_draft_tool.py -q`
  → **30 passed**.
- Neighbours: `test_task5_assets`, `test_dashboard_link`, `test_chat_routes`,
  `test_chat_core`, `test_hermes_chat_backend`, `test_story_describe`,
  `test_draft_preview`, `test_manual_structure` → **all pass** with the gate
  files (145 passed in the combined run; the 5 `test_chat_core` failures in
  that run were the loop bug above, fixed before the full-suite run).
- Probe (`on_call_tool` driven directly, scratch project built from the
  fixture): clean stage → **1 card** (`status=open`, id and summary carried);
  refused stage → **0 cards**; unavailable stage (patched `drafts.dry_run`)
  → **0 cards**; commit of a staged draft → **0 cards**. Before the change the
  same four calls produced 1/1/1/1.
- Full suite: **1328 passed, 2 failed** — the same two pre-existing failures
  recorded in the Phase 1 brief (`test_no_hermes_imports`,
  `tasks/task_30/test_skill_references`), both reproduced earlier at `625beac`.
  1328 = the 1323 baseline + 5 new tests.

Phase 2 → Phase 3 is ready to proceed.

## Phase 3 brief — cleanup

**Summary.** Nothing the change made unused is left behind, and the whole
suite is green. `dry_run` in `src/` appears only in the three files the plan
names; `commit()` is byte-for-byte unchanged; every new import is used. The one
gap the confirmation surfaced — the sandbox **copy**-failure branch had no
test — is closed. Both probe sets reproduce the outputs the gates name.

**Deviations.**

- **One test added beyond the checklist** — `test_a_copy_failure_is_a_verdict_not_an_exception`
  (`tests/test_draft_dry_run.py:145`). Phase 3 asks that every new branch be
  covered, and `dry_run` has two `except` arms: the inner one (a `commit`
  exception) was covered by the Phase 1 test, the outer one (the temp dir or
  backup failing) was not. The new test patches `tempfile.TemporaryDirectory`
  to raise on `__enter__` and asserts `stage` still returns
  `{"status": "unavailable", "error": "OSError: …"}` rather than propagating.
- **The grep list is broader than the plan's wording, legitimately.** The plan
  says `dry_run` appears in `core/drafts.py`, `tools/story_draft.py`,
  `app/mcp_server.py` and "the new test". Phase 2's own checklist required the
  `story_draft` description to name `dry_run`, so it also appears in
  `tests/test_story_draft_tool.py` and in the `test_story_describe.py`
  exemption. Those are test files, not leftovers; no `src/` file outside the
  three carries the name beyond the pre-existing `writes.py`,
  `story_import.py` and `adapters/hermes/setup.py` uses.
- **`app/mcp_server.py:83` still writes `/tmp/draft_debug.txt`.** The plan
  scopes it out ("worth its own ticket"); left alone, as directed.
- **`commit()` was verified by AST source-segment equality** against the
  task_39 branch point `3d9cb08` — 89 lines, identical at HEAD and in the
  worktree. A textual `sed` range was not reliable here because `dry_run` was
  inserted between `commit` and `_commit_report`.

**Contract changes.** None.

**Verification.**

- Greps: `dry_run` in `src/` → only `core/drafts.py`, `tools/story_draft.py`,
  `app/mcp_server.py` plus the three pre-existing files; no stray `print`, no
  `pdb`/`breakpoint`, no leftover temp paths in the repo.
- Imports: an AST pass over the five touched files reports no unused import
  (`mcp_server`'s `annotations` / `StreamableHTTPSessionManager` / `_tools_pkg`
  are `__future__`, an `__all__` re-export and an import side-effect).
- Backstop: `pytest tests/test_draft_dry_run.py -q` → **8 passed** (7 + the
  new branch test).
- Full suite: `.venv/bin/python -m pytest -q` → **1329 passed, 2 failed** —
  the same two pre-existing failures (`tests/test_no_hermes_imports.py`,
  `tasks/task_30/test_skill_references.py`). 1329 = the 1328 Phase 2 result
  + 1 new test.
- Phase 1 probe (scratch project from the fixture markdown): refused batch →
  `{"status": "refused", "failed_op": "edit scene/the-core-day", "error":
  "PlotRoleError: Plot 'the-resistance' already has its climax on scene
  'central-room-night' — one scene per plot."}`; entity/section/relation
  counts and the project file tree unchanged; freeing batch →
  `{"status": "clean"}`; committing the refused draft → `success: False` with
  the identical `failed.error`.
- Phase 2 probe (same scratch project, `on_call_tool` driven directly): clean
  stage → 1 card (`status=open`, summary carried); refused, unavailable
  (patched `drafts.dry_run`) and commit → 0 cards.

Phase 3 complete; the task_39 plan has no remaining phase.
