# REMINDERS WORK TO DO

## SKILL

- One skill multiple refereces vs Multiple skills? To decide
- CONTEXT_SKILL.md  is good, but mya have steal infoo about presenting the preview_md. NOw the app does taht automatically with a card. TO fix in skill and verify where that is still mentioned erronously (the skill  creation must have seen it somewhere)

## SETUP

- we have been too heavy on removing basic functionalities in hermes agent creation . We may want to reintroduce: Memory.md (usefull so the agent cna improve) - consider what skills fro basic heremes agent creation are usefull and keep them (minimal), 
- consider which basic tools are usefull (consideration about terminal use and utility tools, like read file etc.. we want to avoid agent to use those instead teh mcp, yet they may be usefull.. not sure here)

## VERSIONING (general)

- Issue with soft delete as agent ahs no way to look at what sof deleted entoties exist
- No way to save a "draft". for draft i mean the whole project state not only the script.
- no basic functionality in script editing tool, like undo, redo (possily with usual keybindings ctrl+z etc..)
- can these allbe resoluted aslo with the backup strategy we have already existing?

## MANUAL CREATION (in progress task_37)

- Need to implement manual creation of entities form the ui (bypasses the agent, no drafts direct writes), so taht an user can manually create these
- Overlay similar to the memory one. All avaible non comoputed fields and sections avaible. They need descriptions that are suitable for human (in fiels taht erase as input goes in?)
- some can be selection from avaible keys (eg: One of... only the avaibel ones are presented)
- subfield too. DO trey appear once the primary field is inserted?

# VARIOUS

- Inciting incident needs to be unique
- Relationship entity edit manual allows for adding scenes in which the relationship is featured, but doing so doe not propagate in the scene beat. If we do allow for setting this on relationship entity directly, than it should also require the user to provide the `change` (as the entity is already known as the relationship that is being edited). This way the  `changes` (from scene beat schema) can added to the scene beat entry for that scene.
- Characters extended view has some imagination errors (lacks of spaeces betweeen them?))and inconsistent text color (DEEPER GOAL, WHAT THEY KNOW content text bith gray) (different from others)
- Same as above for scenes.
- duplication of plot roles in the ui in scenes (main plot is repeated bith as main plot and as the named version - unecessary). WOuld be nice also if the color matched the plots color.
- Troughout the ui inciting_incident is shown written as "inciting_incident". Ugly. SHould be "inciting incident" without _.
- All sections form entities should be colapsable (default to uncollapsed). plus a button to expand all.
- We should allow fo all (but relationshoips) extended view to expand (like we doi in beats for example)
- I have  a small insecurity about the fact that plot roles do not allow for  multiple roles for each plt in the same scene. While i see the thinking about that, i am not sure that is necessarely something taht should be enforced strictly, as i can see some cases in which a scene may hold multiple roles.. for example a scene taht starts with setup of a plot, and in teh same scene also delivers the inciting incident (maybe is a long scene...). While is for the most parts I undrstant the reasoning behind doing so, i feel taht there are egde cases in which that may limit the author, so i rathet do not enforce that. In fact this creates a split between teh agent path and the manual path right now:

Dashboard form: rejected. manual_entities.py:950 — "This scene already has a role in that plot — one role per plot." Live on both create and edit (_validate runs in both paths); pinned by tests/test_manual_structure.py:131.
Agent write path (create_entity/edit_entity/story_draft): allowed. validate_scene_plot_roles has no duplicate-plot check. Both entries become separate relation rows (plot_setup, plot_inciting_incident) and the read side reports both — story_load.py:349 even documents it: "One plot can promote the same scene twice (setup and crisis)."
So the actual gap: the schema description says "One entry per plot" (constants.py:213) and the form enforces it, but the agent write path doesn't — an agent can write a scene the form would then refuse to save.
I would rather just follow the agent path and allow  tahth One plot can promote the same scene twice.

-in regarsd to the the picker with “+ New…” I am not sure we  may want that. Feesl to me that if we allow the creation of different entoties while creating one that contain them we may start to overcomplicate the process. I would say that a character must be created before is used ina scene, so a plot. THe one ecception may be the value to this, as is not as complex, and really is an evlaution happens after the content is created, and can vary from scene form scene, so its probably right to allow elasticity there.

-  beats  allsow us to choose amogst all the characthers,  locations and words (for most of the fields in the beats tab). NOw it hink that is ok, as it allws for edge cases in which an entity of thoe may not be directly part of the scene, but has effect or is effected, which is good. Howevere i feel that we should firt list the entoties that are in the scene as they will be the most commony used. Than thsoe that are related to the one that are the scenes (entities that belong to the relationships of characthers in the scene , to plots that are present in the scene, and world related to the loaction) as they will be the secondly most commony used. Finally and than we can keep the rest of the list with the remaining one that exist project wide. However the issue reami for the dropdown to become very long if all entoties are listed, so i ma not sure how we can handle that> I hope i was clear in what i ma saying.