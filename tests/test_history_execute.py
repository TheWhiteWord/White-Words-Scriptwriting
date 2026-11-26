"""The executor: order, the dry run, apply, the stale-plan guard and parent recording.

The planner's tests prove the plan is right; these prove the plan LANDS. Every
assertion here is against the database after a real run, because "it applied" is only
true if the target's state says so.

Three things are pinned that no other test covers: the op order is the plan's (a
release before the create that needs the role), a refused op leaves the target
byte-for-byte unchanged, and a complete merge becomes a second parent at the next save
while a cherry-pick leaves no parent at all.
"""

import pytest

from white_words.scriptwriting.core.history import execute, logical, plan, store
from white_words.scriptwriting.core.writes import (
    create_entity,
    delete_entity,
    edit_entity,
)


@pytest.fixture
def base(fixture_path):
    """The fixture, unchanged — the merge base of every test here."""
    return fixture_path


def _copy(source, name="side"):
    import shutil
    import tempfile
    from pathlib import Path

    dest = Path(tempfile.mkdtemp()) / name
    shutil.copytree(str(source), str(dest))
    return dest


@pytest.fixture
def sides(base):
    """`(base, ours, theirs)` — two independent copies of the base."""
    return base, _copy(base, "ours"), _copy(base, "theirs")


def _keys(result, state=None):
    return [i["key"] for i in result["items"] if state is None or i.get("state") == state]


def _scene_with_role(theirs, entity_id, plot, role, holder="central-room-day"):
    """Move a singular role onto a new scene in `theirs`, the way a writer would."""
    current = [
        r
        for r in logical.of_project(theirs)[holder]["fields"]["plot_roles"]
        if not (r["plot"] == plot and r["role"] == role)
    ]
    edit_entity(theirs, "scene", holder, {"plot_roles": current}, "release")
    create_entity(
        theirs,
        "scene",
        entity_id,
        {
            "sequence_id": "seq-discovery",
            "int_ext": "INT.",
            "location": "the-central-room",
            "time_of_day": "DAY",
            "title": entity_id,
            "plot_roles": [{"plot": plot, "role": role, "description": "taken"}],
        },
        {"Content": "Action."},
    )


# ─── the happy path ─────────────────────────────────────────────────────────


def test_a_clean_plan_applies_and_reports_what_landed(sides):
    base, ours, theirs = sides
    edit_entity(theirs, "character", "kael", {"name": "Kael Renamed"}, "theirs")
    planned = plan.plan(base, ours, theirs, selection=["field:character:kael:name"])

    assert execute.dry_run(ours, planned) == {"status": "clean", "ready": True}

    result = execute.apply(ours, planned)
    assert result["status"] == "applied"
    assert [a["op"] for a in result["applied"]] == ["edit"]
    assert logical.of_project(ours)["kael"]["fields"]["name"] == "Kael Renamed"


def test_an_empty_plan_applies_as_a_no_op(sides):
    base, ours, theirs = sides
    planned = plan.plan(base, ours, theirs, selection=[])
    assert execute.apply(ours, planned)["applied"] == []


def test_the_dry_run_writes_nothing(sides):
    """The verdict is a fact about a copy, so the target keeps its own state."""
    base, ours, theirs = sides
    edit_entity(theirs, "character", "kael", {"name": "Kael Renamed"}, "theirs")
    planned = plan.plan(base, ours, theirs, selection=["field:character:kael:name"])

    execute.dry_run(ours, planned)
    assert logical.of_project(ours)["kael"]["fields"]["name"] == "Kael"


# ─── §7.7.2: the order ──────────────────────────────────────────────────────


