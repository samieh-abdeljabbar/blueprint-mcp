"""Integration tests for Blueprint MCP template system."""

import json
from pathlib import Path

import pytest

from src.db import Database
from src.templates.registry import (
    _validate_template,
    apply_template,
    get_templates,
    list_templates,
)
from src.models import Template


TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "templates"


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


# --- Template loading ---


def test_templates_dir_has_at_least_6_json_files():
    json_files = list(TEMPLATE_DIR.glob("*.json"))
    assert len(json_files) >= 6


def test_all_templates_load_without_error():
    templates = get_templates()
    assert len(templates) >= 6
    for t in templates.values():
        assert t.nodes
        assert t.edges
        assert t.display_name
        assert t.description


def test_every_template_has_at_least_one_root_node():
    for t in get_templates().values():
        root_nodes = [n for n in t.nodes if n.parent_ref is None]
        assert len(root_nodes) >= 1, f"Template '{t.name}' has no root node"


def test_every_template_has_unique_refs():
    for t in get_templates().values():
        refs = [n.ref for n in t.nodes]
        assert len(refs) == len(set(refs)), f"Template '{t.name}' has duplicate refs"


def test_every_template_parent_refs_are_valid():
    for t in get_templates().values():
        ref_set = {n.ref for n in t.nodes}
        for n in t.nodes:
            if n.parent_ref is not None:
                assert n.parent_ref in ref_set, (
                    f"Template '{t.name}': invalid parent_ref '{n.parent_ref}'"
                )


def test_every_template_edge_refs_are_valid():
    for t in get_templates().values():
        ref_set = {n.ref for n in t.nodes}
        for e in t.edges:
            assert e.source_ref in ref_set, (
                f"Template '{t.name}': invalid edge source_ref '{e.source_ref}'"
            )
            assert e.target_ref in ref_set, (
                f"Template '{t.name}': invalid edge target_ref '{e.target_ref}'"
            )


def test_parents_listed_before_children_in_every_template():
    for t in get_templates().values():
        refs_seen = []
        for n in t.nodes:
            if n.parent_ref is not None:
                assert n.parent_ref in refs_seen, (
                    f"Template '{t.name}': parent '{n.parent_ref}' not listed before child '{n.ref}'"
                )
            refs_seen.append(n.ref)


# --- list_templates ---


def test_list_templates_returns_expected_keys():
    result = list_templates()
    assert isinstance(result, list)
    assert len(result) >= 6
    for item in result:
        assert "name" in item
        assert "display_name" in item
        assert "description" in item
        assert "node_count" in item
        assert "edge_count" in item
        assert "node_types" in item


def test_list_templates_includes_all_known_names():
    result = list_templates()
    names = {t["name"] for t in result}
    expected = {"saas", "api_service", "fullstack", "data_pipeline", "desktop_app", "multi_entity_business"}
    assert expected.issubset(names)


# --- apply_template ---


async def test_apply_creates_correct_number_of_nodes(db: Database):
    result = await apply_template(db, "saas", "TestSaaS")
    assert result["nodes_created"] == 12
    blueprint = await db.get_blueprint()
    assert blueprint["summary"]["total_nodes"] == 12


async def test_apply_all_nodes_have_status_planned(db: Database):
    await apply_template(db, "saas", "TestSaaS")
    blueprint = await db.get_blueprint()
    for node in blueprint["nodes"]:
        assert node["status"] == "planned"


async def test_apply_all_nodes_have_template_origin(db: Database):
    result = await apply_template(db, "saas", "TestSaaS")
    ref_map = result["ref_map"]
    for ref, node_id in ref_map.items():
        node = await db.get_node(node_id, depth=0)
        assert node.template_origin == "saas"


async def test_apply_project_name_substituted_in_root(db: Database):
    await apply_template(db, "saas", "My Cool App")
    blueprint = await db.get_blueprint(root_only=True)
    root_names = [n["name"] for n in blueprint["nodes"] if n["parent_id"] is None]
    assert "My Cool App" in root_names


