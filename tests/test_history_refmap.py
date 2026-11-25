"""`refmap` pinned to the schema, the reference maps and the relation kinds.

A reference site missing from `refmap` is a reference a merge never resolves and
never rewrites — it disappears silently, on a real project, long after this suite
ran. So the module does not build itself from the existing maps (all incomplete);
it declares the complete list and these tests hold it to every other declaration
in the codebase.

`sequence.primary_plot` is declared by nothing else at all — not a `ref`, not a
soft-delete map, not a relation kind, not a validator. It is the reason the module
exists, and the assertion that names it is what keeps its absence visible.
"""

import json

import pytest

from white_words.scriptwriting.core.constants import ENTITY_SCHEMAS
from white_words.scriptwriting.core.db import get_db
from white_words.scriptwriting.core.entity import (
    _BY_TYPES,
    _CHANGE_TYPES,
    _RELATION_FIELDS,
    ENTITY_COLUMN_MAP,
)
from white_words.scriptwriting.core.history import logical, refmap
from white_words.scriptwriting.core.references import (
    REFERENCE_COLUMNS,
    REFERENCE_LISTS,
    REFERENCE_MAPS,
)
from white_words.scriptwriting.core.writes import create_entity


@pytest.fixture
def project(fixture_path):
    return fixture_path


def _sites():
    return {(t, s.path): s for t, group in refmap.SITES.items() for s in group}


def _declared_refs():
    """Every `ref` in the schema, at any nesting depth, as (type, path, target).

    A `ref` inside a list's entries is reported with the list marker, the way
    refmap spells it (`plot_roles[].plot`, not `plot_roles.plot`).
    """

    def walk(entity_type, meta, path):
        prefix = f"{path}[]" if meta.get("type") == "list" else path
        if meta.get("ref"):
            yield entity_type, prefix, meta["ref"]
        for key, sub in (meta.get("sub_fields") or {}).items():
            yield from walk(entity_type, sub, f"{prefix}.{key}")

    for entity_type, schema in ENTITY_SCHEMAS.items():
        for name, meta in schema.items():
            yield from walk(entity_type, meta, name)


# ─── the pin: every declaration elsewhere agrees with this one ───


def test_every_declared_ref_is_a_site_with_the_same_target():
    """`check_references` resolves a `ref` at write time; refmap must agree.

    `scene.scene_beats` is the one exception and it is declared: the field is
    computed, so it is absent from the logical shape and there is nothing for a
    merge to rewrite.
    """
    sites = _sites()
    derived = {(t, p) for t, group in refmap.DERIVED.items() for p, _why in group}
    missing = []
    for entity_type, path, target in _declared_refs():
        if (entity_type, path) in sites:
            assert sites[(entity_type, path)].targets == (target,), (entity_type, path)
        elif (entity_type, path) not in derived:
            missing.append((entity_type, path, target))
    assert missing == [], f"declared refs with no site: {missing}"


def test_the_only_unchecked_site_is_the_one_nothing_declares():
    """Every site but one is enforced by a validator or a declared `ref`+map.

    `sequence.primary_plot` has neither: a dangling slug is accepted today. That
    is a known gap, not an oversight — naming it here means it cannot grow a
    sibling without this assertion noticing.
    """
    unchecked = {(t, p) for (t, p), s in _sites().items() if s.checked_by is None}
    assert unchecked == {
        ("world", "variant_of"),
        ("location", "world"),
        ("location", "variant_of"),
        ("relationship", "characters[]"),
        ("relationship", "perspectives{}"),
        ("relationship", "scenes[]"),
        ("sequence", "act_id"),
        ("sequence", "primary_plot"),
        ("scene", "characters[]"),
    }, "the set of sites with no validator changed — check each, then update"


def test_the_site_nothing_declares_is_still_a_site():
    """The module's reason to exist: a reference no other mechanism knows about."""
    site = _sites()[("sequence", "primary_plot")]
    assert site.targets == ("plot",)
    assert site.checked_by is None
    # And it is genuinely outside every other declaration.
    assert "primary_plot" not in _RELATION_FIELDS.get("sequence", {})
    assert "ref" not in ENTITY_SCHEMAS["sequence"]["primary_plot"]


def test_every_relation_kind_backs_a_site_or_is_derived():
    """A relation kind fills a field; the plot's role kinds fill a derived one."""
    derived = {(t, p) for t, group in refmap.DERIVED.items() for p, _why in group}
    sites = _sites()
    for entity_type, fields in _RELATION_FIELDS.items():
        for field, (kind, is_list) in fields.items():
            path = f"{field}[]" if is_list else field
            if (entity_type, path) in sites:
                continue
            assert (entity_type, field) in derived, (
                f"{kind} fills {entity_type}.{field}, which is neither a site nor derived"
            )


def test_the_soft_delete_maps_are_sites():
    """`REFERENCE_*` exist for the readers; every entry must be a reference here."""
    sites = _sites()
    assert ("relationship", "characters[]") in sites
    assert ("relationship", "scenes[]") in sites
    assert ("scene", "characters[]") in sites
    assert ("plot", "characters[]") in sites
    assert ("relationship", "perspectives{}") in sites
    assert set(REFERENCE_LISTS) == {"characters", "scenes"}
    assert set(REFERENCE_MAPS) == {"perspectives"}
    assert set(REFERENCE_COLUMNS) == {"location_id", "parent_id"}


