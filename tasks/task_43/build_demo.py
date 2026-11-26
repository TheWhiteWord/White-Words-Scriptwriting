"""Build the Wizard of Oz demo project, story and history, through the real write path.

    .venv/bin/python tasks/task_43/build_demo.py            # refuses if the target exists
    .venv/bin/python tasks/task_43/build_demo.py --force    # replace it

Writes `~/white-words-studio/projects/demo` -- the slug the app ships it under.

Everything goes through create_project / create_entity / edit_entity / delete_entity and
the history store, so every rule the app enforces is enforced here. The content itself is
in `content/*.json`; this file is the ordering and the asserts.

The story is built whole and then walked backwards to Draft 1. That is not laziness: a
draft is a *state*, and the only way to guarantee that state is a real one the validators
accepted is to reach it by editing from a state that existed.

History shape: `06-history-design.md`.
"""

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from white_words.scriptwriting.core import scene_script, trash, writes  # noqa: E402
from white_words.scriptwriting.core.db import get_db  # noqa: E402
from white_words.scriptwriting.core.history import session, store, view  # noqa: E402

HERE = Path(__file__).parent
CONTENT = HERE / "content"
SLUG = "demo"


def load(name):
    return json.loads((CONTENT / name).read_text())


PROJECT = load("project.json")
WORLDS = load("worlds.json")["worlds"]
VALUES = load("values.json")["values"]
LOCATIONS = load("locations.json")["locations"]
CHARACTERS = load("characters.json")["characters"]
PLOTS = load("plots.json")["plots"]
STRUCTURE = load("structure.json")
SCENES = load("scenes.json")["scenes"]
BEATS = load("beats.json")["beats"]
RELATIONSHIPS = load("relationships.json")["relationships"]

SCENE_BY_ID = {s["id"]: s for s in SCENES}

# ── the history's status plan ────────────────────────────────────────────────
# Every draft states the status of ALL fifteen scenes, because a map that only names
# the scenes that moved silently inherits the creation default (`written`) for the rest
# and produces a "first draft" that is already nine-tenths finished.
#
# D1's shape is the demo's argument: Act I mostly there, the ending already written
# because the writer could see it, and the middle soft. Not progressive by act.
D1 = {
    "the-farm-at-dusk": "written",
    "the-house-lifts": "written",
    "the-house-lands": "drafted",
    "the-scarecrow": "written",
    "the-tin-man-and-the-lion": "drafted",
    "the-poppy-field": "planned",
    "the-gates": "planned",
    "the-audience": "planned",
    "the-monkeys": "planned",
    "the-castle": "planned",
    "the-melting": "written",
    "behind-the-curtain": "written",
    "the-balloon": "drafted",
    "the-goodbyes": "planned",
    "glinda-and-home": "planned",
}
D2 = {
    **D1,
    "the-house-lands": "written",
    "the-tin-man-and-the-lion": "written",
    "the-poppy-field": "written",
    "the-gates": "written",
    "the-monkeys": "drafted",
    "the-goodbyes": "written",
}
D4 = {
    **D2,
    "the-audience": "written",
    "the-monkeys": "written",
    "the-castle": "drafted",
    "the-balloon": "written",
    "glinda-and-home": "written",
}
D5 = {**D4, "the-castle": "written"}
D6 = {**D5, "the-poppy-field": None}
D7 = {**D6, "the-farm-at-dusk": "locked", "glinda-and-home": "locked"}

# The read's change to the ending: the Lion's last line is the one the writer cut. Draft 6
# rewrites the close of the balloon, which is a real edit rather than a status flip, and it
# is why the balloon is the scene the read touched.
BALLOON_CLOSE = "SCARECROW\nHe said he'd come back.\n\nLION\nHe said a lot of things."
BALLOON_CLOSE_D6 = "SCARECROW\nHe said he'd come back.\n\nNobody answers him. The balloon is a\ngreen dot and then the afternoon goes on and they are still standing there."

# The open branch's argument: the last scene's logline, rewritten two ways. `the-ending`
# holds one, main holds the other, and the merge is left for the reader to resolve.
END_BRANCH = "Glinda explains the shoes, and Dorothy chooses to go home."
END_MAIN = "Glinda gives her the answer, and Dorothy takes it without asking why."

