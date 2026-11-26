# T10 — HTTP routes and the `list_projects` enrichment

Spec: `../spec-draft-versioning.md` §10 (HTTP surface), §4.3 (read-only views, the
cache), §6 (diff entry point), §7.7 (plan/preview/apply), §9 (layering), §13 T10.
Branch: `draft-versioning`.
Baseline: `c9aa93d`, and on it `137 passed` (the five history core files) plus
`146 passed` (trash routes, story admin, session, execute, plan). The known
`test_no_hermes_imports` failure is not this task's concern.

Status: **blocked on decisions D-T10-A…D** (below). Nothing implemented yet.

## Objective

Every capability T3–T9 built is a Python function today. This task puts them behind
HTTP, and enriches the landing-page listing with the current draft, the branch count,
when it was last saved and whether there are unsaved changes — computed on demand,
never stored.

Two parts:

1. **`app/routes/history.py`** — one new router for `/api/projects/{slug}/history/`:
   branches and drafts, save, branch, switch, rename, delete branch, delete draft,
   diff, read-only views, and the merge session lifecycle.
2. **`services.list_projects`** — four extra keys per project, read from `history.db`
   when it exists and treating a missing manifest as "no history".

Nothing in `core/history/` changes except the one decision payload the reviewer named
(`theirs`/`ours` instead of unlabelled `a`/`b`), which belongs here because this is the
first task that exposes a decision over the wire.

## Verified before starting

Each row is a probe on this branch against the fixture (26 entities, 152 KB
`story.db`), not a reading of the spec or of `Notes.md`.

| # | Claim | Evidence |
|---|---|---|
| 1 | `list_branches` and `head_state` **create `history.db`** on a project that has none | probed on a manifest-less copy: both left `history.db` behind (an empty `branches` table). Latent `Notes.md` T10 finding, now confirmed — the listing must not call them on an unmanifested project. |
| 2 | `store.get_branch` refuses **before** opening a manifest that does not exist, and writes nothing | probed: `ValueError: bare has no history yet.`, `history.db created: False` |
| 3 | A D2 decision's detail is `a` = theirs, `b` = ours, unlabelled | probed: `a='Kael On Side'` (theirs), `b='Kael On Main'` (ours), while the sibling item says `theirs`/`ours`. Matches the reviewer's finding. |
| 4 | A `script` row can be `status: "unchanged"` **and** carry items | probed: `central-room-day status=unchanged items=['field:scene:central-room-day:one_sentence']`. The script view draws its marker from `items`, never `status`. |
| 5 | An unencoded `#` in a path segment **truncates** the value and still returns 200 | probed with a bare FastAPI route: unencoded → `key="field:character:kael:name"` (the `#D2` silently gone); percent-encoded → the full key. A decision would silently stay open. |
| 6 | Cost per project on the fixture: `list_projects` (today, name only) 0.01 ms · `head_state` 1.25 ms · change count on a **dirty** head 11.6 ms (it copies the draft and diffs) · draft-view copy 7 ms · diff between two views 18.5 ms · parked-branch tip (copy + fingerprint + diff) 20 ms | probe, best-of-20 |
| 7 | `resolve_project` fuzzy-matches at 75/100 when no exact folder exists | `tools/story_resolve.py:PROJECT_THRESHOLD = 75`. `save-the-child` resolves to `save-the-children`. Every existing route is read-mostly; these can delete a branch. |
| 8 | The error envelope `{"error": {code, message, …}}` is built by a **local** `_err` in `trash.py:31`, `entities.py:23`, `scripts.py:18` | three identical copies; `history.py` would be the fourth |
| 9 | A core refusal is a `ValueError` whose message is the only payload — `switch`'s open-draft ids live inside the sentence | probed: `This branch has open drafts (d-20261126-034047). …`; the exception carries no attributes. A route cannot build an actionable payload from it. |
| 10 | `session.show` returns `{…session, plan, stale, imprecise_base}`, `preview` returns the dry-run verdict plus the plan, `apply` returns `applied` / `refused` (`stale_plan` or `failures[]`) / `blocked` (`open[]`) | `session.py:266`, `:315`, `:333`; `execute.py:__all__` |
| 11 | A `project_view` copy is 7 ms and the block deletes it; nothing is written beside a draft | `view.py:29`, measured |

## Decisions

### Settled — owner agreed (patch applied: `t10-decisions.patch`)

- **D-T10-A. No cache.** Per-request copies; §4.3 amended in the spec with the measured
  numbers (7 ms copy, 18 ms diff). `project_view` stays the single entry point, so a
  cache can be added behind it later.
