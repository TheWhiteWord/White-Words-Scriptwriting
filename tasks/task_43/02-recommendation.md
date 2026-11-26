# Task 43 — Recommendation after the `variant_of` correction

Supersedes the ranking in `01-candidates.md` §2. The checklist in §1 stands.

## 1. The correction, and what it rules out

`variant_of` is not "the same place at a different time". It is a *transformation*:
the same place in a genuinely different state, caused by something — a wish, a
curse, an event, centuries. The demo's instance has to survive being read as "why
is this a second location at all?".

Checked how the app renders it: `views/locations.js:18` and `views/worlds.js:17` emit
a `variant of X` tag; `panels/entity-panels.js:211` links to the base. Nothing else
reads it. So a weak instance is not merely dull — it is an unexplained duplicate that
looks like authoring noise.

Ruled out by this:

- **Cinderella.** Kitchen before/after midnight is a state change, not a
  transformation. Withdrawn.
- **Three Little Pigs.** Three sibling protagonists, one antagonist, no subplot, no
  transformation. Its whole cast is a single relationship.
- **Red Riding Hood.** Five characters, no subplot, and the only variant candidate is
  the woods by day vs night.

The two simple tales fail on more than `variant_of`, which is why tightening them does
not help: `plot.plot_type` exists only for subplots, so a story with no subplot leaves
four of the six plot fields permanently blank; the structural statistics' plot-coverage
bar shows one thread at 100%; and `plot.characters` has one entry, so the plots view's
cast tags and the journey tab both have a single character to show.

## 2. The length question, answered with the structure

The cost of any 14-scene story is 14 full `scene_beats` records — that is the real
bill, and it does not change with the story. Oz's genuine extra over Cinderella is
**plots and characters, not scenes**.

Oz tightens to the same footprint as any other candidate:

**3 acts · 6 sequences · 14 scenes · 4 plots · 9 characters**

The three compressions, all of them legitimate rather than shortcuts:

1. **One audience with the Wizard, not four.** In the book each companion petitions him
   separately. On screen all four state their need in one scene, and the Wizard's answer
   to each is a single line. Saves three scenes and is dramatically better.
2. **Drop the book-only geography** — China Country, the Quadlings, the Hammer-Heads —
   and the Kalidah chase. None carries a plot turn.
3. **The poppy field is the `no_cast` scene or it is cut.** Its function (the party
   separated, Dorothy alone) is already served by the monkeys.

Sketch, so the shape can be judged rather than imagined:

| Act | Seq | Scenes |
|---|---|---|
| I | 1. Kansas | 1 farm (setup) · 2 the cyclone (transition) |
| I | 2. Munchkinland | 3 the house lands / the slippers (inciting incident) · 4 the Yellow Brick Road, the Scarecrow |
| II | 3. The road | 5 the Tin Man and the Lion · 6 the poppy field (`no_cast`) |
| II | 4. Emerald City | 7 the gates · 8 one audience with the Wizard (the task) |
| II | 5. The Witch | 9 the monkeys take Dorothy (crisis) · 10 the castle · 11 the melting (climax) |
| III | 6. The humbug | 12 the throne room behind the curtain · 13 the balloon leaves · 14 Glinda, and home |

Four plots: Dorothy's **home**, the Scarecrow's **mind**, the Tin Man's **heart**, the
Lion's **courage** — plus the Wizard's fraud as the Complicating subplot. Four values,
so `value_focus` splits 3 major + 1 minor rather than landing entirely in major.

## 3. What Oz gives that the others do not

- **The richest plot demonstration.** Four native quests, each with its own protagonist
  in `plot.characters`, its own value and its own resolution — the plot-coverage
  statistic and the per-plot value graph both look like real analysis instead of one
  thread.
- **A canonical trashed entity.** The Wicked Witch of the East is dead before the story
  starts. She is created, then soft-deleted, and the Trash tab holds an entity whose
  deletion is *the story* rather than an arbitrary click. Every other candidate needs an
  invented deletion.
- **A `variant_of` caused by an event.** The Emerald City as the travellers meet it (green
  glasses, a Wizard on a throne) versus the same city after his departure (an empty throne
  room, a humbug's machinery, the glasses off). A definable change, not a time of day.
- **A world-level variant with an argument.** Kansas (sepia, poor, real) and Oz (colour,
  fantastical) are the same story's world transformed; the 1900 text supports the reading
  and the 1939 film makes it explicit.
- **A `forced_heading` that is unmistakable.** The cyclone, or `THE EMERALD CITY — AS IT
  REALLY IS`, composes neither from int/ext + place + time nor from anything else.
- **Every role tier genuinely used**: Protagonist (Dorothy), Antagonist (the Witch),
  Supporting (the three companions, Glinda, the Wizard), Minor (Aunt Em, Uncle Henry),
  Cameo (the Guardian of the Gates — one scene, which is what a Cameo is), and a trashed
  Minor (the Witch of the East).
- **Dialogue-dense.** The companions and the humbug carry long scenes, so the duration
  statistics' dialogue/action split is a real number.

Weakness, stated honestly: `variant_of` is less spectacular than a castle coming back to
life, and the cast is nine, so the character web is busier than B&B's seven.

## 4. Beauty and the Beast, if `variant_of` is the priority

Kept on the table because the enchanted → restored castle is the app's ideal case for the
feature, and the permanent winter is a world-level transformation with a cause. It also
has the only cast where `story_role` is genuinely ambiguous (the Beast reads as
Antagonist in Act I and co-protagonist by Act III), which is a nice thing to see.

Cost: two people in one room for the middle act, so six sequences need invention to look
full; a broken-speech character skews the statistics; and there is no canonical trashed
entity.

## 5. Question

**Oz tightened to 3 acts / 6 sequences / 14 scenes (recommended), or Beauty and the
Beast?**
