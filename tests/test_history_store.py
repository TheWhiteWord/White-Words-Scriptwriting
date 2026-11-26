"""`history.db`: drafts, branches, and the files they point at.

A draft is a frozen copy of the whole project state; a branch is a named line of
them; the live `story.db` is the working copy of the current branch's head. These
pin the operations that keep the three true of each other.
"""

import json
import sqlite3
import stat

import pytest

from white_words.scriptwriting.core import clock, drafts
from white_words.scriptwriting.core.backups import list_backups
from white_words.scriptwriting.core.history import fingerprint, store
from white_words.scriptwriting.core.writes import edit_entity


def _live(project, sql, params=()):
    conn = sqlite3.connect(str(project / ".story" / "story.db"))
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _name(project, entity="kael"):
    return _live(project, "SELECT name FROM entities WHERE id=?", (entity,))[0][0]


def _rename(project, new):
    edit_entity(project, "character", "kael", {"name": new}, "rename")


def _files(project):
    return sorted(
        str(p.relative_to(project / ".story"))
        for p in (project / ".story" / "history").rglob("*")
        if p.is_file()
    )


@pytest.fixture
def project(fixture_path):
    """The fixture with a manifest, on its first branch, and no stray backups.

    A stashed entity takes an automatic backup, so a test that asserts "this took
    no backup" has to start from an empty backup list.
    """
    for f in (fixture_path / ".story").glob("story_*.db"):
        f.unlink()
    store.adopt(fixture_path)
    return fixture_path


def _saved(project, label):
    _rename(project, label)
    return store.save_snapshot(project, label)


# ─── adoption ───


def test_a_project_adopts_itself_on_first_touch(fixture_path):
    branch = store.adopt(fixture_path)
    assert branch["name"] == "main" and branch["is_current"]
    [snapshot] = store.list_branches(fixture_path)["snapshots"]
    assert snapshot["label"] == "Draft 1" and snapshot["seq"] == 1
    assert snapshot["parents"] == []  # the first state has no ancestor
    assert branch["base_snapshot_id"] == snapshot["id"]
    assert store.snapshot_file(fixture_path, snapshot["id"]).exists()


def test_adoption_happens_once(fixture_path):
    first = store.adopt(fixture_path)
    assert store.adopt(fixture_path)["base_snapshot_id"] == first["base_snapshot_id"]
    assert len(store.list_branches(fixture_path)["snapshots"]) == 1


def test_an_adopted_project_has_nothing_unsaved(project):
    state = store.head_state(project)
    assert state["changed"] is False
    assert state["base"]["label"] == "Draft 1"


def test_a_draft_file_is_one_file_with_no_wal_beside_it(project):
    snapshot = store.head_state(project)["base"]
    folder = store.snapshots_dir(project)
    assert [p.name for p in folder.iterdir()] == [f"{snapshot['id']}.db"]


def test_a_draft_never_keeps_sidecars_a_failed_write_left(project):
    """A read-write open creates -wal/-shm before discovering the file is frozen."""
    snapshot = _saved(project, "frozen")
    frozen = store.snapshot_file(project, snapshot["id"])
    frozen.with_name(frozen.name + "-wal").write_bytes(b"")
    frozen.with_name(frozen.name + "-shm").write_bytes(b"")
    _rename(project, "so the next save is not refused")
    store.save_snapshot(project, "after debris")
    assert [
        p.name for p in store.snapshots_dir(project).iterdir() if "wal" in p.name or "shm" in p.name
    ] == []


# ─── the fingerprint ───


def test_two_reads_of_one_state_agree(project):
    assert fingerprint.of_project(project) == fingerprint.of_project(project)


def test_an_edit_changes_the_fingerprint(project):
    before = fingerprint.of_project(project)
    _rename(project, "Someone Else")
    assert fingerprint.of_project(project) != before


def test_renumbering_without_reordering_is_not_a_change(project):
    """Order is fingerprinted as the id list, so a parent's key VALUES may move."""
    before = fingerprint.of_project(project)
    conn = sqlite3.connect(str(project / ".story" / "story.db"), isolation_level=None)
    try:
        conn.execute("UPDATE entities SET order_key = order_key + 10 WHERE type='scene'")
    finally:
        conn.close()
    assert fingerprint.of_project(project) == before


