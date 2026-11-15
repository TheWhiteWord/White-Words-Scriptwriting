# Draft dry run — spec

Paths below are relative to `src/story_architect/`.

## Problem

A draft is staged, the user approves a card, and only then does the write path
discover that a cross-entity rule forbids it. Measured shape:

```
agent: story_draft(action="stage", ops=[...scene takes main/climax...])
       → {preview_md, validation: []}          # nothing wrong reported
user:  approves the card
agent: story_draft(action="commit", draft_id=...)
       → {success: False, committed: [...], failed: {op, error}, draft_kept: True}
         "PlotRoleError: Plot 'main' already has its climax on scene 'first' — one scene per plot."
```

Staging is structural by design. `validate_ops` checks shape only
(`core/drafts.py:61-68`); `validate_shape` checks fields with no DB
(`:130-139`). Cross-entity rules are deliberately excluded from both: they
read committed state, and at *stage* time a staged create is not there yet.
(At commit, creates land before edits — which is why the replay below is
faithful.) Every such rule — `validate_scene_plot_roles`,
`validate_scene_location`, `check_references`, `validate_scene_dramatic_role`
— therefore fires at commit, and the commit funnel turns it into `⚠️ Partly
saved` (`core/drafts.py:389-404`, `:423-439`).

Three consequences:

1. **The card the user approves can be wrong.** The card is rendered
   automatically from a server snapshot (`app/mcp_server.py:80-107` →
   `web/js/chat-app.js:213` → `web/js/chat-render.js:186`), so the decision UI
   offers no warning the agent could have supplied.
2. **A batch partly lands before stopping**, then waits for the agent to
   re-stage the remainder. Correct and resumable by design, but it reaches the
   user as a failure after they said yes.
3. **The check cannot simply move into staging**: a stage-time check reading
   committed state produces false positives — a batch where one op frees a
   role another op takes looks identical to a real conflict until both have
   run (`drafts.py:320-329` sorts edits stably, so order matters).

## Target model

**Replay the batch for real against a throwaway copy of the project database,
then discard the copy.**

This is not a simulation. The existing `commit()` runs unchanged against the
copy, so op ordering, within-batch effects and every validator behave exactly
as they will at the real commit. There is no second copy of any rule, and no
class of false positive to reason about.

Two properties make it cheap:

- The draft row lives in the database, so copying *after* staging carries it
  along — `commit(temp_path, draft_id)` finds the ops with no extra plumbing.
- The write path is DB-only: no file under `core/` is written at all. A copied
  directory containing `.story/story.db` is therefore a whole project.
  (`get_db` may create `.story/`, but it writes no files.)

## Changes

| # | File | Change |
|---|---|---|
| 1 | `core/drafts.py` | New `dry_run(project_path, draft_id)`: copy `.story/story.db` into a temp dir **outside the project** using SQLite's backup API (WAL-safe — see `db.backup_database`, `:138-171`), call the existing `commit(temp_path, draft_id)`, return its result, and remove the temp dir in a `finally` on every path — the copy is gone before `stage` returns, on `refused` and on an exception alike. A failure to make the copy **or** a `commit` exception maps to `{"status": "unavailable", "error": str}`; the function does not raise. |
| 2 | `core/drafts.py:195-253` | `stage()`: after the draft row is written, run `dry_run` and add the verdict to the response — `{"dry_run": {"status": "clean"}}`, `{"status": "refused", "failed_op": str, "error": str}`, or `{"status": "unavailable", "error": str}`. Reuse `commit`'s own `failed`/`message`; do not restate them. |
| 3 | `tools/story_draft.py:118-121` | SCHEMA description: report `validation` **and** `dry_run`; if `dry_run.status` is `"refused"`, re-stage a corrected op list instead of presenting the draft. |
| 4 | `app/mcp_server.py:80-107` | Publish the approval card only when the stage's dry run is `clean`. A `refused` or `unavailable` stage publishes nothing; the agent acts on the verdict and re-stages. The card carries no verdict — it is the user-facing proposal, not the check. |
| 5 | `tests/test_draft_dry_run.py` | New: conflict caught, freeing-op batch passes, real project untouched, temp cleaned up, commit still refuses. |

