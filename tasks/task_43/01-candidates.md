# Task 43 — Demo project: candidates

Status: **awaiting selection** · Branch: `draft-versioning` · No code or data written yet.

The deliverable this feeds: one shipped demo project that a new user opens to see
what the app does, built here by hand (not by the agent tools, which do not exist
for versioning yet), sitting in the default project folder so the owner can verify
it before it is committed as the demo.

---

## 1. What the demo has to expose

Read from the code at `f27c620`, not assumed. This is the checklist the story is
chosen against; it also becomes the coverage test the finished demo is held to.

### 1.1 Entity types and their fields

Every field is a demonstration target. `computed` fields are derived and only need
the inputs to exist; the rest must be written.

| Type | Fields to fill | Computed (inputs must exist) |
|---|---|---|
| project | name, status, logline, structure_type, genre, act_count, setting, spine, controlling_idea, screenplay_title, credit, author, contact, draft_date, draft, memory | value_focus |
| character | name, story_role, one_sentence, goals_short, goals_long, knowledge[] | relationships |
| location | name, one_sentence, mood, dramatic_function, world, variant_of | places |
| world | name, one_sentence, rules[], period, values[], power[], variant_of | — |
| plot | name, one_sentence, status, characters[], value_arc, plot_scope, plot_type | setups, inciting_incident, complications, crisis, climax, resolutions, value_focus |
| value | name, p, c, cd, nn, note | — |
| relationship | name, characters[2], perspectives{}, scenes[], status, history | — |
| act | title, order, status, act_objective | value_focus |
| sequence | title, order, status, act_id, primary_plot, purpose | value_focus |
| scene | title, status, sequence_id, order, int_ext, place, location, time_of_day, characters[], no_cast, one_sentence, scene_objective, dramatic_role, plot_roles[], value_turns[] | turning_point, scene_beats |
| scene_beats | scene, driver, scene_objective, turning_point, true_character[], changes[], beats[] | — |

Sections (every heading of every type must be written, since an empty section is
the first thing a curious user clicks):

- character: Identity, Desires, Background, Contradictions, Psychology, Arc, Relationships, Voice, Notes
- location: Description, Atmosphere, Image System, History, Dramatic Function, Notes
- world: Description, History, Livelihood, Power, Rituals, Values, Conflict, Notes
- plot: Summary, Role, Threads, Value, Characters, Notes
- project: Premise, Spine, Controlling Idea, Value Arc, Structure, Genre, Notes
- scene: Content, Objective, Conflict, Beats, Value Turn, Dramatic Function, Production, Notes
- sequence: Summary, Purpose, Value Arc, Progression, Sequence Climax, Plots, Notes
- act: Summary, Objective, Value Arc, Reversal, Notes
- relationship: Nature, Perspectives, Tension, History, Scenes to Write, Notes
- value: Definition, Notes
- scene_beats: Notes

### 1.2 Enum values worth showing

- `character.story_role`: Protagonist, Antagonist, Supporting, Minor, Cameo — one of each, so the role colours in the character web all appear.
- `scene.status`: planned, drafted, written, locked — a spread, not all one value.
- `act`/`sequence.status`: planned, in-progress, complete.
- `plot.plot_scope`: main **and** sub; each subplot needs `plot_type` (Contradictory / Resonant / Complicating / Setup) or the form warns.
- `plot.value_arc`: one of six; the main plot and at least one subplot should differ.
- `relationship.status`: active, resolved, complex.
- `scene.dramatic_role`: plot_role, **transition**, **non-event** — the last two are only reachable if the story has a scene that serves no plot, and they are mutually exclusive with `plot_roles`.
- `scene.int_ext`: INT., EXT., INT./EXT., EST.

### 1.3 Structures and edge cases (each needs a deliberate example)

