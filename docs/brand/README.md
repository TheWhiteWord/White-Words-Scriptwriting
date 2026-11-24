## APP MAIN ICON SET

Traced a painted W into a vector, made it larger in the frame, and exported the full icon set. The files are attached: PNGs for the PWA icons, the launcher and the favicons, plus SVG masters.

The white-on-black version is the primary icon, and ink on paper is the alternate (icon-512-paper.png and icon-paper.svg).

- **Size in the frame.** The W now fills about 80% of the icon width, up from about 68% in your original.
- **Faithful tracing.** I traced the real brush edges, including the dry streaks along the right side, so nothing is invented.
- **Small sizes.** The `favicon-32.png`, `favicon-16.png` and `favicon.svg` files use a simplified trace with the finest streaks removed. That keeps the stroke readable in a browser tab.
- **Maskable icons.** `icon-maskable-512.png` and `icon-maskable-192.png` have a smaller W with a safe margin, so Android can crop them into a circle or squircle without cutting the letter.
- **Other files.** `icon-512.png` and `icon-192.png` are the standard PWA icons with rounded corners, `apple-touch-icon-180.png` is full-bleed square, and `launcher-256.png` is for the desktop launcher.

## APP NAVIGATION BAR SET

I drew the nine nav icons as brush strokes and put them on a new board at the bottom of the canvas, "Nav icons": https://claude.ai/artifact/1PfrHKpaFCbWHDnTfgKsPC. I haven't opened it, so tell me what you see.

The board has three parts:
- **The rail:** a mock of your left nav at 24 px, with Script lit as the open view.
- **A 3×3 grid:** the nine icons at 80 px with their names.
- **A size check:** three of the icons at 32, 24, 20 and 16 px, to see whether they hold up small.

They share the logic of the W without copying its texture. Each stroke is heavier where the brush lands and thinner where it lifts, and loops like the character nodes and the pin are left slightly open, as if drawn in one pass. I kept the edges clean on purpose. Rough edges at 24 px would look like a rendering glitch, and the character of the W comes from the weight and the loops.

I matched the icons to your screenshots by shape, so I may have labelled some wrongly. Please check these:
- **Project:** a window grid, for the dashboard.
- **Characters:** three connected nodes.
- **Plots:** two nodes joined by a curving thread.
- **Scenes:** a list with dots.
- **Locations:** a pin.
- **Sequences:** two linked loops. Your current "XX" icon looks like a chain, so I read it as sequences, but it might be something else.
- **Value arc:** a rising zigzag with an arrowhead.
- **Worlds:** a globe with an equator line.
- **Script:** a page with a folded corner and dialogue lines.
- **Notes:** a plain rectangle with three lines, a landscape card without a folded corner, so it reads as different from Script.
- **Trash:** a lid with a handle and a bin with two ribs.
- **Sync:** two circular arrows. It has the finest detail of the set, so it's the one to check at 16 px.
- **Expand:** a brush chevron for the bottom of the rail.

The board shows all thirteen in a rail mock, with the trash badge copied from your current one, plus a grid and a size check. I matched these four to your screenshot by shape, so tell me if any does something different in the app. Notes especially was a guess.

**Downloads**
- `nav-icons.zip` has one SVG per icon, plus the sprite.
- `nav-sprite.svg` is all thirteen as symbols, so you can reference them in the app with `<use href="nav-sprite.svg#ww-script">`. The IDs are `ww-` followed by the name: project, characters, plots, scenes, locations, sequences, value-arc, worlds, script, notes, trash, sync and expand.

Every icon is filled with `currentColor`, so your CSS controls the color. I'd use the dim grey for inactive icons and off-white for the open view. If you load the files through an `<img>` tag they'll render black, so use the sprite or inline them instead.

## BRAND KIT

I chose to package everything into a single brand kit, `white-words-brand-kit.zip`, so you can drop the brand into the app. I haven't opened the finished zip or tested it in your app.

**Inside the kit**
- **`public/`** is ready to copy into your app's public folder. It has the manifest (`manifest.webmanifest`), the `<head>` tags (`head-snippet.html`), all the app icons and favicons, and the thirteen nav icons plus the sprite.
- **`desktop/`** has `white-words.desktop` and the 256 and 512 px launcher icons.
- **`README.md`** has the install steps, including the commands that put the launcher icon in the right place on Linux.

**Two things you need to do**
1. **The launcher command.** I don't know how your app starts, so `Exec=` in the `.desktop` file is a placeholder. Replace it with your start command, then run the install commands in the README.
2. **The old name.** Your screenshots still show "Message Story Architect…" in the chat box. Search the codebase for "Story Architect" and "Hermes" and replace both with "White Words". I didn't touch your code, so those strings are still there.

The manifest uses the dark ink color for both the splash background and the browser theme, so the app should open without a white flash. It lists the maskable icons separately from the standard ones, which is what Android needs to crop them properly.

## WORDMARK LOCKUP

1. **Mark + serif.** The brush W next to "White Words" in Cormorant Garamond, a classical high-contrast serif. This is the safe default and the one I'd use on an About screen, a website or a README.
2. **Brush W as the initial.** The brush W is the first letter, followed by "hite Words". It's the most distinctive and the one that feels most like your painting. It works best large, and I'd avoid it below about 24 px tall because the W and the "h" start to merge.
3. **Icon tile + sans.** The app icon beside "White Words" in Jost, a clean geometric sans. This is for small headers and a title bar, where the tile does the recognising.
4. **Stacked.** The W above the name, centered, for the splash screen.

Each lockup comes in two color versions: light for dark backgrounds and ink for light ones. After rendering, I made two small fixes. In the initial version I added a little more space after the W so it doesn't touch the "h". In the tile version I lightened the tile slightly in the dark version so it doesn't disappear into the background.

My suggestion is to use 1 as the everyday lockup, 2 on the largest surfaces where it can breathe, and 4 for the splash. If you'd rather commit to one, I'd pick 1, because it's the least likely to look wrong in a context you haven't thought of yet.

The files are in `wordmark/` and also zipped as `wordmark.zip`. Both serif and sans fonts are open licence (SIL OFL), so you can bundle them if you want to set live text in the same typeface.

## LOADING STATE

**How it works**
- **Splash:** the brush W is written in one stroke over 2.4 seconds, and then "White Words" fades in underneath and the whole thing holds. It plays once and stays on screen until the app is ready.
- **Inline:** the app icon tile with the W drawing itself, holding for a moment, then wiping away in the same direction, on a 3.2 second loop. This is the loader for anything that takes a moment, like the AI checking continuity in the chat panel, which the board shows.
- **The brush feel:** the stroke slows down at the two bottom turns and at the middle peak, as a brush does when it changes direction, so it doesn't move at a flat speed.
- **Reduced motion:** if the system has reduced motion switched on, both files show the finished W with no animation.

**Using them in the app**
- Load them as an image (`<img src="white-words-loading-splash.svg">`) or paste the SVG inline. Both work, and the animation is built into the file, so no JavaScript is needed.
- The splash has a transparent background, so put it on your ink color (#0E0E10). The inline tile has its own dark background.
- To remove the splash when loading finishes, just hide or fade out the element. The animation doesn't need to be told when to stop.

**Caveats**
- The reveal follows a centerline I drew by hand over your painted W, so the order of the strokes is my best reading of how you made it. If you'd rather the W were drawn in a different order, for example the left stroke first and the right last without doubling back through the middle, tell me and I'll change it.
- At 24 px the tile loader is small enough that the draw-on mostly reads as a shimmer. At 28 px and up it shows as a W being written.

## FONT

The font is Iowan Old Style BT in Roman