def test_reordering_is_a_change(project):
    before = fingerprint.of_project(project)
    conn = sqlite3.connect(str(project / ".story" / "story.db"), isolation_level=None)
    try:
        conn.execute(
            "UPDATE entities SET order_key = 99 WHERE id='central-room-day' AND type='scene'"
        )
    finally:
        conn.close()
    assert fingerprint.of_project(project) != before


def test_a_trashed_entitys_own_content_is_not_hashed(project):
    """Trash bookkeeping is not content: editing something in the bin moves nothing.

    A delete itself DOES move the hash — the trashed entity's references leave the
    live `extra`s it appears in, which changes what the story reads as. What must
    not count is the trashed row's own stored content.
    """
    conn = sqlite3.connect(str(project / ".story" / "story.db"), isolation_level=None)
    try:
        conn.execute(
            "UPDATE entities SET is_deleted=1, deleted_at=? WHERE id='mira'", (clock.now_iso(),)
        )
    finally:
        conn.close()
    bin_state = fingerprint.of_project(project)
    conn = sqlite3.connect(str(project / ".story" / "story.db"), isolation_level=None)
    try:
        conn.execute("UPDATE entities SET name='Renamed in the bin' WHERE id='mira'")
    finally:
        conn.close()
    assert fingerprint.of_project(project) == bin_state


def test_a_delete_and_its_restore_return_to_the_same_state(project):
    before = fingerprint.of_project(project)
    conn = sqlite3.connect(str(project / ".story" / "story.db"), isolation_level=None)
    try:
        conn.execute(
            "UPDATE entities SET is_deleted=1, deleted_at=? WHERE id='mira'", (clock.now_iso(),)
        )
        conn.execute("UPDATE entities SET is_deleted=0, deleted_at=NULL WHERE id='mira'")
    finally:
        conn.close()
    assert fingerprint.of_project(project) == before


def test_staged_drafts_and_revisions_are_not_content(project):
    before = fingerprint.of_project(project)
    drafts.stage(
        project,
        [
            {
                "op": "edit",
                "entity_type": "character",
                "entity_id": "kael",
                "data": {"name": "x"},
                "summary": "s",
            }
        ],
        "a staged change",
    )
    edits = _live(project, "SELECT count(*) FROM revisions")[0][0]
    assert edits >= 0
    assert fingerprint.of_project(project) == before


def test_a_computed_field_in_extra_does_not_move_the_hash(project):
    """`extra` is hashed without the fields the schema derives at read time."""
    before = fingerprint.of_project(project)
    conn = sqlite3.connect(str(project / ".story" / "story.db"), isolation_level=None)
    try:
        row = conn.execute("SELECT extra FROM entities WHERE id='central-room-day'").fetchone()
        extra = json.loads(row[0] or "{}")
        extra["turning_point"] = "a derived value that no author wrote"
        conn.execute(
            "UPDATE entities SET extra=? WHERE id='central-room-day'", (json.dumps(extra),)
        )
    finally:
        conn.close()
    assert fingerprint.of_project(project) == before


# ─── save ───


def test_a_save_with_nothing_changed_is_refused(project):
    with pytest.raises(ValueError, match="Nothing has changed since Draft 1"):
        store.save_snapshot(project)
    assert len(store.list_branches(project)["snapshots"]) == 1


def _add_second_act(project):
    """Two acts, so one can genuinely move ahead of the other."""
    conn = sqlite3.connect(str(project / ".story" / "story.db"))
    try:
        conn.execute(
            "INSERT INTO entities (id, type, name, one_sentence, order_key, status, extra) "
            "VALUES ('act-2', 'act', 'Act Two', '', 2, 'draft', '{}')"
        )
        conn.execute("UPDATE entities SET order_key=1 WHERE id='act-1'")
        conn.commit()
    finally:
        conn.close()