# Branch 2's rewrite of the gate scene: shorter, and the Lion is not in it. The original
# is the longest scene in Act II and the only one where five characters are standing
# around while two of them talk.
GATES_REWRITE = """A gate that has been designed to be walked through, which is a different thing from a gate that keeps people out.

A GUARDIAN stands at the gate with a tray of spectacles and the expression of a man who has been standing there for years.

GUARDIAN
Spectacles must be worn. City regulation.

DOROTHY
For what?

GUARDIAN
(pause)
For your protection.

DOROTHY
From what?

GUARDIAN
The city is very bright.

He fits them. Small locks click at the hinges.

DOROTHY
They don't come off?

GUARDIAN
The regulation does not say at all. It says they must be worn, and they don't come off, and I have never been asked what happens if they did.

SCARECROW
Does the Wizard see everyone who comes?

GUARDIAN
Not everyone. He is very busy. That is what busy means.

TIN MAN
Is he busy now?

GUARDIAN
He is always busy.

The Lion is behind them and does not say anything.

He steps aside and the gate opens.

GUARDIAN
Enjoy the city. It is the finest city there is. That is not a regulation, that is my own opinion, and I am allowed one.
"""

GATES_OBJECTIVE = "to be admitted, and to learn that being admitted is all the city will do."

# Scene -> act, for the checks that care about distribution across the structure.
ACT_OF = {
    "the-farm-at-dusk": "I", "the-house-lifts": "I", "the-house-lands": "I",
    "the-scarecrow": "II", "the-tin-man-and-the-lion": "II", "the-poppy-field": "II",
    "the-gates": "II", "the-audience": "II", "the-monkeys": "II", "the-castle": "II",
    "the-melting": "III", "behind-the-curtain": "III", "the-balloon": "III",
    "the-goodbyes": "III", "glinda-and-home": "III",
}

LION_MAIN = "A lion who is frightened of everything and charges the castle anyway."
LION_BRANCH = "A lion whose fear everyone reads as bravado, who is braver than he knows."


def body_for(scene_id, status):
    """A scene's Content, derived from its status so the two can never disagree."""
    full = SCENE_BY_ID[scene_id]["sections"]["Content"]
    if status == "planned":
        return ""
    if status == "drafted":
        paras = [p for p in full.split("\n\n") if p.strip()]
        return "\n\n".join(paras[:2]) + "\n"
    return full


def assert_true(cond, msg):
    if not cond:
        raise SystemExit(f"ASSERT FAILED: {msg}")


# ── build the story ──────────────────────────────────────────────────────────


def build_story(project):
    """Every entity, at full state. The history walks back from here."""
    writes.edit_entity(project, "project", SLUG, dict(PROJECT["sections"]), "project sections")

    for kind, items in (
        ("world", WORLDS),
        ("value", VALUES),
        ("location", LOCATIONS),
        ("character", CHARACTERS),
        ("plot", PLOTS),
        ("relationship", RELATIONSHIPS),
    ):
        for item in items:
            writes.create_entity(project, kind, item["id"], item["fields"], item["sections"])

    for a in STRUCTURE["acts"]:
        writes.create_entity(project, "act", a["id"], a["fields"], a["sections"])
    for s in STRUCTURE["sequences"]:
        writes.create_entity(project, "sequence", s["id"], s["fields"], s["sections"])

    # Every scene, with every field and section it will ever carry. The history only
    # moves `status` and `Content`; nothing structural is added later, in any draft.
    for sc in SCENES:
        writes.create_entity(project, "scene", sc["id"], sc["fields"], sc["sections"])
    for rec in BEATS:
        writes.create_entity(project, "scene_beats", rec["id"], rec["fields"], rec["sections"])

    conn = get_db(project)
    try:
        counts = {
            t: conn.execute(
                "SELECT COUNT(*) FROM entities WHERE type=? AND is_deleted=0", (t,)
            ).fetchone()[0]
            for t in (
                "world", "value", "location", "character", "relationship",
                "plot", "act", "sequence", "scene", "scene_beats",
            )
        }
    finally:
        conn.close()

    assert_true(counts["act"] == 3, f"acts: {counts['act']}")
    assert_true(counts["sequence"] == 7, f"sequences: {counts['sequence']}")
    assert_true(counts["scene"] == 15, f"scenes: {counts['scene']}")
    assert_true(counts["scene_beats"] == 15, f"beats: {counts['scene_beats']}")
    print(f"  story: {sum(counts.values())} entities {counts}")


def current_content(project):
    conn = get_db(project)
    try:
        return {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT e.id, s.body FROM entities e JOIN sections s ON s.entity_id=e.id "
                "WHERE e.type='scene' AND s.heading='Content' AND e.is_deleted=0"
            )
        }
    finally:
        conn.close()


