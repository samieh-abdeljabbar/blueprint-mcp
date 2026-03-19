"""Tests for Phase E1 — snapshot management."""

import pytest

from src.db import Database
from src.models import (
    EdgeCreateInput,
    EdgeRelationship,
    EdgeStatus,
    NodeCreateInput,
    NodeStatus,
    NodeType,
    NodeUpdateInput,
)
from src.snapshots import snapshot_blueprint, list_snapshots, compare_snapshots, restore_snapshot


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


async def test_snapshot_and_compare_additions(db: Database):
    """Create node A → snapshot → create node B → compare → diff shows B as added."""
    a = await db.create_node(
        NodeCreateInput(name="ServiceA", type=NodeType.service)
    )
    snap = await snapshot_blueprint(db, "before-B")
    b = await db.create_node(
        NodeCreateInput(name="ServiceB", type=NodeType.service)
    )
    diff = await compare_snapshots(db, snap["id"])
    added_names = {n["name"] for n in diff["nodes"]["added"]}
    assert "ServiceB" in added_names
    assert diff["summary"]["nodes_added"] >= 1


async def test_snapshot_and_compare_removals(db: Database):
    """Create A and B → snapshot → delete B → compare → diff shows B as removed."""
    a = await db.create_node(
        NodeCreateInput(name="ServiceA", type=NodeType.service)
    )
    b = await db.create_node(
        NodeCreateInput(name="ServiceB", type=NodeType.service)
    )
    snap = await snapshot_blueprint(db, "with-B")
    await db.delete_node(b.id)
    diff = await compare_snapshots(db, snap["id"])
    removed_names = {n["name"] for n in diff["nodes"]["removed"]}
    assert "ServiceB" in removed_names
    assert diff["summary"]["nodes_removed"] >= 1


async def test_snapshot_and_compare_changes(db: Database):
    """Create A with status=planned → snapshot → update to built → compare → shows status changed."""
    a = await db.create_node(
        NodeCreateInput(name="FeatureX", type=NodeType.service, status=NodeStatus.planned)
    )
    snap = await snapshot_blueprint(db, "planned-state")
    await db.update_node(NodeUpdateInput(id=a.id, status=NodeStatus.built))
    diff = await compare_snapshots(db, snap["id"])
    assert diff["summary"]["nodes_changed"] >= 1
    # Find the change for FeatureX
    changed = next(
        (c for c in diff["nodes"]["changed"] if c["name"] == "FeatureX"), None
    )
    assert changed is not None
    field_changes = {ch["field"]: ch for ch in changed["changes"]}
    assert "status" in field_changes
    assert field_changes["status"]["old"] == "planned"
    assert field_changes["status"]["new"] == "built"


async def test_list_snapshots_count(db: Database):
    """Create 3 snapshots → list_snapshots → total=3."""
    await snapshot_blueprint(db, "snap-1")
    await snapshot_blueprint(db, "snap-2")
    await snapshot_blueprint(db, "snap-3")
    result = await list_snapshots(db)
    assert result["total"] == 3
    assert len(result["snapshots"]) == 3


async def test_restore_snapshot_full_cycle(db: Database):
    """Create 2 nodes + 1 edge → snapshot → delete all → restore → verify original IDs preserved."""
    a = await db.create_node(
        NodeCreateInput(name="Alpha", type=NodeType.service)
    )
    b = await db.create_node(
        NodeCreateInput(name="Beta", type=NodeType.database)
    )
    edge = await db.create_edge(
        EdgeCreateInput(
            source_id=a.id,
            target_id=b.id,
            relationship=EdgeRelationship.connects_to,
        )
    )
    snap = await snapshot_blueprint(db, "full-state")

    # Delete all nodes (edges cascade)
    await db.delete_node(a.id)
    await db.delete_node(b.id)

    # Verify they're gone
    assert await db.get_node(a.id) is None
    assert await db.get_node(b.id) is None

    # Restore
    result = await restore_snapshot(db, snap["id"], confirm=True)
    assert result["restored"] is True
    assert result["snapshot_name"] == "full-state"
    assert result["node_count"] == 2
    assert result["edge_count"] == 1

    # Verify original IDs are preserved
    restored_a = await db.get_node(a.id)
    assert restored_a is not None
    assert restored_a.name == "Alpha"

    restored_b = await db.get_node(b.id)
    assert restored_b is not None
    assert restored_b.name == "Beta"


async def test_restore_snapshot_requires_confirm(db: Database):
    """Call restore_snapshot with confirm=False → error returned and node still exists."""
    a = await db.create_node(
        NodeCreateInput(name="Gamma", type=NodeType.service)
    )
    snap = await snapshot_blueprint(db, "confirm-test")

    result = await restore_snapshot(db, snap["id"], confirm=False)
    assert "error" in result
    assert "confirm=True" in result["error"]

    # Node should still exist (nothing was deleted)
    still_there = await db.get_node(a.id)
    assert still_there is not None
    assert still_there.name == "Gamma"
