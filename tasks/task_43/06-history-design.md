# Task 43 — The history: what the demo shows about writing

Status: **confirmed by the owner, 2026-11-26.** Supersedes §6 of `04-decisions.md`.

Reads with: `05-plan.md` (P3 is rewritten from this).

---

## 1. The correction this file exists for

An earlier plan had the history run: write the whole story, save it, then branch and
merge. The owner rejected that shape twice, and both corrections are structural.

**Correction 1 — the incomplete phase is not optional.** A writer's process includes
*writing* the story, not just refining a finished one. Branching and merging happen
during that, because that is when decisions are still open. A demo whose history starts
with a complete story teaches that version control is for afterwards.

**Correction 2 — the incomplete phase is not progressive by act.** The demos must not
imply "write Act I, then Act II, then Act III". That is a legitimate way to work and it is
not the one we want to endorse. A writer **defines the structure first**: all three acts
and all six sequences exist from the start, and what varies is how much is filled
*inside* them. The acts are the plan; the scenes are the progress.

This is the demo's single most important indirect lesson, because a reader who copies the
shape will copy this ordering. So:

> **The three acts and six sequences are created in the first draft and never added to
> later.** Incompleteness is expressed only as scene status and unwritten prose, spread
> unevenly across all three acts.

An uneven spread is the point. A skeleton with Act I finished and Acts II–III untouched
would still read as progressive. The real shape is a writer who jumped to the ending
early because they knew what it was, left the middle soft, and went back.

---

## 2. The five passes

Seven drafts, two branches, one merge carrying a real conflict, one cut. Names are what
appear in the app; nothing here is a session artefact.

| # | Draft | Branch | Phase | What the writer did |
|---|---|---|---|---|
| 1 | **Draft 1 — Structure and the first scenes** | main | incomplete | The three acts, six sequences, five plots, the cast, and the scenes the writer could already see. Roughly a third of the prose. |
| 2 | **Draft 2 — Pushing into the middle** | main | incomplete | More scenes written across all three acts. The middle is still soft. |
| 3 | **Draft 3 — Lion, second attempt** | `lion-arc` | incomplete | A branch off Draft 2. The Lion's arc is rewritten where it does not work. **The story is incomplete while this branch exists.** |
| 4 | **Draft 4 — Draft 2, continued** | main | incomplete | Main keeps moving while the branch is open. The two sides now diverge on a half-written story. |
| 5 | **Draft 5 — First full draft** | main | incomplete → complete | After the merge, the last scenes close. The story is whole for the first time. |
| 6 | **Draft 6 — Notes from the read** | main | refinement | A subplot tightened, one scene cut, the ending changed. |
| 7 | **Draft 7 — Locked pass** | main | refinement | The scenes that are finished are marked `locked`. |

Branches: `main` and `lion-arc`. Merge: `lion-arc` → `main`, opened after Draft 4 and
closed to produce the state that becomes Draft 5.

### Why the merge sits between drafts 4 and 5, not at the end

A merge that happens after the story is finished demonstrates version control. A merge
that happens while the story is still being written demonstrates **how a writer resolves a
disagreement with themselves**. The second is what the feature is for, and it is the one
the demo shows.

---

## 3. Where the conflict lives

A three-way merge only produces a real conflict (`state: "conflict"`, an unanswered
decision, `ready: false`) when **both sides change the same thing differently**. Verified:
when the two sides edit different fields the planner emits `take` and `keep`, with no
conflict and no decision at all. A merge demo without a deliberate same-field collision is
a merge demo with nothing in it.

The conflict is the **Lion's `one_sentence`** — one field, both sides, differently:

| Side | Value |
|---|---|
| `main` (Draft 4) | `A lion who is frightened of everything and charges the castle anyway.` |
| `lion-arc` (Draft 3) | `A lion whose fear everyone reads as bravado, who is braver than he knows.` |

Why this field:

- It is the field the app shows on every card, so the conflict is legible without opening
  anything.
- Both versions are *defensible readings of the same character*, which is what a real
  conflict looks like — not a typo versus a correction.