def apply_status(project, target, current):
    """Move every scene to `target`, editing only what differs from `current`.

    Status and Content move together in one edit: a `planned` scene has no prose and a
    `written` one has all of it, so leaving them to disagree would produce a story where
    a scene claims to be written and reads as empty.
    """
    bodies = current_content(project)
    changed = 0
    for scene_id, status in target.items():
        if status is None:
            continue
        want = body_for(scene_id, status)
        data = {}
        if current.get(scene_id) != status:
            data["status"] = status
        if bodies.get(scene_id, "") != want:
            data["Content"] = want
        if not data:
            continue
        writes.edit_entity(project, "scene", scene_id, data, f"status {current.get(scene_id)} -> {status}")
        changed += 1
    return changed, dict(current, **{k: v for k, v in target.items() if v is not None})


def statuses(project):
    conn = get_db(project)
    try:
        return {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT id, status FROM entities WHERE type='scene' AND is_deleted=0"
            )
        }
    finally:
        conn.close()


# ── the run ──────────────────────────────────────────────────────────────────


def build(root, force):
    target = root / "projects" / SLUG
    if target.exists():
        if not force:
            raise SystemExit(f"{target} exists. Pass --force to replace it.")
        shutil.rmtree(target)

    writes.create_project(SLUG, PROJECT["fields"], root)
    project = target
    print(f"building {SLUG}")

    build_story(project)

    # ── Draft 1: the structure and the scenes the writer could already see ──
    n, cur = apply_status(project, D1, {})
    d1 = store.save_snapshot(project, "Draft 1 — Structure and the first scenes",
                            "Three acts and seven sequences fixed. The scenes the writer "
                            "could already see, mostly from the opening and the ending.")
    print(f"  Draft 1: {n} status moves -> {d1['label']}")

    # ── Draft 2: pushing into the middle ──
    n, cur = apply_status(project, D2, cur)
    d2 = store.save_snapshot(project, "Draft 2 — Pushing into the middle",
                            "The middle opens up. The Lion's scene is the softest thing in it.")
    print(f"  Draft 2: {n} status moves -> {d2['label']}")
    assert_true(d2["parents"] == [d1["id"]], f"Draft 2 parents {d2['parents']}")

    # ── Draft 3: the branch, opened while the story is unfinished ──
    branch = store.branch_from(project, d2["id"], "lion-arc")
    store.switch(project, branch["id"])
    writes.edit_entity(project, "scene", "the-tin-man-and-the-lion", {"status": "written"},
                       "status drafted -> written")
    writes.edit_entity(project, "character", "lion", {"one_sentence": LION_BRANCH},
                       "the lion, reconsidered")
    d3 = store.save_snapshot(project, "Draft 3 — Lion, second attempt",
                             "His arc rewritten where it did not work. The rest of the story "
                             "is still unfinished.")
    print(f"  Draft 3: branch lion-arc -> {d3['label']}")
    assert_true(d3["parents"] == [d2["id"]], f"Draft 3 parents {d3['parents']}")

    # ── Draft 4: main kept moving while the branch was open ──
    store.switch(project, "main")
    # Main rewrites the same field the branch rewrote. A change on one side only is not a
    # conflict -- the planner reports `take` and applies it -- so main has to disagree,
    # not merely differ, for the merge to have anything to resolve.
    writes.edit_entity(project, "character", "lion", {"one_sentence": LION_MAIN},
                       "the lion, for the stage")
    n, cur = apply_status(project, D4, cur)
    d4 = store.save_snapshot(project, "Draft 4 — Draft 2, continued",
                            "Main went on without the branch. The two sides now disagree "
                            "about one character.")
    print(f"  Draft 4: {n} status moves -> {d4['label']}")
    assert_true(d4["parents"] == [d2["id"]], f"Draft 4 parents {d4['parents']}")

    # ── the merge: a real conflict, resolved ──
    # Merged as a SNAPSHOT, not a branch: only a saved draft can be declared complete, and
    # complete is what records the second parent. The merge-a-branch case is the open
    # session at the end, which is left for the reader.
    sess = session.start(project, "main", {"kind": "snapshot", "id": d3["id"]})
    plan = session.show(project, sess["id"])["plan"]
    conflicts = [i for i in plan["items"] if i.get("state") == "conflict"]
    print(f"  merge: {len(conflicts)} conflict(s) {[c['key'] for c in conflicts]}")
    assert_true(len(conflicts) == 1, f"expected exactly 1 conflict, got {len(conflicts)}")
    assert_true(conflicts[0]["key"] == "field:character:lion:one_sentence",
                f"unexpected conflict {conflicts[0]['key']}")

    session.set_selection(project, sess["id"], [i["key"] for i in plan["items"]
                                                if i.get("state") in ("conflict", "take", "keep")])
    session.set_decision(project, sess["id"], conflicts[0]["key"] + "#D2", "theirs")
    after = session.show(project, sess["id"])["plan"]
    assert_true(after["ready"], f"not ready: {after['open']}")
    assert_true(after["ops"], "plan holds no ops")
    out = session.apply(project, sess["id"], complete=True)
    assert_true(out.get("status") == "applied", f"apply: {out.get('status')}")
    assert_true(out.get("applied"), "applied nothing")

    conn = get_db(project)
    try:
        lion = conn.execute("SELECT one_sentence FROM entities WHERE id='lion'").fetchone()[0]
    finally:
        conn.close()
    assert_true(lion == LION_BRANCH, f"lion holds {lion!r}")
    print(f"  merge applied: {len(out['applied'])} op(s), lion = the branch's reading")

    # ── Draft 5: the story is whole for the first time ──
    n, cur = apply_status(project, D5, cur)
    d5 = store.save_snapshot(project, "Draft 5 — First full draft",
                             "The last scenes close. Every scene written for the first time.")
    print(f"  Draft 5: {n} status moves -> {d5['label']}")
    assert_true(all(v == "written" for v in statuses(project).values()),
                f"not all written: {statuses(project)}")

    # ── Draft 6: the cut ──
    preview = writes.delete_entity(project, "scene", "the-poppy-field", "cut in Draft 6")
    assert_true(preview["would_delete"] == ["the-poppy-field", "the-poppy-field-beats"],
                f"would delete {preview['would_delete']}")
    writes.delete_entity(project, "scene", "the-poppy-field", "cut in Draft 6", confirm=True)
    writes.edit_entity(project, "scene", "the-balloon",
                       {"Content": body_for("the-balloon", "written").replace(
                           BALLOON_CLOSE, BALLOON_CLOSE_D6)},
                       "the ending, after the read")
    d6 = store.save_snapshot(project, "Draft 6 — Notes from the read",
                             "The middle tightened. The poppy field cut and in the bin.")
    print(f"  Draft 6: cut the poppy field -> {d6['label']}")
    assert_true(len(statuses(project)) == 14, f"live scenes: {len(statuses(project))}")

    # ── Draft 7: the refinement draft. Two branches open from here. ──
    n, cur = apply_status(project, D7, cur)
    d7 = store.save_snapshot(project, "Draft 7 — Locked pass",
                             "The scenes that are finished are marked so. The work continues "
                             "on two branches.")
    print(f"  Draft 7: {n} status moves -> {d7['label']}")
    base = d7["id"]

    # ── Branch 2: the gate scene, rewritten. Merged COMPLETE before branch 3 exists. ──
    #
    # A script-level rewrite, so the merge is not only fields: the scene's prose is
    # replaced, and the companion beat inside it changed too, so the merge carries the
    # scene and its beat sheet together. Nobody leaves the cast: the group travels
    # together, and a rewrite that quietly stranded one of them would be the error this
    # demo is supposed to show being caught, not committed.
    tighten = store.branch_from(project, base, "tighten-act-two")
    store.switch(project, tighten["id"])
    writes.edit_entity(project, "scene", "the-gates", {
        "Content": GATES_REWRITE,
    }, "the gate scene, tightened")
    writes.edit_entity(project, "scene_beats", "the-gates-beats", {
        "scene_objective": GATES_OBJECTIVE,
    }, "the beats follow the tighter scene")
    t_draft = store.save_snapshot(project, "Tighten Act II, done",
                                  "The gate scene rewritten shorter, the Guardian given room.")
    store.switch(project, "main")
    _merge_complete(project, t_draft, "Tighten Act II")

    # The merge carried the scene's prose and its cast in one op. The rewrite tightens the
    # scene but does not strand anybody: the group travels together, so the Lion is still
    # there and still silent, and the prose says so.
    conn = get_db(project)
    try:
        cast = sorted(r[0] for r in conn.execute(
            "SELECT from_id FROM live_relations WHERE kind='character_scene' "
            "AND to_id='the-gates'"))
        body = conn.execute("SELECT body FROM sections WHERE entity_id='the-gates' "
                            "AND heading='Content'").fetchone()[0]
    finally:
        conn.close()
    assert_true(body.startswith("A gate that has been designed to be walked through"),
                f"the gate scene prose did not change: {body[:60]!r}")
    assert_true("lion" in cast, f"the rewrite stranded the Lion: {cast}")
    assert_true("The Lion is behind them" in body,
                "the Lion is in the cast but the rewritten scene never places him")
    print(f"  script merge: prose + cast in one op, Lion on set and silent | cast {cast}")

    # ── Branch 3: the ending, left OPEN with a live conflict ──
    ending = store.branch_from(project, base, "the-ending")
    store.switch(project, ending["id"])
    writes.edit_entity(project, "scene", "glinda-and-home", {"one_sentence": END_BRANCH},
                       "the ending, reconsidered")
    store.save_snapshot(project, "The ending, reconsidered",
                        "Glinda's last scene, rewritten.")
    store.switch(project, "main")

    # Main moves on the same field, unsaved: the work in progress the open merge is about.
    writes.edit_entity(project, "scene", "glinda-and-home", {"one_sentence": END_MAIN},
                       "the ending, as it stands")

    sess = session.start(project, "main", {"kind": "branch", "id": ending["id"]})
    plan = session.show(project, sess["id"])["plan"]
    conflicts = [i for i in plan["items"] if i.get("state") == "conflict"]
    assert_true(len(conflicts) == 1, f"open merge conflicts: {len(conflicts)}")
    assert_true(not plan["ready"], "the open merge should still be waiting on a decision")
    print(f"  open merge: 1 conflict left for the reader "
          f"({conflicts[0]['key']}), branch the-ending")

    return project