- **D-T10-B. One shared error helper**, in the **app layer** (the envelope is an HTTP
  concern, not `core`), landed as its own preparatory commit before `history.py`, with
  the three existing copies switched and no behaviour change. The existing route tests
  are the proof nothing moved. → `app/routes/errors.py`, `def _err(...)`.
- **D-T10-C. Decision keys stay in the path**, percent-encoded by the client, taken as a
  `path` parameter. Two checks, **both in `session.set_decision`** so T11's agent tool
  inherits them: reject a key with no `#D<n>` suffix, and reject a key that is not a
  decision of the current plan, listing the valid keys.
- **D-T10-D. Exact slug only on history routes; 404 otherwise.** A strict resolver is
  added and `resolve_project` is left alone (it stays fuzzy for the agent's tools, whose
  callers type names loosely). Moving the rest of the HTTP layer to the strict resolver
  — which already has the same exposure on entity delete and trash purge — is a
  separate commit, deliberately outside T10.

### Confirmed: decisions DO chain (the `set_decision` "not yet asked" case)

Probed by re-planning under every option of every decision and diffing the key sets.
Three shapes were tested; only one chains:

| Shape | Result |
|---|---|
| D9 `take-theirs` on an entity we deleted → does the restore guard raise D4? | **No chain.** The default plan already lists D9; both options produce the same key set. |
| D1 `keep-both` → the incoming entity is re-created as `<id>-2`; do its referrers gain a D5? | **No chain.** `_resolve` brings the referrer with it; only the one D1 key exists under all four options. |
| **D2 on `scene.plot_roles`** answered `theirs` or `custom` → `_emit_change` runs `_check_roles` | **CHAINS.** `D2 = mine` → one key. `D2 = theirs`/`custom` → a NEW `entity:scene:central-room-night#D4` appears that the default plan never mentioned. |

The cause: `plan._emit_change` calls `_check_roles` only for `theirs`/`custom`, so a
collision can only be discovered once that answer exists. Reproduced on the fixture
(side branch moves `inciting_incident` from `central-room-day` to `central-room-night`,
main edits the same field differently).

So `set_decision` needs **three** outcomes, not two:

1. key has no `#D<n>` → 422 naming the form;
2. key is a decision of the re-planned session → stored;
3. **key is not in the plan, but its item is** → 422 `"not yet asked"`, naming the
   decisions that must be answered first. A key whose item is absent from the plan
   entirely is case 1's plain 422 with the valid keys.

The distinction is safe because a decision key is `<item>#<code>`: an item present in
the plan means the answer *could* unlock it. A key whose item is nowhere in the plan is a
typo or a stale session.

### Open — needs the owner

- *(none)*

### Settled without asking

- **The listing never adopts and never calls `list_branches`/`head_state` on a project
  without `history.db`** (verified rows 1–2). It reads the manifest directly, the way
  `head_state` does, and reports `current_draft: null`, `branch_count: 0`,
  `last_saved: null`, `changes_since_save: false` for a project this feature has not
  touched. `Notes.md` T10 says the same; row 1 is the proof it matters.
- **`changes_since_save` is a count, not the boolean `head_state` reports.** §10 names
  the key `changes_since_save`, and the reviewer's "N changes since Draft 3" tip is the
  same fact at a different resolution. A clean head costs 1.25 ms (fingerprint only); a
  dirty head costs 11.6 ms more, because counting needs the diff. Counted as
  `len(diff.compare(base_view, live)["items"])`. The §10 sketch names the key but not
  its type; the count is the reviewer's "N changes since Draft 3" tip, so it is taken
  as the meaning and recorded in the final brief.
