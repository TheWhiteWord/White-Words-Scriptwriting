"""The logical entity: an entity as an author writes it.

An entity is columns plus `extra` plus `sections` plus relations, and some facts
are stored twice or from the other end — a scene's `location_id` column and its
`location_scene` relation; a scene's `plot_roles`, which are relation rows owned
by the plot. Diffing raw rows would report one authored change as several.

So this module assembles the authored shape: ``{id, type, fields, sections}``
with computed fields and ``order_key`` left out. Order is not a field; it is the
per-parent id list in `order_of`.

The shape is what `create_entity` takes, which is what makes the round trip in
`rebuild` possible: materialize a project, create every entity in a second
project, materialize again, and the two shapes are equal.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..constants import ENTITY_SCHEMAS
from ..db import get_db
from ..entity import (
    ENTITY_COLUMN_MAP,
    REVERSED_RELATION_KINDS,
    _RELATION_FIELDS,
    standard_sections,
)
from ..references import REFERENCE_COLUMNS, dead_ids, live_column, live_extra
from ..writes import create_entity
from .fingerprint import ORDERED_TYPES

# `create_entity` numbers a scene or sequence itself, so their `order` field
# would be a second copy of the same fact; an act is not auto-numbered, so its
# `order` is a real field.
AUTO_NUMBERED = ("scene", "sequence")

# A type is created only after every type it names, or `check_references` and
# the parent validators refuse the create.
CREATE_ORDER = (
    "world",
    "value",
    "project",
    "character",
    "location",
    "plot",
    "relationship",
    "act",
    "sequence",
    "scene",
    "scene_beats",
)


def _columns(conn: sqlite3.Connection) -> list[str]:
    return [c[1] for c in conn.execute("PRAGMA table_info(entities)")]


def _relation_values(conn: sqlite3.Connection, entity_id: str, entity_type: str) -> dict:
    """The relation-backed fields of one entity, read from the live view."""
    values = {}
    for field, (kind, is_list) in _RELATION_FIELDS.get(entity_type, {}).items():
        owner, other = (
            ("to_id", "from_id") if kind in REVERSED_RELATION_KINDS else ("from_id", "to_id")
        )
        rows = list(
            conn.execute(
                f"SELECT {other}, note FROM live_relations WHERE {owner}=? AND kind=? "
                'ORDER BY "order"',
                (entity_id, kind),
            )
        )
        if not is_list:
            values[field] = rows[0][0] if rows else ""
        elif kind.startswith("plot_"):
            values[field] = [{"scene_id": to_id, "description": note} for to_id, note in rows]
        else:
            values[field] = [to_id for to_id, _ in rows]
    # A scene's plot_roles are the same rows read from the plot side — one field
    # to six kinds, so the generic map above cannot express it.
    if entity_type == "scene":
        values["plot_roles"] = [
            {"plot": plot, "role": kind[len("plot_") :], "description": note or ""}
            for plot, kind, note in conn.execute(
                "SELECT from_id, kind, note FROM live_relations "
                "WHERE to_id=? AND kind LIKE 'plot\\_%' ESCAPE '\\' ORDER BY \"order\"",
                (entity_id,),
            )
        ]
    return values


def _sections(conn: sqlite3.Connection, entity_id: str, entity_type: str) -> dict:
    """A entity's prose, normalized to the standard set.

    Every write path creates the whole standard set, so a missing heading means
    empty, not absent. Normalizing here is what lets a state whose empty rows
    were pruned round-trip through `create_entity`, which always writes them.
    """
    body = {
        heading: text or ""
        for heading, text in conn.execute(
            "SELECT heading, body FROM sections WHERE entity_id=?", (entity_id,)
        )
    }
    return {heading: body.get(heading, "") for heading in standard_sections(entity_type)}


def materialize(conn: sqlite3.Connection) -> dict[str, dict]:
    """``{id: {id, type, fields, sections}}`` for every live entity.

    References to a trashed entity are hidden, as every other reader hides them
    (`live_extra` / `live_column`): the trashed entity is absent from the shape,
    so an id naming it here would be a reference to nothing.
    """
    columns = _columns(conn)
    dead = dead_ids(conn)
    out = {}
    for row in conn.execute(f"SELECT {', '.join(columns)} FROM entities WHERE is_deleted=0"):
        data = dict(zip(columns, row))
        entity_type = data["type"]
        schema = ENTITY_SCHEMAS[entity_type]
        colmap = ENTITY_COLUMN_MAP.get(entity_type, {})
        extra = live_extra(json.loads(data["extra"] or "{}"), dead)

        fields = {}
        for field, meta in schema.items():
            if meta.get("computed"):
                continue
            if entity_type in AUTO_NUMBERED and field == "order":
                continue
            if field in colmap:
                column = colmap[field]
                value = data[column]
                fields[field] = live_column(value, dead) if column in REFERENCE_COLUMNS else value
            else:
                fields[field] = extra.get(field, meta["default"])
        fields.update(_relation_values(conn, data["id"], entity_type))

        out[data["id"]] = {
            "id": data["id"],
            "type": entity_type,
            "fields": fields,
            "sections": _sections(conn, data["id"], entity_type),
        }
    return out


def order_of(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Child order per parent, as the id list a reader sees.

    ``{"scene:<sequence_id>": [id, ...], "sequence:<act_id>": [...],
    "act:": [...]}``. Ties are broken the way every reader breaks them, because
    two live siblings can share an `order_key` (a delete frees a key and a
    restore can leave the pair).
    """
    order: dict[str, list[str]] = {}
    for entity_type, parent_id, entity_id in conn.execute(
        "SELECT type, parent_id, id FROM entities "
        f"WHERE is_deleted=0 AND type IN ({', '.join('?' * len(ORDERED_TYPES))}) "
        "ORDER BY parent_id, order_key, id",
        ORDERED_TYPES,
    ):
        order.setdefault(f"{entity_type}:{parent_id or ''}", []).append(entity_id)
    return order


def of_project(project_path: Path) -> dict[str, dict]:
    """The logical entities of a live project database."""
    conn = get_db(project_path)
    try:
        return materialize(conn)
    finally:
        conn.close()


def rebuild_copy(entities: dict[str, dict], order: dict[str, list[str]], dest: Path) -> None:
    """Create `entities` in `dest` through `create_entity`.

    Creation order is load-bearing: `create_entity` numbers a scene or sequence
    from its live siblings, so children must be created in their parent's
    declared order or the rebuilt project holds a different story. Acts are not
    auto-numbered, so theirs is carried as a field.
    """
    position = {entity_id: i for ids in order.values() for i, entity_id in enumerate(ids)}
    for entity_id in sorted(
        entities,
        key=lambda e: (
            CREATE_ORDER.index(entities[e]["type"]),
            position.get(e, 0),
            e,
        ),
    ):
        entity = entities[entity_id]
        create_entity(
            dest,
            entity["type"],
            entity_id,
            dict(entity["fields"]),
            dict(entity["sections"]),
        )
