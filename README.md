# White Words Studio

The workspace for White Words, a studio of writing tools that share one story data
model. The studio and app names here are structural: what a user reads is the
app's own name, never the studio's.

## Layout

- `apps/scriptwriting/` — the scriptwriting app. Distribution
  `white-words-scriptwriting`, command `white-words`, importable as
  `white_words.scriptwriting`.
- `packages/` — where code goes once a second app needs to share it. Empty today;
  see its README for what belongs there.
- `docs/` — design material: the brand kit, dashboard inventories, research notes.
- `tasks/`, `archieved/` — historical artefacts. `tasks/` is not collected by the
  test suite.

The import root is the `white_words` namespace, which deliberately has no
`__init__.py`: apps and shared packages are its children, so a film app can join
as `white_words.film` — in this repository or as a distribution of its own —
without taking a top-level package name.

## Running it

    cd apps/scriptwriting
    python -m pytest                     # the suite
    white-words --root <projects root>   # the app

`apps/scriptwriting/README.md` covers installation, the Hermes agent profile, the
dashboard and the MCP surface in detail.