- It is a character, not a scene, so the conflict does not disturb scene numbering and can
  be read on its own.

Resolution: **`theirs`** — the branch's reading wins, because the branch exists precisely
to argue it.

> `A lion whose fear everyone reads as bravado, who is braver than he knows.`

### Finding — `custom` is offered but does nothing

`D2` lists `("mine", "theirs", "custom")`, so the UI will show three choices. But no caller
supplies a custom value: `set_decision` takes only a choice string, the decision record
stores only `{"choice": …}`, and `_emit_change` reads `item["theirs"]` for both `theirs`
and `custom`.

Verified end to end: choosing `custom` on a real conflict applied **their value unchanged**,
with `status: applied` and no error. It is `theirs` wearing a third button.

Consequences, and they are not this demo's to fix:

- **The demo must not use `custom`.** It would show a feature that silently does nothing,
  which is worse than not showing it. `theirs` is used, and `mine`/`theirs` alone is a
  complete, honest story about resolving a conflict.
- **The draft-versioning UI work needs a decision** on `custom` before it ships: either it
  gains a value-supplying path (`set_decision(..., choice="custom", value=...)` through
  `session` into `_emit_change`), or it is removed from `D2`'s options. Leaving a button
  that quietly does the same thing as its neighbour is the kind of thing a demo exposes and
  a spec never does.
- Recorded as an issue rather than fixed here: this is task 42's feature, and changing the
  merge executor is out of scope for a demo build.

---

## 4. Incompleteness, act by act

Drafts 1–4 hold all three acts and all six sequences. What changes is the prose inside
them, and it is deliberately uneven.

One ordering detail the table makes visible: scene 6, the poppy field, is `written` in Draft
2 and cut in Draft 6, so it is never trashed *and* never a gap. It is a real scene in five
drafts and then it is gone — which is what makes its trash entry worth restoring.

| Scene | Act | D1 | D2 | D3 (`lion-arc`) | D4 (main) | D5 | D6 | D7 |
|---|---|---|---|---|---|---|---|---|
| The farm at dusk | I | written | written | — | written | written | written | **locked** |
| The house lifts | I | written | written | — | written | written | written | **locked** |
| The house lands | I | drafted | written | — | written | written | written | written |
| The Scarecrow | II | written | written | — | written | written | written | written |
| The Tin Man and the Lion | II | planned | drafted | **written** | drafted | written | written | written |
| The poppy field | II | planned | written | — | written | written | **trashed** | trashed |
| The gates | II | planned | written | — | written | written | written | written |
| The audience | II | planned | planned | — | **written** | written | written | written |
| The monkeys | II | planned | drafted | — | drafted | written | written | written |
| The castle | II | planned | planned | — | planned | written | written | written |
| The melting | III | **written** | written | — | written | written | written | written |
| Behind the curtain | III | **written** | written | — | written | written | written | written |
| The balloon | III | drafted | drafted | — | drafted | written | drafted | written |
| The goodbyes | III | planned | planned | — | planned | written | written | written |
| Glinda, and home | III | planned | planned | — | planned | written | written | **locked** |

`—` means the scene is not on that branch at all, or was not touched by that draft.

Read the Draft 1 column: Act I is nearly done, **Act III is already half written**, and
Act II is the softest. That is a writer who wrote the opening, jumped to the ending they
could already see, and left the middle for later. It is not progressive, and it is not
arbitrary.

Draft 2 pushes into the middle. Draft 3 branches to fix the Lion, whose scene is the
softest thing in Act II — which is exactly why a writer would branch there rather than
after finishing.

---

## 5. What each pass demonstrates

| Pass | The feature it exposes |
|---|---|
| D1 | A project that is not a story yet; all structure declared, most prose absent. `planned` as an honest status. |
| D2 | Progress as a diff: statuses moving, prose appearing, structure unchanged. |
| D3 | Branching **during** the work. A branch whose base is an incomplete draft. |
| D4 | Divergence: two sides of a half-written story. |
| Merge | A real conflict, three ways to answer it, `custom` chosen. |
| D5 | The complete story for the first time. Every scene `written`. |
| D6 | Refinement: a cut, a renumber, a trash entry that can be restored. |
| D7 | `locked` as a claim about this pass, not about the story. |

