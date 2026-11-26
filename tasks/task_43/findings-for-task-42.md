# Findings from building the demo — for task 42

Found while building the Oz demo (task 43). None of these are demo problems; the demo works
around each. They are recorded here because a spec never surfaces them and a demo does.

---

## F1 — `custom` conflict resolution silently applies `theirs`

**Where:** `core/history/plan.py:44` (`D2` options `("mine","theirs","custom")`),
`plan.py:797` / `_emit_change` (`if _choice(ctx, item) not in ("theirs","custom"): return`,
then `value = item["theirs"]`).

**What happens.** `D2` offers three options. Choosing `custom` behaves exactly like `theirs`:
`_emit_change` reads `item["theirs"]` for both, and nothing anywhere supplies a custom value —
`session.set_decision` takes only a `choice` string, the decision record stores only
`{"choice": …, "set_by": …}`, and no route or UI control posts a value alongside it.

**Verified.** A real two-sided conflict on `field:character:lion:one_sentence`, resolved
`custom`:

```
ready after custom: True
applied: applied
lion now: THEIRS: fear read as bravado.
```

No error, no warning, `status: applied`. The button labelled "custom" writes their text.

**Why it matters.** A user who chooses `custom` believes they are merging the two versions by
hand. They are discarding their own. This is the worst class of bug in a merge tool: the
result is plausible and the record claims the choice was made.

**Two ways out, and it is a design decision, not a fix:**

1. **Give it a path.** `set_decision(..., choice="custom", value=<anything>)` → store the
   value on the decision record → `_emit_change` uses `decision["value"]` when the choice is
   `custom` → validate it as the field's type before it reaches the executor.
2. **Remove it.** Drop `custom` from `D2` (and `D7`) until it means something. A two-option
   conflict is complete and honest; a three-option one where two are the same is not.

Until one is chosen, the demo uses `theirs` and does not demonstrate `custom`.

**Not fixed here** — this is task 42's executor and its UI, and the demo is not the place to
change merge semantics.

---

## F2 — a merge contributes a branch's saved draft, not its unsaved head

Not a bug, a rule that is easy to get wrong: `session._source_of` sets a branch source's
`base_snapshot_id` to the branch's `base_snapshot_id`, and `_base` walks from there. A branch
with unsaved work contributes nothing, and the merge reports clean with zero ops.

Consequence for anyone building a demo or a test: **save the branch before merging it.** An
empty merge reports `status: applied` with `applied: []`, which reads like success.

---

## F3 — an empty selection applies zero ops and reports success

Already known (recorded in task 42's own notes) but confirmed again here: a session with no
selection returns `status: applied`, `applied: []`. Any caller must assert `applied` is
non-empty, not merely that apply did not raise.

---

## F4 — two sides editing *different* fields is not a conflict

Useful to know when building fixtures: if the two sides change different fields, the planner
emits `state: "take"` and `state: "keep"` with no decision and `ready: true` immediately. A
conflict requires both sides to change *the same* field differently. A "merge demo" that
edits different fields on each side demonstrates nothing about conflict resolution.
