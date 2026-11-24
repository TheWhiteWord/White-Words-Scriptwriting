# Staging changes

*Schematic draft — headings and notes only.*

The write path: propose, show, confirm, write. Five behaviours, all of them
things the tool does that are not obvious from its parameters.

The op grammar is not here — `story_draft`'s schema declares every op kind's
fields, and that is where the model reads them.

---

## The loop

1. **Stage** the batch. This writes nothing to the story.
2. **Relay `preview_md` to the user, in full.** It is the artefact under review.
3. **Fix anything in `validation`** before asking for confirmation, not after.
4. **Commit only once the user has confirmed.**

- **Step 3 is not optional and not the user's job.** A validation finding is
  something the agent can fix — a required field, a wrong charge word, a
  reference that does not resolve. Report the proposal *and* the finding, having
  already dealt with what can be dealt with.
- **Step 2 is not a summary.** The preview is what the user is approving, and a
  summary of it is not what they approved. Relay it.

## Staging writes one row and nothing else

*Verified: entity, section and relation counts are identical before and after;
only the drafts table moves.*

- So staging is genuinely inert. A proposal the user never confirms leaves **no
  trace in the story** — which is what makes it safe to propose freely.
- The corollary: **the dashboard will not show a staged change.** It renders
  committed data. → `references/mechanics/dashboard.md`
- A consequence for the conversation: the user cannot inspect a proposal
  anywhere except the preview. It has to be relayed.

## Restaging replaces, it does not queue

*The behaviour that changes how a revision is made.*

- Staging again **replaces the proposal** rather than adding to it. Verified:
  the drafts table still holds exactly one row.
- **So a restage is "here is the batch as it now stands", not "and also this".**
  Anything left out of the new call is gone from the proposal.
- **The response says what changed**, in three lists: ops **added**, ops
  **dropped**, and ops **changed** with the specific fields that differ.
  Verified both ways — removing an entire op is reported as dropped, and editing
  one field inside a surviving op is reported as that field changing.
- That report is the safety net for exactly the mistake restaging invites: an op
  that was in the first batch and is not in the second. **Read it and relay the
  dropped list** if there is one — a silently dropped op is a change the user
  did not agree to.

## A commit lands everything or nothing

*The reason a commit's result is still read rather than assumed.*

- **A commit is all-or-nothing.** If any op in the batch fails, **none** of it is
  written: the response is `success: false`, `committed` is `[]`, `failed` names the
  op that was refused, and the message says nothing was changed. The project is
  exactly as it was.
- **The draft is kept.** Fix the problem, **re-stage the whole batch** under the same
  `draft_id` (a restage replaces — see above), and commit again. There is no
  "remainder" to work out: nothing landed, so nothing is repeated.
- **Relay the failure plainly**: which change failed and why, and that nothing was
  saved. Do not tell the user part of it went in.
- **Ops in one batch can depend on each other.** A new location and the scene that
  names it, a new character and the plot that lists them, commit together — the
  later op sees the earlier one.
- **A repeated commit is not an error.** Committing the same draft again returns
  success with `already_committed: true` and writes nothing.
- **The one exception is a purge**, which is staged on its own by
  `story_admin(action="purge")` and cannot be undone. A single purge is all-or-nothing
  like any other. Only if a draft held several purges could an earlier one stay done
  when a later one fails; then `committed` lists exactly what was purged.

## One batch per decision

- Ops are sorted at commit — creates before edits, edits before deletes — so the
  order they are written in does not matter and a new scene can be created and
  written in the same batch.
- **That makes one batch per decision the right shape**, not a limitation: a
  scene plus its location, its cast and its position in the sequence is one
  thing the user is agreeing to, and splitting it means asking twice about a
  single change.
- The cost is a larger preview. If a batch is genuinely two decisions, the user
  is being asked to approve both at once — which is worth noticing before
  staging it.

## Finding a draft left behind

- `action="list"` reports the **open** drafts in a project. Verified: a
  committed or discarded draft is history and does not appear.
- So a draft from a previous session is invisible until asked for. **Call `list`
  at the start of a session** before proposing something new, so an existing
  proposal is resumed rather than duplicated.
- Discarding drops the row entirely. Committing leaves it, marked committed, as a
  record.

---

## Open questions

- [ ] The dropped-ops report exists precisely because restaging replaces. Is that
      enough, or should the agent be told to restate the whole batch in its
      message when anything is dropped?
- [ ] `list` is the only way to find a leftover draft. Worth stating as a
      session-opening step in SKILL.md, or is it one line here?
