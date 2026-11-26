# Task 43 — Execution plan

Status: **for confirmation.** Nothing written to a project yet.

Reads with: `01-candidates.md` (checklist), `04-decisions.md` (the decisions that bind).

Deliverable: a runnable generator that builds *The Wizard of Oz* demo — story plus a
**seven-draft history across two branches**, carrying a branch opened while the story was
still being written, a merge with a real resolved conflict, and a cut that restores — into
`~/white-words-studio/projects/<slug>`, verified by opening it in the app.

The history's shape is specified in `06-history-design.md`; this plan implements it.

---

## P0 — Where it lives

`~/white-words-studio/projects/demo`

Not `demo`. The `demo` slug currently holds the live *Save the Children* project, which is
moved to its own folder when this is committed. It ships as `demo`, the slug
`white-words seed-demo` writes, so the build and the shipped copy have one name.
and needs no migration to test.

The generator refuses to run if the target directory exists. Rerunning is a decision
(`--force`), never an accident.

---

## P1 — The generator

One file: `tasks/task_43/build_demo.py`. Run with the project venv:

```
.venv/bin/python tasks/task_43/build_demo.py [--force]
```

Why one file and not a package: it runs once, it is read by whoever audits the demo, and
every helper it needs (`create_project`, `create_entity`, `edit_entity`, `delete_entity`,
`drafts.stage/commit`, `store.*`, `session.*`) already exists. No new module in `src/`.

Structure, in the order it must run:

| Step | What | Why this order |
|---|---|---|
| 1 | `create_project` + project fields + 7 sections + `memory` | everything else references it |
| 2 | 2 worlds | locations point at them |
| 3 | 5 values | `value_turns` validate against them |
| 4 | 6 locations (incl. the variant) | scenes point at them |
| 5 | 9 live characters + 1 (the East witch) | plots and beats reference them |
| 6 | 5 plots | `value_turns` validate protagonists against them |
| 7 | 3 acts, 6 sequences | scenes need a `sequence_id` |
| 8 | 14 scenes: fields, headings, `Content`, sections | needs plots + sequences + cast + location |
| 9 | 14 `scene_beats` — the mechanism of each written scene | **reads the scene's `Content`** |
| 10 | 22 `value_turns` — edits on the scenes | **reads steps 8 + 9**; needs values + plots |
| 11 | 6 relationships, `scenes[]` filled | needs characters **and** scenes |
| 12 | project `memory` | last, so it can reference the whole |
| 13 | **history**: Draft 1 → branch → Draft 2 → Draft 3 → merge | needs a complete state |

### Why steps 9 and 10 come after the scene, not with it

A value turn is not a design decision made in advance. It is a **measurement of what the
scene actually does**: which value moves, from which rung to which, and how that lands on
each protagonist. It can only be honestly written once the action and dialogue exist,
because those are what move the value. The beat sheet is the same: it describes the
mechanism of a scene that has been written.

This is the repo's own design convention — declare the levers, then derive the
measurements. So:

- **Declared before the scenes** (the levers): values (ladders), plots (scope, type, cast,
  value arc), sequences, and each scene's `plot_roles`.
- **Derived after the scenes** (the measurements): `scene_beats`, then `value_turns`.

No validator enforces this order — `validate_scene_value_turns` checks plots, values and
protagonists, never the beats. It is a craft rule, and it is the reason the generator is
ordered this way rather than in the order that merely satisfies the validators.

Consequence for the plan's passes: the turns are written **while reading the finished
scene and its beats**, in one sitting per act, never invented ahead of the prose. If a
scene's prose and its turn disagree, the prose wins and the turn is rewritten.

Steps 1–11 run as one staged/comitted draft where the ops allow it (creates apply before
edits), so every op passes the real validators. Where an op cannot be expressed as a
create (setting `plot_roles` on a scene, `value_turns` after the value exists), it is an
`edit` in a later batch — the same two-batch shape the agent itself uses.

**Every step asserts.** A generator that prints "done" is not evidence. Each phase ends
with a count assertion (14 scenes, 5 plots, 22 value turns, 6 relationships) and a check
that no entity has an unfilled required field. `story_load view="unfilled"` is the reader;
if it reports gaps, the build fails.

