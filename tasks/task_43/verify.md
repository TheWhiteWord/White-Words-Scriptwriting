# verify.md — the demo, read in the app

`~/white-words-studio/projects/demo` (`white-words seed-demo` puts it there). Open it and
work down the list.

A tick means it was seen, not that it was built. Anything that fails is a finding against
the app or the demo, and goes in the last column rather than being fixed quietly here.

**Before you start:** the project is on branch `main`, at `After Tighten Act II`. The last
draft on `main` is `After Tighten Act II`; `the-ending` holds an unresolved draft that is
not on `main`.

---

## 1. Story view

| Check | Seen |
|---|---|
| Stats grid: 14 scenes, 13 characters, 8 locations, 5 plots, 3 acts, 7 sequences, 2 worlds | ☐ |
| Logline from the project's `one_sentence`, not empty | ☐ |
| Spine and controlling idea render | ☐ |
| Value focus: **1 major (`home`) + 4 minor** (`mind`, `belief`, `courage`, `heart`) | ☐ |

**Expected, not a bug:** value focus is *computed* from the scenes' `value_turns`
(`core/value_focus.py`), never stored. One major is correct here — `home` is the only value
carried by the main plot; the other four are each a subplot's value.

---

## 2. Character web

| Check | Seen |
|---|---|
| 12 relationships, no orphans (every character appears or is deliberately unpaired) | ☐ |
| Both signs of strength: positive (`dorothy-toto` +1.0/+1.0) and negative (`wicked-witch-of-the-west-dorothy` −0.9/−0.5) | ☐ |
| The `secret` badge (🔒) on `the-wizard-guardian-of-the-gates`, the Wizard's perspective | ☐ |
| A `complex` status relationship renders (`the-wizard-wicked-witch-of-the-west`, `glinda-wicked-witch-of-the-west`) | ☐ |

**Cast is presence, not speech.** Everyone on set is in the cast whether or not they have a
line — background players still have to be on set for the filming.

The generator asserts the decidable half: every registered character who **speaks** is in the
cast. The other half — everyone on set is in the cast — is a **reading of the scene, not a
derivation**. Presence without a name can't be read off the text: Toto is "a dog in her lap"
in the opening, the Tin Man is one of "the three of them" at the close. Beats don't settle it
either, because a beat can be played from offstage — the Witch sends the monkeys from
somewhere that is not the road, and putting her in that cast would be wrong.

So keep cast lists true by reading the scenes. `the-house-lifts` is `no_cast` (the cyclone
lifts an empty house) and is exempt.

The schema settles the meaning: `characters` is *"Character slugs present in this scene"* —
presence, not speech. So the touring party is on set from the moment it forms: Dorothy,
Scarecrow, Tin Man, Lion, and Toto, who is never separated from Dorothy and is in her arms
from the cyclone onward.

Seven scenes were corrected on this reading:

| Scene | Correction |
|---|---|
| `the-farm-at-dusk` | +Toto ("a dog in her lap") |
| `the-house-lands` | +Toto ("holding the dog") |
| `the-scarecrow` | +Toto (with her on the road) |
| `the-monkeys` | −Wicked Witch (offstage); +Toto ("the dog held against her") |
| `the-castle` | +Toto ("the dog on her knee", and she speaks to it) |
| `the-gates` | +Toto |
| `the-balloon` | −Glinda (not there, never mentioned) |
| `the-tin-man-and-the-lion` onwards | +Toto through the close |

**Group integrity is the real check**, and it caught one genuine mistake: the `tighten-act-two`
branch used to rewrite the gate scene and drop the Lion from the cast — stranding a companion
on the road for no reason. He is now on set and silent, and the scene's prose says so
("The Lion is behind them and does not say anything"). The generator asserts both: he is in
the cast *and* the rewrite places him.

Two absences are correct and stay: `the-castle` has Dorothy held alone (the companions break
in during `the-melting`), and the companions are not in Act I — the party does not exist yet.

`aunt-em-uncle-henry` is the one relationship with no scene behind it — a deliberate
backdrop pair.

---

## 3. Character journey — Dorothy

