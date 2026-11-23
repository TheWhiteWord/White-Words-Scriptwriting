# White Words brand kit

## Web / PWA  (copy `public/` into the app's public folder)
- `manifest.webmanifest` and `head-snippet.html` (paste the tags into <head>).
- `favicon.svg` is the main tab icon; the 16/32 PNGs are fallbacks.
- `icon-maskable-*` have extra margin so Android can crop them to any shape.
- `icons/icon-512-paper.png` is the ink-on-paper alternate (not referenced by default).

## Navigation icons  (`public/nav/`)
- One SVG per icon, all filled with `currentColor`.
- Or use the sprite: `<svg><use href="/nav/nav-sprite.svg#ww-script"/></svg>`
  Note: `<use>` with an external file only works same-origin; otherwise inline the sprite once in the page.
- Suggested colours: inactive #8E8C86, open view #F4F2EC on a #26262B tile.

## Linux launcher  (`desktop/`)
1. Edit `Exec=` in `white-words.desktop` to the command that starts the app.
2. Install:
   mkdir -p ~/.local/share/icons/hicolor/256x256/apps ~/.local/share/icons/hicolor/512x512/apps ~/.local/share/applications
   cp white-words-256.png ~/.local/share/icons/hicolor/256x256/apps/white-words.png
   cp white-words-512.png ~/.local/share/icons/hicolor/512x512/apps/white-words.png
   cp white-words.desktop ~/.local/share/applications/
   update-desktop-database ~/.local/share/applications 2>/dev/null; gtk-update-icon-cache ~/.local/share/icons/hicolor 2>/dev/null
3. If the app runs as a PWA in Chrome/Chromium, it creates its own launcher; the manifest icons are used for it.

## Strings still saying "Story Architect"
The chat box placeholder ("Message Story Architect…") and any window title or export header.
Search the codebase for "Story Architect" and "Hermes" and replace with "White Words".

## Colours
Ink #0E0E10 · Off-white #F4F2EC · Paper #F1EDE3 · Dim UI #8E8C86 · Tile #26262B
