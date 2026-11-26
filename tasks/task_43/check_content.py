"""Check the demo's content JSON against the app's real schema.

Not a test suite: one pass/fail per file, so a typo in a field name or a section
heading is caught here rather than at the first write. Run with the project venv:

    .venv/bin/python tasks/task_43/check_content.py
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from white_words.scriptwriting.core.constants import (  # noqa: E402
    CONFLICT_LEVELS,
    ENTITY_SCHEMAS,
    PLOT_ROLES,
    PLOT_TYPES,
    SCENE_DRAMATIC_ROLES,
    SCENE_STATUSES,
    SCENE_TIMES_OF_DAY,
    INT_EXT_CHOICES,
    VALID_ROLES,
    VALUE_ARCS,
)
from white_words.scriptwriting.core.entity import ENTITY_COLUMN_MAP, relation_fields  # noqa: E402
from white_words.scriptwriting.core.manual_entities import (  # noqa: E402
    ENUMS,
    REL_TYPES,
    standard_sections,
)

HERE = Path(__file__).parent
CONTENT = HERE / "content"

failures = []


def fail(where, msg):
    failures.append(f"{where}: {msg}")


def load(name):
    path = CONTENT / name
    if not path.exists():
        return None
    return json.loads(path.read_text())


def allowed_fields(entity_type):
    """Every key create_entity accepts, from the same sources it validates against."""
    return (
        set(ENTITY_SCHEMAS[entity_type])
        | set(standard_sections(entity_type))
        | set(relation_fields(entity_type))
        | set(ENTITY_COLUMN_MAP.get(entity_type, {}))
    )


def check_entity(where, entity_type, fields, sections):
    allowed = allowed_fields(entity_type)
    meta = ENTITY_SCHEMAS[entity_type]

    for key in fields:
        if key not in allowed:
            fail(where, f"unknown field {key!r} (valid: {', '.join(sorted(allowed))})")
        elif meta.get(key, {}).get("computed"):
            fail(where, f"field {key!r} is computed and must not be written")

    # A required field whose schema default is non-empty is filled by the write path
    # (create_entity merges the default), so only an empty default means "must author".
    from white_words.scriptwriting.core.constants import WRITE_PATH_SUPPLIED

    for field, m in meta.items():
        if m.get("optional") or m.get("computed"):
            continue
        if field in WRITE_PATH_SUPPLIED or m.get("default"):
            continue
        if not fields.get(field):
            fail(where, f"required field {field!r} is empty")

    standard = standard_sections(entity_type)
    for heading in sections:
        if heading not in standard:
            fail(where, f"unknown section {heading!r}")
    missing = [h for h in standard if h not in sections]
    if missing:
        fail(where, f"sections missing: {', '.join(missing)}")
    for heading, body in sections.items():
        if not (body or "").strip():
            fail(where, f"section {heading!r} is empty")
        elif entity_type != "scene" and not (25 <= len(body.split()) <= 70):
            fail(where, f"section {heading!r} is {len(body.split())} words, target 30-60")


def check_enum(where, entity_type, fields):
    for (etype, field), options in ENUMS.items():
        if etype != entity_type or field not in fields:
            continue
        if fields[field] and fields[field] not in options:
            fail(where, f"{field}={fields[field]!r} not in {options}")


# ── project ──
project = load("project.json")
if project:
    check_entity("project", "project", project["fields"], project["sections"])
    if project["fields"]["act_count"] != 3:
        fail("project", "act_count should be 3")

# ── worlds ──
worlds = load("worlds.json")
if worlds:
    for w in worlds["worlds"]:
        check_entity(f"world/{w['id']}", "world", w["fields"], w["sections"])

# ── values ──
values = load("values.json")
if values:
    seen_rungs = {}
    for v in values["values"]:
        where = f"value/{v['id']}"
        check_entity(where, "value", v["fields"], v["sections"])
        rungs = [v["fields"][r].strip().lower() for r in ("p", "c", "cd", "nn")]
        if len(set(rungs)) != 4:
            fail(where, f"the four rungs must be distinct words, got {rungs}")
        if v["fields"]["name"].strip().lower() != v["id"]:
            fail(where, "id must be the slug of `name` (a turn names the value by name)")
        for r in rungs:
            if r in seen_rungs:
                fail(where, f"rung word {r!r} already used by {seen_rungs[r]}")
            seen_rungs[r] = where

# ── locations ──
locations = load("locations.json")
if locations:
    world_ids = {w["id"] for w in (worlds or {}).get("worlds", [])}
    loc_ids = {loc["id"] for loc in locations["locations"]}
    base_count = 0
    for loc in locations["locations"]:
        where = f"location/{loc['id']}"
        check_entity(where, "location", loc["fields"], loc["sections"])
        if loc["id"] in loc["fields"]["name"] or " - " in loc["fields"]["name"]:
            fail(where, "name must not contain ' - ' (it becomes the heading's middle segment)")
        if loc["fields"].get("world") and loc["fields"]["world"] not in world_ids:
            fail(where, f"world {loc['fields']['world']!r} does not exist")
        variant = loc["fields"].get("variant_of")
        if variant:
            base_count += 1
            if variant not in loc_ids:
                fail(where, f"variant_of {variant!r} does not exist")
            if variant == loc["id"]:
                fail(where, "a location cannot be a variant of itself")
    if base_count != 1:
        fail("locations", f"expected exactly one variant_of, found {base_count}")

# ── characters ──
characters = load("characters.json")
if characters:
    seen_roles = set()
    for c in characters["characters"]:
        where = f"character/{c['id']}"
        check_entity(where, "character", c["fields"], c["sections"])
        check_enum(where, "character", c["fields"])
        role = c["fields"]["story_role"]
        if role not in VALID_ROLES:
            fail(where, f"story_role {role!r} not in {VALID_ROLES}")
        seen_roles.add(role)
        if not c["fields"].get("knowledge"):
            fail(where, "knowledge list is empty — it is a demonstration field")
    missing = set(VALID_ROLES) - seen_roles
    if missing:
        fail("characters", f"no character demonstrates role(s): {', '.join(sorted(missing))}")

# ── plots ──
plots = load("plots.json")
if plots:
    char_ids = {c["id"] for c in (characters or {}).get("characters", [])}
    scopes = {"main": 0, "sub": 0}
    types = set()
    for pl in plots["plots"]:
        where = f"plot/{pl['id']}"
        check_entity(where, "plot", pl["fields"], pl["sections"])
        check_enum(where, "plot", pl["fields"])
        scope = pl["fields"].get("plot_scope")
        if scope not in ("main", "sub"):
            fail(where, f"plot_scope {scope!r} must be 'main' or 'sub'")
            continue
        scopes[scope] += 1
        if scope == "sub":
            ptype = pl["fields"].get("plot_type")
            if not ptype:
                fail(where, "a sub plot requires plot_type")
            elif ptype not in PLOT_TYPES:
                fail(where, f"plot_type {ptype!r} not in {PLOT_TYPES}")
            else:
                types.add(ptype)
        elif pl["fields"].get("plot_type"):
            fail(where, "a main plot must not carry plot_type")
        cast = pl["fields"].get("characters") or []
        if not cast:
            fail(where, "characters is empty — value_turns validate effects against it")
        for cid in cast:
            if cid not in char_ids:
                fail(where, f"protagonist {cid!r} is not a character")
    if scopes["main"] != 1:
        fail("plots", f"expected exactly 1 main plot, found {scopes['main']}")
    if scopes["sub"] != 4:
        fail("plots", f"expected 4 sub plots, found {scopes['sub']}")
    if len(types) < 3:
        fail("plots", f"expected at least 3 distinct plot_type badges, got {sorted(types)}")

# ── structure ──
structure = load("structure.json")
if structure:
    act_ids = {a["id"] for a in structure["acts"]}
    for a in structure["acts"]:
        where = f"act/{a['id']}"
        check_entity(where, "act", a["fields"], a["sections"])
        check_enum(where, "act", a["fields"])
        if not isinstance(a["fields"].get("order"), int):
            fail(where, "order must be an int (acts are not auto-numbered)")
    if len(act_ids) != 3:
        fail("structure", f"expected 3 acts, found {len(act_ids)}")
    orders = [a["fields"]["order"] for a in structure["acts"]]
    if orders != [1, 2, 3]:
        fail("structure", f"act order must be 1,2,3 — got {orders}")

    plot_ids = {p["id"] for p in (plots or {}).get("plots", [])}
    per_act = {aid: 0 for aid in act_ids}
    for s in structure["sequences"]:
        where = f"sequence/{s['id']}"
        check_entity(where, "sequence", s["fields"], s["sections"])
        check_enum(where, "sequence", s["fields"])
        act = s["fields"].get("act_id")
        if act not in act_ids:
            fail(where, f"act_id {act!r} is not an act")
        else:
            per_act[act] += 1
        primary = s["fields"].get("primary_plot")
        if primary and primary not in plot_ids:
            fail(where, f"primary_plot {primary!r} is not a plot")
    for aid, n in per_act.items():
        if n < 2:
            fail("structure", f"{aid} has {n} sequences; an act needs at least 2")

    # A duplicate order inside one act is not refused by any writer, it just makes
    # the story order depend on id strings. Catch it here.
    by_act = {}
    for s in structure["sequences"]:
        by_act.setdefault(s["fields"]["act_id"], []).append(s["fields"]["order"])
    for aid, orders in by_act.items():
        if len(orders) != len(set(orders)):
            fail("structure", f"{aid} sequence orders are not unique: {sorted(orders)}")

# ── relationships ──
rels = load("relationships.json")
if rels:
    char_ids = {c["id"] for c in (characters or {}).get("characters", [])}
    pairs = set()
    rel_types, rel_statuses = set(), set()
    secrets = []
    strengths = []
    for r in rels["relationships"]:
        where = f"relationship/{r['id']}"
        f = r["fields"]
        check_entity(where, "relationship", f, r["sections"])
        chars = f.get("characters") or []
        if len(chars) != 2:
            fail(where, f"characters must be exactly two, got {len(chars)}")
        for cid in chars:
            if cid not in char_ids:
                fail(where, f"character {cid!r} does not exist")
        key = tuple(sorted(chars))
        if key in pairs:
            fail(where, f"duplicate pair {key}")
        pairs.add(key)
        pv = f.get("perspectives") or {}
        if set(pv) != set(chars):
            fail(where, f"perspectives keys {sorted(pv)} != characters {sorted(chars)}")
        for who, view in pv.items():
            if who not in chars:
                fail(where, f"perspective {who!r} is not in characters")
            if view.get("type") not in REL_TYPES:
                fail(where, f"perspective type {view.get('type')!r} not in {REL_TYPES}")
            s = view.get("strength")
            if not isinstance(s, (int, float)) or not -1.0 <= s <= 1.0:
                fail(where, f"strength {s!r} must be a number in -1.0..1.0")
            else:
                strengths.append(s)
            for req in ("label", "feeling"):
                if not (view.get(req) or "").strip():
                    fail(where, f"perspective {who!r} has no {req}")
            if view.get("secret"):
                secrets.append((r["id"], who))
            if view.get("type"):
                rel_types.add(view["type"])
        if f.get("status") not in ENUMS[("relationship", "status")]:
            fail(where, f"status {f.get('status')!r} not in {ENUMS[('relationship', 'status')]}")
        rel_statuses.add(f.get("status"))

    if len(secrets) < 2:
        fail("relationships", f"expected >=2 secret perspectives, got {secrets}")
    if len(rel_types) < 5:
        fail("relationships", f"expected >=5 distinct types, got {sorted(rel_types)}")
    if rel_statuses != set(ENUMS[("relationship", "status")]):
        fail("relationships", f"statuses {sorted(rel_statuses)} must cover {ENUMS[('relationship','status')]}")
    if not any(s < 0 for s in strengths):
        fail("relationships", "no negative strength — the graph has no enemies")
    if max(strengths) < 1.0:
        fail("relationships", "no relationship at the 1.0 ceiling")

# ── global id uniqueness (ids are unique ACROSS types) ──
if not failures:
    seen_ids = {}
    for fn in ("worlds.json", "values.json", "locations.json", "characters.json",
               "plots.json", "structure.json", "scenes.json", "relationships.json"):
        doc = load(fn)
        if not doc:
            continue
        for key in ("worlds", "values", "locations", "characters", "plots",
                    "acts", "sequences", "scenes", "relationships"):
            for item in doc.get(key, []):
                if item["id"] in seen_ids:
                    fail(item["id"], f"id is used by both {seen_ids[item['id']]} and {fn}")
                seen_ids[item["id"]] = fn

# ── scenes ──
scenes = load("scenes.json")
if scenes:
    plot_ids = {p["id"] for p in (plots or {}).get("plots", [])}
    char_ids = {c["id"] for c in (characters or {}).get("characters", [])}
    loc_ids = {loc["id"] for loc in (locations or {}).get("locations", [])}
    seq_ids = {s["id"] for s in (structure or {}).get("sequences", [])}

    per_seq = {}
    singular = {}          # (plot, role) -> scene id, for the UNIQUE_PLOT_ROLES check
    roles_seen = set()
    int_exts = set()
    statuses = set()
    turn_words_ok = True

    for sc in scenes["scenes"]:
        where = f"scene/{sc['id']}"
        f = sc["fields"]
        check_entity(where, "scene", f, sc["sections"])
        check_enum(where, "scene", f)

        if f["sequence_id"] not in seq_ids:
            fail(where, f"sequence_id {f['sequence_id']!r} is not a sequence")
        else:
            per_seq.setdefault(f["sequence_id"], []).append(f["order"])
        if f.get("location") and f["location"] not in loc_ids:
            fail(where, f"location {f['location']!r} does not exist")
        for cid in f.get("characters") or []:
            if cid not in char_ids:
                fail(where, f"character {cid!r} is not a character")

        # heading rules, from core/writes._scene_heading_guard
        forced = f.get("forced_heading") or ""
        int_ext = f.get("int_ext") or ""
        # The guard excludes int_ext / place / time_of_day from a forced heading, but
        # NOT location: the scene still happens somewhere, it just names itself.
        if forced and (int_ext or f.get("place") or f.get("time_of_day")):
            fail(where, "forced_heading is exclusive with int_ext / place / time_of_day")
        if forced and not forced.startswith("."):
            fail(where, f"forced_heading {forced!r} must start with '.'")
        if not forced and not (int_ext and f.get("location")):
            fail(where, "a scene with a script needs int_ext + location, or forced_heading")
        if int_ext:
            if int_ext not in INT_EXT_CHOICES:
                fail(where, f"int_ext {int_ext!r} not in {INT_EXT_CHOICES}")
            int_exts.add(int_ext)
        if f.get("time_of_day") and f["time_of_day"] not in SCENE_TIMES_OF_DAY:
            fail(where, f"time_of_day {f['time_of_day']!r} not in {SCENE_TIMES_OF_DAY}")

        # no_cast is the deliberate-empty flag; it must not disagree with characters
        if f.get("no_cast") and (f.get("characters") or []):
            fail(where, "no_cast is set but characters is not empty")
        if not f.get("no_cast") and not (f.get("characters") or []):
            fail(where, "no characters and no_cast is not set — the gap would be flagged forever")

        # Content must not carry a heading line: the heading is composed.
        content = sc["sections"]["Content"]
        first = next((ln for ln in content.splitlines() if ln.strip()), "")
        if first.startswith(". ") or first.startswith("."):
            fail(where, "Content starts with a forced heading line; the heading is composed")
        if first.upper().startswith(("INT.", "EXT.", "INT./EXT.", "EST.")):
            fail(where, "Content starts with a heading line; the heading is composed")

        # plot roles
        proles = f.get("plot_roles") or []
        role = f.get("dramatic_role") or ""
        if role in ("transition", "non-event") and proles:
            fail(where, f"dramatic_role {role!r} requires plot_roles to be empty")
        if role in ("transition", "non-event"):
            roles_seen.add(role)
        elif role:
            roles_seen.add(role)
        seen_pairs = set()
        for entry in proles:
            if entry["plot"] not in plot_ids:
                fail(where, f"plot_roles names unknown plot {entry['plot']!r}")
            if entry["role"] not in PLOT_ROLES:
                fail(where, f"plot_roles role {entry['role']!r} not in {PLOT_ROLES}")
            pair = (entry["plot"], entry["role"])
            if pair in seen_pairs:
                fail(where, f"duplicate plot_roles entry {pair}")
            seen_pairs.add(pair)
            if entry["role"] in ("inciting_incident", "crisis", "climax"):
                if pair in singular:
                    fail(where, f"{pair} is already held by {singular[pair]}")
                singular[pair] = sc["id"]

        statuses.add(f.get("status"))

        # dialogue: the duration statistics read real cues, so require them
        cue_lines = [ln for ln in content.splitlines() if ln.isupper() and ln.strip() and len(ln.split()) <= 4]
        if not f.get("no_cast") and len(cue_lines) < 2:
            fail(where, f"only {len(cue_lines)} character cue(s) — needs at least 2 for the stats")

    # ── value turns, read off the beats ──
    rungs = {}
    for v in (values or {}).get("values", []):
        rungs[v["fields"]["name"].strip().lower()] = {
            k: v["fields"][k] for k in ("p", "c", "cd", "nn")
        }
    plot_cast = {p["id"]: set(p["fields"].get("characters") or [])
                 for p in (plots or {}).get("plots", [])}

    chain = {}
    turns_total = 0
    levels_seen = set()
    for sc in scenes["scenes"]:
        f = sc["fields"]
        where = f"scene/{sc['id']}"
        turns = f.get("value_turns") or []
        if not turns:
            continue
        # `dramatic_role` governs the scene's structural slot in a plot, and
        # `value_turns` measure a value's movement — two axes. A transition may
        # turn a value (the cyclone is where home is lost in transit) because it
        # occupies no plot role. A non-event moves nothing by definition, so it
        # may not: that is the contradiction the engine's own docstring names.
        if f.get("dramatic_role") == "non-event":
            fail(where, "a non-event scene moves nothing, so it cannot carry value_turns")
        for i, tn in enumerate(turns):
            turns_total += 1
            at = f"{where}.value_turns[{i}]"
            plot = tn.get("plot")
            if plot not in plot_cast:
                fail(at, f"plot {plot!r} does not exist")
                continue
            val = (tn.get("value") or "").strip().lower()
            if val not in rungs:
                fail(at, f"value {val!r} is not a defined value")
                continue
            words = rungs[val]
            for key in ("from", "to"):
                w = (tn.get(key) or "").strip()
                if w.lower() not in {x.lower() for x in words.values()}:
                    fail(at, f"{key} {w!r} is not a rung of {val}: {list(words.values())}")
            if (tn.get("from") or "").lower() == (tn.get("to") or "").lower():
                fail(at, f"from and to are the same rung ({tn['from']!r}) — that is not a turn")
            effects = tn.get("effects") or []
            if not effects:
                fail(at, "effects is empty")
            seen_chars = set()
            for j, e in enumerate(effects):
                cid = e.get("character")
                if cid in seen_chars:
                    fail(at, f"{cid} appears twice in effects")
                seen_chars.add(cid)
                if cid not in plot_cast[plot]:
                    fail(at, f"{cid} is not a protagonist of {plot}")
                circles = [lv["conflict_level"] for lv in e.get("levels") or []]
                if len(circles) != len(set(circles)):
                    fail(at, f"{cid} has a duplicate conflict_level")
                for lv in e.get("levels") or []:
                    levels_seen.add(lv["conflict_level"])
                    if not (lv.get("effect") or "").strip():
                        fail(at, f"{cid}/{lv['conflict_level']} has no effect sentence")
            # the ladder must be continuous per plot
            key = plot
            if key in chain and chain[key] != tn.get("from"):
                fail(at, f"ladder break on {plot}: previous turn ended at "
                         f"{chain[key]!r}, this one starts at {tn.get('from')!r}")
            chain[key] = tn.get("to")

    if turns_total < 20:
        fail("scenes", f"only {turns_total} value turns; expected >=20")
    if len(levels_seen) < 3:
        fail("scenes", f"conflict levels used: {sorted(levels_seen)}; expected all of CONFLICT_LEVELS")

    for seq_id, orders in per_seq.items():
        if len(orders) != len(set(orders)):
            fail("scenes", f"{seq_id} scene orders are not unique: {sorted(orders)}")

    if len(scenes["scenes"]) != 15:
        fail("scenes", f"expected 15 scenes, found {len(scenes['scenes'])}")
    missing = {"plot_role", "transition", "non-event"} - roles_seen
    if missing:
        fail("scenes", f"no scene demonstrates dramatic_role(s): {', '.join(sorted(missing))}")
    # INT./EXT. is deliberately absent: nothing in this story is a moving-vehicle
    # or threshold scene, and inventing one only to fill an enum would be fake.
    if not {"INT.", "EXT.", "EST."} <= int_exts:
        fail("scenes", f"int_ext coverage is {sorted(int_exts)}; needs INT., EXT. and EST.")
    if len(statuses) < 4:
        fail("scenes", f"scene statuses are {sorted(statuses)}; expected all 4")

# ── beats ──
beats = load("beats.json")
if beats:
    scene_ids = {s["id"] for s in (scenes or {}).get("scenes", [])}
    char_ids = {c["id"] for c in (characters or {}).get("characters", [])}
    loc_ids = {loc["id"] for loc in (locations or {}).get("locations", [])}
    world_ids = {w["id"] for w in (worlds or {}).get("worlds", [])}
    rel_ids = {r["id"] for r in (rels or {}).get("relationships", [])}
    by_types = char_ids | loc_ids | world_ids
    change_types = char_ids | rel_ids | loc_ids | world_ids

    covered = set()
    non_char_actors, rel_changes, loc_changes, empty_changes = set(), set(), set(), []
    tc_count = 0

    for rec in beats["beats"]:
        where = f"beats/{rec['id']}"
        f = rec["fields"]
        check_entity(where, "scene_beats", f, rec["sections"])
        if f["scene"] not in scene_ids:
            fail(where, f"scene {f['scene']!r} does not exist")
        covered.add(f["scene"])
        if f.get("driver") and f["driver"] not in char_ids:
            fail(where, f"driver {f['driver']!r} is not a character")
        for tc in f.get("true_character") or []:
            tc_count += 1
            if tc["character"] not in char_ids:
                fail(where, f"true_character {tc['character']!r} is not a character")
            for key in ("dilemma", "choice_reveals"):
                if not (tc.get(key) or "").strip():
                    fail(where, f"true_character entry is missing {key}")
        for ch in f.get("changes") or []:
            if ch["entity"] not in change_types:
                fail(where, f"changes entity {ch['entity']!r} is not a character, "
                            f"relationship, location or world")
            if not (ch.get("change") or "").strip():
                empty_changes.append((rec["id"], ch["entity"]))
            if ch["entity"] in rel_ids:
                rel_changes.add(ch["entity"])
            if ch["entity"] in loc_ids:
                loc_changes.add(ch["entity"])
        for i, beat in enumerate(f.get("beats") or []):
            for side in ("action", "reaction"):
                entry = beat.get(side) or {}
                by = entry.get("by")
                if by and by not in by_types:
                    fail(where, f"beats[{i}].{side}.by {by!r} is not a character, location or world")
                if by in (loc_ids | world_ids):
                    non_char_actors.add(by)
            # a beat with nothing on either side is an empty shell
            if not (beat.get("action", {}).get("surface")
                    or beat.get("reaction", {}).get("surface")
                    or beat.get("action", {}).get("subtext")
                    or beat.get("reaction", {}).get("subtext")
                    or beat.get("gap")):
                fail(where, f"beats[{i}] has no content on either side")

    if covered != scene_ids:
        fail("beats", f"scenes without a beats record: {sorted(scene_ids - covered)}")
    if empty_changes:
        fail("beats", f"empty change sentence on {empty_changes}")
    if tc_count < 10:
        fail("beats", f"only {tc_count} true_character moments; expected >=10")
    if not non_char_actors:
        fail("beats", "no location or world ever acts — the demo would never show that case")
    if not rel_changes:
        fail("beats", "no changes entry lands on a relationship")
    if not loc_changes:
        fail("beats", "no changes entry lands on a location")

# ── report ──
print()
if failures:
    print(f"FAIL — {len(failures)} problem(s):")
    for f in failures:
        print("  ·", f)
    sys.exit(1)

counts = {
    "worlds": len(worlds["worlds"]) if worlds else 0,
    "values": len(values["values"]) if values else 0,
    "locations": len(locations["locations"]) if locations else 0,
    "characters": len(characters["characters"]) if characters else 0,
}
print("PASS —", ", ".join(f"{k}={v}" for k, v in counts.items()))
if characters:
    roles = {c["fields"]["story_role"] for c in characters["characters"]}
    print("      roles covered:", ", ".join(sorted(roles)))
