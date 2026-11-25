"""The fingerprint of a project's logical content.

Two states are the same draft when their fingerprints match, so this decides what
counts as content: live entities (their columns and `extra`, computed fields
excluded), their `sections`, live relations, and the child order. Everything a
snapshot deliberately does not carry is out — timestamps, `revisions`, `drafts`,
the trash — and so are the `order_key` VALUES: order is fingerprinted as the
per-parent id list instead, so renumbering a parent without reordering it changes
nothing.

`live_relations` and `is_deleted=0` are what make "trash excluded" true: a
trashed row still holds its relations and its sections, and none of them may
reach the hash.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..constants import ENTITY_SCHEMAS
from ..db import get_db
from ..versions import token

# The columns that carry authored content. `order_key` is order (serialized
# separately), and `is_deleted`/`deleted_at` are the trash, which is not content.
_CONTENT_COLUMNS = ("id", "type", "name", "one_sentence", "status", "parent_id", "location_id")

# The types whose order is authored, and so fingerprinted as a list per parent.
ORDERED_TYPES = ("scene", "sequence", "act")


def _computed(entity_type: str) -> set:
    """The field names a type derives at read time rather than storing."""
    return {
        name for name, meta in ENTITY_SCHEMAS.get(entity_type, {}).items() if meta.get("computed")
    }


def of_conn(conn: sqlite3.Connection) -> str:
    """The fingerprint of the state behind `conn`."""
    entities = []
    for row in conn.execute(
        f"SELECT {', '.join(_CONTENT_COLUMNS)}, extra FROM entities WHERE is_deleted=0 ORDER BY id"
    ):
        content = dict(zip(_CONTENT_COLUMNS, row))
        computed = _computed(content["type"])
        extra = json.loads(row[-1] or "{}")
        entities.append(
            {
                **{k: (v if v is not None else "") for k, v in content.items()},
                "extra": {k: v for k, v in extra.items() if k not in computed},
            }
        )

    sections = [
        list(r)
        for r in conn.execute(
            "SELECT s.entity_id, s.heading, s.body FROM sections s "
            "JOIN entities e ON e.id = s.entity_id "
            "WHERE e.is_deleted=0 ORDER BY s.entity_id, s.heading"
        )
    ]

    relations = [
        list(r)
        for r in conn.execute(
            'SELECT from_id, to_id, kind, note, "order" FROM live_relations '
            "ORDER BY from_id, to_id, kind"
        )
    ]

    # Order as the id list a reader sees, ties broken the way every reader breaks
    # them. Two live siblings can share an order_key (a delete frees a key and a
    # restore can leave the pair), so the raw values are not a stable stand-in.
    order: dict[str, list] = {}
    for entity_type, parent_id, entity_id in conn.execute(
        "SELECT type, parent_id, id FROM entities "
        f"WHERE is_deleted=0 AND type IN ({', '.join('?' * len(ORDERED_TYPES))}) "
        "ORDER BY parent_id, order_key, id",
        ORDERED_TYPES,
    ):
        order.setdefault(f"{entity_type}:{parent_id or ''}", []).append(entity_id)

    return token(
        {"entities": entities, "sections": sections, "relations": relations, "order": order}
    )


def of_project(project_path: Path) -> str:
    """The fingerprint of the live database of `project_path`."""
    conn = get_db(project_path)
    try:
        return of_conn(conn)
    finally:
        conn.close()