async def test_apply_parent_ids_resolved(db: Database):
    result = await apply_template(db, "api_service", "TestAPI")
    ref_map = result["ref_map"]
    templates = get_templates()
    t = templates["api_service"]
    for node_def in t.nodes:
        if node_def.parent_ref is not None:
            node = await db.get_node(ref_map[node_def.ref], depth=0)
            assert node.parent_id == ref_map[node_def.parent_ref]


async def test_apply_edges_created_with_correct_uuids(db: Database):
    result = await apply_template(db, "api_service", "TestAPI")
    ref_map = result["ref_map"]
    blueprint = await db.get_blueprint()
    edge_pairs = {(e["source_id"], e["target_id"]) for e in blueprint["edges"]}
    # api -> database edge should exist
    assert (ref_map["api"], ref_map["database"]) in edge_pairs


async def test_apply_all_edges_have_status_planned(db: Database):
    await apply_template(db, "saas", "TestSaaS")
    blueprint = await db.get_blueprint()
    for edge in blueprint["edges"]:
        assert edge["status"] == "planned"


async def test_apply_template_not_found():
    db = Database(":memory:")
    await db.connect()
    try:
        with pytest.raises(ValueError, match="not found"):
            await apply_template(db, "nonexistent_template", "Test")
    finally:
        await db.close()


async def test_apply_changelog_has_template_applied_entry(db: Database):
    await apply_template(db, "saas", "TestSaaS")
    summary = await db.get_blueprint_summary()
    actions = [c["action"] for c in summary["recent_changes"]]
    assert "template_applied" in actions
    # Find the entry and check details
    template_entry = next(c for c in summary["recent_changes"] if c["action"] == "template_applied")
    assert template_entry["details"]["template"] == "saas"
    assert template_entry["details"]["project_name"] == "TestSaaS"


async def test_apply_multi_entity_business(db: Database):
    result = await apply_template(db, "multi_entity_business", "Acme Corp")
    assert result["nodes_created"] == 22
    assert result["edges_created"] == 17
    # Root node named correctly
    blueprint = await db.get_blueprint(root_only=True)
    root_names = [n["name"] for n in blueprint["nodes"] if n["parent_id"] is None]
    assert "Acme Corp" in root_names


async def test_two_templates_applied_to_same_db(db: Database):
    r1 = await apply_template(db, "saas", "SaaS App")
    r2 = await apply_template(db, "api_service", "API Svc")
    blueprint = await db.get_blueprint()
    assert blueprint["summary"]["total_nodes"] == r1["nodes_created"] + r2["nodes_created"]
    assert blueprint["summary"]["total_edges"] == r1["edges_created"] + r2["edges_created"]


# --- Validation ---


def test_validate_duplicate_refs_raises():
    data = {
        "name": "bad",
        "display_name": "Bad",
        "description": "Bad template",
        "nodes": [
            {"ref": "a", "name": "A", "type": "system"},
            {"ref": "a", "name": "B", "type": "service"},
        ],
        "edges": [],
    }
    t = Template(**data)
    with pytest.raises(ValueError, match="duplicate ref"):
        _validate_template(t)


def test_validate_invalid_parent_ref_raises():
    data = {
        "name": "bad",
        "display_name": "Bad",
        "description": "Bad template",
        "nodes": [
            {"ref": "a", "name": "A", "type": "system"},
            {"ref": "b", "name": "B", "type": "service", "parent_ref": "nonexistent"},
        ],
        "edges": [],
    }
    t = Template(**data)
    with pytest.raises(ValueError, match="invalid parent_ref"):
        _validate_template(t)


def test_validate_invalid_edge_ref_raises():
    data = {
        "name": "bad",
        "display_name": "Bad",
        "description": "Bad template",
        "nodes": [
            {"ref": "a", "name": "A", "type": "system"},
        ],
        "edges": [
            {"source_ref": "a", "target_ref": "nonexistent", "relationship": "calls"},
        ],
    }
    t = Template(**data)
    with pytest.raises(ValueError, match="invalid edge target_ref"):
        _validate_template(t)