Plus, carried by the structure rather than any single draft: `variant_of`, `no_cast`,
`forced_heading`, `transition`, `non-event`, four `int_ext` values, five `story_role`s,
three `relationship.status` values, five plot ladders including one ending on `nn`, and a
cast member (the Witch of the East) who is dead, present, and in no scene.

---

## 6. The trash, precisely

The cut is **the poppy field**, in Draft 6. It is the honest cut: it sits in Act II between
the companions and the city, it is a `non-event` that moves no plot, and Draft 6 is
refinement — the phase where a writer removes what the story does not need.

### What the delete actually takes, verified

```
would_delete:        ['the-poppy-field', 'the-poppy-field-beats']
cascade_children:    [{'id': 'the-poppy-field-beats', 'type': 'scene_beats'}]
affected_relationships: []
live scenes after:   14
trash:               ['the-poppy-field', 'the-poppy-field-beats']
```

Two rows, not three. **The Queen of the Field Mice is not trashed**, and an earlier draft of
this document said she was. She is *referenced* by the scene, not a child of it: the cascade
follows `parent_id` (the scene's `scene_beats`), and a referenced character is not a
contained row. She is also not in the scene's cast, because the poppy field is `no_cast` —
her rescue is narrated by the Tin Man and happens off screen.

That is the more honest outcome anyway: a cut scene's cast survives the cut, which is what a
writer would expect. The demo's trash holds a scene and its beat sheet.

### Restore, verified

```
blockers:  []      collisions: []      warnings: {}      placement: None
returned:  children [the-poppy-field-beats], relations 0, sections 8, referenced_by []
restore  → ['the-poppy-field', 'the-poppy-field-beats'] restored
live scenes: 15    Act II order: The Scarecrow 1, The Tin Man and the Lion 2, The poppy field 3
```

The scene comes back to its own position between the two scenes it sat between, with its
eight sections and its beats. No blockers because its parent sequence is live; no collisions
because a `non-event` holds no plot role. That restorability is the whole point — the demo
shows a deletion you can come back from.

The Queen stays live and unplaced throughout: a `Minor` character with one relationship and
zero scenes, which is the demo's other case — someone in the cast who is not in the story,
alongside the dead Witch of the East.

---

## 7. Constraints this puts on the generator

1. **All three acts and all six sequences are created before the first `save_snapshot`.**
   Never appended later, in any draft.
2. **Every scene row exists in Draft 1**, including the `planned` ones, with its title,
   sequence, order and sections filled. A `planned` scene is a readable stub to the user
   and an invisible stub to the agent; it is never an empty shell (`04-decisions.md` §4).
3. **The prose is written in five passes**, matching the status table above; a scene's
   `Content`, sections, beats and value turns arrive together, because a beat sheet
   describes a scene that exists.
4. **A draft is only saved when something actually changed.** `save_snapshot` refuses an
   unchanged head, and each of the seven saves must be a real difference.
5. **The first `save_snapshot` is the one that names Draft 1.** Calling `adopt()` first
   burns the naming path and the save then fails as "nothing has changed".
6. **The branch is saved before it is merged.** A merge contributes a branch's *saved
   draft*, not its unsaved head, so `lion-arc` must save Draft 3 before the merge will
   offer anything.
7. **The merge asserts four things**: selection non-empty, `plan["ops"]` non-empty,
   `result["applied"]` non-empty, and the Lion's field holding the branch's sentence
   afterwards. An empty selection applies zero ops and still reports `applied`.
8. **Call shapes, verified** — the obvious ones are wrong:
   - `trash.restore_check(conn, entity_id, also_restoring=())` takes a **connection**, not a
     path.
   - `trash.restore(project_path, entity_type, entity_id, summary)` takes the project first
     and the type second.
   - `delete_entity(...)` **returns** a preview payload without `confirm`, it does not raise.
   - `session.show()` nests the plan: `show()["plan"]["ready"]`, not `show()["ready"]`.