def test_the_release_runs_before_the_create_that_takes_the_role(sides):
    """§7.7.2: the incoming scene cannot hold a singular role while the old holder does.

    The plan emits the release first; the executor must not re-sort. If it did, the
    create would be refused by the validator and the merge would never land.
    """
    base, ours, theirs = sides
    _scene_with_role(theirs, "rival", "the-resistance", "inciting_incident")
    key = plan.plan(base, ours, theirs, selection=["entity:scene:rival"])["decisions"][0]["key"]
    planned = plan.plan(
        base,
        ours,
        theirs,
        selection=["entity:scene:rival"],
        decisions={key: {"choice": "theirs", "set_by": "user"}},
    )
    assert [op["op"] for op in planned["ops"]] == ["edit", "create", "reorder"]

    assert execute.dry_run(ours, planned)["status"] == "clean"
    assert execute.apply(ours, planned)["status"] == "applied"

    shapes = logical.of_project(ours)
    assert shapes["rival"]["fields"]["plot_roles"] == [
        {"description": "taken", "plot": "the-resistance", "role": "inciting_incident"}
    ]
    # The holder keeps its other plots' roles; only the released entry is gone.
    assert [
        r
        for r in shapes["central-room-day"]["fields"]["plot_roles"]
        if r["plot"] == "the-resistance"
    ] == []


def test_a_restore_op_runs_inside_the_apply_transaction(sides):
    """`restore` is dispatched by the executor, and it must not open its own connection.

    Without a `conn` the op would be a second writer inside the transaction and the
    apply would fail with "database is locked". Landing at all is the assertion, and a
    restored scene also renumbers its parent through `reorder` from inside that
    transaction, which is the other write T2 opened up.
    """
    base, ours, theirs = sides
    # Made and trashed here, live there: an id our bin holds and theirs' head has (D6).
    create_entity(
        ours,
        "scene",
        "late",
        {
            "sequence_id": "seq-discovery",
            "int_ext": "INT.",
            "location": "the-central-room",
            "time_of_day": "NIGHT",
            "title": "Old title",
        },
        {"Content": "Action."},
    )
    delete_entity(ours, "scene", "late", "ours", confirm=True)
    create_entity(
        theirs,
        "scene",
        "late",
        {
            "sequence_id": "seq-discovery",
            "int_ext": "INT.",
            "location": "the-central-room",
            "time_of_day": "NIGHT",
            "title": "Late",
        },
        {"Content": "Action."},
    )
    key = plan.plan(base, ours, theirs, selection=["entity:scene:late"])["decisions"][0]["key"]
    planned = plan.plan(
        base,
        ours,
        theirs,
        selection=["entity:scene:late"],
        decisions={key: {"choice": "restore", "set_by": "user"}},
    )
    assert [op["op"] for op in planned["ops"]] == ["restore", "edit"]

    assert execute.apply(ours, planned)["status"] == "applied"
    shapes = logical.of_project(ours)
    assert shapes["late"]["fields"]["title"] == "Late"
    assert "late" in _order_of(ours)["scene:seq-discovery"]


def _order_of(project):
    import sqlite3

    conn = sqlite3.connect(str(project / ".story" / "story.db"))
    try:
        return logical.order_of(conn)
    finally:
        conn.close()


# ─── §7.7.3: a refused run ──────────────────────────────────────────────────


def test_a_refused_op_rolls_back_everything_and_names_its_item(sides):
    """All or none: the edit that would have landed first must be gone too.

    The plan is made against a target that still holds a live `the-core-day`. The scene
    is then trashed behind the plan's back and the plan re-stamped with the new
    fingerprint, so the stale guard passes and the delete itself is what fails — which
    is the path that has to roll back rather than half-apply.
    """
    base, ours, theirs = sides
    edit_entity(theirs, "character", "kael", {"name": "Kael Renamed"}, "theirs")
    delete_entity(theirs, "scene", "the-core-day", "theirs", confirm=True)
    planned = plan.plan(
        base,
        ours,
        theirs,
        selection=["field:character:kael:name", "entity:scene:the-core-day"],
    )
    planned["ops"].sort(key=lambda op: op["op"] != "edit")
    delete_entity(ours, "scene", "the-core-day", "behind the plan", confirm=True)
    planned["fingerprint"] = __import__(
        "white_words.scriptwriting.core.history.fingerprint", fromlist=["of_project"]
    ).of_project(ours)

    result = execute.apply(ours, planned)

    assert result["status"] == "refused"
    [failure] = result["failures"]
    assert failure["op"] == "delete"
    assert failure["item"]["key"] == "entity:scene:the-core-day"
    # The edit that ran before the failure is rolled back with it.
    assert logical.of_project(ours)["kael"]["fields"]["name"] == "Kael"


