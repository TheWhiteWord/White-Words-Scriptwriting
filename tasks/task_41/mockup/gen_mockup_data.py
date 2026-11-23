"""Build the mockup's payload from the real fixture project, through the real API.

Nothing here is hand-written sample data: every name, stamp and warning comes out
of `core.trash.trash_for_ui` / `trash_detail` on a throwaway copy of
tests/fixtures/save-the-children, so the mockup shows what the app will show.

The deletions are chosen to cover one of each row shape:
  * a bundle with two children        the world "The I" and its two locations
  * a bundle whose root has a script  the scene "Central Room - Night" + beats
  * a row that wears the 30+ chip     a plot, stamped two months back
  * a row whose restore is blocked    a beats record whose scene is in the trash
  * a plain row, and a live reference the character Kael, still named by its
                                      relationships
"""
import json
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "src")

ROOT = Path("/tmp/mockup-src")
SRC = Path("tests/fixtures/save-the-children")
JS = Path("tasks/task_41/mockup/data.js")

shutil.rmtree(ROOT, ignore_errors=True)
project = ROOT / "projects" / "save-the-children"
project.parent.mkdir(parents=True)
shutil.copytree(SRC, project)

import story_architect.core.config as cfg
real = cfg.load_plugin_config
cfg.load_plugin_config = lambda: {"root_path": str(ROOT)}
try:
    from story_architect.tools.story_import import handler as import_handler
    result = json.loads(import_handler({"project": str(project), "confirm": True,
                                        "root_path": str(ROOT)}))
    assert result.get("success"), result
finally:
    cfg.load_plugin_config = real

from story_architect.core import trash
from story_architect.core.writes import delete_entity


def sql(sql_text, *args):
    conn = sqlite3.connect(str(project / ".story" / "story.db"))
    try:
        rows = conn.execute(sql_text, args).fetchall()
        conn.commit()
        return rows
    finally:
        conn.close()


def restamp(ids, stamp):
    """Move one deletion's stamp, children included, so the bundle stays one."""
    for eid in ids:
        sql("UPDATE entities SET deleted_at=? WHERE id=?", stamp, eid)


def drop(entity_type, entity_id, stamp=None):
    """Delete through the write path, then (optionally) age the whole bundle."""
    res = delete_entity(project, entity_type, entity_id, "t", True)
    assert res.get("success"), res
    ids = [entity_id] + res.get("cascade_deleted", [])
    if stamp:
        restamp(ids, stamp)
    return ids


# 1. two months old: a plot, alone, so the 30-day chip has something to sit on
drop("plot", "the-resistance", "2026-09-21T08:00:00+00:00")

# 2. a beats record deleted on its own six days ago...
blocked_beats = sql("SELECT id FROM entities WHERE type='scene_beats' "
                    "AND parent_id='central-room-day'")[0][0]
drop("scene_beats", blocked_beats, "2026-11-14T21:40:00+00:00")

# 3. ...and its scene, which went later. Restoring the beats is refused.
drop("scene", "central-room-day", "2026-11-22T10:05:00+00:00")

# 4. a scene with its beats: one bundle, with a script
drop("scene", "central-room-night", "2026-11-20T09:15:00+00:00")

# 5. a character whose relationships stay live and keep naming it
drop("character", "kael", "2026-11-21T18:02:00+00:00")

# 6. a world with two locations: the widest bundle, and the newest
drop("world", "the-i", None)

payload = {
    "list": trash.trash_for_ui(project),
    "blocked": trash.trash_detail(project, "scene_beats", blocked_beats),
    "bundle": trash.trash_detail(project, "scene", "central-room-night"),
    "world": trash.trash_detail(project, "world", "the-i"),
    "character": trash.trash_detail(project, "character", "kael"),
    "details": {},
    "purgePreview": trash.purge_preview(project, [
        {"entity_type": "character", "id": "kael"},
        {"entity_type": "scene", "id": "central-room-night"},
    ]),
}
JS.parent.mkdir(parents=True, exist_ok=True)

print("rows:", payload["list"]["count"], "entities:", payload["list"]["entities"])
for item in payload["list"]["items"]:
    blocked = item["restore"]["blockers"]
    print(f'  {item["deleted_at"][:19]}  {item["label"]:<12} {item["name"]:<22} '
          f'entities={1 + len(item["includes"])}  '
          f'{"BLOCKED" if blocked else "restorable"}{"  30+" if item["purge_eligible"] else ""}')
print("purge preview items:", [i["name"] for i in payload["purgePreview"]["items"]])
print("purge preview affected:", [(a["name"], a["field"]) for a in payload["purgePreview"]["affected"]])
print("character warnings:", json.dumps(payload["character"]["restore"]["warnings"], indent=1)[:600])
print("wrote", JS)

# one detail payload per row, so every row in the mockup opens a real panel
payload["details"] = {
    item["id"]: trash.trash_detail(project, item["type"], item["id"])
    for item in payload["list"]["items"]
}
JS.write_text(
    "/* Mockup data, produced by core/trash.trash_for_ui / trash_detail / purge_preview\n"
    "   on a throwaway copy of tests/fixtures/save-the-children (gen_mockup_data.py).\n"
    "   A build artefact of the mockup, not sample data written by hand. */\n"
    "window.MOCKUP = " + json.dumps(payload, ensure_ascii=False, indent=1) + ";\n")
print("wrote", JS)
