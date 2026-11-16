# Draft dry run — verification findings

Spec: `draft_dry_run_spec.md`. Plan: `draft_dry_run_implementation_plan.md`.
Verified against the tree on `task-38-structured-scene-heading` (clean at
`3d9cb08`). Every `file:line` claim was opened; the load-bearing premise was
then exercised for real (probe at the end).

**Status:** the spec and plan were corrected for B1, B2, C1, C2, C4, C5, C6 and
C7. **C8** is decided: the card is published only for a `clean` stage and
carries no verdict — the verdict is agent-facing only, and `unavailable` is
reported with its error. **S1** resolved: `entity.update_sections` and its
unused import are deleted, and the spec's DB-only premise is now unconditional.

## Method

1. Read both documents fully, then read every file they name.
2. Corrected the paths: both docs cite `core/…`, `tools/…`, `app/…`, `web/…`
   with no prefix. The real tree is `src/story_architect/…`. Line numbers are
   correct for the real files.
3. Ran a probe: built the fixture DB, staged a batch that moves a plot's
   `climax`, replayed `commit` against a backup-API copy in a temp dir, and
   compared the copy's verdict with the real commit.

## Sound claims (verified, no conflict)

| Claim | Evidence |
|---|---|
| `validate_ops` is structural; `validate_shape` is field-level, no DB | `core/drafts.py:61-127`, `:130-192` |
| Cross-entity rules are excluded from both and fire at commit | `validate_scene_plot_roles` / `validate_scene_location` / `check_references` / `validate_scene_dramatic_role` called only from `core/writes.py:230-245`, `:689-694` |
| Commit funnel reports `⚠️ Partly saved` and keeps the draft | `core/drafts.py:389-404`, `:423-439` |
| `sorted_ops` is stable within a kind, so op order matters | `core/drafts.py:320-329` |
| `commit` deliberately avoids one shared transaction | `core/drafts.py:339-346`; `get_db` is autocommit (`core/db.py:112-123`) |
| `backup_database` writes into `<project>/.story/`, so it cannot be reused | `core/db.py:138-171`, `dest` at `:156` |
| WAL mode is on, so a plain copy can be stale | `core/db.py:124` |
| `get_db` resolves `.story/story.db` | `core/db.py:121` |
| The write path is DB-only | grep of `core/` finds no file writes in `writes.py`; the only `open(...,'w')` is `entity.update_sections` (`core/entity.py:283-288`), which has no `src/` caller (only `tests/test_core.py:6` imports it) |
| The draft row travels with the copy, so `commit(temp_path, draft_id)` needs no plumbing | `stage` writes the row before the copy would be taken (`core/drafts.py:223-235`) |
| Card pipeline: server snapshot → bus → SSE → chat UI | `app/mcp_server.py:80-107` → `app/tool_bus.py` → `app/routes/chat.py:84-85` → `web/js/chat-api.js` → `web/js/chat-app.js:213` → `web/js/chat-render.js:205` renders `warnings` above the Approve button |
| `app/mcp_server.py:83` writes `/tmp/draft_debug.txt` on every draft call | confirmed, and the plan correctly leaves it alone |
| `fixture_path` fixture and `test_drafts._counts` exist and are the right tools | `tests/conftest.py:79-90`; `tests/test_drafts.py:21-30` (counts `entities`/`sections`/`relations` only, so the draft row does not disturb it) |
| Replay is faithful and isolated | probe below |

## Conflicts