def test_a_dry_run_refusal_maps_a_release_failure_to_the_arriving_scene(sides):
    """§7.7.3: the release edits the HOLDER, the decision is about the scene ARRIVING.

    A failure is keyed on the op's `source`, not on the row it writes, or the caller
    would be told the wrong entity is the problem.
    """
    base, ours, theirs = sides
    _scene_with_role(theirs, "rival", "the-resistance", "inciting_incident")
    key = plan.plan(base, ours, theirs, selection=["entity:scene:rival"])["decisions"][0]["key"]
    planned = plan.plan(
        base,
        ours,
        theirs,
        selection=["entity:scene:rival"],
        decisions={key: {"choice": "theirs", "set_by": "user"}},
    )
    # Break the releasing edit's own target: the scene is gone, so the edit is refused.
    delete_entity(ours, "scene", "central-room-day", "behind the plan", confirm=True)
    planned["fingerprint"] = __import__(
        "white_words.scriptwriting.core.history.fingerprint", fromlist=["of_project"]
    ).of_project(ours)

    result = execute.dry_run(ours, planned)

    assert result["status"] == "refused"
    [failure] = result["failures"]
    assert failure["op"] == "edit"
    assert failure["source"] == "entity:scene:rival"
    assert failure["decision"]["code"] == "D4"


# ─── §7.7.4: the guards ─────────────────────────────────────────────────────


def test_an_unready_plan_is_not_applied(sides):
    """Defaults are in `ops`, so applying an unready plan would silently drop content."""
    base, ours, theirs = sides
    edit_entity(ours, "character", "kael", {"name": "Mine"}, "ours")
    edit_entity(theirs, "character", "kael", {"name": "Theirs"}, "theirs")
    planned = plan.plan(base, ours, theirs, selection=["field:character:kael:name"])
    assert planned["ready"] is False

    result = execute.apply(ours, planned)
    assert result["status"] == "blocked"
    assert result["open"] == ["field:character:kael:name#D2"]
    assert logical.of_project(ours)["kael"]["fields"]["name"] == "Mine"


def test_a_stale_plan_is_refused_and_writes_nothing(sides):
    """§7.7.4: the target moved since planning, so the ops were computed against nothing.

    Neither the ops nor a restore point may be taken — a refused apply has no trace.
    """
    base, ours, theirs = sides
    edit_entity(theirs, "character", "kael", {"name": "Kael Renamed"}, "theirs")
    planned = plan.plan(base, ours, theirs, selection=["field:character:kael:name"])

    edit_entity(ours, "character", "mira", {"name": "Mira Moved"}, "someone else")
    result = execute.apply(ours, planned)

    assert result["status"] == "refused" and result["code"] == "stale_plan"
    assert logical.of_project(ours)["kael"]["fields"]["name"] == "Kael"
    assert store.list_branches(ours)["snapshots"] == []


def test_a_plan_carries_the_target_fingerprint(sides):
    """The guard is on the plan, so a caller cannot forget to pass it."""
    base, ours, theirs = sides
    planned = plan.plan(base, ours, theirs, selection=[])
    from white_words.scriptwriting.core.history import fingerprint

    assert planned["fingerprint"] == fingerprint.of_project(ours)
    edit_entity(ours, "character", "kael", {"name": "Moved"}, "ours")
    assert plan.plan(base, ours, theirs, selection=[])["fingerprint"] != planned["fingerprint"]


# ─── the restore point ──────────────────────────────────────────────────────


def test_apply_takes_a_draft_of_the_target_first(sides):
    """§7.7.4: "before merge from …" is the state a user returns to."""
    base, ours, theirs = sides
    store.adopt(ours)
    edit_entity(ours, "character", "mira", {"name": "Mira Before"}, "ours")
    edit_entity(theirs, "character", "kael", {"name": "Kael Renamed"}, "theirs")
    planned = plan.plan(base, ours, theirs, selection=["field:character:kael:name"])

    result = execute.apply(ours, planned, label="Before merge from theirs")

    assert result["baseline"]["created"] is True
    assert result["baseline"]["label"] == "Before merge from theirs"
    labels = [s["label"] for s in store.list_branches(ours)["snapshots"]]
    assert "Before merge from theirs" in labels