def test_reordering_acts_is_a_change(project):
    """Act order is authored (§5.2) and read in four places, so it is content."""
    _add_second_act(project)
    before = fingerprint.of_project(project)
    conn = sqlite3.connect(str(project / ".story" / "story.db"))
    try:
        conn.execute("UPDATE entities SET order_key = 1 WHERE id='act-2'")
        conn.execute("UPDATE entities SET order_key = 2 WHERE id='act-1'")
        conn.commit()
    finally:
        conn.close()
    assert fingerprint.of_project(project) != before


def test_renumbering_acts_without_reordering_is_not_a_change(project):
    _add_second_act(project)
    before = fingerprint.of_project(project)
    conn = sqlite3.connect(str(project / ".story" / "story.db"))
    try:
        conn.execute("UPDATE entities SET order_key = order_key * 3 + 7 WHERE type='act'")
        conn.commit()
    finally:
        conn.close()
    assert fingerprint.of_project(project) == before


def test_a_save_captures_an_act_reorder(project):
    """The guard that used to refuse this was the fingerprint ignoring act order."""
    _rename(project, "second")
    store.save_snapshot(project, "second")
    _add_second_act(project)
    conn = sqlite3.connect(str(project / ".story" / "story.db"))
    try:
        conn.execute("UPDATE entities SET order_key = 1 WHERE id='act-2'")
        conn.execute("UPDATE entities SET order_key = 2 WHERE id='act-1'")
        conn.commit()
    finally:
        conn.close()
    assert store.save_snapshot(project, "act reorder")["label"] == "act reorder"


def test_a_save_freezes_the_current_state(project):
    snapshot = _saved(project, "After the rename")
    assert snapshot["label"] == "After the rename" and snapshot["seq"] == 2
    assert snapshot["fingerprint"] == fingerprint.of_project(project)
    assert snapshot["schema_version"] == _live(project, "PRAGMA user_version")[0][0]
    assert snapshot["counts"]["scene"] == 3


def test_a_saved_draft_file_is_read_only(project):
    snapshot = _saved(project, "frozen")
    mode = stat.S_IMODE(store.snapshot_file(project, snapshot["id"]).stat().st_mode)
    assert mode == store.FROZEN_MODE


def test_a_saved_draft_is_independent_of_later_edits(project):
    snapshot = _saved(project, "Before")
    _rename(project, "After")
    _saved(project, "After")
    conn = sqlite3.connect(
        f"file:{store.snapshot_file(project, snapshot['id'])}?mode=ro&immutable=1", uri=True
    )
    try:
        assert conn.execute("SELECT name FROM entities WHERE id='kael'").fetchone()[0] == "Before"
    finally:
        conn.close()


def test_a_draft_carries_no_staged_proposals(project):
    """A staged proposal belongs to the head it was made on, not to the story."""
    drafts.stage(
        project,
        [
            {
                "op": "edit",
                "entity_type": "character",
                "entity_id": "kael",
                "data": {"name": "x"},
                "summary": "s",
            }
        ],
        "a staged change",
    )
    _rename(project, "unrelated")  # so the save is not refused as unchanged
    snapshot = store.save_snapshot(project, "with a proposal open")
    conn = sqlite3.connect(
        f"file:{store.snapshot_file(project, snapshot['id'])}?mode=ro&immutable=1", uri=True
    )
    try:
        assert conn.execute("SELECT count(*) FROM drafts").fetchone()[0] == 0
    finally:
        conn.close()
    # the head keeps it: the save is a copy, not a move
    assert _live(project, "SELECT count(*) FROM drafts WHERE status='open'")[0][0] == 1


def test_a_save_records_its_parent_and_moves_the_base(project):
    first = store.head_state(project)["base"]
    second = _saved(project, "Second")
    assert second["parents"] == [first["id"]]
    assert store.list_branches(project)["branches"][0]["base_snapshot_id"] == second["id"]


def test_a_save_takes_no_backup(project):
    _saved(project, "no backup")
    assert [b for b in list_backups(project) if b["kind"] == "automatic"] == []


