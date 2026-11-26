"""P2a probe: write the standing set through the real write path.

Same code the generator will use, limited to project/worlds/values/locations/characters.
Proves the content is accepted by the validators, not just by check_content.py.

    .venv/bin/python tasks/task_43/probe_p2a.py
"""

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from white_words.scriptwriting.core.writes import (  # noqa: E402
    create_entity,
    create_project,
    edit_entity,
)

CONTENT = Path(__file__).parent / "content"


def load(name):
    return json.loads((CONTENT / name).read_text())


root = Path(tempfile.mkdtemp(prefix="p2a-"))
project_json = load("project.json")
slug = project_json["slug"]

create_project(slug, project_json["fields"], root)
project = root / "projects" / slug
print(f"project: {slug}")

# project sections are created empty by create_project, so fill them by edit.
edit_entity(project, "project", slug, dict(project_json["sections"]), "project sections")
print("  project sections written")

counts = {}

for kind, key in (
    ("world", "worlds"),
    ("value", "values"),
    ("location", "locations"),
    ("character", "characters"),
    ("plot", "plots"),
):
    for item in load(f"{key}.json")[key]:
        create_entity(project, kind, item["id"], item["fields"], item["sections"])
        counts[kind] = counts.get(kind, 0) + 1
    print(f"  {kind}: {counts.get(kind, 0)}")

structure = load("structure.json")
for a in structure["acts"]:
    create_entity(project, "act", a["id"], a["fields"], a["sections"])
    counts["act"] = counts.get("act", 0) + 1
for s in structure["sequences"]:
    create_entity(project, "sequence", s["id"], s["fields"], s["sections"])
    counts["sequence"] = counts.get("sequence", 0) + 1
print(f"  act: {counts.get('act', 0)}, sequence: {counts.get('sequence', 0)}")

for r in load("relationships.json")["relationships"]:
    create_entity(project, "relationship", r["id"], r["fields"], r["sections"])
    counts["relationship"] = counts.get("relationship", 0) + 1
print(f"  relationship: {counts['relationship']}")

for sc in load("scenes.json")["scenes"]:
    create_entity(project, "scene", sc["id"], sc["fields"], sc["sections"])
    counts["scene"] = counts.get("scene", 0) + 1
print(f"  scene: {counts['scene']}")

# Read it back through the same reader the dashboard uses.
from white_words.scriptwriting.core.db import get_db  # noqa: E402

conn = get_db(project)
rows = conn.execute(
    "SELECT type, COUNT(*) FROM entities WHERE is_deleted=0 GROUP BY type ORDER BY type"
).fetchall()
print("\nstored:", dict(rows))

# The location->world link is parent_id, and variant_of is a relation: prove both landed.
world_of = conn.execute(
    "SELECT parent_id FROM entities WHERE id='munchkinland'"
).fetchone()[0]
variant = conn.execute(
    "SELECT from_id, to_id, kind FROM live_relations WHERE kind='location_variant'"
).fetchall()
print("munchkinland world:", world_of)
print("location_variant relation:", variant)

section_count = conn.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
print("sections:", section_count)

# Plot roles are computed from scenes, so every plot must currently hold none.
role_rels = conn.execute(
    "SELECT kind, COUNT(*) FROM live_relations WHERE kind LIKE 'plot_%' GROUP BY kind"
).fetchall()
print("plot role relations (must be empty until scenes exist):", dict(role_rels))

# A sub plot's plot_type and scope are extra columns, so prove they landed.
print("plots:", conn.execute(
    "SELECT id, extra FROM entities WHERE type='plot' ORDER BY id").fetchall() and "")
for pid, extra in conn.execute("SELECT id, extra FROM entities WHERE type='plot' ORDER BY id"):
    e = json.loads(extra)
    print(f"  {pid:26} scope={e.get('plot_scope'):5} type={e.get('plot_type','')!r}")

# Scenes must land under their sequence with the order we passed, and the
# plot roles must have become relations rather than staying in extra.
print("scene count by sequence:", conn.execute(
    "SELECT parent_id, COUNT(*) FROM entities WHERE type='scene' "
    "GROUP BY parent_id ORDER BY parent_id").fetchall())
print("scene orders:", conn.execute(
    "SELECT parent_id, order_key FROM entities WHERE type='scene' "
    "ORDER BY parent_id, order_key").fetchall())
print("plot role relations:", dict(conn.execute(
    "SELECT kind, COUNT(*) FROM live_relations WHERE kind LIKE 'plot_%' GROUP BY kind").fetchall()))
print("location relations:", conn.execute(
    "SELECT COUNT(*) FROM live_relations WHERE kind='location_scene'").fetchone()[0])

