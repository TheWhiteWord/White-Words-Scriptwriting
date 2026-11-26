# Task 43 — Story design: The Wizard of Oz (tightened)

**Decided: The Wizard of Oz.** `variant_of` is a nice-to-have rather than the focus;
plots and values are the real features, and this story supplies both without invention.

Correction accepted: **character death is not deletion.** The Witch of the East stays in
the cast, has no scenes, and her death lives in beats and `changes`. Deletion is reserved
for **cut material** — the parts of the story the tightening removed, which is what a
writer's bin actually holds.

Shape: **3 acts · 6 sequences · 14 scenes · 5 plots · 9 live characters + 2 trashed**

---

## 1. Values — the spine of the whole demo

Five values. One belongs to the main plot, three to the companion subplots (so each
companion has a *track* to show), one to the Wizard's fraud. Two of them land in
`value_focus.minor`, which is what makes the project's value panel look like analysis
rather than a list.

| Value | p | c | cd | nn |
|---|---|---|---|---|
| **home** | home | wandering | exile | a home that is not yours |
| **mind** | sense | muddle | foolishness | cleverness that cannot think |
| **heart** | feeling | numbness | cruelty | sentiment that never acts |
| **courage** | courage | caution | cowardice | bravado |
| **belief** | belief | doubt | fraud | a lie people need |

Each ladder is written so the *words* are what the scenes record. `home`'s `nn` is the
trap: a home you are given that is not the one you left.

Reason for five and not three: `VALUE_MAJOR_COUNT = 3`, so the story's `value_focus` splits
3 major + 2 minor. With exactly three values, `minor` is empty and the panel's second
section never renders.

---

## 2. Plots

Two main, three sub. The two mains run over the same scenes without competing, and the
three subs each belong to one companion.

| Plot | Scope | Type | Protagonists | Value arc | Value |
|---|---|---|---|---|---|
| **There's no place like home** | main | — | dorothy | Education | home |
| **The humbug** | main | — | dorothy, the-wizard | Disillusionment | belief |
| **A brain** | sub | Contradictory | scarecrow | Maturation | mind |
| **A heart** | sub | Resonant | tin-man | Maturation | heart |
| **A nerve** | sub | Complicating | lion | Testing | courage |

`plot_type` is required for every sub and is what the plots view badges in colour. Using
three different types (Contradictory / Resonant / Complicating) puts all three badge
colours on screen at once — the enum has four members and `Setup` is deliberately unused,
because a Setup subplot that exists only to launch the main plot is not a thing this story
needs and inventing one would be padding.

**The humbug is a second main plot, not a sub.** It is the story's argument, it has its own
protagonist, and it resolves in its own scene. This is the one place the demo departs from
the book's emphasis, and it is the reason the value graph shows two main lines crossing.

### Role placement (every singular role, one scene per plot)

| Scene | Plot | Role |
|---|---|---|
| 1 Kansas farm | home | setup |
| 2 The cyclone | home | complication |
| 3 Munchkinland | home | inciting_incident |
| 4 The road / Scarecrow | mind | inciting_incident |
| 4 The road / Scarecrow | home | complication |
| 5 Tin Man and Lion | heart, courage | inciting_incident (both) |
| 6 Poppy field | courage | complication |
| 7 Emerald City gates | humbug | setup |
| 8 The audience | humbug | inciting_incident |
| 8 The audience | mind, heart, courage | complication (all three) |
| 9 The monkeys | home | crisis |
| 10 The castle | humbug | complication |
| 11 The melting | home | climax |
| 11 The melting | humbug | crisis |
| 12 Behind the curtain | humbug | climax |
| 13 The balloon | home | resolution (attempted, fails) |
| 14 Glinda | home | resolution |
| 14 Glinda | mind, heart, courage | resolution (all three) |

Note scene 13 carries a `resolution` role for the main plot *and* the plot continues to
scene 14 — the demo shows that a role is a beat, not a terminal state, and that
`plot.status` stays `active` until the last one. `The humbug` is the one plot marked
`resolved` at the end; the others are `active` or `resolved` as their last scene dictates,
which is what makes the plots view show more than one status.