### The one thing the generator must not get wrong

Probe-verified trap: **an empty selection applies zero ops and returns `status: "applied"`**.
The merge step therefore asserts:

- `selection` is non-empty before `set_selection`;
- `plan["ops"]` is non-empty before `apply`;
- `result["applied"]` is non-empty after `apply`;
- the chosen field holds the expected value afterwards.

Without those four asserts, a broken merge demo reports success.

Second probe-verified trap: merge items carry **`state`**, not `status`
(`added|removed|changed|conflict|unchanged`). Filtering on `status` silently selects nothing.

---

## P2 — Content: what gets written

The prose is written by me in this session, in the plan's own files, then read by the
generator from JSON — not embedded as Python string literals. One `content.json` beside the
script, so the story text is reviewable without reading code and editable without touching
the builder.

```
tasks/task_43/
  content/
    project.json          project fields + 7 sections + memory
    worlds.json           2 worlds, all 8 sections each
    values.json           5 ladders
    characters.json       10 characters, all 9 sections each
    locations.json        6 locations, all 6 sections each
    plots.json            5 plots, all 6 sections each
    structure.json        3 acts + 6 sequences, all sections each
    scenes.json           14 scenes: fields, plot_roles, all 8 sections, Content in Fountain
    beats.json            14 scene_beats records
    turns.json            22 value turns
    relationships.json    6 relationships, both perspectives, all 6 sections
    history.json          the three drafts, the branch, the merge and its expected result
```

This is the bulk of the work and it is writing, not engineering. Split across four passes so
each is reviewable on its own:

- **P2a** — project, worlds, values, locations, characters (the standing set).
- **P2b** — plots, acts, sequences (the structure — the levers).
- **P2c** — the 14 scenes: fields, headings, `Content`, all eight sections each.
- **P2d** — the 14 beat sheets, read against the prose of P2c.
- **P2e** — the 22 value turns, read against P2c + P2d, one act at a time.
- **P2f** — the relationships. **Moved before P2d**: a beat's `changes[].entity` may name a
  relationship, so the relationships have to exist first. This was found by the validator,
  not by design.

I will show you P2a before continuing, because if the voice or the level of detail is wrong,
everything after it is wrong in the same way. Same again at the end of P2c (the scenes are
the thing the demo is judged on) and at the end of P2e (the value tracking is the feature
the story was chosen for).

Nothing is written into a project until every pass is written. The generator reads the JSON;
the JSON is the deliverable that gets reviewed.

### Voice and length targets

- `Content`: 25–40 lines of Fountain per scene. Real dialogue, not narration — the duration
  statistics depend on it. Minimum 2 speaking characters per scene except the deliberate
  `no_cast` and the solo scenes.
- Sections: 60–150 words each. Enough to be worth reading, not a novel. The demo's job is to
  show the *shape* of a filled section.
- `scene_beats`: 4–6 beats per scene, each with action/reaction `by`+`surface`+`subtext`,
  and a `gap` on most. `true_character` on 6 of the 14. `changes` on 9.
- Total estimated screenplay: ~420 lines, ~15 pages. Plausible for a 14-scene short.

---

## P3 — The history: five passes, seven drafts, one merge

Full rationale and the per-scene status table are in **`06-history-design.md`**, which is
the binding document for this section. P3 implements it; it does not re-argue it.

The shape, in one line: **all three acts and six sequences exist from Draft 1**, and
incompleteness is expressed only as scene status and unwritten prose, spread unevenly
across all three acts. No draft ever appends an act.

| # | Draft | Branch | Pass |
|---|---|---|---|
| 1 | Structure and the first scenes | main | incomplete |
| 2 | Pushing into the middle | main | incomplete |
| 3 | Lion, second attempt | `lion-arc` | incomplete — **branch** |
| 4 | Draft 2, continued | main | incomplete |
| 5 | First full draft | main | complete |
| 6 | Notes from the read | main | refinement — **the cut** |
| 7 | Locked pass | main | refinement |

### Order of operations, and why