1. **A subplot** with its own protagonists in `plot.characters` — not the main cast.
2. **A scene serving two plots** at once (one `plot_roles` entry per plot).
3. **A scene holding several roles in one plot** (the validator allows it).
4. **All three singular roles** (inciting_incident, crisis, climax) placed on one scene each, per plot.
5. **A scene with `no_cast`** — a deliberate empty room / landscape, which is also the only clean way to clear the "characters unfilled" gap.
6. **A scene with `forced_heading`** — a heading the fields cannot compose (a montage, a flash-forward, a title card).
7. **`location.variant_of`** — one place that appears in two states (before/after, dream/real, enchanted/restored). One instance is enough; it is the same concept as `world.variant_of`, so the world does not need its own.
8. **`place` set on scenes** — it feeds `location.places` (computed) and gives one location several distinct sub-areas.
9. **`relationship.perspectives`** for **both** characters, asymmetric, with **`secret: true` on one side** — the flag only means something if one party hides something from the other.
10. **`strength` negative on at least one relationship** (hostility) and positive on another (devotion), so the web shows both signs.
11. **`character.knowledge`** — a list of facts, ideally facts that differ between characters (who knows what), which is what makes it worth showing.
12. **`value_turns` with `effects` at all three conflict levels** (inner, personal, extra-personal) across the demo.
13. **`scene_beats` fully written** for most scenes: `driver`, `scene_objective`, `turning_point`, `true_character` (dilemma + choice_reveals), `changes` (including at least one **relationship**, one **location** and one **world** change, not just characters), and `beats` with action/reaction each carrying `by`, `surface`, `subtext`, plus a `gap`.
14. **A beat whose `by` is a location or a world** (the validator accepts three types) — e.g. the storm, the house, the forest acting.
15. **A beat where the same character is on both sides** (inner conflict) and one where driver ≠ the character who faces the choice.
16. **Three or more `value` entities**, since the project's `value_focus` splits into major (≤3) and minor — one value needs to land in minor.
17. **A character in the trash** — the Trash tab, the restore guard and `restore_check` have nothing to show otherwise.
18. **At least one `plot` `resolved`**, so `plot.status` is not uniformly "active".

### 1.4 What the UI reads, and therefore what must be true of the data

| Surface | Needs |
|---|---|
| Story view | project stats grid, logline, spine, controlling idea, setting, value focus, structure, and the main plot's **inciting incident + climax** scenes to link |
| Character web | relationships with `perspectives.strength` on both sides; unlinked entities are drawn as neutral virtual edges to the protagonist, so a few isolated characters look stocked, not broken |
| Scenes view | scenes per sequence with status and dramatic role; the bin icon and the "transition/non-event" handling |
| Locations view + panel | `variant_of` tag, `world` link, `places` |
| Worlds view + panel | rules, period, values, power, `variant_of`, and the plot threads filtered by world |
| Plots view + panel | scope badge, plot type colour, cast tags, and the six role lists populated |
| Relationships view + panel | both perspectives, type colour, strength bar (signed), `secret` badge |
| Values view | the 4-rung ladders placed on lanes; scenes with value turns; per-plot and per-act filtering; "N scenes with value shifts" |
| Script view + editor | composed headings from `int_ext`/`location`/`place`/`time_of_day`, the `Content` bodies in Fountain, cast cues matched to characters, and the heading-compose escape (edit as fields ↔ edit as a forced heading) |
| Statistics aside | length/duration (needs real dialogue, not narration), character chart, scene barcode, structural stats (status mix, role mix, plot coverage %) |
| Detail panel tabs | a character's **journey** tab is derived from `value_turns` effects reaching that character *and* their membership in a plot's cast; the **beats** tab per scene |
| Memory dialog | `project.memory` across decisions / directions / open_questions / continuity_warnings |
| Trash | a soft-deleted entity with a restorable position and no blockers |
| Projects page + graph | (history demo, see §3) |

Two consequences that rule stories out:

- **Duration statistics and the script view both need real dialogue.** A tale told
  purely in narration produces a screenplay page with no cues, a dialogue/action
  split of ~0%, and a cast list that never appears in the script.
- **The character journey tab needs the protagonist to be both a plot protagonist
  and the target of value-turn effects.** A story where the lead is silent or
  passive cannot fill it.