def test_a_failed_save_leaves_no_file_behind(project, monkeypatch):
    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(store.os, "replace", boom)
    with pytest.raises(OSError):
        _saved(project, "doomed")
    leftovers = [p.name for p in store.snapshots_dir(project).iterdir() if "partial" in p.name]
    assert leftovers == []
    assert len(store.list_branches(project)["snapshots"]) == 1


# ─── branches ───


def test_a_branch_starts_parked_at_its_draft(project):
    base = store.head_state(project)["base"]
    branch = store.branch_from(project, base["id"], "alternate")
    assert branch["name"] == "alternate" and not branch["is_current"]
    assert branch["base_snapshot_id"] == base["id"]
    parked = store.head_file(project, branch["id"])
    assert parked.exists()
    conn = sqlite3.connect(f"file:{parked}?mode=ro&immutable=1", uri=True)
    try:
        assert conn.execute("SELECT count(*) FROM entities WHERE is_deleted=0").fetchone()[0] > 0
    finally:
        conn.close()


def test_a_branch_id_is_slugged_once_and_survives_a_rename(project):
    base = store.head_state(project)["base"]
    branch = store.branch_from(project, base["id"], "Second Attempt")
    assert branch["id"] == "second-attempt"
    renamed = store.rename_branch(project, branch["id"], "Third Try")
    assert renamed["name"] == "Third Try" and renamed["id"] == "second-attempt"


def test_two_branches_cannot_share_a_name(project):
    base = store.head_state(project)["base"]
    store.branch_from(project, base["id"], "alternate")
    with pytest.raises(ValueError, match="already a branch called"):
        store.branch_from(project, base["id"], "alternate")


def test_a_branch_from_a_missing_draft_is_refused(project):
    with pytest.raises(ValueError, match="No such draft"):
        store.branch_from(project, "s-nope", "x")


# ─── switch ───


def test_a_switch_carries_the_other_branch_state(project):
    base = store.head_state(project)["base"]
    branch = store.branch_from(project, base["id"], "alternate")
    store.switch(project, branch["id"])
    _rename(project, "On the alternate")
    store.save_snapshot(project, "alternate one")

    store.switch(project, "main")
    assert _name(project) == "Kael"  # main's head, untouched by the alternate

    store.switch(project, branch["id"])
    assert _name(project) == "On the alternate"


def test_a_switch_parks_the_outgoing_head_and_keeps_only_one(project):
    base = store.head_state(project)["base"]
    branch = store.branch_from(project, base["id"], "alternate")
    store.switch(project, branch["id"])
    assert store.head_file(project, "main").exists()
    assert not store.head_file(project, branch["id"]).exists()  # its head is live now

    store.switch(project, "main")
    assert store.head_file(project, branch["id"]).exists()
    assert not store.head_file(project, "main").exists()


def test_a_switch_leaves_the_manifest_claiming_one_current_branch(project):
    base = store.head_state(project)["base"]
    branch = store.branch_from(project, base["id"], "alternate")
    store.switch(project, branch["id"])
    assert [b["name"] for b in store.list_branches(project)["branches"] if b["is_current"]] == [
        "alternate"
    ]


def test_a_switch_takes_no_backup(project):
    """The parked head IS the pre-switch state; a backup would evict a daily one."""
    base = store.head_state(project)["base"]
    branch = store.branch_from(project, base["id"], "alternate")
    store.switch(project, branch["id"])
    assert list_backups(project) == []


def test_a_switch_is_refused_while_a_draft_is_staged(project):
    base = store.head_state(project)["base"]
    branch = store.branch_from(project, base["id"], "alternate")
    store.switch(project, branch["id"])
    drafts.stage(
        project,
        [
            {
                "op": "edit",
                "entity_type": "character",
                "entity_id": "kael",
                "data": {"name": "x"},
                "summary": "s",
            }
        ],
        "a staged change",
    )
    with pytest.raises(ValueError, match="open drafts"):
        store.switch(project, "main")
    assert _live(project, "SELECT count(*) FROM drafts WHERE status='open'")[0][0] == 1