| Step | Call | Assert |
|---|---|---|
| 1 | create the project, acts, sequences, plots, cast, **all 15 scene rows** | acts = 3, sequences = 7, scenes = 15 |
| 2 | write the Draft-1 prose set (the D1 column of the table) | each written scene has non-empty `Content`; each `planned` one has sections but no prose |
| 3 | `save_snapshot("Draft 1 — Structure and the first scenes")` | labels the first draft; returns `Draft 1` |
| 4 | write the Draft-2 prose set | statuses match the D2 column |
| 5 | `save_snapshot("Draft 2 — Pushing into the middle")` | parents = [D1] |
| 6 | `branch_from(D2, "lion-arc")` then `switch` | current branch is `lion-arc` |
| 7 | rewrite the Lion on the branch | his `one_sentence` differs from main's |
| 8 | `save_snapshot("Draft 3 — Lion, second attempt")` | parents = [D2] |
| 9 | `switch("main")`, write the Draft-4 set | current branch is `main` |
| 10 | `save_snapshot("Draft 4 — Draft 2, continued")` | parents = [D2] |
| 11 | `session.start(main, {kind: branch, id: lion-arc})` | base resolves to D2 |
| 12 | select the conflict item, answer `#D2` = `theirs` | `ready` true, `open` empty |
| 13 | `preview` → `apply` | `applied` non-empty |
| 14 | assert the Lion holds the branch's sentence | exact string match |
| 15 | write the Draft-5 set: the last scenes close | all 15 `written` |
| 16 | `save_snapshot("Draft 5 — First full draft")` | every scene `status == "written"` |
| 17 | cut the poppy field: `delete_entity(..., confirm=True)` | trash = scene + its beats; **not** the Queen |
| 18 | `edit_entity` the two locked scenes | `locked` on 2 |
| 19 | `save_snapshot("Draft 6 — Notes from the read")` | 14 live scenes |
| 20 | `save_snapshot("Draft 7 — Locked pass")` | graph has 7 nodes, 2 branches, 1 merge edge |

Steps 3 and 5–20 each need a **real difference** from the previous draft or `save_snapshot`
refuses with "nothing has changed". That refusal is the check that every draft is a draft.

### Three traps this section exists to prevent

1. **`adopt()` before the first `save_snapshot()` burns the naming path**, and the save then
   fails as "nothing has changed". The first call on a fresh project is `save_snapshot`,
   which adopts *and* names.
2. **A branch must be saved before it can be merged.** A merge contributes the branch's
   saved draft, not its unsaved head. Step 8 is not optional.
3. **`custom` silently degrades to `theirs`.** Verified: it applies their value unchanged
   with `status: applied` and no error, because no caller supplies a custom value. The demo
   uses `theirs`. See `06-history-design.md` §3 — this is a finding for task 42's UI work,
   not something the demo should paper over.

The four merge asserts from the earlier draft of this plan stand: selection non-empty,
`plan["ops"]` non-empty, `result["applied"]` non-empty, and the field holding the expected
value afterwards.

## P4 — Verification

Three levels, each of which must pass before the next.

**P4a — data** (in the generator, always):
- no unfilled required field on any live entity;
- counts: 1 project, 2 worlds, 5 values, 6 locations, 10 characters (9 live), 5 plots,
  3 acts, 6 sequences, 14 scenes, 6 relationships, 14 beat sheets;
- 22 value turns; every plot has ≥3; every conflict level ≥2;
- every enum value intended is present: 5 `story_role`s, 4 `scene.status` values, 3
  `dramatic_role`s, 4 `int_ext`s, 3 `plot_type`s, 3 `relationship.status` values.

**P4b — history** (in the generator, always):
- the branch graph is the shape in `06-history-design.md` §2, as revised: 10 drafts, four
  branches (`main`, `lion-arc`, `tighten-act-two`, `the-ending`), forks at Draft 2 and Draft
  7, **two completed merges recorded as two-parent drafts**, and `the-ending` left open with
  one unresolved conflict;
- **Draft 1 already holds all 3 acts, 7 sequences and 15 scene rows** — no act is appended
  later, in any draft;
- Draft 1's spread is uneven across acts: at least one scene `written` in each of the three
  acts, and at least one `planned` in Act II;