| Check | Seen |
|---|---|
| Value paths across all three acts | ☐ |
| More than one value line (she carries `home`, `belief` and others) | ☐ |

---

## 4. Scenes

| Check | Seen |
|---|---|
| 14 scenes across 3 acts and 7 sequences | ☐ |
| Status colours: two `locked` (`the-farm-at-dusk`, `glinda-and-home`), twelve `written` | ☐ |
| Role tags on the plot scenes | ☐ |
| `the-poppy-field` **absent** | ☐ |
| `the-gates` shows the tightened cast — **the Lion is not in it** | ☐ |
| `the-goodbyes` cast **includes Dorothy** (she is addressed on its last line) | ☐ |

---

## 5. Script view

| Check | Seen |
|---|---|
| Headings compose from `INT./EXT.` + place + time | ☐ |
| Dialogue renders as dialogue, not action | ☐ |
| Statistics show a real action/dialogue split | ☐ |
| `the-gates` prose opens "A gate that has been designed to be walked through…" — the merged rewrite | ☐ |

---

## 6. Values

| Check | Seen |
|---|---|
| 5 ladders (`home`, `mind`, `heart`, `courage`, `belief`), each with four rungs | ☐ |
| Story view and per-plot view both populate | ☐ |
| Act filter changes the numbers (Act I: `home` only; Act II: four values) | ☐ |

---

## 7. Plots

| Check | Seen |
|---|---|
| 1 main (`there-s-no-place-like-home`, no type badge) + 4 sub | ☐ |
| Three distinct type badges: Contradictory, Resonant, Complicating ×2 | ☐ |
| Six role lists per main plot, all populated (setup, inciting incident, complication, crisis, climax, resolution) | ☐ |
| Subplots show fewer roles — `a-brain`/`a-heart`/`a-nerve` have **no** crisis or climax | ☐ |

**Expected, not a bug:** the three subplots are carried by their protagonists' value turns
and never take a crisis or a climax of their own. The main plot owns them.

---

## 8. Relationships

| Check | Seen |
|---|---|
| Both perspectives render with their own label and feeling | ☐ |
| The `secret` badge on the Wizard's side of `the-wizard-guardian-of-the-gates` | ☐ |
| `resolved` and `complex` statuses are distinguishable | ☐ |

---

## 9. Locations

| Check | Seen |
|---|---|
| 8 locations | ☐ |
| The `variant_of` tag on `emerald-city-after` (variant of `emerald-city`) | ☐ |

---

## 10. Trash

| Check | Seen |
|---|---|
| Exactly two rows: `the-poppy-field` and `the-poppy-field-beats` | ☐ |
| The Queen of the Field Mice is **not** in the trash — she is live and unplaced | ☐ |
| Restore preview reports no blockers and no collisions | ☐ |

---

## 11. Projects / history page

| Check | Seen |
|---|---|
| **10 drafts**, 4 branches (`main`, `lion-arc`, `tighten-act-two`, `the-ending`) | ☐ |
| **Two merge edges** (two-parent drafts): `First full draft` ← Draft 4 + Draft 3; `After Tighten Act II` ← Draft 7 + Tighten Act II | ☐ |
| The graph forks at Draft 2 (two ways: Draft 3 and Draft 4) and at Draft 7 (three ways: `tighten-act-two`, `the-ending`, and Draft 7's own continuation) | ☐ |
| `the-ending` is shown as **open** with one unresolved conflict | ☐ |

---

## 12. Draft 1 — the shape the demo argues for

| Check | Seen |
|---|---|
| 3 acts, 7 sequences, 15 scene rows — the structure was there from the start | ☐ |
| Act I: mostly `written`, one `drafted` | ☐ |
| Act II: one `written`, one `drafted`, **five `planned`** | ☐ |
| Act III: `written` scenes **before** Act II's middle was written | ☐ |

Draft 1 is as close to the load-bearing check as this list gets: if the graph shows a
story written front-to-back, the demo is endorsing the wrong process.

---

## Findings

Anything that fails above, recorded here rather than fixed in the demo.

| # | Surface | What happened | App bug or demo bug? |
|---|---|---|---|
| | | | |