def test_a_switch_to_the_branch_already_current_is_refused(project):
    with pytest.raises(ValueError, match="Already on main"):
        store.switch(project, "main")


def test_a_switch_to_a_branch_with_no_parked_head_is_refused(project):
    base = store.head_state(project)["base"]
    branch = store.branch_from(project, base["id"], "alternate")
    store.head_file(project, branch["id"]).unlink()
    with pytest.raises(ValueError, match="no parked head"):
        store.switch(project, branch["id"])


def test_a_switch_refuses_a_head_from_a_newer_build(project):
    base = store.head_state(project)["base"]
    branch = store.branch_from(project, base["id"], "alternate")
    conn = sqlite3.connect(str(store.head_file(project, branch["id"])))
    try:
        conn.execute("PRAGMA user_version = 99")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ValueError, match="newer version"):
        store.switch(project, branch["id"])
    assert [b["id"] for b in store.list_branches(project)["branches"] if b["is_current"]] == [
        "main"
    ]


# ─── delete ───


def test_deleting_a_draft_reattaches_its_children(project):
    first = _saved(project, "one")
    second = _saved(project, "two")
    third = _saved(project, "three")
    assert third["parents"] == [second["id"]]

    store.delete_snapshot(project, second["id"])

    graph = {s["id"]: s for s in store.list_branches(project)["snapshots"]}
    assert second["id"] not in graph
    assert graph[third["id"]]["parents"] == [first["id"]]
    assert not store.snapshot_file(project, second["id"]).exists()


def test_a_branchs_latest_draft_cannot_be_deleted(project):
    saved = _saved(project, "the latest")
    with pytest.raises(ValueError, match="cannot be deleted"):
        store.delete_snapshot(project, saved["id"])


def test_deleting_a_branch_removes_the_drafts_nothing_reaches(project):
    base = store.head_state(project)["base"]
    branch = store.branch_from(project, base["id"], "alternate")
    store.switch(project, branch["id"])
    orphan = _saved(project, "only on the alternate")
    store.switch(project, "main")

    result = store.delete_branch(project, branch["id"])

    assert orphan["id"] in result["snapshots_removed"]
    assert not store.snapshot_file(project, orphan["id"]).exists()
    assert not store.head_file(project, branch["id"]).exists()
    # shared ancestry stays: `base` is where main still is
    assert store.snapshot_file(project, base["id"]).exists()


def test_deleting_a_branch_removes_drafts_only_it_reached(project):
    """Reachability, not ownership: a draft another branch's parents link to stays."""
    base = store.head_state(project)["base"]
    branch = store.branch_from(project, base["id"], "alternate")
    store.switch(project, branch["id"])
    picked = _saved(project, "picked into main by a merge")
    store.switch(project, "main")
    _rename(project, "main moved on")
    on_main = store.save_snapshot(project, "main's next draft")
    # what §7.9's complete merge records: main's new draft has two parents
    conn = store.connect(project)
    try:
        conn.execute(
            "INSERT INTO snapshot_parents (snapshot_id, parent_id, ord) VALUES (?,?,1)",
            (on_main["id"], picked["id"]),
        )
    finally:
        conn.close()

    store.delete_branch(project, branch["id"])

    assert store.snapshot_file(project, picked["id"]).exists()  # still reachable
    assert store.snapshot_file(project, base["id"]).exists()
    graph = {s["id"]: s["parents"] for s in store.list_branches(project)["snapshots"]}
    assert graph[on_main["id"]] == [base["id"], picked["id"]]
    assert picked["id"] in graph


def test_the_current_branch_cannot_be_deleted(project):
    with pytest.raises(ValueError, match="branch you are working on"):
        store.delete_branch(project, "main")


def test_deleting_a_missing_branch_is_refused(project):
    with pytest.raises(ValueError, match="No such branch"):
        store.delete_branch(project, "nope")


# ─── the manifest ───


def test_the_manifest_is_its_own_file_with_its_own_version(project):
    conn = sqlite3.connect(str(store.history_path(project)))
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == store.LATEST
    finally:
        conn.close()
    assert store.history_path(project).name == "history.db"


