# Task 43 — Decisions and revised design

Supersedes `03-story-design.md` where they differ. Decisions D1–D3 are the owner's,
from the session of 2026-11-26.

---

## D1 — 14 scenes. Confirmed.

## D2 — One main plot. Confirmed.

`The humbug` becomes a **sub** plot, `plot_type: Complicating`, protagonists
dorothy + the-wizard. There is exactly one `plot_scope: main` plot.

Consequence to accept: the story's argument (that the Wizard is a fraud) now lives in a
subplot, so the main plot must carry its own value arc cleanly on `home` alone. That is
the common case in real screenwriting and is exactly why it is the right demo.

The four subplots and their types:

| Plot | Type | Value | Protagonists |
|---|---|---|---|
| There's no place like home | *(main)* | home | dorothy |
| A brain | Contradictory | mind | scarecrow |
| A heart | Resonant | heart | tin-man |
| A nerve | Complicating | courage | lion |
| The humbug | Complicating | belief | dorothy, the-wizard |

Two subplots share `Complicating`. That is deliberate rather than lazy: the plots view
badges by `plot_type`, and the demo should show that two plots of the same type is a
normal state, not an error. `Setup` remains unused — a subplot that exists only to launch
the main one is padding.

## D3 — Status is a two-phase story, and the draft history is built to show both phases

The owner's framing: **a writer goes through an incomplete phase and then a refinement
phase.** In the incomplete phase the story is being built — scenes are `planned`,
`drafted`, some `written`; decisions are still being made; the story can branch. Once the
story is fully written, later drafts *refine* it — every scene is `written`, and the work
is about narrative problems, not about filling gaps.

This is the spine of the demo's history, and it means **scene status is not a cosmetic
mix**. It is the honest record of which phase each draft was made in.

### The two phases as drafts

| Draft | Phase | Scenes | What the draft is |
|---|---|---|---|
| **Draft 1 — "First pass"** | incomplete | 8 of 14 `written`, 4 `drafted`, 2 `planned` | The story as it stood when the writer stopped to save. Two scenes not yet started. |
| **Draft 2 — "First full draft"** | incomplete → complete | all 14 written, but two of them thin | Every scene now exists. The story is whole for the first time. |
| **Draft 3 — "Notes from the read"** | refinement | all 14 `written`, one `locked` | Refinement: a subplot tightened, one scene cut, the ending changed. |

`locked` appears **only in Draft 3**, on one scene. Its meaning is exact: this scene is
not being touched again in this pass. A demo where every scene is `locked` claims a
finished screenplay and leaves nothing for the reader to imagine doing; one locked scene
shows the status exists and what it is for.

The `planned` scenes in Draft 1 are the visible proof of the incomplete phase. They are
also the reason the truncation finding below matters.

---

## 4. Finding — a `planned` scene is a stub to the agent and a full scene to the user

Verified in the code:

- `core/db.py:855` — `_is_scene_stub(s)` returns `s["status"] == "planned"`.
- The **dashboard** payload (`get_dashboard_data`) does **not** strip stubs. It builds every
  scene with its full fields, so the user sees a `planned` scene rendered normally.
- The **`story_load`** map does strip them, to `{"id": ...}` plus characters.
- `get_unfilled_map` skips them entirely ("maximally unfilled by definition").

This is correct behaviour, not a bug, and it is worth recording because it decides how the
demo must be built: **a `planned` scene still needs its `title`, `sequence_id`, `order` and
sections to be written**, because those are what the dashboard draws. The agent will not
see them; the user will.

Consequence for the demo: the two `planned` scenes in Draft 1 are real, readable scenes
whose prose is not written yet. They are not empty shells.

---

## 5. Revised scene table

Fifteen scenes are written; fourteen are live in the final state, because one is cut in
Draft 3. `dramatic_role` is fixed for the story; only the status moves.

| # | Seq | Scene | D1 | D2 | D3 (final) | dramatic_role |
|---|---|---|---|---|---|---|
| 1 | 1.1 Kansas | The farm at dusk | written | written | written | plot_role |
| 2 | 1.1 Kansas | The cyclone | drafted | written | **locked** | **transition** |
| 3 | 1.2 Munchkinland | The house lands | written | written | written | plot_role |
| 4 | 2.1 The road | The Scarecrow | written | written | written | plot_role |
| 5 | 2.1 The road | The Tin Man and the Lion | written | written | written | plot_role |
| 6 | 2.1 The road | The poppy field | written | written | **trashed** | **non-event** |
| 7 | 2.2 Emerald City | The gates | drafted | written | written | plot_role |
| 8 | 2.2 Emerald City | The audience with the Wizard | **planned** | written | written | plot_role |
| 9 | 2.3 The Witch | The monkeys | written | written | written | plot_role |
| 10 | 2.3 The Witch | The castle | drafted | written | written | plot_role |
| 11 | 3.1 The humbug | The melting | written | written | written | plot_role |
| 12 | 3.1 The humbug | Behind the curtain | **planned** | written | written | plot_role |
| 13 | 3.2 The return | The balloon | drafted | written | written | plot_role |
| 14 | 3.2 The return | The goodbyes | written | written | written | plot_role |
| 15 | 3.2 The return | Glinda, and home | written | written | written | plot_role |

