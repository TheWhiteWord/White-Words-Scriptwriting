# packages/

Shared code for the studio's apps.

Empty on purpose. `white_words.scriptwriting` is self-contained today, so nothing
needs sharing yet; the directory marks where code goes when a second app wants it
— the story data model and the engine under `apps/scriptwriting/src/white_words/
scriptwriting/core/` are the obvious first candidates, since a film app would work
on the same projects.

Anything placed here is imported as `white_words.<name>`, alongside the apps, so
the studio namespace stays the only import root.