---

## 3. Cast

Nine live, two trashed. Roles chosen so every member of `VALID_ROLES` appears.

| Character | Role | Why they are in the demo |
|---|---|---|
| Dorothy Gale | Protagonist | main-plot protagonist; the journey tab's subject |
| The Wicked Witch of the West | Antagonist | the antagonist tier, and the only character whose `knowledge` differs on every fact |
| The Scarecrow | Supporting | owns the `mind` plot and its value track |
| The Tin Woodman | Supporting | owns the `heart` plot; the one `changes` entry that is a **relationship** |
| The Cowardly Lion | Supporting | owns the `courage` plot; the one beat where `by` is fear itself (a world) |
| The Wizard of Oz | Supporting | second main plot; `secret: true` on his relationship with Dorothy |
| Glinda | Supporting | mentor; delivers the controlling idea in scene 14 |
| Aunt Em | Minor | appears in scene 1 only; the `home` the story argues about |
| The Guardian of the Gates | Cameo | one scene; proves the Cameo tier renders |

Trashed (cut in the tightening, kept in the bin as real work):

| Character | Was | Cut because |
|---|---|---|
| The Wicked Witch of the East | Minor | her one scene (the shoes) merged into scene 3 |
| The Queen of the Field Mice | Minor | her rescue belongs to a sequence the tightening removed |

Both are referenced from a **trashed scene** too, so the Trash tab shows a parent/child
group rather than an isolated row, and `restore_check` has a `stranded_children` case to
report. That is the point: the bin demonstrates the guard, not just the delete.

---

## 4. Relationships (6)

| A ↔ B | perspectives | Why |
|---|---|---|
| dorothy ↔ wicked-witch-of-the-west | both `enemy`, strength −0.9 / −0.9 | a symmetric hatred, the negative extreme of the strength bar |
| dorothy ↔ scarecrow | `family` +0.7 / `ally` +0.8 | asymmetric labels for a mutual bond |
| dorothy ↔ tin-man | `ally` +0.6 / `ally` +0.7 | the calm middle |
| dorothy ↔ lion | `ally` +0.5 / `family` +0.6 | the lion reads it as family |
| dorothy ↔ the-wizard | `mentor` +0.4 / `professional` +0.2, **`secret: true` on the Wizard's side** | the fraud: he knows the relationship is a performance and she does not |
| wicked-witch-of-the-west ↔ wicked-witch-of-the-east | `family` +0.5 / `family` +0.9 | **a relationship whose other end is trashed** — the case that exercises `reference_in_trash` |

The last one is the deliberate edge case the user's correction created: the East witch is
gone from the story but the bond survives, so the relationship's second end sits in the
bin and the panel has to say so.

`scenes[]` is filled on four of the six (the two Witch relationships touch scenes 9–11,
the companion ones scenes 4–5 and 14), which is what the Relationships view's scene count
reads.

---

## 5. Locations (6) and worlds (2)

| Location | World | Variant of | Notes |
|---|---|---|---|
| The Gale Farm | kansas | — | base |
| The Cyclone | kansas | — | the `forced_heading` scene's place |
| Munchkinland | oz | — | base; the `place` values show here |
| The Yellow Brick Road | oz | — | `place` varies: the wheat field, the orchard, the poppy field |
| The Emerald City | oz | — | base |
| The Emerald City, after the Wizard | oz | **the-emerald-city** | the transformation: green glasses off, throne room empty |

The variant is the story's one `location.variant_of`, and it is a real transformation with
a cause (the Wizard leaves), not a time of day. Scene 12 is set in it.

**Worlds.** `kansas` (period: 1900, values: work, thrift, endurance; power: the bank and the
weather) and `oz` (rules: the shoes and the cap bind; power: the Wizards, then Glinda).
`kansas`'s `variant_of` is left empty — one instance of the concept is enough, and the
unfilled check skips the field, so an empty one is not a gap. The **Oz** world gets the
`variant_of` relationship to Kansas instead, recorded as a note in its `History` section
rather than as a field: making the fantasy world a "variant" of the real one is a critical
reading, not a structural fact, and encoding it as a field would assert something the app
would then display as if it were true.