- **A parked branch reports its own tip in `GET /history/`.** `head_state` describes the
  current branch only (reviewer's finding); for every other branch the route compares
  the parked head's fingerprint with that branch's base draft and counts the diff,
  behind one `head_view` copy (20 ms measured, so it is computed **only** for
  `GET /history/`, never for the landing-page listing, which reports the current
  branch's figure only).
- **The merge routes translate three result shapes** (`applied`/`refused`/`blocked` from
  `apply`; `clean`/`refused` from `dry_run`) into: 200 for applied and clean,
  409 with `code: "stale_plan"` for a stale refusal (a client must re-plan), 409 with
  `open` for blocked, 409 with `failures` for a refused dry run. `Notes.md` T10 already
  specifies this split.
- **A `switch` refusal carries the open draft ids as data.** The core's `ValueError`
  message is the only payload today (row 9). The route re-reads the open drafts before
  calling `switch` and puts them in the 409 body under `open_drafts`, so the UI can name
  them. The message stays the message.
- **`PATCH /branches/{id}` and `DELETE` follow the core's `ValueError`** and map to
  409/400 with the envelope; a missing branch is a 404, matched on the core's
  `No such branch:` message.
- **`GET /diff` and the read routes take refs, not drafts only.** A ref is
  `{"kind": "snapshot"|"branch", "id": …}`, the shape `session.start` already accepts;
  on the wire it is two query parameters, `a=snapshot:<id>` / `b=branch:<id>`, so the
  route needs no JSON-encoded query argument. A bare id means `snapshot:`.
- **Nothing in the router touches `history.db` with a write for a GET.** Verified rows
  1–2 are the reason; the test pins it by asserting no manifest appears.

## Tasks

- [x] **T10.0 — planner crash, own commit** (`2f54179`). `plan._change_item` drops a
      `field:`/`section:` item whose entity ours deleted: the `D9` entity item owns it,
      and planning it raised `KeyError` from `_resolve_change`. Test asserts the item is
      in the diff for `theirs` and absent from the plan, with one D9 and no ops.
      `126 passed` across plan/session/execute/diff.
- [x] **T10.1 — error envelope** (`2f8d227`). `app/routes/errors.py`; the three
      byte-identical copies (verified by md5) now import it. `35 passed` on the route
      suites; app builds.
- [x] **T10.2 — decision payload** (`85ed841`). `plan._change_item` emits `theirs`/`ours`
      instead of unlabelled `a`/`b` — nothing read them, and D1/D7 already name sides.
- [ ] **T10.3 — `app/routes/history.py`, reads**: `GET /` (branches + drafts + parents
      + per-branch tip + current), `GET /diff`, `GET /read/{ref}/entities/{type}/{id}`,
      `GET /read/{ref}/script`.
- [ ] **T10.4 — `app/routes/history.py`, writes**: `POST /snapshots`, `POST /branches`,
      `POST /switch` (with `open_drafts` on refusal), `PATCH /branches/{id}`,
      `DELETE /branches/{id}`, `DELETE /snapshots/{id}`. Each destructive route requires
      an explicit `confirm: true` in the body (owner: switch, delete branch, delete
      draft, apply) and refuses with 422 naming the action when it is absent.
- [ ] **T10.5 — merge session routes**: `POST /merges`, `GET /merges/{id}`,
      `PUT /merges/{id}/selection`, `PUT /merges/{id}/decisions/{key}` (D-T10-C's three
      outcomes), `POST /merges/{id}/preview`, `POST /merges/{id}/apply`, `DELETE /merges/{id}`.
- [ ] **T10.6 — `services.list_projects` enrichment**: `current_draft`, `branch_count`,
      `last_saved`, `changes_since_save`; no manifest → the four defaults; never adopt,
      never `list_branches`.
- [ ] **T10.7 — `tests/test_history_routes.py`**, and the listing tests for the four keys.
- [ ] **T10.8 —** `server.py` router registration; `Notes.md` findings.
- [x] **T10.9 — the `set_decision` guards** (`4ef042d`). Two refusals, both raised from
      `session.py` so T11 inherits them: malformed key, and a well-formed key this plan
      does not hold ("is not asked (yet)"). The chained D2→D4 case is pinned.

## Notes carried in from earlier tasks

- **T3/T4:** `head_state` migrates `story.db` and must never be pointed at a draft;
  reading a draft goes through `project_view`. The routes call the core, so this is a
  constraint on what they call, not on what they may build.
- **T4 Issues:** "views are cached per session — T10 owns sessions and is where a cache
  belongs." → D-T10-A.
- **T6 Issues:** `compare` materializes both states; a session-level cache is where a
  saving would go. → same decision.
- **T8/T9:** `session.show` re-plans on every call; `preview` copies the target; `apply`
  holds the manifest lock and copies the target for its restore point. The preview and
  apply routes are **explicit actions**, never triggered by a form change — this is a
  route-contract statement, and the UI task must not wire it to an `oninput`.
- **T7:** `imprecise_base` must be surfaced; `session.show` already returns it, so the
  route passes it through rather than recomputing.
- **T7 review finding:** unticking the arriving scene while keeping the holder's
  `plot_roles` edit leaves a plot with no holder. Nothing refuses it. A **warning** on
  the workspace is T13's; no route work is needed, but `GET /merges/{id}` must not
  claim the plan is sound — it reports `ready` and `decisions`, nothing more.
- **T9:** `session.py` stores inputs and never an op list; a route that wants "the plan"
  calls `show`/`preview`, so there is no stored plan to serve.
- **T11 will follow this task** and needs the same core functions, so the routes must
  stay thin: resolve, call, translate. No logic that a tool would have to repeat.