def test_exactly_one_branch_can_be_current(project):
    """The partial unique index is the rule, not a convention."""
    conn = sqlite3.connect(str(store.history_path(project)))
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO branches (id, name, base_snapshot_id, is_current, created_at) "
                "VALUES ('x', 'x', 's', 1, 'now')"
            )
    finally:
        conn.close()


def test_the_listing_carries_the_parents_the_graph_draws(project):
    second = _saved(project, "second")
    third = _saved(project, "third")
    graph = {s["id"]: s for s in store.list_branches(project)["snapshots"]}
    assert graph[third["id"]]["parents"] == [second["id"]]
    assert graph[second["id"]]["parents"] == [store.list_branches(project)["snapshots"][0]["id"]]


# ─── the merge base ─────────────────────────────────────────────────────────


def _renamed(project, label, name):
    _rename(project, name)
    return store.save_snapshot(project, label)


def test_the_merge_base_of_a_draft_with_itself_is_itself(project):
    first = _saved(project, "first")
    assert store.merge_base(project, first["id"], first["id"]) == {
        "base": first["id"],
        "imprecise": False,
    }


def test_the_merge_base_of_a_draft_and_its_parent_is_the_parent(project):
    first = _saved(project, "first")
    second = _renamed(project, "second", "Kael Two")
    assert store.merge_base(project, second["id"], first["id"])["base"] == first["id"]


def test_the_merge_base_of_two_siblings_is_their_common_parent(project):
    first = _saved(project, "first")
    branch = store.branch_from(project, first["id"], "side")
    store.switch(project, branch["id"])
    side = _renamed(project, "side-draft", "Kael Side")
    store.switch(project, store.list_branches(project)["branches"][0]["id"])
    main = _renamed(project, "main-draft", "Kael Main")

    assert store.merge_base(project, main["id"], side["id"]) == {
        "base": first["id"],
        "imprecise": False,
    }


def test_the_merge_base_prefers_the_nearest_shared_draft(project):
    """A cherry-picked source cannot beat a later shared ancestor (§7.1)."""
    first = _saved(project, "first")
    second = _renamed(project, "second", "Kael Two")
    third = _renamed(project, "third", "Kael Three")
    # third reaches first through second, so first is shared but further away.
    assert store.merge_base(project, third["id"], second["id"])["base"] == second["id"]
    assert store.merge_base(project, third["id"], first["id"])["base"] == first["id"]


def test_a_criss_cross_history_is_reported_imprecise(project):
    """Two equally near shared drafts: one is taken, and the plan is told it is a guess.

    Both merge drafts carry `left` and `right` as parents, so each is one step from
    both and neither can win — the recursive-merge shape (§14-F) the flag exists for.
    """
    root = _saved(project, "root")
    left = store.branch_from(project, root["id"], "left")
    right = store.branch_from(project, root["id"], "right")
    sides = {}
    for branch, name in ((left, "Kael Left"), (right, "Kael Right")):
        store.switch(project, branch["id"])
        sides[branch["id"]] = _renamed(project, f"{name}-draft", name)["id"]

    def merge_on(branch_id, label):
        store.switch(project, branch_id)
        conn = sqlite3.connect(str(store.history_path(project)))
        try:
            conn.execute(
                "UPDATE branches SET pending_merge_parents=? WHERE id=?",
                (json.dumps(list(sides.values())), branch_id),
            )
            conn.commit()
        finally:
            conn.close()
        return _renamed(project, label, f"Kael {label}")

    first_merge = merge_on(left["id"], "merge-one")
    second = store.branch_from(project, root["id"], "second")
    second_merge = merge_on(second["id"], "merge-two")

    result = store.merge_base(project, first_merge["id"], second_merge["id"])
    assert result["base"] in sides.values()
    assert result["imprecise"] is True


def test_a_draft_from_another_project_is_refused(project):
    _saved(project, "first")
    with pytest.raises(ValueError, match="No such draft"):
        store.merge_base(project, "s-19700101-000000", "s-19700101-000001")