---

## 2. Candidates

All five are public domain, culturally fixed (the user does not have to learn the
plot), and have a native subplot. Ranked by fit to §1.

### A. Cinderella (Perrault / Grimm) — **recommended**

Cast (8): Cinderella (Protagonist), the Stepmother (Antagonist), two Stepsisters
(Supporting — one vain, one cruel, which gives *two* differently-flavoured
antagonists), the Prince (Supporting), the Fairy Godmother (Supporting, a mentor),
the Father (Minor — a weak man who does not intervene), the King or the Herald
(Cameo).

Acts: I the house and the invitation, II the ball, III the search and the fitting.

| Requirement | How Cinderella meets it |
|---|---|
| Native subplot | The Stepmother's campaign to marry a daughter to the Prince — runs through all three acts and has its own protagonists, and its climax (the fitting) can be a *different scene* from the main plot's |
| Secrets | Cinderella's identity at the ball is the story's engine: `perspectives.secret` on the Prince's side is literally the plot. The Fairy Godmother's aid is a second secret held from the family |
| `variant_of` | The kitchen/scullery in Act I vs the same kitchen the morning after the ball (soot, the shoe missing) — a real two-state place. Also the garden by night vs dawn |
| `no_cast` scene | The ballroom after midnight, everyone gone, the clock still wrong — and it is dramatically load-bearing, not filler |
| `forced_heading` | `THE BALL — MIDNIGHT` or a montage of the household preparing; neither composes from int/ext + place + time |
| transition / non-event | The carriage ride (transition); the palace corridor where nothing happens but waiting (non-event) |
| Values (≥3, one minor) | **kindness** (the main plot), **worth** (what a person is valued for — the subplot), **justice** (the resolution), **obedience** (minor: what Cinderella unlearns) |
| `knowledge` | Who knows the shoe fits: Cinderella, the stepsisters (suspect), the Prince (does not), the Godmother (does). A real information map, not decoration |
| Dialogue | The stepfamily and the Prince give long, quotable scenes; the ball is dialogue-dense |
| Cast in the script | Everyone appears in at least one scene except the Cameo, which is a deliberate demonstration of the role |
| Length | Fits 3 acts / 7 sequences / ~14 scenes without padding |

Risk: it is *the* default choice; if the demo is meant to feel authored rather than
textbook, this is the least surprising pick.

### B. Beauty and the Beast (Villeneuve / Beaumont) — strongest on the two hardest features

Cast (7–8): Beauty (Protagonist), the Beast (co-protagonist or Antagonist depending
on the reading — this ambiguity is itself a good demonstration of `story_role`),
the Father (Supporting), two Sisters (Minor/Supporting, envious), the Merchant's
household, the Enchantress (Cameo), the Castle's household (one or two, or a
`world`-level presence).