def test_a_column_backed_site_names_the_column_the_map_holds():
    """`ENTITY_COLUMN_MAP` is where a column-backed reference is stored."""
    for (entity_type, path), _site in _sites().items():
        column = ENTITY_COLUMN_MAP.get(entity_type, {}).get(path)
        if column is None:
            continue
        assert column.endswith("_id"), (entity_type, path, column)


def test_the_multi_type_sites_are_the_validators_tuples():
    """Two sites name several types; a copy of the tuple here would drift."""
    sites = _sites()
    assert sites[("scene_beats", "beats[].action.by")].targets == _BY_TYPES
    assert sites[("scene_beats", "beats[].reaction.by")].targets == _BY_TYPES
    assert sites[("scene_beats", "changes[].entity")].targets == _CHANGE_TYPES


def test_only_the_value_turn_is_name_keyed():
    """A name-keyed site cannot be rewritten by an id mapping; the list is short."""
    assert {(t, p) for (t, p), s in _sites().items() if s.keyed_by == "name"} == {
        ("scene", "value_turns[].value")
    }


def test_spec_742_marks_the_sites_it_names():
    """Four optional, four required — §7.4.2's own list, so a change is deliberate."""
    sites = _sites()
    optional = {
        ("scene", "characters[]"),
        ("scene", "location"),
        ("scene", "plot_roles[].plot"),
        ("relationship", "scenes[]"),
    }
    required = {
        ("scene_beats", "beats[].action.by"),
        ("scene_beats", "beats[].reaction.by"),
        ("scene", "value_turns[].value"),
        ("scene", "sequence_id"),
    }
    for key in optional:
        assert sites[key].required is False, key
    for key in required:
        assert sites[key].required is True, key


def test_every_site_path_starts_with_a_declared_field():
    """A typo in a path would silently walk nothing; the field must be real."""
    for (entity_type, path), _site in _sites().items():
        top = path.split(".")[0].rstrip("[]{}")
        assert top in ENTITY_SCHEMAS[entity_type], (entity_type, path)


# ─── the fixture sweep: nothing id-shaped is unaccounted for ───


def _ids(project):
    conn = get_db(project)
    try:
        return {r[0] for r in conn.execute("SELECT id FROM entities")}
    finally:
        conn.close()


def _materialized(project):
    conn = get_db(project)
    try:
        return logical.materialize(conn)
    finally:
        conn.close()


def _strings(value, path=""):
    """Every non-empty string in a field tree, with its path."""
    if isinstance(value, str):
        if value:
            yield path, value
    elif isinstance(value, list):
        for i, entry in enumerate(value):
            yield from _strings(entry, f"{path}[{i}]")
    elif isinstance(value, dict):
        for key, entry in value.items():
            yield from _strings(entry, f"{path}.{key}" if path else key)


def _matches(concrete: str, declared: str) -> bool:
    """Is a concrete path (`plot_roles[0].plot`) at the declared site (`plot_roles[].plot`)?

    Concrete paths carry indices; a declaration carries `[]`. A `{}` declaration
    matches the map's keys, which appear as ordinary segments.
    """
    if declared.endswith("{}"):
        base = declared[:-2]
        return concrete.startswith(f"{base}.") and concrete.count(".") == base.count(".") + 1
    import re

    pattern = re.escape(declared).replace(re.escape("[]"), r"\[\d+\]")
    return re.fullmatch(pattern, concrete) is not None


def _at_a_site(path: str, entity_type: str) -> bool:
    return any(_matches(path, site.path) for site in refmap.sites(entity_type))


@pytest.mark.parametrize("entity_type", sorted(ENTITY_SCHEMAS))
def test_no_id_shaped_value_lands_outside_a_site(project, entity_type):
    """The fixture holds an id at every site and at no other string field.

    This is the empirical half of the pin. It catches a reference field that is
    undeclared **and in use** — the fixture value lands here as an unaccounted id
    instead of being missed silently. It cannot catch a field that no fixture entity
    fills: there is nothing to see. The declared half is
    `test_every_declared_ref_is_a_site_with_the_same_target`, and
    `sequence.primary_plot` is the standing example of a site no declaration
    outside this module knows about.
    """
    ids = _ids(project)
    derived = {p for p, _why in refmap.DERIVED.get(entity_type, ())}
    stray = []
    for entity in _materialized(project).values():
        if entity["type"] != entity_type:
            continue
        for path, value in _strings(entity["fields"]):
            if value not in ids:
                continue
            if _at_a_site(path, entity_type):
                continue
            if path.split(".")[0].split("[")[0] in derived:
                continue
            stray.append((entity["id"], path, value))
    assert stray == [], f"id-shaped values at no declared site: {stray}"


