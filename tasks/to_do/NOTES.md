# REMINDERS WORK TO DO

## VERSIONING (general)

- Issue with soft delete as agent has no way to look at what soft deleted entities exist. Also Soft deleted entities can not be hard deleted individually or by batch. Only purge all exist.
- No way to save a "draft". for draft i mean the whole project state not only the script. This would include abiltiy to open different draft (question: possibly created branches of development?)
- no basic functionality in script editing tool, like undo, redo (possily with usual keybindings ctrl+z etc..)
- can these all be resoluted also with the backup strategy we have already existing?

## UI

- No UI for soft deleted entities (bin?) or ability to manually hard delete individual, multiple or all soft deleted entities.
- Main project selection page not working and never really designed or worked on.
- Characters extended view has some imagination errors (lacks of spaeces betweeen them?) and inconsistent text color (DEEPER GOAL, WHAT THEY KNOW content text bith gray) (different from others)
- Same as above for scenes.
- duplication of plot roles in the ui in scenes (main plot is repeated bith as main plot and as the named version - unecessary). WOuld be nice also if the color matched the plots color.
- Troughout the ui inciting_incident is shown written as "inciting_incident". Ugly. SHould be "inciting incident" without _.
- All sections form entities should be colapsable (default to uncollapsed). plus a button to expand all.
- We should allow fo all (but relationshoips) extended view to expand (like we doi in beats for example)

## VARIOUS

- Relationship entity edit manual allows for adding scenes in which the relationship is featured, but doing so doe not propagate in the scene beat. If we do allow for setting this on relationship entity directly, than it should also require the user to provide the `change` (as the entity is already known as the relationship that is being edited). This way the  `changes` (from scene beat schema) can added to the scene beat entry for that scene.
-  beats  allsow us to choose amogst all the characthers,  locations and words (for most of the fields in the beats tab). NOw it hink that is ok, as it allws for edge cases in which an entity of thoe may not be directly part of the scene, but has effect or is effected, which is good. Howevere i feel that we should firt list the entoties that are in the scene as they will be the most commony used. Than thsoe that are related to the one that are the scenes (entities that belong to the relationships of characthers in the scene , to plots that are present in the scene, and world related to the loaction) as they will be the secondly most commony used. Finally and than we can keep the rest of the list with the remaining one that exist project wide. However the issue reami for the dropdown to become very long if all entoties are listed, so i ma not sure how we can handle that> I hope i was clear in what i ma saying.

## SKILL

- One skill multiple refereces vs Multiple skills? To decide
- CONTEXT_SKILL.md  is good, but mya have steal infoo about presenting the preview_md. NOw the app does taht automatically with a card. TO fix in skill and verify where that is still mentioned erronously (the skill  creation must have seen it somewhere)

## SETUP

- we have been too heavy on removing basic functionalities in hermes agent creation . We may want to reintroduce: Memory.md (usefull so the agent cna improve) - consider what skills fro basic heremes agent creation are usefull and keep them (minimal), 
- consider which basic tools are usefull (consideration about terminal use and utility tools, like read file etc.. we want to avoid agent to use those instead teh mcp, yet they may be usefull.. not sure here)