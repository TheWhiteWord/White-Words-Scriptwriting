# Trash tab — mockup

Open `trash-mockup.html` in a browser. It is a static page: no server, no build.

It is not a drawing of the tab. It is the tab's real markup and real stylesheets
(`src/story_architect/web/css/*.css`) fed with the real payload that
`core/trash.py` returns, generated from a throwaway copy of
`tests/fixtures/save-the-children`. `trash.css` is the candidate stylesheet for
`web/css/trash.css`; the HTML's inline script is the shape `views/trash.js` will
take.

## What to look at

| state | how to reach it |
|---|---|
| the list, one panel open | open the file |
| list only, panel closed | `#noppanel` |
| nothing selected, nothing open | click a row's ✕ |
| selection, buttons with counts | `#selectall`, or tick rows |
| a selection that contains a blocked row: `Restore` goes inert, `Delete permanently` does not | `#selectall` — hover the disabled `Restore` for the reason |
| the purge confirmation | `#dialog`, or `Delete permanently` |
| empty trash | `#empty` |
| filter with no match | `#nomatch` |
| expanded sidebar (badge on the right) | the `Expand sidebar` button |

The mockup bar along the bottom is **not** part of the design; it exists to flip
states.

## What each row proves

The fixture was deliberately deleted in six ways, so the list has one row of
every shape:

- **World “The I”** — a bundle: two locations were flagged with it, shown nested
  and read-only. Restoring or removing the world takes all three.
- **Scene “Central Room - Day”** — carries a script; the panel shows the prose.
- **Character “Kael”** — its three relationships stayed live and still name it:
  they appear under `Referenced by`, and the purge card lists them as affected.
- **Scene “Central Room - Night”** — a bundle whose root has a script.
- **Scene Beats “central-room-day-beats”** — deleted on its own six days before
  its scene went. **Restore is blocked** with the real message and the one-click
  fix, because a beats record restored without its scene is invisible to every
  reader.
- **Plot “The Resistance”** — two months old, so it wears the `30+ days` chip.

## Regenerating the data

```bash
.venv/bin/python tasks/task_41/mockup/gen_mockup_data.py
```

Writes `data.js`, which the page loads with a `<script>` tag (`file://` cannot
`fetch` a sibling file). The stamps are fixed in the script, and the page
pins “now” to `2026-11-23T15:12Z`, so the relative labels ("3 days ago") stay
put instead of drifting as the real clock moves.