# Content must be body-only: no stored heading line.
bad = [sid for (sid,) in conn.execute(
    "SELECT e.id FROM entities e JOIN sections s ON s.entity_id=e.id "
    "WHERE e.type='scene' AND s.heading='Content' "
    "AND (s.body LIKE 'INT.%' OR s.body LIKE 'EXT.%' OR s.body LIKE '.%')"
)]
print("scenes whose Content opens with a heading:", bad or "none")

# The forced-heading scene must still resolve its location relation, and its
# composed heading must be the authored text.
print("the-house-lifts location:", conn.execute(
    "SELECT location_id FROM entities WHERE id='the-house-lifts'").fetchone())
from white_words.scriptwriting.core.scene_script import scene_heading
row = conn.execute(
    "SELECT e.extra, l.name FROM entities e LEFT JOIN entities l ON l.id=e.location_id "
    "WHERE e.id='the-house-lifts'").fetchone()
ex = json.loads(row[0])
print("composed heading:", scene_heading(ex.get("int_ext",""), row[1] or "", ex.get("place",""),
                                          ex.get("time_of_day",""), ex.get("forced_heading","")))
empty_all = conn.execute(
    "SELECT COUNT(*) FROM sections s JOIN entities e ON e.id=s.entity_id "
    "WHERE s.heading!='Content' AND TRIM(s.body)=''").fetchone()[0]
print("empty non-Content section bodies:", empty_all)
assert empty_all == 0, "a section was created with no body — sections were not passed to create_entity"
print("empty Content sections:", conn.execute(
    "SELECT COUNT(*) FROM sections s JOIN entities e ON e.id=s.entity_id "
    "WHERE e.type='scene' AND s.heading='Content' AND TRIM(s.body)=''").fetchone()[0])

# Acts must be numbered, sequences must sit under their act.
for rec in load("beats.json")["beats"]:
    create_entity(project, "scene_beats", rec["id"], rec["fields"], rec["sections"])
    counts["scene_beats"] = counts.get("scene_beats", 0) + 1
print(f"  scene_beats: {counts['scene_beats']}")

# Every beat reference must have resolved to a real row.
print("beats records:", conn.execute(
    "SELECT COUNT(*) FROM entities WHERE type='scene_beats'").fetchone()[0])
print("distinct scenes with beats:", conn.execute(
    "SELECT COUNT(DISTINCT parent_id) FROM entities WHERE type='scene_beats'").fetchone()[0])
print("scene_beats parented to a scene:", conn.execute(
    "SELECT COUNT(*) FROM entities b JOIN entities s ON s.id=b.parent_id "
    "WHERE b.type='scene_beats' AND s.type='scene'").fetchone()[0])
by_actor = {}
for (e,) in conn.execute("SELECT extra FROM entities WHERE type='scene_beats'"):
    for bt in json.loads(e).get("beats", []):
        for side in ("action", "reaction"):
            k = (bt.get(side) or {}).get("by")
            if k: by_actor[k] = by_actor.get(k, 0) + 1
non_char = {k: v for k, v in by_actor.items()
            if conn.execute("SELECT type FROM entities WHERE id=?", (k,)).fetchone()[0] != "character"}
print("non-character actors used:", non_char)
chg = {}
for (e,) in conn.execute("SELECT extra FROM entities WHERE type='scene_beats'"):
    for c in json.loads(e).get("changes", []):
        t = conn.execute("SELECT type FROM entities WHERE id=?", (c["entity"],)).fetchone()
        chg[t[0] if t else "MISSING"] = chg.get(t[0] if t else "MISSING", 0) + 1
print("changes by entity type:", chg)

print("relationships:", conn.execute(
    "SELECT COUNT(*) FROM entities WHERE type='relationship'").fetchone()[0])
sec = next((sid for (sid,) in conn.execute(
    "SELECT id FROM entities WHERE type='relationship' AND id='dorothy-scarcrow'")), None)
print("scarcrow typo still present:", bool(sec))
print("secret perspectives:", sum(
    1 for (_e,) in conn.execute("SELECT extra FROM entities WHERE type='relationship'")
    if any(v.get("secret") for v in json.loads(_e).get("perspectives", {}).values())))

print("acts:", conn.execute(
    "SELECT id, order_key FROM entities WHERE type='act' ORDER BY order_key").fetchall())
print("sequences:", conn.execute(
    "SELECT id, parent_id, order_key FROM entities WHERE type='sequence' ORDER BY parent_id, order_key").fetchall())
conn.close()

print("\nPROBE ROOT:", root)