| # | Issue | Severity | Resolution |
|---|---|---|---|
| B1 | **The "loud break" guard does not work.** Spec §Isolation rules and the plan's Phase 1 test both assert the **real project's** file set is unchanged. The replay runs with `project_path = <tmp>`, so a future file write lands in the copy; the real tree stays identical and the assertion passes. The precondition the spec calls load-bearing ("the write path stays DB-only") can break silently. | HIGH | Assert the **copy's** file set after the replay is still only `.story/story.db` (+ `-wal`/`-shm`), or diff the copy against the source. The real-project assertion stays as a second guard, not the primary one. |
| B2 | **`dry_run` "does not raise" contradicts the plan's `try/finally`.** Phase 1 maps `unavailable` only to "when the copy itself fails", but `commit` can raise (`DraftError` at `core/drafts.py:358`, `get_db` errors). With `try/finally` alone the exception propagates through `stage`, breaking "staging must not fail because the replay could not run" (plan §Code practices) and the spec's `unavailable` contract. | HIGH | Wrap the `commit` call in `except Exception` → `{"status": "unavailable", "error": ...}`; keep the `finally` cleanup. Say so in the checklist, not just in the prose. |

## Clarifications (the implementer would get these wrong)

| # | Issue | Severity |
|---|---|---|
| C1 | **Every path in both documents is missing the `src/story_architect/` prefix.** `core/drafts.py` does not exist at the repo root; a literal read fails. Line numbers are correct once the prefix is added. | MEDIUM |
| C2 | **The spec's probe expects the wrong error prefix.** Actual: `PlotRoleError: Plot 'the-resistance' already has its climax on scene 'central-room-night' — one scene per plot.` `PlotRoleError(ValueError)` (`core/entity.py:951`), and `_call` formats `type(e).__name__` (`core/drafts.py:489`). The §Verification string says `ValueError:`; the §Problem example omits the prefix entirely, so the spec disagrees with itself. | MEDIUM |
| C3 | **The copy destination's parent must exist before `sqlite3.connect`.** `get_db` would `mkdir`, but the backup *target* is a raw connection and `sqlite3.connect` does not create parents — the probe hit `OperationalError: unable to open database file` until `<tmp>/.story/` was made. | LOW |
| C4 | **Two docstrings become inaccurate and are not in the plan's edit list.** `stage`: "Writes one row and nothing else" (`core/drafts.py:197`); module docstring: "Nothing here touches `entities`, `sections` or `relations` until `commit_draft`" (`:4`) — `commit_draft` is a stale name (the function is `commit`), and the dry run *does* dispatch ops into `core.writes`, on the copy. | LOW |
| C5 | **`_draft_snapshot(obj, summary, changes)` is not pure** if it computes `created_at` (`datetime.now()`) internally. Pass `created_at` in, or drop the word "pure". | LOW |
| C6 | `web/js/chat-render.js:195` is the Approve button, not the card builder (`createDraft` starts at `:186`); warnings render at `:205`. Line drift only. | LOW |
| C7 | **Phase 3's grep will hit pre-existing `dry_run` uses**: `core/writes.py:794`, `tools/story_import.py:16,117,119,151`. The grep must exclude them or it reports leftovers that are not attributable to this change. | LOW |
| C8 | **`unavailable` never reaches the card.** The mapping appends a warning only for `refused`; a sandbox failure is reported in the agent's message but the user sees nothing. The spec's own "no news is ambiguous with the check did not run" argument applies here too. Decide whether that is intended. | LOW |

## Corrections with no decision needed

- **R1.** `get_db` does `db_path.parent.mkdir(parents=True, exist_ok=True)` (`core/db.py:122`) — a filesystem mutation on every connection. It is a no-op on a real project and inside the temp dir for the copy, so isolation holds. State the precondition as "no file *writes*; `get_db` may create `.story/`" rather than "DB-only", or the next reader will be misled.
- **R2.** `validate_scene_location`'s docstring (`core/entity.py:727-729`) says a location created in the same draft **is** visible at commit. That is consistent with the replay, and the spec's "a staged create is not there yet" is about *stage* time. No contradiction, but the spec's phrasing invites a misreading — worth one clarifying clause.
- **R3.** Baseline suite on this branch: **2 pre-existing failures, unrelated to task 39** — `tests/test_no_hermes_imports.py` (`app/server.py` contains "hermes") and `tasks/task_30/test_skill_references.py` (`success: false` backticked in `SKILL.md`). 1316 passed. Phase 3's "no new failures" is the right bar; name these two so they are not chased as regressions.