def test_an_unchanged_head_reuses_its_draft_as_the_restore_point(sides):
    """An unchanged head IS its saved draft, so no second identical draft is written."""
    base, ours, theirs = sides
    store.adopt(ours)
    edit_entity(theirs, "character", "kael", {"name": "Kael Renamed"}, "theirs")
    planned = plan.plan(base, ours, theirs, selection=["field:character:kael:name"])

    result = execute.apply(ours, planned)

    assert result["baseline"]["created"] is False
    assert len(store.list_branches(ours)["snapshots"]) == 1


def test_apply_adopts_a_project_this_feature_has_never_touched(sides):
    """No manifest means no branch, and therefore no draft to be the restore point."""
    base, ours, theirs = sides
    edit_entity(theirs, "character", "kael", {"name": "Kael Renamed"}, "theirs")
    planned = plan.plan(base, ours, theirs, selection=["field:character:kael:name"])
    assert store.head_state(ours)["branch"] is None

    assert execute.apply(ours, planned)["status"] == "applied"
    assert store.head_state(ours)["branch"]["name"] == "main"


# ─── §7.9: what a merge records ─────────────────────────────────────────────


def _source_draft(base):
    """A draft on another branch of the SAME project — §7.9's source (§7.8).

    The source of a merge is a draft in this project's own manifest, so it is made by
    branching, changing that branch, saving, and switching back. `main`'s head is then
    the state it started at, and the source is addressable by id.
    """
    store.adopt(base)
    store.branch_from(base, store.head_state(base)["base"]["id"], "side")
    store.switch(base, "side")
    edit_entity(base, "character", "kael", {"name": "Kael On The Side"}, "side")
    source = store.save_snapshot(base, "Side 1")["id"]
    store.switch(base, "main")
    return source


def test_a_complete_merge_records_the_source_and_the_next_save_makes_it_a_parent(sides):
    """§7.9: only a complete merge records a parent, and the save writes the row."""
    base, _ours, _theirs = sides
    source = _source_draft(base)
    planned = plan.plan(base, base, base, selection=[])
    assert planned["ready"] is True

    result = execute.apply(base, planned, parent_source=source)

    assert result["status"] == "applied"
    assert result["parents"] == [source]

    edit_entity(base, "character", "mira", {"name": "After the merge"}, "ours")
    saved = store.save_snapshot(base, "After merge")
    assert saved["parents"] == [result["baseline"]["id"], source]


def test_a_cherry_pick_records_no_parent(sides):
    """§7.9's default: unselected changes are offered again next time."""
    base, _ours, _theirs = sides
    source = _source_draft(base)
    planned = plan.plan(base, base, base, selection=[])

    result = execute.apply(base, planned)

    assert result["status"] == "applied" and result["parents"] is None
    edit_entity(base, "character", "mira", {"name": "After the pick"}, "ours")
    saved = store.save_snapshot(base, "After the pick")
    assert saved["parents"] == [result["baseline"]["id"]]
    assert source not in saved["parents"]


def test_a_refused_merge_records_no_parent(sides):
    """§7.9: a parent means "everything in it is accounted for", so a failed run records none.

    The plan is re-stamped with a fresh fingerprint so the stale guard passes and the
    op itself is what fails; the source must still not become a parent.
    """
    base, _ours, _theirs = sides
    source = _source_draft(base)
    edit_entity(base, "character", "mira", {"name": "Local edit"}, "ours")
    planned = plan.plan(base, base, base, selection=[])
    planned["ops"] = [
        {"op": "delete", "entity_type": "character", "entity_id": "nobody", "summary": "x"}
    ]
    planned["fingerprint"] = __import__(
        "white_words.scriptwriting.core.history.fingerprint", fromlist=["of_project"]
    ).of_project(base)

    result = execute.apply(base, planned, parent_source=source)

    assert result["status"] == "refused"
    branch = store.head_state(base)["branch"]
    assert branch["pending_merge_parents"] == []


def test_recording_the_same_parent_twice_keeps_it_once(sides):
    base, _ours, _theirs = sides
    source = _source_draft(base)
    store.record_pending_parent(base, source)
    branch = store.record_pending_parent(base, source)
    assert branch["pending_merge_parents"] == [source]


def test_an_unknown_source_draft_is_refused(sides):
    base, ours, theirs = sides
    store.adopt(base)
    with pytest.raises(ValueError, match="No such draft"):
        store.record_pending_parent(base, "s-nope")