def _merge_complete(project, source_draft, label):
    """Merge a saved draft into main and declare it complete, so it gains a parent edge.

    Complete needs a snapshot source: an unsaved head is accounted for by no draft.
    """
    sess = session.start(project, "main", {"kind": "snapshot", "id": source_draft["id"]})
    plan = session.show(project, sess["id"])["plan"]
    items = [i["key"] for i in plan["items"] if i.get("state") != "unchanged"]
    assert_true(items, f"{label}: merge has nothing to bring over")
    session.set_selection(project, sess["id"], items)
    assert_true(session.show(project, sess["id"])["plan"]["ready"], f"{label}: not ready")
    out = session.apply(project, sess["id"], complete=True)
    assert_true(out.get("status") == "applied" and out.get("applied"),
                f"{label}: apply {out.get('status')}")

    saved = store.save_snapshot(project, f"After {label}", "The merge is in.")
    assert_true(len(saved["parents"]) == 2,
                f"{label}: expected a two-parent draft, got {saved['parents']}")
    print(f"  merge complete: {label} -> {len(saved['parents'])}-parent draft "
          f"{saved['label']}")
    return saved


def verify(project):
    """Everything the demo claims, checked against the database it was written into."""
    conn = get_db(project)
    try:
        def count(sql, *a):
            return conn.execute(sql, a).fetchone()[0]

        live = {t: count("SELECT COUNT(*) FROM entities WHERE type=? AND is_deleted=0", t)
                for t in ("world", "value", "location", "character", "relationship",
                          "plot", "act", "sequence", "scene", "scene_beats")}
        assert_true(live["scene"] == 14, f"live scenes {live['scene']}")
        assert_true(live["character"] == 13, f"characters {live['character']}")
        assert_true(live["location"] == 8, f"locations {live['location']}")

        # the trash holds a scene and its beats, and nothing else
        binned = [r[0] for r in conn.execute(
            "SELECT id FROM entities WHERE is_deleted=1 ORDER BY id")]
        assert_true(binned == ["the-poppy-field", "the-poppy-field-beats"],
                    f"trash holds {binned}")
        assert_true(len(statuses(project)) == 14, f"live scenes {len(statuses(project))}")

        # Cast is presence, not speech: everyone on set is in it, whether or not they have a
        # line. Two things follow, and only one of them is decidable:
        #
        #   * a registered character who SPEAKS is in the cast -- asserted below;
        #   * everyone on set is in the cast -- not asserted. Presence without a name cannot
        #     be read off the text (Toto is "a dog in her lap"; the Tin Man is one of "the
        #     three of them"), and beats do not settle it either: a beat can be played from
        #     offstage, as the Witch sends the monkeys from somewhere that is not the road.
        #     The cast list is the writer's statement of who is on set, so it is a reading,
        #     not a derivation. Keep it true by reading the scene.
        characters = [
            {"id": r[0], "name": r[1] or r[0]}
            for r in conn.execute(
                "SELECT id, name FROM entities WHERE type='character' AND is_deleted=0")
        ]
        for sid, body in conn.execute(
            "SELECT e.id, s.body FROM entities e JOIN sections s ON s.entity_id=e.id "
            "WHERE e.type='scene' AND s.heading='Content' AND e.is_deleted=0"
        ).fetchall():
            if json.loads(conn.execute(
                    "SELECT extra FROM entities WHERE id=?", (sid,)).fetchone()[0]).get("no_cast"):
                continue  # the cyclone lifts an empty house
            cast = {r[0] for r in conn.execute(
                "SELECT from_id FROM live_relations WHERE kind='character_scene' AND to_id=?",
                (sid,))}
            speaking = {s["id"] for s in scene_script.script_cast(
                scene_script.parse_blocks(body), characters) if s.get("id")}
            assert_true(speaking <= cast,
                        f"{sid}: {sorted(speaking - cast)} speak but are not in the cast")

    # every non-planned scene has prose; no scene has a heading line in Content
        for sid, body in conn.execute(
            "SELECT e.id, s.body FROM entities e JOIN sections s ON s.entity_id=e.id "
            "WHERE e.type='scene' AND s.heading='Content' AND e.is_deleted=0"
        ):
            assert_true(not body.lstrip().upper().startswith(("INT.", "EXT.", "EST.", ".")),
                        f"{sid} Content opens with a heading")
    finally:
        conn.close()

    # Draft 1's shape is the demo's argument about process. Check it on the saved draft.
    d1 = store.list_branches(project)["snapshots"][0]
    acts = {k: v for k, v in ACT_OF.items()}
    with view.project_view(project, d1["id"]) as v:
        conn1 = sqlite3.connect(v / ".story" / "story.db")
        try:
            st = dict(conn1.execute("SELECT id, status FROM entities WHERE type='scene'"))
            n_act = conn1.execute("SELECT COUNT(*) FROM entities WHERE type='act'").fetchone()[0]
            n_seq = conn1.execute("SELECT COUNT(*) FROM entities WHERE type='sequence'").fetchone()[0]
        finally:
            conn1.close()
    assert_true(n_act == 3 and n_seq == 7, f"Draft 1 structure: {n_act} acts, {n_seq} sequences")
    assert_true(len(st) == 15, f"Draft 1 scene rows: {len(st)}")
    for act in ("I", "II", "III"):
        written = [s for s, a in acts.items() if a == act and st.get(s) == "written"]
        assert_true(written, f"Draft 1 has nothing written in Act {act} -- reads as progressive")
    act2 = [s for s, a in acts.items() if a == "II"]
    assert_true(any(st.get(s) == "planned" for s in act2),
                "Draft 1 has no planned scene in Act II -- the middle is not soft")

    chk = trash.restore_check(get_db(project), "the-poppy-field",
                              also_restoring=("the-poppy-field-beats",))
    assert_true(not chk["blockers"] and not chk["collisions"] and not chk["warnings"],
                f"restore would be refused: {chk}")

    branches = store.list_branches(project)
    names = sorted(b["name"] for b in branches["branches"])
    assert_true(names == ["lion-arc", "main", "the-ending", "tighten-act-two"],
                f"branches {names}")

    h = store.connect(project)
    try:
        drafts = h.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        edges = [r[0] for r in h.execute(
            "SELECT snapshot_id FROM snapshot_parents GROUP BY snapshot_id "
            "HAVING COUNT(*)>1 ORDER BY snapshot_id")]
        sessions = dict(h.execute("SELECT status, COUNT(*) FROM merge_sessions "
                                  "GROUP BY status").fetchall())
    finally:
        h.close()
    assert_true(drafts == 10, f"drafts {drafts} (expected 10)")
    assert_true(len(edges) == 2, f"two-parent drafts {edges} (expected 2)")
    assert_true(sessions.get("applied") == 2 and sessions.get("open") == 1,
                f"merge sessions {sessions}")

    print(f"  verify: {live} | trash {binned} | restore clean")
    print(f"          branches {names} | {drafts} drafts | {len(edges)} merge edges "
          f"| sessions {sessions}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path.home() / "white-words-studio"))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    project = build(Path(args.root), args.force)
    verify(project)
    print(f"\nbuilt: {project}")


if __name__ == "__main__":
    main()