def test_the_fixture_exercises_every_site_but_one(project):
    """A site no fixture value reaches is untested; one is known and constructed.

    `location.variant_of` has no fixture row — the fixture's only variant link is
    a world's — so `test_a_constructed_location_variant_is_found` covers it.
    """
    entities = _materialized(project)
    exercised = set()
    for entity in entities.values():
        for path, _value, site in refmap.iter_references(entity["type"], entity["fields"]):
            exercised.add((entity["type"], site.path))
    declared = {(t, s.path) for t, group in refmap.SITES.items() for s in group}
    assert declared - exercised == {("location", "variant_of")}, sorted(declared - exercised)


def test_a_constructed_location_variant_is_found(project):
    """The one site the fixture never exercises: prove the walker sees it."""
    assert create_entity(
        project, "location", "the-gardens-shadow", {"name": "Shadow", "variant_of": "the-garden"}
    )
    found = refmap.iter_references("location", {"variant_of": "the-garden"})
    assert [p for p, _v, _s in found] == ["variant_of"]


# ─── the walker, on a real scene ───


def test_a_scene_reports_every_reference_with_a_concrete_path(project):
    """Paths name the entry a resolution belongs to, not the declaration's shape."""
    scene = _materialized(project)["central-room-day"]
    found = {(path, value) for path, value, _s in refmap.iter_references("scene", scene["fields"])}
    assert ("plot_roles[0].plot", "the-resistance") in found
    assert ("value_turns[0].value", "freedom") in found
    assert ("characters[0]", "kael") in found


def test_a_missing_or_empty_reference_is_not_reported():
    """An unfilled field is not a reference to resolve or drop."""
    assert refmap.iter_references("scene", {"location": "", "characters": []}) == []
    assert refmap.iter_references("scene", {}) == []
    assert refmap.iter_references("scene", {"plot_roles": "nonsense"}) == []


def test_a_keyed_site_reports_its_keys_as_the_references():
    found = refmap.iter_references(
        "relationship", {"characters": [], "perspectives": {"kael": {"label": "a"}, "mira": {}}}
    )
    assert [(p, v) for p, v, _s in found] == [
        ("perspectives.kael", "kael"),
        ("perspectives.mira", "mira"),
    ]


# ─── rewrite ───


def _scene():
    return {
        "sequence_id": "seq-discovery",
        "location": "the-central-room",
        "characters": ["kael", "mira"],
        "plot_roles": [
            {"plot": "the-resistance", "role": "inciting_incident", "description": "x"},
            {"plot": "the-scientists-last-stand", "role": "setup", "description": "y"},
        ],
        "value_turns": [
            {
                "plot": "the-resistance",
                "value": "freedom",
                "from": "free",
                "to": "dependent",
                "effects": [{"character": "kael", "levels": []}],
            }
        ],
    }


def test_rewrite_substitutes_every_reference_at_any_depth():
    out = refmap.rewrite("scene", _scene(), by_id={"kael": "kael-2"})
    assert out["characters"] == ["kael-2", "mira"]
    assert out["value_turns"][0]["effects"][0]["character"] == "kael-2"
    assert out["value_turns"][0]["plot"] == "the-resistance"


def test_rewrite_leaves_its_input_untouched():
    """The caller holds these items in a diff; changing them changes its plan."""
    fields = _scene()
    before = json.dumps(fields, sort_keys=True)
    refmap.rewrite("scene", fields, by_id={"kael": "kael-2"}, by_name={"freedom": "liberty"})
    assert json.dumps(fields, sort_keys=True) == before


def test_a_name_mapping_never_touches_an_id_site():
    """The two lookup spaces are separate: a name equal to an id is not a match."""
    fields = {"characters": ["freedom"], "value_turns": [{"plot": "p", "value": "freedom"}]}
    by_id = refmap.rewrite("scene", fields, by_id={"freedom": "X"})
    assert by_id["characters"] == ["X"]
    assert by_id["value_turns"][0]["value"] == "freedom"
    by_name = refmap.rewrite("scene", fields, by_name={"freedom": "Y"})
    assert by_name["characters"] == ["freedom"]
    assert by_name["value_turns"][0]["value"] == "Y"


def test_rewrite_renames_a_keyed_site():
    """`perspectives` holds its characters as KEYS, so renaming one renames a key."""
    fields = {"characters": ["kael", "mira"], "perspectives": {"kael": {"label": "a"}, "mira": {}}}
    out = refmap.rewrite("relationship", fields, by_id={"kael": "kael-2"})
    assert list(out["perspectives"]) == ["kael-2", "mira"]
    assert out["perspectives"]["kael-2"] == {"label": "a"}
    assert out["characters"] == ["kael-2", "mira"]


def test_rewrite_with_no_mapping_returns_the_same_content():
    fields = _scene()
    assert refmap.rewrite("scene", fields) == fields


def test_rewrite_reaches_the_fixture_scene(project):
    """End to end on real data: rename Kael and the scene's own fields follow."""
    scene = _materialized(project)["central-room-day"]["fields"]
    out = refmap.rewrite("scene", scene, by_id={"kael": "kael-2"})
    assert "kael-2" in out["characters"]
    assert "kael" not in out["characters"]
    for path, value, _site in refmap.iter_references("scene", out):
        assert value != "kael", path
