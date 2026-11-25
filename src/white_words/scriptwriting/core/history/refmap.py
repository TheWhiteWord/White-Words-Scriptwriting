"""Every place an entity names another entity, declared once.

A reference is stored in one of four ways, and no single one of them is complete:

  * a `ref` in ENTITY_SCHEMAS   — checked at write time, not exhaustive
  * REFERENCE_LISTS/MAPS/COLUMNS — the soft-delete readers' view, ids only
  * a relation kind              — storage, but the field↔kind map stops there
  * a bespoke validator          — `validate_beat_references` and friends

A merge has to resolve, drop or rewrite every reference the incoming content makes
(§7.4), and it can only do that for sites it knows about. A site missing from all
four is a reference that is silently never resolved. This is the complete list, and
tests/test_history_refmap.py pins it to the other four — adding a reference
anywhere else fails the suite rather than being missed at merge time. Five sites
are declared by none of the four, four of them accepted with a dangling slug.

Three paths are in the shape but deliberately not sites:

  * `plot.<role>` (six) — the same relation rows as `scene.plot_roles`, read from
    the plot side. One authored role change is one edit on the scene; listing both
    would make a merge item out of a derived view, and no write path accepts it
    either way (it is `computed`).
  * `scene.act_id` — a copy of the parent chain. `edit_entity` derives it on every
    write, so it cannot disagree with the sequence; it is not a reference a merge
    resolves, so it stays out of the rewrite set.
  * `scene.scene_beats` — a declared `ref`, but computed and absent from the shape;
    the record is reached from its own `scene` side.

`value_turns[].value` is keyed by NAME, not id: a turn stores the value's display
name and the write path refuses the id. Sites are looked up in one space or the
other, never a merged one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..entity import _BY_TYPES, _CHANGE_TYPES


@dataclass(frozen=True)
class Site:
    """One place an entity names another.

    `path` uses `[]` for a list of references and `{}` for a keyed object whose
    KEYS are the references, so the same notation names a site in the declaration
    and one concrete reference (`plot_roles[0].plot`) in a plan. `required` is
    §7.4.2's: False means "drop the reference" is offered as a resolution, True
    means the reference is what the containing value means and dropping it is not
    among the choices.

    `checked_by` names the validator that refuses a dangling slug, or None.

    Being in the soft-delete maps is NOT the same as being checked: they exist so
    a reader hides a deleted id, and four sites are in them (or nowhere) while the
    write path accepts a slug that names nothing. `sequence.primary_plot` is
    declared by nothing at all — not a `ref`, not a map, not a relation kind, not a
    validator — and that is the reason this module exists.
    """

    path: str
    targets: tuple[str, ...]
    required: bool
    checked_by: str | None = None
    keyed_by: str = "id"


# Ordered by entity type in CREATE_ORDER so a reader can compare against
# `logical.CREATE_ORDER` and the schema without jumping around.
SITES: dict[str, tuple[Site, ...]] = {
    "world": (Site("variant_of", ("world",), False),),
    "location": (
        Site("world", ("world",), False),
        Site("variant_of", ("location",), False),
    ),
    "plot": (Site("characters[]", ("character",), False, "check_references"),),
    "relationship": (
        Site("characters[]", ("character",), True),
        Site("perspectives{}", ("character",), True),
        Site("scenes[]", ("scene",), False),
    ),
    "act": (),
    "sequence": (
        Site("act_id", ("act",), True),
        Site("primary_plot", ("plot",), False),
    ),
    "scene": (
        Site("sequence_id", ("sequence",), True, "_validate_sequence_exists"),
        Site("location", ("location",), False, "validate_scene_location"),
        Site("characters[]", ("character",), False),
        Site("plot_roles[].plot", ("plot",), False, "check_references"),
        Site("value_turns[].plot", ("plot",), True, "validate_scene_value_turns"),
        Site("value_turns[].value", ("value",), True, "validate_scene_value_turns", "name"),
        Site(
            "value_turns[].effects[].character",
            ("character",),
            True,
            "validate_scene_value_turns",
        ),
    ),
    "scene_beats": (
        Site("scene", ("scene",), True, "validate_scene_beats"),
        Site("driver", ("character",), False, "check_references"),
        Site("true_character[].character", ("character",), True, "check_references"),
        Site("changes[].entity", _CHANGE_TYPES, True, "validate_beat_references"),
        Site("beats[].action.by", _BY_TYPES, True, "validate_beat_references"),
        Site("beats[].reaction.by", _BY_TYPES, True, "validate_beat_references"),
    ),
    "project": (),
    "character": (),
    "value": (),
}

# In the shape, never a site. The reason is load-bearing: the pinning test uses
# this to tell a deliberate exclusion from a missed reference.
DERIVED: dict[str, tuple[tuple[str, str], ...]] = {
    "plot": tuple(
        (role, "read side of scene.plot_roles")
        for role in (
            "setups",
            "inciting_incident",
            "complications",
            "crisis",
            "climax",
            "resolutions",
        )
    ),
    "scene": (
        ("act_id", "derived from the scene's sequence on every write"),
        ("scene_beats", "computed pointer; reached from the scene_beats side"),
    ),
}


def sites(entity_type: str) -> tuple[Site, ...]:
    """The reference sites of one entity type."""
    return SITES.get(entity_type, ())


def iter_references(entity_type: str, fields: dict) -> list[tuple[str, str, Site]]:
    """Every reference present in `fields`, as `(path, value, site)`.

    The path is concrete (`plot_roles[0].plot`, `perspectives.kael`), so a plan can
    name the item a resolution belongs to. Values that are not a reference are
    never yielded; an empty string, an empty list or a missing key is not one.
    """
    out = []
    for site in sites(entity_type):
        for path, value in _walk(fields, site):
            out.append((path, value, site))
    return out


def rewrite(
    entity_type: str,
    fields: dict,
    *,
    by_id: dict[str, str] | None = None,
    by_name: dict[str, str] | None = None,
) -> dict:
    """A copy of `fields` with site values substituted.

    `by_id` and `by_name` are separate lookup spaces on purpose: a name-keyed site
    must never be substituted by an id mapping that happens to share a string. A
    value with no mapping is left as it is — rewrite renames what the caller
    decided to rename, it does not resolve or validate.

    The input is never mutated: the caller holds the incoming items in a diff, and
    changing them would change what its plan was computed from.
    """
    maps = {"id": by_id or {}, "name": by_name or {}}
    out = dict(fields)
    for site in sites(entity_type):
        mapping = maps[site.keyed_by]
        if not mapping:
            continue
        replaced = _rewrite_at(out, site, mapping)
        if replaced is not None:
            out = replaced
    return out


# ─── the path walker, shared so a declaration and a concrete path agree ───


def _steps(path: str) -> list[tuple[str, str]]:
    """`value_turns[].effects[].character` → [(value_turns, list), (effects, list),
    (character, leaf)]. A `{}` step is `map`: its KEYS are the references."""
    steps = []
    for raw in path.split("."):
        many = raw.endswith("[]")
        keyed = raw.endswith("{}")
        steps.append((raw.rstrip("[]{}"), "list" if many else "map" if keyed else "leaf"))
    return steps


def _walk(fields: dict, site: Site) -> list[tuple[str, str]]:
    """Concrete `(path, value)` for every reference present at `site`."""
    found: list[tuple[str, str]] = []

    def descend(value, steps, at: str) -> None:
        if not steps:
            if isinstance(value, str) and value:
                found.append((at, value))
            return
        key, kind = steps[0]
        rest = steps[1:]
        if not isinstance(value, dict) or key not in value:
            return
        holder = value[key]
        where = f"{at}.{key}" if at else key
        if kind == "leaf":
            descend(holder, rest, where)
        elif kind == "list":
            if isinstance(holder, list):
                for i, entry in enumerate(holder):
                    descend(entry, rest, f"{where}[{i}]")
        elif isinstance(holder, dict):
            for k, entry in holder.items():
                if rest:
                    descend(entry, rest, f"{where}.{k}")
                elif k:
                    found.append((f"{where}.{k}", k))

    descend(fields, _steps(site.path), "")
    return found


def _rewrite_at(fields: dict, site: Site, mapping: dict[str, str]) -> dict | None:
    """`fields` with this site's values mapped, or None when nothing changed."""
    changed_any = [False]

    def apply(value: Any, steps) -> Any:
        """Returns the rewritten value; sets `changed_any` when it mapped one."""
        if not steps:
            if isinstance(value, str) and value in mapping:
                changed_any[0] = True
                return mapping[value]
            return value
        key, kind = steps[0]
        rest = steps[1:]
        if not isinstance(value, dict) or key not in value:
            return value
        holder = value[key]
        if kind == "leaf":
            new = apply(holder, rest)
        elif kind == "list":
            new = [apply(entry, rest) for entry in holder] if isinstance(holder, list) else holder
        elif isinstance(holder, dict):
            if rest:
                new = {k: apply(entry, rest) for k, entry in holder.items()}
            else:
                new = {mapping.get(k, k): entry for k, entry in holder.items()}
                changed_any[0] = changed_any[0] or new != holder
        else:
            return value
        return value if new == holder else {**value, key: new}

    result: Any = apply(fields, _steps(site.path))
    return result if changed_any[0] else None
