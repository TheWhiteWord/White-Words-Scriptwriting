"""The trash: who was deleted together, and removing them for good.

A delete only flags rows (core/writes.py), so everything here works on rows that
are flagged `is_deleted=1`. `deleted_together` is the one definition of "deleted
in the same operation", shared by restore and purge. `purge_deleted` is the only
irreversible entity operation; it is reached through an approved draft
(core/drafts.py), never on the agent's word alone.

The rest of this module is the same model, reachable without the agent: the
dashboard's Trash tab reads `trash_for_ui`, and restores and purges through
`restore`, `restore_many` and `purge_selected`. Those are definitions, not a
second implementation — `tools/story_admin.py` calls them for its own actions,
so the browser and the agent can never disagree about what a bundle is.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import clock
from .constants import ENTITY_LABELS, UNIQUE_PLOT_ROLES
from .references import REFERENCE_LISTS, REFERENCE_MAPS, references_to, scrub_live_extras

# A section body of `[placeholder — type/Section]` is the template's marker, not
# prose. Kept as a copy of the dashboard's predicate on purpose: this module runs
# in Python, that one in the browser, and neither can import the other.
_PLACEHOLDER = re.compile(r"^\s*\[placeholder", re.I)

# Types whose row is INVISIBLE without its parent, which is why restoring one
# while the parent is still in the trash is refused rather than warned about: a
# scene under no sequence is not in the Scenes tree, and a beats record with no
# scene is read by nothing at all. Every other parent link (a location's world, a
# variant's base) is a label, not a place in the structure, and only warns.
_NEEDS_PARENT = ("scene_beats", "scene", "sequence")


def purge_cutoff(days: int) -> str:
    """ISO timestamp: entities deleted at or before it are old enough to purge.

    Compared against `deleted_at` as text, so it comes from the same clock and
    has the same format (UTC, whole seconds, explicit offset).
    """
    return clock.ago_iso(days)


def select_one_deletion(conn, target: dict):
    """The rows a targeted purge removes: the entity and what was deleted with it.

    Returns (rows, None), or (None, refusal) when the target is not something
    that may be purged. "Deleted with it" is the same test list_deleted uses: a
    child of the target carrying the target's own deletion stamp. A child that
    was deleted separately keeps its own entry and stays in the trash.
    """
    entity_id = target.get("id") or ""
    entity_type = target.get("entity_type") or ""
    row = conn.execute(
        "SELECT id, type, deleted_at, is_deleted FROM entities WHERE id=?", (entity_id,)
    ).fetchone()
    if not row:
        return None, {"error": f"Entity not found: {entity_type}/{entity_id}"}
    if entity_type and entity_type != row[1]:
        return None, {"error": f"{row[0]} is a {row[1]}, not a {entity_type}. Nothing was purged."}
    if not row[3]:
        return None, {
            "error": f"{row[0]} is not in the trash — purge only removes entities "
            f"that are already deleted. Nothing was purged.",
            "entity_id": row[0],
        }
    return [(row[0], row[1], row[2])] + deleted_together(conn, row[0], row[2]), None


def deleted_together(conn, entity_id: str, deleted_at) -> list:
    """The children that were deleted in the same operation as `entity_id`.

    One rule, used by restore, by targeted purge and (as a Python grouping) by
    list_deleted: a child in the trash whose deletion stamp equals the parent's.
    A child deleted on its own, earlier or later, carries another stamp and is a
    separate item in the trash.

    Returns (id, type, deleted_at) rows.
    """
    return conn.execute(
        "SELECT id, type, deleted_at FROM entities "
        "WHERE parent_id=? AND is_deleted=1 AND deleted_at = ? ORDER BY type, id",
        (entity_id, deleted_at),
    ).fetchall()


def hard_delete(conn, ids: list) -> list:
    """Remove entities and everything that hangs off them. Inside a transaction.

    Anything else still pointing at one of them as its parent or location (a
    trashed child that was deleted separately) loses that link; a link to a row
    that no longer exists is worse than none.

    `extra` is the same problem one layer down, and a different one from a
    delete: a delete leaves both rows in place, so readers hide the reference. A
    purge removes the row, so nothing knows the id was ever there and readers
    stop hiding it (core/references.py). A live entity's `extra` is therefore
    rewritten here, and the entities that had to change are returned so the
    caller can say which.
    """
    marks = ",".join("?" * len(ids))
    affected = scrub_live_extras(conn, ids)
    conn.execute(f"DELETE FROM sections WHERE entity_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM revisions WHERE entity_id IN ({marks})", ids)
    conn.execute(
        f"DELETE FROM relations WHERE from_id IN ({marks}) OR to_id IN ({marks})", ids + ids
    )
    conn.execute(f"DELETE FROM entities WHERE id IN ({marks})", ids)
    conn.execute(f"UPDATE entities SET parent_id='' WHERE parent_id IN ({marks})", ids)
    conn.execute(f"UPDATE entities SET location_id='' WHERE location_id IN ({marks})", ids)
    return affected


def select_for_purge(conn, target: dict | None, older_than_days: int):
    """What a purge would remove: (rows of id, type, deleted_at, refusal).

    Shared by the purge itself and by the preview the person approves, so the
    card can never describe a different set from the one that goes.
    """
    if target:
        return select_one_deletion(conn, target)
    rows = conn.execute(
        "SELECT id, type, deleted_at FROM entities "
        "WHERE is_deleted=1 AND deleted_at <= ? "
        "ORDER BY type, id",
        (purge_cutoff(older_than_days),),
    ).fetchall()
    return rows, None


def preview_purge(
    project_path: Path, target: dict | None = None, older_than_days: int = 30
) -> dict:
    """What `purge_deleted` would remove, read-only: {items, refusal}.

    Each item is {id, type, name, deleted_at}; `refusal` is the error dict a purge
    of this target would return (a live entity, an unknown id), or None.
    """
    from white_words.scriptwriting.core.db import get_db

    conn = get_db(project_path)
    try:
        rows, refusal = select_for_purge(conn, target, older_than_days)
        if refusal:
            return {"items": [], "refusal": refusal}
        names = _names(conn, [r[0] for r in rows])
        return {
            "items": [
                {
                    "id": r[0],
                    "type": r[1],
                    "name": (names.get(r[0]) or (r[0], r[1]))[0],
                    "deleted_at": r[2],
                }
                for r in rows
            ],
            "refusal": None,
        }
    finally:
        conn.close()


def purge_deleted(
    project_path: Path, target: dict | None = None, older_than_days: int = 30
) -> dict:
    """Remove deleted entities for good. The ONLY irreversible entity operation.

    * no `target` — everything deleted more than `older_than_days` ago (default
      30). The age floor means tidying up can never destroy a fresh mistake.
    * `target` {entity_type, id} — exactly that one entity, plus whatever was
      deleted along with it. The age floor does not apply: naming one item is
      the opposite of a sweep. It must already be in the trash; a live entity
      is refused.

    There is no confirmation here: the person's approval is the draft they
    approve in the app (core/drafts.py, op "purge"), and a backup is taken
    first, so even this is recoverable by hand.
    """
    from white_words.scriptwriting.core.backups import create_backup
    from white_words.scriptwriting.core.db import get_db, transaction

    conn = get_db(project_path)
    try:
        # Selecting what to purge and deleting it are one transaction: the
        # deletes below must land together, or a stop part-way leaves entities
        # with no sections, or sections with no entity.
        with transaction(conn):
            rows, refusal = select_for_purge(conn, target, older_than_days)
            if refusal:
                return refusal
            if not rows:
                younger = conn.execute(
                    "SELECT count(*) FROM entities WHERE is_deleted=1"
                ).fetchone()[0]
                return {
                    "success": True,
                    "purged": [],
                    "message": (
                        f"Nothing is old enough to purge ({younger} deleted entities are "
                        f"younger than {older_than_days} days). They stay restorable."
                    ),
                }

            ids = [r[0] for r in rows]
            backup = create_backup(project_path, automatic=True)
            hard_delete(conn, ids)
    finally:
        conn.close()

    return {
        "success": True,
        "message": f"Purged {len(ids)} entities permanently.",
        "purged": [{"id": r[0], "type": r[1], "deleted_at": r[2]} for r in rows],
        "backup": backup,
        "note": ("Markdown files for these entities are removed by the next story_export."),
    }


# ─── reading the trash ───────────────────────────────────────────────────────


def _label(type_name: str) -> str:
    return ENTITY_LABELS.get(type_name) or type_name.replace("_", " ").capitalize()


def _names(conn, ids) -> dict:
    """{id: (name, type)} for the ids that still exist. Missing ids are absent."""
    ids = [i for i in ids if i]
    if not ids:
        return {}
    rows = conn.execute(
        f"SELECT id, name, type FROM entities WHERE id IN ({','.join('?' * len(ids))})", ids
    ).fetchall()
    return {r[0]: (r[1] or r[0], r[2]) for r in rows}


def _affected(conn, holders, detached) -> list:
    """The live entities a purge touches, as one list for the confirmation card.

    `holders` keep a mention that is about to read empty; `detached` are the
    fields (a location) that will go blank. Both were computed by
    `references_to` before anything was deleted.
    """
    names = _names(conn, list(holders) + [d.get("entity_id", "") for d in detached])
    out = [
        {
            "entity_type": (names.get(h) or ("", ""))[1],
            "id": h,
            "name": (names.get(h) or (h, ""))[0],
            "field": "",
        }
        for h in holders
    ]
    out += [
        {
            "entity_type": d.get("entity_type") or (names.get(d.get("entity_id")) or ("", ""))[1],
            "id": d.get("entity_id", ""),
            "name": (names.get(d.get("entity_id")) or ("", ""))[0],
            "field": d.get("field", ""),
        }
        for d in detached
    ]
    return out


def list_deleted(project_path: Path, older_than_days: int = 30, *, conn=None) -> dict:
    """The trash: every soft-deleted entity, newest deletion first.

    One entry per *deletion*. Deleting a scene also deletes its beats, all
    stamped with the same `deleted_at`; they are folded under the scene as
    `includes` instead of listed as separate things, because restoring the scene
    brings them back with it. An entity deleted separately, at another time, is
    its own entry.

    `purge_eligible` says whether a purge with the current age floor would
    remove it.

    This is the shape `story_admin(action="list_deleted")` returns. The dashboard
    wants more per row; `trash_for_ui` adds it rather than changing this.
    """
    from white_words.scriptwriting.core.db import get_db

    own_conn = conn is None
    if own_conn:
        conn = get_db(project_path)
    days = older_than_days
    cutoff = purge_cutoff(days)

    try:
        rows = conn.execute(
            "SELECT id, type, name, deleted_at, parent_id FROM entities "
            "WHERE is_deleted=1 ORDER BY deleted_at DESC, type, id"
        ).fetchall()
    finally:
        if own_conn:
            conn.close()

    by_id = {r[0]: r for r in rows}

    entries, includes = {}, {}
    for row in rows:
        parent = by_id.get(row[4])
        if parent is not None and parent[3] == row[3]:
            # Same deletion stamp as its parent: deleted in the same operation.
            includes.setdefault(parent[0], []).append(
                {"type": row[1], "id": row[0], "name": row[2] or row[0]}
            )
        else:
            entries[row[0]] = row

    deleted = [
        {
            "type": r[1],
            "id": r[0],
            "name": r[2] or r[0],
            "deleted_at": r[3],
            "purge_eligible": r[3] <= cutoff,
            "includes": includes.get(r[0], []),
        }
        for r in entries.values()
    ]
    result = {
        "success": True,
        "count": len(deleted),
        "deleted": deleted,
        "purge_older_than_days": days,
    }
    if not deleted:
        result["message"] = "Nothing has been deleted."
    else:
        result["hint"] = (
            'Bring one back with action="restore" and target '
            "{entity_type, id}; anything in `includes` comes back with it."
        )
    return result


# ─── what a restore would change, and would refuse ───────────────────────────


def _warning(warnings: dict, code: str, refs: list) -> None:
    """File one warning's refs under its code, keeping the payload JSON-shaped.

    One entity, one line: the key is (type, id), not the field. A scene's
    location is stored twice — the `location_id` column *and* a relation row, the
    same fact written by two paths — so keying on the field produced "The Central
    Room" twice in the same warning, reading as two links to bring back when
    there is one. The first ref wins, and the caller files the column before the
    relation, so the label is the plain one ("location", not "location_scene").
    """
    if not refs:
        return
    bucket = warnings.setdefault(code, [])
    seen = {(r.get("entity_type"), r.get("id")) for r in bucket}
    for ref in refs:
        key = (ref.get("entity_type"), ref.get("id"))
        if key not in seen:
            bucket.append(ref)
            seen.add(key)


def _classify_refs(conn, warnings: dict, ids, field: str, dead, existing, batch) -> None:
    """Split the ids one `extra` field names into "still deleted" and "gone".

    `dead` is every id in the trash, `existing` every id in the table: an id in
    neither was purged, and the reference to it can never resolve again.
    """
    names = _names(conn, ids)
    in_trash, purged = [], []
    for vid in ids:
        if vid in batch:
            continue
        known = names.get(vid)
        ref = {
            "entity_type": (known or ("", ""))[1],
            "id": vid,
            "name": (known or (vid, ""))[0],
            "field": field,
        }
        if vid in dead:
            in_trash.append(ref)
        elif vid not in existing:
            purged.append(ref)
    _warning(warnings, "reference_in_trash", in_trash)
    _warning(warnings, "reference_purged", purged)


def _relations_touching(conn, entity_id: str) -> list:
    """Every relation row with this entity at either end, straight from the table.

    Deliberately not `live_relations`: while the entity is in the trash the view
    hides *all* of them (both ends checked), and the two things that need these
    rows are the two that exist to look at the hidden state — the restore
    preview's "these links stay hidden" warning, and the panel's Links list.
    """
    return conn.execute(
        "SELECT from_id, to_id, kind, note FROM relations WHERE from_id=? OR to_id=? ORDER BY kind",
        (entity_id, entity_id),
    ).fetchall()


# ─── collisions a restore can land in ────────────────────────────────────────

# The two ways out of a role collision, as the message offers them.
_ROLE_CHOICES = ("drop", "take")


def _singular_role_collisions(conn, entity_id: str, batch) -> list:
    """The singular plot roles restoring this scene would put on a second scene.

    A `plot_<role>` row is owned by the plot (`from_id=plot, to_id=scene`) and
    hidden, not removed, by a delete — so a trashed climax still holds its row
    while `validate_scene_plot_roles` (which counts live scenes only) lets
    another scene take the same role. Clearing the flag would then leave two
    live holders, a state no writer permits.

    Read from the `relations` table rather than `live_relations`, because while
    the row is in the trash the view hides every relation it is party to — and
    this is one of the readers that exists to look at the hidden state.

    A scene in `batch` is being restored in the same call, so it competes for
    the role too and is reported; a live holder is what the caller must resolve.
    """
    rows = conn.execute(
        "SELECT from_id, kind FROM relations "
        "WHERE to_id=? AND kind IN ({}) ORDER BY from_id".format(
            ",".join("?" * len(UNIQUE_PLOT_ROLES))
        ),
        (entity_id, *[f"plot_{r}" for r in UNIQUE_PLOT_ROLES]),
    ).fetchall()
    if not rows:
        return []

    out = []
    for plot, kind in rows:
        role = kind[len("plot_") :]
        # Straight from `relations`: a trashed holder's row is hidden by the
        # `live_relations` view, and a scene in the same batch is exactly the
        # case where two rows would arrive on one role together.
        holders = conn.execute(
            "SELECT e.id, e.name, e.is_deleted FROM relations r "
            "JOIN entities e ON e.id = r.to_id "
            "WHERE r.from_id=? AND r.kind=? AND r.to_id<>? ORDER BY e.id",
            (plot, kind, entity_id),
        ).fetchall()
        plot_name = _names(conn, [plot]).get(plot, (plot, "plot"))[0]
        # A live holder is what the caller must resolve. A trashed one only
        # competes when it is arriving in the same call.
        live = [h for h in holders if not h[2]]
        competing = [h for h in holders if h[2] and h[0] in batch]
        if not live and not competing:
            continue
        holder = (live or competing)[0]
        out.append(
            {
                "code": "role_collision",
                "plot": plot,
                "plot_name": plot_name,
                "role": role,
                "holder": {"id": holder[0], "name": holder[1] or holder[0]},
                # `take` moves the role off the holder. A second scene in the
                # batch means both would hold it, so the choice is not offered.
                "choices": list(_ROLE_CHOICES) if not competing else ["drop"],
                "message": (
                    f"Plot “{plot_name}” already has its {role.replace('_', ' ')} on "
                    f"“{holder[1] or holder[0]}”. One scene per plot: choose which "
                    f"of the two keeps it."
                ),
            }
        )
    return out


def _position_collision(
    conn, etype: str, entity_id: str, parent_id: str, order_key, is_deleted: int
):
    """The live sibling that took this row's `order_key` while it was trashed.

    `_get_next_order_db` hands out `MAX(order_key)+1` over live rows, so a
    deleted row's key goes to the next scene created. Both rows then share a
    key, and readers break the tie on the id string — which puts the restored
    scene wherever its id sorts, not where it was.

    Only for `REORDERABLE_TYPES`: `order_key` is a sequence there. Every other
    type sits on the default 0, siblings included, and a shared 0 means nothing.

    Returns {order_key, after, taken_by}, or None. `after` is the live sibling
    the row followed before the delete: its key was the highest below its own.
    """
    from .writes import REORDERABLE_TYPES

    if etype not in REORDERABLE_TYPES or not parent_id or not is_deleted or order_key is None:
        return None
    taken_by = conn.execute(
        "SELECT id, name FROM entities WHERE parent_id=? AND is_deleted=0 AND order_key=? "
        "AND id<>? ORDER BY id",
        (parent_id, order_key, entity_id),
    ).fetchone()
    if not taken_by:
        return None
    after = conn.execute(
        "SELECT id, name, order_key FROM entities WHERE parent_id=? AND is_deleted=0 "
        "AND order_key<? AND id<>? ORDER BY order_key DESC, id DESC",
        (parent_id, order_key, entity_id),
    ).fetchone()
    return {
        "order_key": order_key,
        "taken_by": {"id": taken_by[0], "name": taken_by[1] or taken_by[0]},
        "after": ({"id": after[0], "name": after[1] or after[0]} if after else None),
    }


def _settle_positions(conn, etype: str, entity_id: str, parent_id: str, after_id: str | None):
    """Put a restored row back in a clean sequence. Returns its position, or None.

    Renumbers the parent's live scenes/sequences through `reorder()` — the only
    writer of `order_key` that produces a complete sibling list — with the
    restored row placed directly after the sibling it followed before the
    delete. `reorder` requires the complete live set, which is exactly what this
    builds. Types that are not reorderable keep their `order_key`: it is not a
    sequence there, so a shared value means nothing (every `value` is key 0).
    """
    from .writes import REORDERABLE_TYPES, reorder

    if etype not in REORDERABLE_TYPES or not parent_id:
        return None
    siblings = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM entities WHERE type=? AND parent_id=? AND is_deleted=0 "
            "ORDER BY order_key, id",
            (etype, parent_id),
        ).fetchall()
    ]
    if entity_id not in siblings:
        return None
    siblings.remove(entity_id)
    at = siblings.index(after_id) + 1 if after_id and after_id in siblings else len(siblings)
    siblings.insert(at, entity_id)
    reorder(None, etype, siblings, "restored", conn=conn)
    return at + 1


def restore_check(conn, entity_id: str, *, also_restoring=()) -> dict:
    """What restoring `entity_id` would bring back, and what stands in the way.

    Read-only. One function, called by the preview and by the restore itself, so
    the panel can never describe a restore that the button will refuse.

      * **blockers** — a structural parent still in the trash (or gone for good):
        restoring would produce a row no reader can see (see `_NEEDS_PARENT`).
        `fix` names the parent to restore in the same batch.
      * **collisions** — a singular plot role this row would put on a second
        live scene, with the scene holding it now and the two ways out. The
        restore is refused until the caller chooses one.
      * **placement** — the sibling that took this row's position while it was
        in the trash. Not a blocker: the restore puts it back after its old
        neighbour and renumbers, so there is nothing to choose.
      * **warnings** — links that will stay hidden because the other end is
        still deleted (`reference_in_trash`), or can never come back because it
        was purged (`reference_purged`), or children that stay behind because
        they were deleted separately (`stranded_children`).
      * **returned** — what becomes VISIBLE again. Nothing is rebuilt: sections
        and relation rows were only hidden, so this is a census, not a promise.

    `also_restoring` is the rest of the batch: a parent in it is not a blocker,
    and a scene in it counts as a competing holder.
    """
    from .references import dead_ids

    row = conn.execute(
        "SELECT id, type, name, parent_id, location_id, extra, is_deleted, deleted_at, order_key "
        "FROM entities WHERE id=?",
        (entity_id,),
    ).fetchone()
    if not row:
        return {"blockers": [], "collisions": [], "warnings": {}, "returned": {}}
    eid, etype, ename, parent_id, location_id, extra_json, is_deleted, deleted_at, order_key = row
    extra = json.loads(extra_json) if extra_json else {}
    batch = set(also_restoring)
    dead = dead_ids(conn)
    existing = {r[0] for r in conn.execute("SELECT id FROM entities")}

    blockers, warnings = [], {}

    # 1. The parent link.
    if parent_id:
        prow = conn.execute(
            "SELECT id, type, name, is_deleted, deleted_at FROM entities WHERE id=?", (parent_id,)
        ).fetchone()
        structural = etype in _NEEDS_PARENT
        if prow is None:
            msg = (
                f"Its {_label(etype)} parent no longer exists — it was removed "
                f"for good, so this would come back with nothing to hang from."
            )
            if structural:
                blockers.append({"code": "parent_missing", "message": msg, "fix": None})
            else:
                _warning(
                    warnings,
                    "parent_missing",
                    [{"entity_type": etype, "id": eid, "field": "parent", "name": ename or eid}],
                )
        elif prow[3] and prow[0] not in batch:
            msg = (
                f"“{prow[2] or prow[0]}” is still in the trash. Restore it too, "
                f"or this comes back where nothing can see it."
            )
            if structural:
                blockers.append(
                    {
                        "code": "parent_trashed",
                        "message": msg,
                        "fix": {"entity_type": prow[1], "id": prow[0], "name": prow[2] or prow[0]},
                    }
                )
            else:
                _warning(
                    warnings,
                    "parent_trashed",
                    [
                        {
                            "entity_type": prow[1],
                            "id": prow[0],
                            "name": prow[2] or prow[0],
                            "field": "parent",
                        }
                    ],
                )

    # 2. A location that is still in the trash reads as no location (dead column).
    if location_id:
        lrow = conn.execute(
            "SELECT id, type, name, is_deleted FROM entities WHERE id=?", (location_id,)
        ).fetchone()
        if lrow and lrow[3] and lrow[0] not in batch:
            _warning(
                warnings,
                "reference_in_trash",
                [
                    {
                        "entity_type": lrow[1],
                        "id": lrow[0],
                        "name": lrow[2] or lrow[0],
                        "field": "location",
                    }
                ],
            )
        elif lrow is None:
            _warning(
                warnings,
                "reference_purged",
                [
                    {
                        "entity_type": "location",
                        "id": location_id,
                        "name": location_id,
                        "field": "location",
                    }
                ],
            )

    # 3. Relation rows that stay hidden: the view drops a row with a dead end.
    kind_by_other = {}
    for from_id, to_id, kind, _note in _relations_touching(conn, eid):
        other = to_id if from_id == eid else from_id
        if other in batch or other == eid:
            continue
        kind_by_other.setdefault(other, set()).add(kind)
    if kind_by_other:
        names = _names(conn, [i for i in kind_by_other if i in existing])
        dead_refs, gone_refs = [], []
        for other, kinds in kind_by_other.items():
            ref = {
                "entity_type": (names.get(other) or ("", ""))[1],
                "id": other,
                "name": (names.get(other) or (other, ""))[0],
                "field": "/".join(sorted(kinds)),
            }
            if other in dead:
                dead_refs.append(ref)
            elif other not in existing:
                gone_refs.append(ref)
        _warning(warnings, "reference_in_trash", dead_refs)
        _warning(warnings, "reference_purged", gone_refs)

    # 4. `extra` references: the same three places readers hide (core/references.py).
    for field in REFERENCE_LISTS:
        values = extra.get(field)
        if isinstance(values, list):
            _classify_refs(conn, warnings, [str(v) for v in values], field, dead, existing, batch)
    for field in REFERENCE_MAPS:
        values = extra.get(field)
        if isinstance(values, dict):
            _classify_refs(conn, warnings, [str(v) for v in values], field, dead, existing, batch)

    # 5. Children in the trash that this restore does NOT bring back.
    #
    # The bundle comes back with the parent — that is the rule `_clear_flags`
    # applies — so a child of the bundle is never "stranded". What stays behind
    # is a child deleted on its own, carrying another stamp: restoring the parent
    # leaves it in the trash, and a reader that walks `parent_id` will not see it.
    bundle = deleted_together(conn, eid, deleted_at) if deleted_at else []
    in_bundle = {c[0] for c in bundle}
    stranded = [
        r
        for r in conn.execute(
            "SELECT id, type FROM entities WHERE parent_id=? AND is_deleted=1 "
            "AND (deleted_at IS NULL OR deleted_at <> ?) ORDER BY type, id",
            (eid, deleted_at),
        ).fetchall()
        if r[0] not in in_bundle
    ]
    if stranded:
        names = _names(conn, [c[0] for c in stranded])
        _warning(
            warnings,
            "stranded_children",
            [
                {
                    "entity_type": c[1],
                    "id": c[0],
                    "field": "parent",
                    "name": (names.get(c[0]) or (c[0], ""))[0],
                }
                for c in stranded
            ],
        )

    # 6. What becomes visible again.
    names = _names(conn, [c[0] for c in bundle])
    children = [
        {"type": c[1], "id": c[0], "name": (names.get(c[0]) or (c[0], ""))[0]} for c in bundle
    ]
    live_relations = conn.execute(
        "SELECT count(*) FROM live_relations WHERE from_id=? OR to_id=?", (eid, eid)
    ).fetchone()[0]
    sections = conn.execute("SELECT count(*) FROM sections WHERE entity_id=?", (eid,)).fetchone()[0]
    holders, detached = references_to(conn, [eid])
    collisions = _singular_role_collisions(conn, eid, batch) if etype == "scene" else []

    return {
        "blockers": blockers,
        "collisions": collisions,
        "placement": _position_collision(conn, etype, eid, parent_id, order_key, is_deleted),
        "warnings": warnings,
        "returned": {
            "children": children,
            "relations": live_relations,
            "sections": sections,
            "referenced_by": _affected(conn, holders, detached),
        },
    }


def trash_for_ui(project_path: Path, older_than_days: int = 30) -> dict:
    """`list_deleted`, plus everything one row of the Trash tab renders.

    One connection and one pass, so the row, the preview panel and the buttons
    are looking at the same state. `restore` per row is `restore_check`: a row
    whose restore would be refused says so before it is clicked.
    """
    from white_words.scriptwriting.core.db import get_db

    conn = get_db(project_path)
    try:
        base = list_deleted(project_path, older_than_days, conn=conn)
        rows = conn.execute(
            "SELECT e.id, e.type, e.name, e.one_sentence, e.location_id, e.extra, "
            "l.name FROM entities e LEFT JOIN entities l ON l.id = e.location_id "
            "WHERE e.is_deleted=1"
        ).fetchall()
        content = {
            r[0]: r[1]
            for r in conn.execute("SELECT entity_id, body FROM sections WHERE heading='Content'")
        }

        info = {}
        for eid, etype, name, one_sentence, location_id, extra_json, location_name in rows:
            extra = json.loads(extra_json) if extra_json else {}
            info[eid] = {
                "type": etype,
                "name": name or eid,
                "one_sentence": one_sentence or "",
                "extra": extra,
                "location_name": location_name or "",
            }

        items = []
        for entry in base["deleted"]:
            row = info.get(entry["id"], {})
            extra = row.get("extra") or {}
            preview = row.get("one_sentence") or ""
            has_script = False
            if entry["type"] == "scene":
                from .scene_script import scene_heading

                heading = scene_heading(
                    extra.get("int_ext", ""),
                    row.get("location_name", ""),
                    extra.get("place", ""),
                    extra.get("time_of_day", ""),
                    extra.get("forced_heading", ""),
                )
                preview = heading or preview
                body = content.get(entry["id"]) or ""
                has_script = bool(body.strip()) and not _PLACEHOLDER.match(body)
            items.append(
                {
                    **entry,
                    "label": _label(entry["type"]),
                    "preview": preview or entry["name"],
                    "has_script": has_script,
                    "includes": [
                        {**inc, "label": _label(inc["type"])} for inc in entry["includes"]
                    ],
                    "restore": restore_check(conn, entry["id"]),
                }
            )

        counts = {}
        for eid, row in info.items():
            counts[row["type"]] = counts.get(row["type"], 0) + 1
    finally:
        conn.close()

    return {
        "success": True,
        "count": len(items),
        "entities": sum(counts.values()),
        "counts_by_type": counts,
        "purge_older_than_days": older_than_days,
        "items": items,
    }


def trash_detail(project_path: Path, entity_type: str, entity_id: str) -> dict:
    """One trashed entity, whole: what the preview panel renders.

    Everything a reader would hide is read unfiltered here — fields, `extra`,
    sections, relation rows, the references other entities hold. This is the one
    reader that must show the dead links, because the person is deciding whether
    to bring them back.

    `restore` is `restore_check`, so the panel and the button cannot disagree,
    and `purge` is `purge_preview` for the same reason.
    """
    from white_words.scriptwriting.core.db import get_db

    conn = get_db(project_path)
    try:
        row = conn.execute(
            "SELECT id, type, name, one_sentence, order_key, status, parent_id, "
            "location_id, deleted_at, extra FROM entities WHERE id=?",
            (entity_id,),
        ).fetchone()
        if not row or row[1] != entity_type:
            return {"error": f"Entity not found: {entity_type}/{entity_id}", "code": "not_found"}
        if row[8] is None:
            return {"error": f"{entity_id} is not in the trash.", "code": "not_deleted"}

        (
            eid,
            etype,
            name,
            one_sentence,
            order_key,
            status,
            parent_id,
            location_id,
            deleted_at,
            extra_json,
        ) = row
        extra = json.loads(extra_json) if extra_json else {}

        bundle = deleted_together(conn, eid, deleted_at)

        # Every id this panel will name: the bundle, the structural parent, the
        # location, and the far end of each relation row. Without the last group
        # a character's cast links printed raw ids ("central-room-day") where the
        # reader wants a scene's name — the panel is the one reader that must
        # name dead links, so it must have them in hand.
        relation_rows = _relations_touching(conn, eid)
        ends = [(r[1] if r[0] == eid else r[0]) for r in relation_rows]
        names = _names(conn, [c[0] for c in bundle] + [parent_id, location_id] + ends)

        def _ref(vid):
            known = names.get(vid) or ("", "")
            return {"id": vid, "entity_type": known[1], "name": known[0] or vid}

        sections = {
            r[0]: r[1]
            for r in conn.execute("SELECT heading, body FROM sections WHERE entity_id=?", (eid,))
        }
        content = sections.get("Content") or ""

        relations, out_links, in_links = [], [], []
        live = {r[0] for r in conn.execute("SELECT id FROM entities WHERE is_deleted=0")}
        for from_id, to_id, kind, note in relation_rows:
            other = to_id if from_id == eid else from_id
            link = {**_ref(other), "kind": kind, "note": note or "", "live": other in live}
            relations.append(link)
            (out_links if from_id == eid else in_links).append(link)

        holders, detached = references_to(conn, [eid])
        check = restore_check(conn, eid)

        return {
            "entity": {
                "id": eid,
                "type": etype,
                "name": name or eid,
                "label": _label(etype),
                "deleted_at": deleted_at,
                "one_sentence": one_sentence or "",
                "has_script": bool(content.strip()) and not _PLACEHOLDER.match(content),
                "fields": {
                    "name": name or "",
                    "one_sentence": one_sentence or "",
                    "status": status or "",
                    "order_key": order_key,
                    "parent": _ref(parent_id) if parent_id else None,
                    "location": _ref(location_id) if location_id else None,
                },
                "extra": extra,
            },
            "includes": [{**_ref(c[0]), "type": c[1], "label": _label(c[1])} for c in bundle],
            "sections": sections,
            "relations": {"out": out_links, "in": in_links, "all": relations},
            "referenced_by": _affected(conn, holders, detached),
            "restore": check,
            "purge": purge_preview(project_path, [{"entity_type": etype, "id": eid}], conn=conn),
        }
    finally:
        conn.close()


# ─── restoring ───────────────────────────────────────────────────────────────


def _clear_flags(conn, entity_id: str, deleted_at) -> list:
    """Un-flag one row and the children this same delete flagged. Returns ids."""
    conn.execute("UPDATE entities SET is_deleted=0, deleted_at=NULL WHERE id=?", (entity_id,))
    children = sorted(r[0] for r in deleted_together(conn, entity_id, deleted_at))
    if children:
        conn.executemany(
            "UPDATE entities SET is_deleted=0, deleted_at=NULL WHERE id=?", [(c,) for c in children]
        )
    return [entity_id] + children


def _resolve(conn, entity_id: str, etype: str, collisions: list, resolutions) -> list:
    """Apply the caller's choices for a row's role collisions.

    `resolutions` is a list of `{plot, role, choice}`. `drop` leaves the role on
    the current holder only, so the incoming row arrives without it — its
    `plot_<role>` row goes, which is the same write an edit makes when a role is
    removed. `take` moves it: the holder loses its row, the restored scene keeps
    its own.

    Raises ValueError naming what is missing, before anything is written.
    """
    chosen = {}
    for r in resolutions or []:
        if not isinstance(r, dict):
            continue
        key = (str(r.get("plot") or ""), str(r.get("role") or ""))
        choice = str(r.get("choice") or "")
        if choice not in _ROLE_CHOICES:
            raise ValueError(
                f"Unknown resolution for {key[0]}/{key[1]}: {choice or '(empty)'}. "
                f"One of: {', '.join(_ROLE_CHOICES)}."
            )
        chosen[key] = choice

    for c in collisions:
        key = (c["plot"], c["role"])
        if key not in chosen:
            raise ValueError(c["message"] + " Choose one: " + " / ".join(c["choices"]) + ".")
        if chosen[key] not in c["choices"]:
            raise ValueError(
                f"“{chosen[key]}” is not available for {c['plot']}/{c['role']}: the other "
                f"scene is in this same restore, so the role can only be dropped. "
                f"Choose one: {', '.join(c['choices'])}."
            )

    applied = []
    for c in collisions:
        plot, role, kind = c["plot"], c["role"], f"plot_{c['role']}"
        choice = chosen[(plot, role)]
        if choice == "drop":
            conn.execute(
                "DELETE FROM relations WHERE from_id=? AND to_id=? AND kind=?",
                (plot, entity_id, kind),
            )
        else:  # take
            # Only a LIVE holder loses the role. A row hidden on a trashed scene
            # is not the caller's to rewrite: that scene's own restore is where
            # it is decided, and deleting it here would drop the role silently.
            conn.execute(
                "DELETE FROM relations WHERE from_id=? AND kind=? AND to_id<>? "
                "AND to_id IN (SELECT id FROM entities WHERE is_deleted=0)",
                (plot, kind, entity_id),
            )
        applied.append({"plot": plot, "role": role, "choice": choice})
    return applied


def restore(
    project_path: Path | None,
    entity_type: str,
    entity_id: str,
    summary: str = "",
    *,
    resolutions=None,
    conn=None,
) -> dict:
    """Undelete an entity by clearing is_deleted. The exact inverse of the delete.

    The delete changes nothing but the flags: sections, relation rows, the names
    other entities hold in `extra`, and `location_id` all stay as written, and
    readers hide the ones that name a deleted entity (the `live_relations` view
    and core/references.py). So there is nothing to rebuild here — clearing the
    flag makes cast, location links, plot roles, relationship characters and
    perspectives visible again, and the stored data is byte for byte what it was.

    The one thing that is not given back: a field someone set to a new value
    while the entity was in the trash. An edit that sets `characters` replaces
    the stored list, hidden names included.

    Two things can stand in the way, both created while the row was hidden:

    * a **singular plot role** another scene took in the meantime. Refused until
      `resolutions` names which scene keeps it (`drop` / `take`), because a
      second live climax is a state no writer permits.
    * a **position** another sibling took: `_get_next_order_db` hands out the
      key of a deleted row. Not refused — the row goes back after the sibling
      it followed before the delete, and the parent is renumbered, which is what
      any other ordering change does.

    Structural checks on the parent are not here: `restore_check` reports them
    and the dashboard refuses on it. `restore_many` applies that check, because
    a batch is one action.

    `project_path` is read only when `conn` is None, so a caller already inside
    its own transaction passes `None` and its `conn`.
    """
    from white_words.scriptwriting.core.db import get_db, transaction

    own_conn = conn is None
    if own_conn:
        assert project_path is not None, (
            "restore needs a project_path when it opens its own connection"
        )
        conn = get_db(project_path)
    try:
        # The parent and its children come back together or not at all.
        with transaction(conn):
            # Deliberately NOT filtered on is_deleted — that is the point.
            row = conn.execute(
                "SELECT id, type, name, is_deleted, deleted_at, parent_id, order_key "
                "FROM entities WHERE id=?",
                (entity_id,),
            ).fetchone()
            if not row:
                return {"error": f"Entity not found: {entity_type}/{entity_id}"}
            entity_id, etype, ename, is_deleted, deleted_at, parent_id, order_key = row
            if not is_deleted:
                return {
                    "error": f"{entity_id} is not deleted — nothing to restore.",
                    "entity_id": entity_id,
                }
            resolved = []
            if etype == "scene":
                collisions = _singular_role_collisions(conn, entity_id, set())
                if collisions:
                    try:
                        resolved = _resolve(conn, entity_id, etype, collisions, resolutions)
                    except ValueError as e:
                        return {
                            "error": str(e),
                            "code": "restore_needs_decision",
                            "collisions": collisions,
                        }
            placement = _position_collision(
                conn, etype, entity_id, parent_id, order_key, is_deleted
            )
            restored = _clear_flags(conn, entity_id, deleted_at)
            placed = None
            if placement:
                placed = _settle_positions(
                    conn,
                    etype,
                    entity_id,
                    parent_id,
                    (placement["after"] or {}).get("id"),
                )
    finally:
        if own_conn:
            conn.close()

    result = {
        "success": True,
        "message": f"Restored: {summary}",
        "entity_id": entity_id,
        "was_deleted_at": deleted_at,
        "restored": restored,
        "restored_cascade_children": restored[1:],
    }
    if resolved:
        result["resolved_roles"] = resolved
    if placement:
        result["placed"] = {
            "position": placed,
            "after": (placement["after"] or {}).get("name"),
            "was_taken_by": placement["taken_by"]["name"],
        }
    return result


class RestoreRefused(Exception):
    """A batch refused by one of its targets. Raises out of the transaction, so
    nothing in the batch lands; `refused` is the per-target account of why."""

    def __init__(self, refused):
        super().__init__(refused[0]["error"] if refused else "restore refused")
        self.refused = refused


def restore_many(project_path: Path, targets: list, *, resolutions=None) -> dict:
    """Restore several deletions in one transaction, or none of them.

    All-or-nothing on purpose: the batch the person selected is one action, and
    a half-applied one leaves them comparing the list against what they clicked.
    A target whose restore is blocked (its parent is still in the trash and not
    part of the batch) refuses the batch and names the parent, so the caller can
    offer the one-click fix rather than explain a partial result.

    Parents included in the batch are allowed in any order: `restore_check` is
    told what else is being restored, so a scene listed before its sequence is
    not a false blocker.

    `resolutions` is `{target_id: [{plot, role, choice}, …]}` — the roles each
    target keeps. A role collision with no resolution refuses the batch, and
    every target already examined reports its own collisions, so the caller sees
    the whole set of decisions at once.
    """
    from white_words.scriptwriting.core.db import get_db, transaction

    wanted = []
    for target in targets or []:
        eid = (target or {}).get("id") or ""
        if eid and eid not in [w[0] for w in wanted]:
            wanted.append((eid, (target or {}).get("entity_type") or ""))
    if not wanted:
        return {"error": "restore needs targets: [{entity_type, id}, …]"}
    batch = [eid for eid, _ in wanted]
    per_target = resolutions or {}

    conn = get_db(project_path)
    try:
        with transaction(conn):
            # Every check first, against the state the batch started in, then the
            # writes. Interleaved, a target's collision would be judged after an
            # earlier target had already moved the role it collided on, and the
            # caller's resolution would be silently dropped.
            checks, refused = {}, []
            resolved = []
            for eid, etype in wanted:
                row = conn.execute(
                    "SELECT id, type, name, is_deleted, deleted_at, parent_id, order_key "
                    "FROM entities WHERE id=?",
                    (eid,),
                ).fetchone()
                if not row:
                    refused.append(
                        {
                            "entity_type": etype,
                            "id": eid,
                            "error": f"Entity not found: {etype}/{eid}",
                            "blockers": [],
                            "collisions": [],
                        }
                    )
                    continue
                if not row[3]:
                    refused.append(
                        {
                            "entity_type": row[1],
                            "id": eid,
                            "error": f"{eid} is not deleted — nothing to restore.",
                            "blockers": [],
                            "collisions": [],
                        }
                    )
                    continue
                check = restore_check(conn, eid, also_restoring=batch)
                if check["blockers"]:
                    refused.append(
                        {
                            "entity_type": row[1],
                            "id": eid,
                            "error": check["blockers"][0]["message"],
                            "blockers": check["blockers"],
                            "collisions": check["collisions"],
                        }
                    )
                    continue
                checks[eid] = (row, check)

            for eid, (row, check) in checks.items():
                if check["collisions"]:
                    try:
                        resolved += [
                            {"id": eid, **r}
                            for r in _resolve(
                                conn, eid, row[1], check["collisions"], per_target.get(eid)
                            )
                        ]
                    except ValueError as e:
                        refused.append(
                            {
                                "entity_type": row[1],
                                "id": eid,
                                "error": str(e),
                                "blockers": [],
                                "collisions": check["collisions"],
                            }
                        )

            restored, also, placed = [], [], []
            if not refused:
                for eid, (row, check) in checks.items():
                    children = _clear_flags(conn, eid, row[4])
                    restored.append({"type": row[1], "id": eid, "name": row[2] or eid})
                    also.extend(c for c in children if c != eid)
                    if check["placement"]:
                        placed.append(
                            {
                                "id": eid,
                                "position": _settle_positions(
                                    conn,
                                    row[1],
                                    eid,
                                    row[5],
                                    (check["placement"]["after"] or {}).get("id"),
                                ),
                                "after": (check["placement"]["after"] or {}).get("name"),
                            }
                        )
            if refused:
                # Nothing was written: raise out of the transaction with the
                # payload, and the route turns it into a 409.
                raise RestoreRefused(refused)
    finally:
        conn.close()

    result = {
        "success": True,
        "message": f"Restored {len(restored)} item(s).",
        "restored": restored,
        "also_restored": sorted(set(also)),
        "returned": {"entities": len(restored) + len(set(also))},
    }
    if placed:
        result["placed"] = placed
    if resolved:
        result["resolved_roles"] = resolved
    return result


# ─── removing for good, by name ──────────────────────────────────────────────


def _normalise_targets(targets) -> list:
    out = []
    for target in targets or []:
        if not isinstance(target, dict):
            continue
        eid = target.get("id") or ""
        if eid and eid not in [t["id"] for t in out]:
            out.append({"entity_type": target.get("entity_type") or "", "id": eid})
    return out


def purge_preview(project_path: Path, targets: list, *, conn=None) -> dict:
    """What a purge of these targets would remove. Read-only, and the card the
    person approves is built from this — never from the caller's copy."""
    from white_words.scriptwriting.core.db import get_db

    wanted = _normalise_targets(targets)
    own_conn = conn is None
    if own_conn:
        conn = get_db(project_path)
    try:
        rows, refusal = [], None
        for target in wanted:
            got, refusal = select_one_deletion(conn, target)
            if refusal:
                return {"items": [], "affected": [], "refusal": refusal}
            rows.extend(got)
        ids, seen = [], set()
        for rid in (r[0] for r in rows):
            if rid not in seen:
                ids.append(rid)
                seen.add(rid)
        names = _names(conn, ids)
        holders, detached = references_to(conn, ids)
        affected = _affected(conn, holders, detached)
        return {
            "items": [
                {
                    "id": rid,
                    "type": names.get(rid, ("", ""))[1] or "",
                    "name": (names.get(rid) or (rid, ""))[0],
                    "label": _label(names.get(rid, ("", ""))[1] or ""),
                }
                for rid in ids
            ],
            "affected": affected,
            "backup": True,
            "refusal": None,
        }
    finally:
        if own_conn:
            conn.close()


