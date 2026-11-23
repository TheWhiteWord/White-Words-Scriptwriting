# Task 41 — Trash bin UI

Design spec. Branch `trash-bin-ui`. Paths below are relative to
`src/story_architect/` unless stated otherwise.

---

## 1. What is already there

A delete is a flag, not a removal, and the app already has a complete,
deliberately minimal trash *model*. The UI is the only missing piece.

| Fact | Where |
|---|---|
| A delete sets `is_deleted=1, deleted_at=<one stamp>` on the entity and on every live child | `core/writes.py:794` (`delete_entity`), stamp at `:888-893` |
| Sections, revisions, relation rows and other entities' references are **left as written** | `core/writes.py:895-907` |
| Reads hide the deleted: the `live_relations` view and `core/references.py` | `core/db.py:97-103`, `core/references.py:41` (`dead_ids`) |
| So restore is exact: clear the flag, nothing is rebuilt | `tools/story_admin.py:416` (`_restore_entity`) |
| "Deleted together" is **one** rule: same `parent_id` **and** same `deleted_at` | `core/trash.py:52` (`deleted_together`) |
| The agent's trash: `list_deleted` folds those children under the parent as `includes` | `tools/story_admin.py:358` |
| Permanent removal: `purge_deleted` (single target, or a sweep over an age floor), backup first | `core/trash.py:123`, `:100` (`preview_purge`) |
| The agent's purge is not executed: it stages a draft the user approves | `tools/story_admin.py:324`, `core/drafts.py:1066+` |
| Dashboards read only live entities | `core/db.py:1203` (`is_deleted=0` at `:1243`) |

Two consequences drive the whole design:

1. **The trash rules already exist in `core/`+`tools/`; the UI must not invent a
   second copy of them.** Restore and purge from the browser go through new
   `core` functions that the agent's tool also calls.
2. **Nothing in `app/` can reach them today.** `_restore_entity` and
   `_list_deleted` live in the *tool* layer and return agent-shaped payloads, and
   `app/routes/entities.py` only knows form CRUD and a soft delete that refuses
   on blockers (`:76`, `:81`). A small, mechanical move of those two functions
   into `core/trash.py` is part of this task.

No schema change. Baseline stays at 5 (`core/db.py:BASELINE_VERSION`); the
trash needs only columns that already exist.

---

## 2. Decisions

The three open questions, settled.

### 2.1 A deletion bundle is atomic

- One trash row per **deletion**, not per entity: the root plus whatever was
  flagged by that same operation (`deleted_together`).
- The bundle's children are **listed nested and read-only**: they have no
  checkbox and no actions of their own. Restore and purge act on the whole
  bundle, always.