## Stale / redundant code

- **S1 — resolved.** `entity.update_sections` (`core/entity.py:283-288`) was dormant: no `src/` callers, imported only by `tests/test_core.py:6`. Deleted, with the import and the spec's citation; the spec now states the premise unconditionally ("no file under `core/` is written at all").
- **S2.** `app/mcp_server.py:83` (`/tmp/draft_debug.txt`) — the plan correctly defers it to its own ticket.
- **S3.** The plan introduces no redundancy: `validation` (shape findings) and `dry_run` (replay verdict) are distinct; the card gate is one condition in `on_call_tool`; `describe_ops` stays in use.
- **S4.** No test in the plan duplicates an existing guard. `test_drafts.py` already pins "stage writes nothing"; the new file adds the replay-specific cases (conflict, freeing-op, isolation, temp cleanup, commit backstop).

## Probe (real execution)

Built `tests/fixtures/save-the-children`, staged an edit giving `the-core-day`
the `climax` that `central-room-night` holds, then replayed `commit` against a
backup-API copy:

```
stage validation: []                      # stage reports nothing wrong
REAL commit : failed — PlotRoleError: Plot 'the-resistance' already has its
              climax on scene 'central-room-night' — one scene per plot.
COPY commit : identical result, identical message
real project: entities/sections/relations unchanged, file tree unchanged
              (only the draft row the stage itself wrote changed)
copy draft status: open
FREEING batch (clear climax on night, give it to core-day):
              COPY commit success — Committed 2 change(s)
```

So: staging is blind to the conflict, the replay reproduces the real verdict
exactly, the freeing-op batch that a committed-state check would false-positive
on passes, and the real project is untouched. The design's premise holds.

## Probe 2 — the two HIGH findings, by execution

**B1.** A `create_entity` patched to also write `<project_path>/LEAK.md` was
replayed on a copy:

```
replay success: True
real project has LEAK: False
copy has LEAK: True
real tree unchanged (the spec's assertion): True
```

The file landed in the copy; the real tree assertion passed. The spec's
"loud break" is silent.

**B2.** A copy whose `drafts` row was deleted before the replay:

```
commit raised: DraftError - No open draft: d-20261115-141020-1
```

`try/finally` alone propagates it, so `stage` would fail — the `unavailable`
contract is not met by the plan's checklist.

## `unavailable` in practice (verified)

The common causes, with the exact error the agent will see:

| Cause | Error |
|---|---|
| no usable temp dir | `FileNotFoundError: [Errno 2] No usable temporary directory found in [...]` |
| full disk (copy or mkdtemp) | `OSError: [Errno 28] No space left on device` |
| source path unreadable / a directory | `OperationalError: unable to open database file` |
| source not a database | `DatabaseError: file is not a database` |
| project has no built DB yet | `OperationalError: no such table: drafts` |
| draft row missing from the copy | `DraftError: No open draft: <id>` |

`dry_run` formats these as `{"status": "unavailable", "error": "<type>: <msg>"}`
— the same shape as `commit`'s `failed.error`, so the agent can relay it verbatim.

## Temp-copy cleanup (verified)

The copy is removed in a `finally`, before `stage` returns — so a `refused`
batch leaves nothing behind, and a re-stage makes a fresh copy. Probe: three
dry runs (refused, clean retry, exception) created three temp dirs and left
**zero** survivors. The only leak is the process dying mid-run; the dir lives
under TMPDIR, which is pruned. `ignore_cleanup_errors=True` makes a rmtree
failure silent, so the "none survive" test is the guard. The plan uses
`tempfile.TemporaryDirectory(ignore_cleanup_errors=True)` rather than a manual
`mkdtemp`/`finally` pair.

