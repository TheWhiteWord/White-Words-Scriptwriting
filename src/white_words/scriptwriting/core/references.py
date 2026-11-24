"""References to deleted entities: kept in storage, hidden from readers.

An entity can name another by id in three places that are not relation rows:

  * `extra` lists:      `characters`, `scenes`   (a relationship, a plot)
  * `extra` keyed maps: `perspectives`           (one entry per character)
  * columns:            `location_id`            (a scene's location)
                        `parent_id`              (a location's world, ...)

Deleting the entity they name only flags it. These references stay exactly as
written, so restoring the entity puts everything back; what changes is what a
READER sees. A reader that parses an entity's `extra`, or reads `location_id`,
passes it through `live_extra` / `live_column` first, with the ids from
`dead_ids`. (Relation rows are hidden the same way, in SQL, by the
`live_relations` view.)

WRITERS use the stored values as they are: an edit merges into the raw `extra`,
so a reference the edit does not touch stays. An edit that sets one of these
fields replaces it outright, and the dead id goes with it.

Whatever is added to REFERENCE_LISTS / REFERENCE_MAPS / REFERENCE_COLUMNS is
hidden everywhere at once; a reader that does not call these shows the ghost.
tests/test_live_references.py compares every reader against a project where the
references were physically removed, which is how a missed reader is found.
"""
from __future__ import annotations

import json

REFERENCE_LISTS = ("characters", "scenes")
REFERENCE_MAPS = ("perspectives",)
# `parent_id` is a reference only for an entity whose parent was deleted without
# it: a delete flags every live CHILD, so what is left is a grandchild (a location
# put under a location). It reads as having no parent, as it did when the delete
# blanked the column; the structural parents (act, sequence, scene) cannot be
# orphaned because a delete with live structural children is refused.
REFERENCE_COLUMNS = ("location_id", "parent_id")


def dead_ids(conn) -> frozenset:
    """Ids of every entity in the trash. Cheap: the trash is small."""
    return frozenset(r[0] for r in conn.execute(
        "SELECT id FROM entities WHERE is_deleted=1"))


def live_extra(extra: dict, dead) -> dict:
    """`extra` as a reader should see it: no reference to a deleted entity.

    Returns `extra` itself when nothing in it is dead, otherwise a copy; the
    caller's stored dict is never changed. A list keeps its key (it reads as
    empty, not absent) and loses only the dead ids.
    """
    if not dead or not extra:
        return extra
    out = extra
    for field in REFERENCE_LISTS:
        value = extra.get(field)
        if isinstance(value, list) and any(str(v) in dead for v in value):
            if out is extra:
                out = dict(extra)
            out[field] = [v for v in value if str(v) not in dead]
    for field in REFERENCE_MAPS:
        value = extra.get(field)
        if isinstance(value, dict) and any(k in dead for k in value):
            if out is extra:
                out = dict(extra)
            out[field] = {k: v for k, v in value.items() if k not in dead}
    return out


def live_column(value, dead):
    """A reference column's value as a reader should see it: '' if it names a
    deleted entity. '' rather than None, as the old scrub wrote: an empty value
    and a missing one read the same to unfilled_fields, and '' shows as a
    visible blank in Markdown."""
    return "" if value and value in dead else value


def scrub_live_extras(conn, ids) -> list:
    """Remove references to `ids` from the `extra` of LIVE entities.

    For a *delete* nothing needs this: the ids stay in `entities`, so `dead_ids`
    knows them and `live_extra` hides them, and that is what makes restore exact.
    A *purge* is the one case where the id leaves `entities` altogether — after
    which `dead_ids` no longer lists it and every reader stops hiding it. A live
    scene would keep `characters: ["kael"]` for a character that no longer
    exists, and render a chip for it. So a purge physically removes what a delete
    only hid.

    Call it inside the purge's transaction, before the rows go. Returns the ids
    of the live entities whose `extra` changed.
    """
    ids = {str(i) for i in ids}
    if not ids:
        return []
    changed = []
    for entity_id, extra_json in conn.execute(
            "SELECT id, extra FROM entities WHERE is_deleted=0").fetchall():
        extra = json.loads(extra_json) if extra_json else {}
        shown = live_extra(extra, ids)
        if shown is extra:
            continue
        conn.execute("UPDATE entities SET extra=? WHERE id=?",
                     (json.dumps(shown), entity_id))
        changed.append(entity_id)
    return changed


def references_to(conn, ids) -> tuple:
    """What deleting `ids` leaves pointing at them, for the delete's report.

    Read-only. Returns (entity ids whose `extra` names one of them, one entry per
    live scene-like entity whose `location_id` did). The first is what readers now
    hide from those entities; the second is the fields that now read empty.
    """
    ids = set(ids)
    holders, detached = [], []
    for entity_id, entity_type, extra_json, location_id in conn.execute(
            "SELECT id, type, extra, location_id FROM entities WHERE is_deleted=0"):
        if entity_id in ids:
            continue
        extra = json.loads(extra_json) if extra_json else {}
        hit = live_extra(extra, ids) is not extra
        if location_id and location_id in ids:
            hit = True
            detached.append({"entity_id": entity_id, "entity_type": entity_type,
                             "field": "location", "was_pointing_at": location_id})
        if hit:
            holders.append(entity_id)
    return holders, detached


def live_extra_json(extra_json, dead):
    """`live_extra` for a reader that keeps `extra` as the stored JSON text.

    The same string comes back when nothing in it is dead.
    """
    if not dead or not extra_json:
        return extra_json
    extra = json.loads(extra_json)
    shown = live_extra(extra, dead)
    return extra_json if shown is extra else json.dumps(shown)