Scene 6 is the **cut scene**: written and real in Drafts 1 and 2, deleted in Draft 3 as part
of the refinement. It sits where it belongs — on the road, in Act II, between the companions
and the city — so cutting it is a writer's decision about the story, not a way to make a
diff visible at the end. The cut leaves 14 live scenes and renumbers Act II's remaining
scenes, which is itself a visible change in the diff.

The 6 sequences (2 per act) and the 3 acts are fixed across all drafts; only the scenes
inside them move.

---

## 6. The history narrative

> **Superseded by `06-history-design.md`.** The two-phase insight below still holds; the
> three-draft history does not. The owner's later correction — that the incomplete phase is
> not progressive by act, and that all three acts exist from the first draft — is what the
> demo now builds. Read §6 for the reasoning, `06` for the design.

Five states, one branch, one merge. Deliberately modest — the point is legibility, not
exhaustiveness.

```
Draft 1 (first pass) ── Draft 2 (first full draft) ── Draft 3 (notes) ── main, in progress
        └── branch "poppy-field" ────────────────────────────┘  (merged into Draft 3)
```

1. **Draft 1 — First pass.** 9 written, 4 drafted, 2 planned. The two planned scenes are the
   ones the writer had not reached.
2. **Branch `poppy-field`** from Draft 1, at the moment the writer decided the poppy field
   was worth more than it looked and began expanding it.
3. **Draft 2 — First full draft** on `main`: all 15 written. The story is whole for the first
   time, including the poppy field as a proper `no_cast` set piece.
4. **On the branch**: scene 6 is expanded further — the field becomes a real sequence with
   the Queen of the Field Mice brought back to life in it, which is the second trashed
   character and the reason the branch's version references her.
5. **Draft 3 — Notes from the read** on `main`: scene 6 is **cut** (trashed with the Queen),
   scene 2 is **locked**, the title page's draft label moves to "Third Draft". This is the
   refinement phase, and the scene count drops from 15 to 14.
6. **Merge** `poppy-field` into `main`. The conflict is real and visible:

   | Item | Ours (main) | Theirs (branch) | Resolution |
   |---|---|---|---|
   | scene 6 (the poppy field) | deleted | expanded, with the Queen restored | **Mine** — the cut wins |
   | `the-wizard.one_sentence` | refined in Draft 3 | untouched | **Mine** (auto — no conflict) |
   | The Queen of the Field Mice | absent | restored with the scene | **dropped** as a dependency of the losing item |

   That is D2 (a decision the user answers), D8 (cleanup after removal, unticked) and the
   cherry-pick-vs-complete-merge distinction, all in one merge, and the winning answer is one
   a writer would actually give.

The merge is a **cherry-pick** (records no parent). A second, complete merge is *not* part of
the demo: one merge is enough to show the mechanism, and a second would add a dashed parent
edge without teaching a new idea. Say so if you want the complete-merge case demonstrated
too — it is a one-line change to the generator and one more edge in the graph.

---

## 7. Characters — revised for D2

The trashed pair becomes a **parent/child group** so the bin shows a real containment
relationship and `restore_check` has something to report:

| Character | Role | Draft 1 | Draft 3 |
|---|---|---|---|
| Dorothy Gale | Protagonist | live | live |
| The Wicked Witch of the West | Antagonist | live | live |
| The Scarecrow | Supporting | live | live |
| The Tin Woodman | Supporting | live | live |
| The Cowardly Lion | Supporting | live | live |
| The Wizard of Oz | Supporting | live | live |
| Glinda | Supporting | live | live |
| Aunt Em | Minor | live | live |
| The Guardian of the Gates | Cameo | live | live |
| The Queen of the Field Mice | Minor | live | **trashed** (with scene 13) |
| The Wicked Witch of the East | Minor | live (no scenes) | live (no scenes) |

Correction carried: **the Witch of the East is never deleted.** She dies in the story, not
in the database. She has no scenes at all, is referenced by her sister's `family`
relationship, and is the case that proves a cast member can exist without appearing.

The Queen is the one character the bin holds, and she goes there because her scene went
there — cascaded, not invented, and restorable as a pair with scene 13.

---

## 8. What remains unchanged from `03-story-design.md`

Values (5), relationships (6), locations (6), worlds (2), the `variant_of` instance, the
`no_cast`/`forced_heading`/`transition`/`non-event` cases, and the knowledge map. The
plot table changes only in that `The humbug` is now `sub` / `Complicating`.

---

## 9. Still open, and offered rather than asked

- **Complete merge.** Not included. Add if you want the second parent edge demonstrated.
- **A second branch.** Not included. The demo shows branching works with one branch; a
  second would add a lane without a new idea.