def purge_selected(project_path: Path, targets: list) -> dict:
    """Remove the named deletions for good. One backup, one transaction.

    Each target is named by the person, which is what bypasses the age floor
    (`purge_deleted` says why): this is not a sweep. All-or-nothing, so a target
    that is not in the trash (restored by the agent a moment ago) refuses the
    whole call instead of removing the rest and reporting a mystery.
    """
    from white_words.scriptwriting.core.backups import create_backup
    from white_words.scriptwriting.core.db import get_db, transaction

    wanted = _normalise_targets(targets)
    if not wanted:
        return {"error": "purge needs targets: [{entity_type, id}, …]"}

    conn = get_db(project_path)
    try:
        with transaction(conn):
            rows, refusal = [], None
            for target in wanted:
                got, refusal = select_one_deletion(conn, target)
                if refusal:
                    return {"purged": [], **refusal}
                rows.extend(got)
            ids, seen = [], set()
            for rid in (r[0] for r in rows):
                if rid not in seen:
                    ids.append(rid)
                    seen.add(rid)
            names = _names(conn, ids)
            holders, detached = references_to(conn, ids)
            affected = _affected(conn, holders, detached)
            purged = [
                {
                    "id": rid,
                    "type": names.get(rid, ("", ""))[1],
                    "name": (names.get(rid) or (rid, ""))[0],
                    "deleted_at": next((r[2] for r in rows if r[0] == rid), None),
                }
                for rid in ids
            ]
            backup = create_backup(project_path, automatic=True)
            cleared = hard_delete(conn, ids)
    finally:
        conn.close()

    return {
        "success": True,
        "message": f"Permanently deleted {len(ids)} entities.",
        "purged": purged,
        "backup": backup,
        "affected": affected,
        "cleared": cleared,
        "note": (
            "A backup was taken first. Markdown files for these entities are "
            "removed by the next story_export."
        ),
    }