- the merge's conflict was real (`state: "conflict"`) and resolved (`ready` true);
- `applied` non-empty, and the Lion holds the branch's exact sentence afterwards;
- the trash holds **exactly** `the-poppy-field` and `the-poppy-field-beats` — the Queen is
  live and unplaced, not trashed;
- `restore_check` on the scene reports no blockers and no collisions, and restoring returns
  it to order 3 under `seq-the-road`.

**P4c — the app, by hand** (you):
1. Open the project. Story view: stats grid, logline, spine, controlling idea, value focus
   with 3 major + 2 minor, and the two key-scene links.
2. Character web: 6 relationships, both signs of strength, no orphans.
3. Character journey tab on Dorothy: value paths across acts.
4. Scenes: 14 in **7 sequences**, 3 acts, status colours, role tags, the cut scene absent,
   and `the-gates` showing the tightened cast (the Lion out).
5. Script view: headings compose, dialogue renders, statistics show a real action/dialogue
   split.
6. Values: 5 ladders, story and per-plot views, act filter.
7. Plots: 1 main + 4 sub, three different badges, six role lists populated on the main plot
   (the subplots carry no crisis or climax by design).
8. Relationships: both perspectives, the `secret` badge on the Wizard, the trashed-end case.
9. Locations: the `variant_of` tag on the Emerald City after.
10. Trash: scene 13 + the Queen, restore preview clean.
11. Projects/history page: **10 drafts, 4 branches**, **two merge edges**, forks at Draft 2
    and Draft 7, and `the-ending` shown open with one conflict.
12. Open Draft 1: the structure was already there — 3 acts, 7 sequences, 15 scenes, most
    `planned`, and the ending scenes written before the middle ones.

A checklist file `tasks/task_43/verify.md` with these eleven steps and a blank beside each,
so the pass/fail record outlives the session.

---

## P5 — When it is right

Not part of the build, recorded so it is not lost:

- the `demo` slug is freed and *Save the Children* moves to its own folder;
- this project is renamed or copied to `demo`;
- the generator is kept, because a demo that cannot be rebuilt rots. It is the answer to
  "how was this made?" for as long as the demo ships.

---

## Commit plan

| Commit | Contents |
|---|---|
| 1 | `tasks/task_43/` docs (`01`–`04`, this plan) |
| 2 | `build_demo.py` + `content/*.json` |
| 3 | `verify.md` with the filled record |

Commits 2 and 3 wait until you have opened the project and the checklist is honest.

---

## Pacing

This is expected to take several sessions, and a pass is finished when it is right, not when
it exists. Each pass ends with the JSON written and shown; nothing proceeds to the next pass
on the same turn it was started unless the pass is short. The order of work is the plan's;
the speed is not.

---

## What this plan does not do

- No new module in `src/`. The generator is a script under `tasks/`.
- No change to the schema, the validators, or the UI.
- No versioning agent tools — that is T11's separate work.
- ~~No complete merge (`complete=True`)~~ — **superseded.** Two merges on the demo are complete,
  because a finished merge is only visible as a two-parent draft, and a demo that shows only
  the open case shows half the feature. A complete merge needs a *snapshot* source: a branch's
  unsaved head is accounted for by no draft.
- ~~No third branch~~ — **superseded.** Four branches, because the refinement phase opens two
  from the same draft, one merged and one still open.
- No **location** change in the script-level rewrite. Moving `the-gates` would put Act II's
  scene in Act III's sequence; the engine merges `location_id` fine, the demo does not need a
  third structural move.
- No `custom` conflict resolution, because it does not work yet (see P3, trap 3).

---

## Open, needing your answer before P2a

**Answered (owner, 2026-11-26):**

1. **Slug:** `demo` (shipped); the *display* name is `The Wizard of Oz` — folder and title are
   separate fields and should not look alike.
2. **Voice:** whichever is easiest to write. Taken as plain and declarative: short
   sentences, no flourishes, the story's own words. Note the useful side effect — the
   screenplay's `Content` stays plain too, so the dialogue/action split the statistics show
   is a real reading rather than a style artefact.
3. **Sections:** the short end of the range, **30–60 words**. Enough to show the section is
   real, not so much that it reads as worked prose.

Then P2a is the first thing I write, and it stops there for your review.