## Isolation rules

This is the trust boundary. `stage` promises "writes nothing to the story"
(`tools/story_draft.py:127-130`) and `discard` promises "nothing it proposed was
ever written"; a dry run must not break either.

- The temp dir lives outside the project, and is removed on **every** path,
  including a dry-run exception — before `stage` returns, so a refused batch
  leaves nothing behind to retry against.
- Copy with `Connection.backup()`, never `shutil.copy`: the DB is in WAL mode,
  so a plain copy can miss recent commits.
- Do **not** reuse `db.backup_database` directly — it writes into
  `<project>/.story/`, i.e. the footprint this feature promises does not exist.
- The precondition is that the write path stays DB-only. If a future change
  makes a write touch files, the sandbox is no longer a whole project and the
  dry run must be revisited. The test asserts the **copy's** file set is
  unchanged by the replay (still only `.story/story.db` and its WAL/SHM
  sidecars), not the real project's: a write the replay makes lands in the
  copy, so a real-tree assertion passes over exactly the break this guards.

## What must not change

- **`commit()` stays the enforcer.** The dry run validates against state *now*;
  a race between it and the real commit still exists. Nothing downstream is
  weakened or removed.
- **No in-process simulation**, and no second implementation of op ordering or
  of any rule.
- **No threading a connection through the write paths.** That is the
  BEGIN/ROLLBACK route `commit` explicitly avoided (`core/drafts.py:339-346`).
- **The verdict does not go into `preview_md`.** The preview describes the
  proposal; the dry run describes our ability to apply it. Mixing them would
  make the approved text depend on a transient check.

## Agent-facing contract

- `dry_run.status == "clean"` → present the draft. The card appears
  automatically; say nothing about the check.
- `"refused"` → **do not present the draft.** Either fix the offending ops and
  re-stage silently (a technical inconsistency), or relay the conflict to the
  user when it is a story decision they should make.
- `"unavailable"` → the replay could not run: a sandbox problem, not a verdict
  about the batch. Relay the `error` to the user rather than presenting or
  silently re-staging. Most common causes: no usable temp directory
  (`FileNotFoundError: … No usable temporary directory`), a full disk
  (`OSError: [Errno 28]`), an unreadable source (`OperationalError: unable to
  open database file`, `DatabaseError: file is not a database`), a project with
  no built database yet (`OperationalError: no such table: drafts`).
- Report the verdict in the message alongside `validation` when it is not clean.

The card carries no verdict: it is presented only for a clean stage, so a card
on screen means the batch was checked and will commit.

## Rejected alternatives

- **Check at stage against committed state.** False positives: a batch whose
  first edit clears `main/climax` and whose second gives it to another scene
  reads as a conflict until both have run. Fixing this properly means
  simulating the batch, which is the complexity this design avoids.
- **BEGIN / ROLLBACK around a replay in-process.** Truer isolation, but
  `create_entity` runs in autocommit, so a shared transaction means threading a
  connection through every write path in the plugin.
- **Teach the agent to look first.** The data is readable today, but it is
  advisory: nothing forces the read, and a forgotten read is silent.
- **Commit for real, then undo.** Without a shared connection the real project
  would carry the writes and their WAL/journal; an undo path is a second way to
  write, which is the duplication this codebase keeps removing.

## Verification

```
.venv/bin/python -m pytest tests/test_draft_dry_run.py tests/test_drafts.py tests/test_draft_preview.py -q
```

Plus the probe, on a scratch project with two scenes:

- Stage a batch giving scene B the `climax` scene A already holds →
  `dry_run == {"status": "refused", "failed_op": ..., "error": "PlotRoleError: Plot 'main' already has its climax on scene 'a' — one scene per plot."}`
  and the real project unchanged (same entity/relation counts, no new files in
  the project tree).
- Stage a batch where one edit clears the `climax` and a later edit gives it to
  another scene → `dry_run == {"status": "clean"}` (the false-positive case,
  which is why this is a replay and not a check).
- Commit the refused draft for real → still refused, unchanged message
  (the backstop holds).