- Why this and not per-child control: the backend's restore already restores
  the bundle (`_restore_entity` clears the children with the parent's stamp) and
  the purge already removes it (`select_one_deletion`). A UI that let one child
  out would either lie about what the button does, or need a new DB rule for a
  case that has no meaning — a `scene_beats` record restored without its scene
  is invisible to every reader that keys on `parent_id`, and the write path
  refuses to create one that way.
- The UI is therefore a *view* of the existing rule, not a policy of its own.

**Not a bundle, though it looks like one.** Deleting a character from the form
also deletes its relationships (`core/manual_entities.py:1453`, the loop over
`prev["relationships"]`), but each of those is a separate `delete_entity` call,
so each carries its own stamp and its own row. They are separate items that
happen to share a second. The UI shows them as separate rows (grouped by time,
§5.3) — that is the honest reading, and it is what the agent's `list_deleted`
already reports.

### 2.2 Restoring into a live story: warn, let the user choose

Restoring is never refused for *references*. What can refuse it is a
**structural parent still in the trash**, because the invisible outcome is a
scene that vanishes from the Scenes tab (`parent_id` reads as `''` when its
parent is dead, `core/references.py:32-37`). So:

| Situation | UI behaviour |
|---|---|
| Parent (act / sequence / scene) is trashed | **Block** the restore. Explain it, and offer one button that restores the parent's bundle plus this item in one call. |
| Parent no longer exists (purged) | **Block** for `scene_beats` (a beat with no scene), **warn** for anything else (restores parentless). |
| References entities still in the trash (relationships, plot roles, cast, location) | **Warn**: the preview lists them, each with a "restore this too" action that adds it to the same batch. |
| References an id that was purged | **Warn** with a different colour: the link is gone for good and will read empty. |

Restore itself needs no confirmation: it is reversible (`story_admin.py:416`
docstring; the project's own rule that only irreversible things ask, `:6-10`).

### 2.3 Purge acts on an explicit selection, in one call

- Per-item, per-bundle, and "select all → delete permanently". No age-based
  action in the UI: naming an item is what bypasses the 30-day floor
  (`core/trash.py:129-131`), and select-all names every item too. The floor
  stays what it is — the guard on the agent's *sweep*, not on a human clicking a
  named thing.
- One **confirmation dialog** listing every name that will go (and what else
  loses a link), then one backup, then one transaction. Not a typed string:
  nothing in the app asks for one any more (`tools/story_admin.py:6-10`), and
  the dialog *is* the human's approval that the agent's draft card would be.
- One backup for the whole call, not one per item.

---

## 3. Backend work

### 3.1 `core/trash.py` gains the read/write paths the UI needs

Moved (not rewritten) from the tool, so there stays one implementation:

```python
def list_deleted(project_path, older_than_days=30, *, conn=None) -> dict
    # body of tools/story_admin.py:358, unchanged output
def restore(project_path, entity_type, entity_id, summary="") -> dict
    # body of tools/story_admin.py:416, plus "restored": [ids]
```

New, small, and shared by preview + action so a card can never describe a
different set from the one that happens:

```python
def restore_check(conn, entity_id) -> dict          # {"blockers": [...], "warnings": [...], "returned": {...}}
def restore_many(project_path, targets) -> dict     # one transaction, all-or-nothing
def purge_selected(project_path, targets) -> dict   # one backup, one transaction
def trash_for_ui(project_path, older_than_days=30)  # list_deleted + per-item UI fields
```

`restore_check` is a read. It returns:

```
blockers: [{code: "parent_trashed"|"parent_missing", message,
            fix: {entity_type, id, name}}]
warnings: [{code: "reference_in_trash", message,
            refs: [{entity_type, id, name, field}]},
           {code: "reference_purged", message, refs: [...]},
           {code: "stranded_children", message, refs: [...]}]
returned: {children: [{type,id,name}], relations: n, cast_scenes: [...],
           plot_roles: [...], location_links: n, sections: n}
```

`returned` is what becomes visible again — read before the restore, from the
same tables the readers use (`live_relations`, `references_to`). It is the
"nothing was rebuilt, it was only hidden" fact, shown to the user.

### 3.2 The one real bug this surfaces

`hard_delete` (`core/trash.py:68`) deletes the relation rows and blanks
`parent_id` / `location_id` on every row, but it does **not** touch the `extra`
JSON of **live** entities. After a purge, the id is gone from `entities`
entirely, so `dead_ids` (`core/references.py:41`) no longer knows it and
`live_extra` stops stripping it: a live scene keeps a `characters: ["kael"]`
that points at nothing, and renders a chip for a character that does not exist.

This is already reachable through the agent path; the trash tab makes it easy to
hit. Fix, ~15 lines, inside the same transaction:

```python
# core/references.py — one function, next to the readers that must agree with it
def scrub_live_extras(conn, ids) -> list:   # returns affected entity ids
    # for each LIVE row, rewrite `extra` with live_extra(extra, ids) when it changes
```

Call it from `hard_delete` before the `DELETE`, and report the affected ids in
the purge result so the confirmation and the toast can say
"also cleared from: scene 'The Unlocked Door'".

### 3.3 `tools/story_admin.py` delegates

`_list_deleted` and `_restore_entity` become thin calls into `core.trash`. Their
JSON must not change: `tests/test_list_deleted.py` and
`tests/test_delete_stamps.py` pin the shape, and the agent's behaviour is out of
scope for this task. In particular `restore` stays permissive the way it is
today — the structural-parent block in §2.2 is applied by the **route**, from
`restore_check`. The rule is core, so gating the tool later is a one-line change
rather than a rewrite.

### 3.4 New router: `app/routes/trash.py`

Registered in `app/server.py:118-123` beside the others. Non-GET requests get
the Host / Origin / `X-Story-Architect` checks from the middleware, so no second
auth model is added here. Errors use the existing
`{"error": {"code", "message"}}` envelope (`app/routes/entities.py:17`).

```
GET    /api/projects/{slug}/trash?older_than_days=30
GET    /api/projects/{slug}/trash/{etype}/{eid}
POST   /api/projects/{slug}/trash/{etype}/{eid}/restore
POST   /api/projects/{slug}/trash/restore          {targets: [{entity_type, id}, ...]}
POST   /api/projects/{slug}/trash/purge-preview    {targets: [...]}
POST   /api/projects/{slug}/trash/purge            {targets: [...]}
```

`GET /trash` — the list. One entry per deletion; children nested:

```json
{"count": 3, "purge_older_than_days": 30,
 "counts_by_type": {"scene": 2, "character": 1, "scene_beats": 4},
 "items": [
   {"type": "scene", "id": "the-unlocked-door", "name": "The Unlocked Door",
    "label": "Scene", "deleted_at": "2026-11-20T09:15:00+00:00",
    "preview": "INT. THE CENTRAL ROOM - DAY", "purge_eligible": false,
    "has_script": true,
    "includes": [{"type": "scene_beats", "id": "the-unlocked-door-beats",
                  "name": "The Unlocked Door beats", "label": "Scene Beats"}],
    "restore": {"blockers": [], "warnings": [{"code": "reference_in_trash", "...": "..."}]}
   }]}
```

`restore` and `restore.purge_eligible` on every row are computed in the same
pass, so the row, the panel and the button cannot disagree. `age_seconds` is
derived client-side from `deleted_at` (the browser's clock is fine for a
relative label; the absolute stamp stays the source of truth and is what the row
shows on hover).

`GET /trash/{etype}/{eid}` — the preview:

```json
{"entity": {"id", "type", "name", "label", "deleted_at", "one_sentence",
            "fields": {"...": "..."}, "extra": {}},
 "includes": [...], "sections": {"Content": "...", "Objective": "..."},
 "relations": {"out": [{"kind", "to": {"id","type","name"}}],
               "in":  [{"kind", "from": {"id","type","name"}}]},
 "referenced_by": [{"entity_type","id","name","field"}],
 "restore": {"blockers": [], "warnings": [], "returned": {}},
 "purge": {"items": [{"type","id","name"}], "affected": [{"entity_type","id","name","field"}]}}
```

Sections come straight from the `sections` table — they survive a delete by
design, which is why the preview can show the prose the user is about to lose.
Fields are the `entities` columns plus `extra`, read unfiltered: the preview is
the one reader that must show the dead references.

`POST .../restore` and `POST /trash/restore` — 200 with
`{restored: [{type,id,name}], also_restored: [ids], returned: {...}}`. A blocked
target is `409 {"error": {"code": "restore_blocked", "message", "blockers": []}}`;
batch restore is **all-or-nothing** and names the refusal.

`POST /trash/purge-preview` → `{items, affected, backup: true}` and
`POST /trash/purge` → `{purged: [...], backup: "<name>", affected: [...]}`. A
live or unknown target is `409`, an empty `targets` list is `422` — the UI must
name what it removes, so "purge everything" is select-all, never an implicit
sweep.

---

## 4. UI: the tab

### 4.1 Nav

`index.html:155` — a bin button between **Memory** (`:148`) and **Refresh**
(`:156`), which is directly above Refresh as asked:

```html
<button class="nav-btn" data-view="trash" id="nav-trash"
        onclick="DASH.switchView('trash', this)" title="Trash">
  <svg class="nav-icon" viewBox="0 0 16 16" fill="none">
    <path d="M3 4.5h10M6.5 4.5V3h3v1.5" stroke="currentColor" stroke-width="1.3"/>
    <path d="M4.5 4.5l.6 8.2a1 1 0 0 0 1 .9h3.8a1 1 0 0 0 1-.9l.6-8.2"
          stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
    <path d="M6.8 7v4M9.2 7v4" stroke="currentColor" stroke-width="1.1"/>
  </svg>
  <span class="nav-label">Trash</span>
  <span class="nav-badge" id="nav-trash-count" hidden>0</span>
</button>
```

`data-view="trash"` is required: `switchView` (`web/js/navigation.js:18`) clears
`active` from `.nav-btn[data-view]` and lights the button it is handed. The view
container id must be `trash-view` — the same invariant every other view obeys.

The badge is the one new sidebar element. `.nav-btn` gains `position: relative`;
the badge sits `top: 3px; right: 4px` with a 9px tabular numeral, the antagonist
red token (`--role-antagonist`) as background and `#111` as text, and moves to
`margin-left: auto` when `#sidebar.expanded`. It is `hidden` at zero. It is
`aria-hidden`; the button's `title` carries "Trash — 3 items".

### 4.2 View

`index.html` after `#script-view` (before `</main>` at `:339`), same
header/body convention as every other view:

```html
<div class="view" id="trash-view">
  <div class="view-header">
    <div class="view-title">Trash</div>
    <div class="view-subtitle" id="trash-subtitle">—</div>
    <div class="view-header-actions">
      <div class="search-bar"> <input id="trash-search" …> </div>
      <button class="btn" id="trash-select-all">Select all</button>
      <button class="btn" id="trash-restore">Restore</button>
      <button class="btn btn-danger" id="trash-purge">Delete permanently</button>
    </div>
  </div>
  <div class="view-body">
    <div class="trash-list" id="trash-list"></div>
  </div>
</div>
```

The two action buttons are **disabled** until something is selected, and carry
the count in their label: `Restore 3`, `Delete permanently 3`. Their disabled
state is the affordance; nothing pops up unprompted.

New files: `web/js/views/trash.js` (all of it), `web/css/trash.css` (scoped to
`#trash-view` / `.trash-*`). `index.html` also gets the stylesheet link (after
`:32`) and the script tag (after `:558`).

Wiring is a hook, not an edit to another module's body:

```js
DASH.onViewOpened(view => { if (view === 'trash') DASH.trashOpen(); });
```

`DASH.onViewOpened` already exists (`navigation.js:7`) and fires at the end of
`switchView`. `DASH.boot` calls `DASH.refreshTrashBadge()`, so the count is
right before the tab is ever opened (one small GET — the trash is small by
design, `core/references.py:41`).

### 4.3 The list

```
Deleted 2 hours ago ──────────────────────────────────────────────
☐  SCENE   The Unlocked Door            INT. THE CENTRAL ROOM - DAY
       └ also deleted with it: 1 scene-beats record        [Restore] [Delete…]
☐  CHARACTER  Kael                       Protagonist
       └ also deleted with it: —                            [Restore] [Delete…]
Deleted yesterday ────────────────────────────────────────────────
☐  WORLD  Gilead                         Near-future city-state
```

- **Grouped by deletion time** — `Deleted just now` / `today` / `yesterday` /
  `this week` / `older` — newest first. This is the "organized" part: one
  deletion, one heading, and the bundles underneath. Items deleted in the same
  second (a character and the relationships the form took with it) land under
  the same heading naturally.
- A row shows: checkbox, type label, name, and a `preview` line (a scene's
  composed heading, `one_sentence` otherwise), then on the right the relative
  age and the "also deleted with it" line when `includes` is non-empty.
- A row with a restore blocker shows a small amber marker (`--c-gap`) and its
  Restore button is disabled with a `title` giving the reason; clicking the row
  explains it fully in the panel.
- Hovering the age shows the absolute stamp (`title`, from `deleted_at`).
- `purge_eligible` (>30 days) shows a muted `30+ days` chip — informational; it
  changes nothing about what the UI will do.
- Search filters by name and type (`input` event, no debounce needed at this
  size); the subtitle shows `3 items · 7 entities`.
- `Select all` selects every **root** row currently visible after filtering.
  Selected state is `Set` of `type:id` in `DASH.trashState.selected`.
- Empty state: the bin icon, "The trash is empty", and one line — "Deleted
  scenes, characters and everything else wait here until you restore them or
  remove them for good."
- With a filter that matches nothing: "No deleted item matches “…”. Clear the
  filter." (never the empty state, which would be a lie).

### 4.4 Selection and the two actions

- `Restore n` → one `POST /trash/restore` with every selected root. No
  confirmation: reversible, and the app never asks about reversible things. On
  `409 restore_blocked` the response's blockers are shown in a dialog with the
  offered fix ("Restore “Act One” as well" → resends with the parent added to
  the batch).
- `Delete permanently n` → `POST /trash/purge-preview`, then
  `DASH.efDialog(...)` (`web/js/forms/entity-form.js:768` — the app's own small
  confirm, already used by Reorder's review):

```
Permanently delete 3 items?                       kicker: cannot be undone
  Scene — The Unlocked Door  (deleted 2 hours ago)
    + 1 scene-beats record
  Character — Kael           (deleted yesterday)
  World — Gilead             (deleted 12 Nov)

  Also affected: Scene “The Final Offer” will lose a cast entry.
  A backup is taken first (story.db, before-purge).
        [Keep them]  [Delete 3 permanently]
```

  The dialog's `busy()` covers the round trip; the list is built from the
  preview response, never from the client's cached row (so a row restored by the
  agent since the page loaded cannot be described wrongly).
- Both actions end the same way: `await DASH.reloadData()` (the existing
  no-page-reload refetch, `web/js/script-editor/editor.js:900`), then the trash
  list refetches, selection is pruned to ids that still exist, the badge
  updates, and a toast names what happened
  (`Restored 3 items · 5 entities`, `Permanently deleted 3 items — backup before-purge`).
  `DASH._ownWriteUntil = Date.now() + 8000` is set first, so the app's own write
  does not raise the "Project updated" banner (`core.js:75`, the same guard the
  form uses at `entity-form.js:547`).

### 4.5 The preview panel

A row click opens the **existing** detail panel and renders into it, so the shell,
width transition and close behaviour are already right
(`web/css/components.css:88`, `web/js/panels/panel-manager.js`):

```js
DASH.showTrashPanel = function (item) {           // in views/trash.js
  document.getElementById('panel-type').textContent = item.label + ' · in the trash';
  document.getElementById('panel-name').textContent = item.name;
  document.getElementById('panel-body').innerHTML = …;
  document.getElementById('panel-footer').innerHTML = …;
  DASH.openPanel();
};
```

- The panel opens **wide** (`#detail-panel.panel-wide`): a scene's script at
  320px is unreadable. The class is removed when the trash view is reopened.
- Body, in order: *Deleted* (absolute + relative, "N days ago"), the entity's
  fields, the prose **sections** (a scene's Content first — that is what the
  user came to check), *Also deleted with it* (the bundle, read-only), *Links*
  (relations in/out), *Referenced by* (live entities naming it, which will show
  it again), then *When restored* (the `returned` summary in words: "5 entities
  become visible again: 1 scene-beats record, 3 relationships, the cast entry on
  “The Final Offer”").
- Blockers and warnings are printed where they belong — at the top when they are
  blockers (with the fix button), beside the link they concern when they are a
  reference warning (each with "Restore this too", which adds that id to the
  pending batch).
- Footer: `Restore` (primary), `Delete permanently` (danger, ghost), and a
  `Close`. Plus, for a scene with a script, nothing else — the preview is
  read-only. Editing a trashed entity is out of scope (§8).
- `Esc` closes the panel (`switchView` already closes it on a view change).

### 4.6 Copy rules

- Say *deleted*, never *trashed*, in sentences; use **Trash** for the tab, and
  *Delete permanently* for the irreversible action. The word "purge" is the
  agent's vocabulary and stays inside the backend and the tool schema.
- Every irreversible statement carries its consequence and its undo in the same
  breath: "Cannot be undone. A backup is taken first (`before-purge`), so it can
  be restored by hand."
- Never claim something is gone that is not: after a purge the Markdown file
  survives until the next export (`core/trash.py:174`) — the toast note says so
  rather than implying the vault is clean.

---

## 5. Edge cases the UI must get right

| Case | Behaviour |
|---|---|
| The agent restored an item while the tab was open | The next mutation's 404/409 names it; the list refetches and selection drops the dead id. The "Project updated" banner still covers the plain case. |
| Two rows share a `deleted_at` but are not parent/child (a character and its relationships) | Two rows. Never merged: merging would claim a restore does more than it does. |
| Purging a character whose relationships are still in the trash | Allowed. `hard_delete` removes the relation rows; the relationship rows left behind now name a purged id — the restore preview of *those* warns with `reference_purged`. |
| A bundle whose root is a `scene_beats` record with no parent (deleted separately) | Its own row, `restore_check` reports `parent_trashed`, block with the fix. |
| The trash holds a `project` row | Impossible: `SINGLETONS` (`core/manual_entities.py:47`) and `_refuse_singleton`. The UI does not special-case it; an empty/short list is the answer. |
| `deleted_at` is naive or unparseable | The backend refuses to write such a stamp (`core/clock.py:30,52`); the UI formats defensively (`—` rather than `NaN days`) and never sorts on it. |
| Deleted **project folders** (`.story-trash`, `tools/story_admin.py:38`) | Out of scope (§8). They are a different kind of trash with a different restore. |
| A very large trash | The list is unpaginated on purpose (`dead_ids` already assumes it is small). Above ~500 rows the grouping is still one pass; if it ever matters, the header gets a "show older" fold, not a new endpoint. |

---

## 6. Files

| File | Change |
|---|---|
| `core/trash.py` | + `list_deleted`, `restore` (moved verbatim), + `restore_check`, `restore_many`, `purge_selected`, `trash_for_ui` |
| `core/references.py` | + `scrub_live_extras` (§3.2) |
| `tools/story_admin.py` | `_list_deleted` / `_restore_entity` delegate; output unchanged |
| `app/routes/trash.py` | **new** — six endpoints (§3.4) |
| `app/server.py` | one `include_router` line (`:118-123`) |
| `web/index.html` | nav button (`:155`), view (before `:339`), css link (`:32`), script (`:558`) |
| `web/js/views/trash.js` | **new** — state, list, grouping, selection, panel, actions, badge |
| `web/css/trash.css` | **new** — `.trash-*`, `.nav-badge`, all scoped |
| `tests/test_trash_routes.py` | **new** (§7) |
| `tests/trash_harness.js`, `tests/test_trash_ui.py` | **new** — the render functions run in node, as `test_story_view_structure.py` does |
| `docs/Dashboard inventory/0.4.1 — Views and tabs.md` | nine views → ten; add the `trash` row and the badge |

---

## 7. Tests

- **Round trip** (`test_trash_routes.py`): delete a scene via
  `core.writes.delete_entity` → `GET /trash` shows one row with `includes` →
  `POST .../restore` → the row is gone, the beat is back, `live_relations` shows
  the cast again. Pins that the route and the tool agree.
- **Bundles**: the child is never a root row; restoring the root restores the
  child; a child deleted earlier keeps its own row (`test_delete_stamps.py`'s
  fixture is the shape to reuse).
- **Parent block**: a separately-deleted child whose parent is in the trash →
  `409 restore_blocked` with `fix`, and the fix-then-retry call succeeds.
- **Batch atomicity**: one blocked target in a batch of three restores nothing.
- **Purge**: takes exactly one backup; removes the bundle; leaves a live
  sibling's `location_id` blank rather than dangling; `extra` scrub
  (§3.2) — a live scene's cast no longer names the purged character, and the
  result reports the affected entity.
- **Purge refusals**: live target → 409, unknown → 409, empty `targets` → 422.
- **UI**: grouping buckets from `deleted_at`, row HTML for a bundle and for a
  blocked row, selection pruning after a refetch, and that no inline handler is
  built with an unescaped id (the dashboard's habit — ids go through
  `data-*` + one delegated listener).

---

## 8. Non-goals

- Editing a trashed entity. Restore it, edit it, delete it again — the write
  path refuses a deleted target (`core/writes.py:1087`), and weakening that for
  a nicer trash is not worth the invariant.
- Deleting *to* the trash from the UI (already exists: the form's Delete, and
  the agent). This task only opens the other direction.
- Project-folder trash (`list_trashed_projects` / `.story-trash`). Same idea,
  different mechanism, no DB. A second section in this tab would be the right
  place, later.
- Automatic or scheduled purging. The agent's sweep stays the only unattended
  route, and it goes through a draft.
- Pagination, virtual scrolling, undo-stack. The trash is small and restore is
  the undo.

---

## 9. Phases

1. **Core** — move `list_deleted` / `restore` into `core/trash.py`, add
   `restore_check` / `restore_many` / `purge_selected` / `trash_for_ui`, the
   `scrub_live_extras` fix. Existing tests green, tool output byte-identical.
2. **Routes** — `app/routes/trash.py` + registration + `test_trash_routes.py`.
   The whole feature is reachable with `curl` before any JS exists.
3. **Nav + view skeleton** — bin button, badge, empty-state view, hook, badge
   fetch at boot. Nothing else works yet, and that is fine.
4. **List** — grouping, rows, search, select-all, disabled action buttons.
5. **Panel** — preview body, links, warnings, footer actions.
6. **Actions** — restore (with the blocked dialog and the fix), purge-preview →
   `efDialog` → purge, `reloadData`, badge refresh, toasts.
7. **Docs** — inventory 0.4.1, and a line in `tasks/tasks.md`.