---

## 6. Scenes (14) — the beat of each

Every scene gets a full `scene_beats` record, `Content` in Fountain, and all eight
sections. Abbreviated here to what the demo is *demonstrating* per scene.

| # | Seq | Scene | status | dramatic_role | Demonstrates |
|---|---|---|---|---|---|
| 1 | 1.1 | The farm at dusk | written | plot_role | setup for `home`; `no_cast` false; Aunt Em; Kansas as sepia |
| 2 | 1.1 | The cyclone | drafted | **transition** | **`forced_heading`**, `no_cast: true` (the house, empty, airborne), no plot roles |
| 3 | 1.2 | Munchkinland | written | plot_role | inciting incident; `INT./EXT.`; the shoes; the East witch mentioned, not present |
| 4 | 2.1 | The road, and the Scarecrow | written | plot_role | two plots at once; `EXT.` at DAY; the Scarecrow's first turn |
| 5 | 2.1 | The orchard, the Tin Man, the Lion | written | plot_role | three plots in one scene; five characters on screen — the cast list's fullest |
| 6 | 2.2 | The poppy field | drafted | **non-event** | `no_cast: true`, no plot roles, the party asleep — a scene that moves nothing on purpose |
| 7 | 2.3 | The gates of the Emerald City | written | plot_role | `humbug` setup; the Guardian (Cameo); `place` |
| 8 | 2.3 | The audience with the Wizard | written | plot_role | **four plots in one scene**; the Wizard's four answers; `secret` on his side |
| 9 | 3.1 | The monkeys | drafted | plot_role | `home` crisis; `EXT.` NIGHT; a beat whose `by` is the **world** |
| 10 | 3.1 | The castle of the Witch | written | plot_role | `humbug` complication; the Witch's `knowledge` at its peak |
| 11 | 3.2 | The melting | written | plot_role | `home` climax + `humbug` crisis in one scene; the strongest `value_turn` |
| 12 | 3.2 | Behind the curtain | written | plot_role | set in the **variant** location; `humbug` climax; the `nn` rung of `belief` |
| 13 | 3.3 | The balloon | drafted | plot_role | `home` resolution that **fails** — a status of `drafted`, not `written`, because it is the draft the writer was unsure of |
| 14 | 3.3 | Glinda, and home | written | plot_role | resolution for four plots; the controlling idea spoken; `ESC`/forced heading for the return |

Scene statuses are deliberately mixed: 9 `written`, 4 `drafted`, 1 `planned` — no `locked`,
because a demo where every scene is locked claims a finished screenplay and there is
nothing for the reader to imagine doing next. **No `locked`, and one `planned`** (scene 6
is `drafted`; the one `planned` is assigned in the plan's status table, not here).

Value turns: 22 across the 14 scenes, distributed so every plot gets 3+ and every conflict
level (inner / personal / extra-personal) appears at least twice.

---

## 7. The one thing this design refuses to do

It does not invent a subplot to fill a field. Five plots already exceed what the demo
needs; a sixth would be padding, and padding is what makes a demo read as a schema dump.
Likewise `Setup` as a `plot_type` is left unused rather than manufactured.

---

## 8. Open questions for the owner

1. **Scene count.** 14 is the commitment. Confirm, or say 12 (dropping the poppy field and
   merging 12–13), or 16 (restoring the field mice and the Kalidah).
2. **The second main plot.** I made `The humbug` main rather than sub, which puts two main
   lines in the value graph. Alternative: keep it sub (`Complicating`), one main plot only.
3. **The `planned` scene.** I want exactly one scene left `planned` to show the status mix;
   nominating scene 9 (the monkeys) means the story's lowest point is the un-written one,
   which reads oddly. Scene 6 (the poppy field) is the better candidate but I have it as
   `drafted`. Either is fine — it is a one-field choice, but it is a visible one.