| Requirement | How it meets it |
|---|---|
| `variant_of` | The best in the set: the castle enchanted vs the castle restored, plus the rose garden in winter vs summer. This is the feature's ideal case |
| Secrets | The Beast's nature is hidden from Beauty for the whole first half; the sisters hide their scheme; the Beast hides his dying |
| `world` material | A world with real `rules` (the castle's laws), `power` (who is bound by them), `values` |
| Values | love, appearance, sacrifice, gratitude |
| Subplot | The sisters' envy and the father's ruin — genuinely separate protagonists |
| Risk | The Beast's dialogue is broken by design, which skews the statistics; and the cast is thin in the middle acts (two people in one place for a long stretch), so scenes-per-sequence needs invention to look full |

### C. The Little Mermaid (Andersen) — best tragic arc, weakest script

Cast (6–7): the Little Mermaid (Protagonist), the Sea Witch (Antagonist), the
Prince (Supporting), the Prince's bride (Supporting), the Grandmother (Minor), the
five sisters (Cameo/Merged), the Sea King (Minor).

| Requirement | How it meets it |
|---|---|
| Native subplot | The Prince's arranged marriage to the neighbouring princess — a real Contradictory subplot whose resolution decides the main plot |
| Secrets | The voice, the bargain, the sisters' knife — the strongest `secret` material of any candidate |
| `world` | Two worlds (sea / land) with opposed `values` and `power`, and `world.variant_of` is meaningful here |
| Value arc | `Testing`, and the ending is genuinely Punitive — good for showing a non-Maturation arc |
| **Risk** | **The protagonist is mute for the middle act.** That is the story, and it empties the screenplay: no cues, near-zero dialogue split in Act II, and the Statistics "dialogue" chart shows a hole that looks like a data bug rather than a story |

### D. The Wizard of Oz (Baum) — best multi-subplot demonstration

Cast (8–9): Dorothy (Protagonist), the Wicked Witch (Antagonist), the Scarecrow,
the Tin Woodman, the Cowardly Lion (Supporting ×3), the Wizard (Supporting/trickster),
Glinda (Supporting), Aunt Em (Minor), Toto (Cameo).

| Requirement | How it meets it |
|---|---|
| Subplots | **Four native quests**, each with its own protagonist, value and arc — the richest `plot.characters` and plot-coverage demonstration available. The structural statistics' plot coverage would look like a real analysis |
| Secrets | The Wizard's fraud — a `secret` on a *plot-bearing* relationship, not a romance |
| `variant_of` | Kansas vs Oz as `world.variant_of`; the Emerald City as seen by the travellers vs behind the curtain |
| Values | home, courage, heart, mind — four values that map cleanly onto four plots (two would be minor) |
| Risk | Length. A faithful demo is 18–20 scenes and three subplots' worth of beats — roughly 40% more writing than Cinderella, and every scene must still be fully filled or the demo shows gaps |

### E. Hansel and Gretel (Grimm) — the tightest, and too tight

Cast (5): Hansel, Gretel (both Protagonist), the Witch (Antagonist), the Father
(Supporting), the Stepmother (Antagonist/Minor).

| Requirement | How it meets it |
|---|---|
| Variant | The gingerbread house as it appears vs as it is (the trap); the forest by day and by night |
| No-cast scene | The forest at night, the children gone — genuinely good |
| Secrets | The witch's intent; the parents' abandonment |
| **Risk** | Five named characters is the floor, not a good set to display a web with. No supporting tier, no Cameo, no native subplot worth the name (the parents' thread is two scenes), and two protagonists split the journey tab between them |

---

## 3. What the versioning demo needs, independent of the story

The chosen story also has to carry a believable *revision history*. From the spec
(`tasks/task_42/spec-draft-versioning.md`) and the probe run today:

- **A main line of 3–4 drafts**, each a state a writer would plausibly have
  written, not a random field toggled. "First draft", "After the notes", "Act II
  rewritten", "Ready to read".
- **One branch** from an early draft, representing the writer's alternative — the
  classic real case is *an alternative ending*, or *a cut subplot*.
- **One merge** from that branch back, with **a non-empty selection**, showing:
  one item taken, one conflict resolved, and one item deliberately left out (so
  the cherry-pick vs complete-merge distinction has something to demonstrate).
- **One deliberate conflict** on a field or section that changed on both sides —
  this is the single most important thing to see working.
- **Nothing that requires the agent.** The probe confirmed a scripted
  `store.save_snapshot` → `branch_from` → `switch` → `session.start` →
  `preview` → `apply` sequence runs end to end without the versioning agent tools.

Probe finding worth recording now: `session.apply` with an empty selection applied
zero ops and returned `status: "applied"`. That is correct per §7.2 (nothing is
applied that is not selected), and it means **the demo's merge must set
`selection` explicitly** or it will look like a no-op.

---

## 4. Decision requested

One question: **which story**.

Considering the whole checklist, my recommendation is **A. Cinderella**, with **D.
The Wizard of Oz** as the choice if the priority is the subplot/plot-coverage
demonstration over writing volume, and **B. Beauty and the Beast** if the priority
is `variant_of` and the `secret` flag looking their best.

Not recommended: **E** (too few characters), **C** (the mute middle act actively
spoils the script and statistics views).
