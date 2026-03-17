"""Integration tests for Blueprint MCP — all tests hit a real in-memory SQLite database."""

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


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


# --- Node creation ---


async def test_create_node_minimal(db: Database):
    """Create a node with only required fields, verify UUID and defaults."""
    node = await db.create_node(
        NodeCreateInput(name="API Service", type=NodeType.service)
    )
    assert len(node.id) == 36  # UUID format
    assert node.name == "API Service"
    assert node.type == NodeType.service
    assert node.status == NodeStatus.built  # default for register_node
    assert node.parent_id is None
    assert node.description is None
    assert node.metadata is None
    assert node.created_at != ""
    assert node.updated_at != ""

    # Read it back from DB and verify the values match
    fetched = await db.get_node(node.id)
    assert fetched is not None
    assert fetched.id == node.id
    assert fetched.name == "API Service"
    assert fetched.type == NodeType.service
    assert fetched.status == NodeStatus.built


async def test_create_node_full(db: Database):
    """Create a node with all fields, verify each one persists."""
    node = await db.create_node(
        NodeCreateInput(
            name="users",
            type=NodeType.table,
            status=NodeStatus.planned,
            description="User accounts table",
            metadata={"columns": [{"name": "id", "type": "UUID"}], "primary_key": "id"},
            source_file="src/models.py",
            source_line=42,
        )
    )
    fetched = await db.get_node(node.id)
    assert fetched.name == "users"
    assert fetched.type == NodeType.table
    assert fetched.status == NodeStatus.planned
    assert fetched.description == "User accounts table"
    assert fetched.metadata["primary_key"] == "id"
    assert fetched.metadata["columns"][0]["name"] == "id"
    assert fetched.source_file == "src/models.py"
    assert fetched.source_line == 42


# --- Node retrieval ---


async def test_get_node_not_found(db: Database):
    """Getting a non-existent node returns None."""
    result = await db.get_node("00000000-0000-0000-0000-000000000000")
    assert result is None


async def test_get_node_with_children(db: Database):
    """Create parent with 2 children, verify children are returned with depth=1."""
    parent = await db.create_node(
        NodeCreateInput(name="Database", type=NodeType.database)
    )
    child1 = await db.create_node(
        NodeCreateInput(name="users", type=NodeType.table, parent_id=parent.id)
    )
    child2 = await db.create_node(
        NodeCreateInput(name="orders", type=NodeType.table, parent_id=parent.id)
    )

    fetched = await db.get_node(parent.id, depth=1)
    assert fetched.children is not None
    assert len(fetched.children) == 2
    child_names = {c.name for c in fetched.children}
    assert child_names == {"users", "orders"}
    # Verify child IDs match
    child_ids = {c.id for c in fetched.children}
    assert child1.id in child_ids
    assert child2.id in child_ids


async def test_get_node_with_edges(db: Database):
    """Create 2 nodes with an edge, verify edges returned on get_node."""
    n1 = await db.create_node(
        NodeCreateInput(name="API", type=NodeType.service)
    )
    n2 = await db.create_node(
        NodeCreateInput(name="DB", type=NodeType.database)
    )
    edge = await db.create_edge(
        EdgeCreateInput(
            source_id=n1.id,
            target_id=n2.id,
            relationship=EdgeRelationship.connects_to,
            label="SQLAlchemy",
        )
    )

    fetched = await db.get_node(n1.id)
    assert fetched.edges is not None
    assert len(fetched.edges) == 1
    assert fetched.edges[0].id == edge.id
    assert fetched.edges[0].source_id == n1.id
    assert fetched.edges[0].target_id == n2.id
    assert fetched.edges[0].relationship == EdgeRelationship.connects_to
    assert fetched.edges[0].label == "SQLAlchemy"


# --- Node update ---


async def test_update_node_name(db: Database):
    """Update just the name, verify name changed and other fields untouched."""
    node = await db.create_node(
        NodeCreateInput(name="Old Name", type=NodeType.service, description="My service")
    )
    updated = await db.update_node(NodeUpdateInput(id=node.id, name="New Name"))

    assert updated.name == "New Name"
    assert updated.description == "My service"  # unchanged
    assert updated.type == NodeType.service  # unchanged

    # Read back from DB
    fetched = await db.get_node(node.id)
    assert fetched.name == "New Name"


async def test_update_node_status(db: Database):
    """Transition status from planned to built."""
    node = await db.create_node(
        NodeCreateInput(name="Auth", type=NodeType.module, status=NodeStatus.planned)
    )
    assert node.status == NodeStatus.planned

    updated = await db.update_node(
        NodeUpdateInput(id=node.id, status=NodeStatus.built)
    )
    assert updated.status == NodeStatus.built

    fetched = await db.get_node(node.id)
    assert fetched.status == NodeStatus.built


async def test_update_node_metadata_merge(db: Database):
    """Metadata update merges — original keys preserved, new keys added."""
    node = await db.create_node(
        NodeCreateInput(
            name="API",
            type=NodeType.service,
            metadata={"framework": "fastapi", "port": 8000},
        )
    )

    updated = await db.update_node(
        NodeUpdateInput(id=node.id, metadata={"version": "2.0", "port": 9000})
    )
    # Both old and new keys must exist
    assert updated.metadata["framework"] == "fastapi"  # preserved
    assert updated.metadata["version"] == "2.0"  # added
    assert updated.metadata["port"] == 9000  # overwritten

    # Read back from DB to be sure
    fetched = await db.get_node(node.id)
    assert fetched.metadata["framework"] == "fastapi"
    assert fetched.metadata["version"] == "2.0"
    assert fetched.metadata["port"] == 9000


async def test_update_node_not_found(db: Database):
    """Updating a non-existent node returns None."""
    result = await db.update_node(
        NodeUpdateInput(id="00000000-0000-0000-0000-000000000000", name="Ghost")
    )
    assert result is None


# --- Node deletion ---


async def test_delete_node(db: Database):
    """Delete a node, then verify it's gone from the DB."""
    node = await db.create_node(
        NodeCreateInput(name="Temp", type=NodeType.service)
    )
    deleted = await db.delete_node(node.id)
    assert deleted is True

    fetched = await db.get_node(node.id)
    assert fetched is None


async def test_delete_node_cascade_children(db: Database):
    """Delete parent → children must be gone from the database."""
    parent = await db.create_node(
        NodeCreateInput(name="System", type=NodeType.system)
    )
    child1 = await db.create_node(
        NodeCreateInput(name="Service A", type=NodeType.service, parent_id=parent.id)
    )
    child2 = await db.create_node(
        NodeCreateInput(name="Service B", type=NodeType.service, parent_id=parent.id)
    )
    grandchild = await db.create_node(
        NodeCreateInput(name="Route /api", type=NodeType.route, parent_id=child1.id)
    )

    # Delete the parent
    deleted = await db.delete_node(parent.id)
    assert deleted is True

    # SELECT each child and grandchild — all must be None
    assert await db.get_node(child1.id) is None
    assert await db.get_node(child2.id) is None
    assert await db.get_node(grandchild.id) is None

    # Also verify via raw SQL that no rows remain
    cursor = await db.db.execute(
        "SELECT COUNT(*) as cnt FROM nodes WHERE id IN (?, ?, ?, ?)",
        (parent.id, child1.id, child2.id, grandchild.id),
    )
    row = await cursor.fetchone()
    assert row["cnt"] == 0


async def test_delete_node_cascade_edges(db: Database):
    """Delete a node → its edges must be gone from the database."""
    n1 = await db.create_node(
        NodeCreateInput(name="API", type=NodeType.service)
    )
    n2 = await db.create_node(
        NodeCreateInput(name="DB", type=NodeType.database)
    )
    n3 = await db.create_node(
        NodeCreateInput(name="Cache", type=NodeType.cache)
    )
    edge1 = await db.create_edge(
        EdgeCreateInput(
            source_id=n1.id,
            target_id=n2.id,
            relationship=EdgeRelationship.connects_to,
        )
    )
    edge2 = await db.create_edge(
        EdgeCreateInput(
            source_id=n1.id,
            target_id=n3.id,
            relationship=EdgeRelationship.reads_from,
        )
    )

    # Delete n1 → both edges should be gone
    await db.delete_node(n1.id)

    assert await db.get_edge(edge1.id) is None
    assert await db.get_edge(edge2.id) is None

    # Raw SQL check: no edges referencing n1
    cursor = await db.db.execute(
        "SELECT COUNT(*) as cnt FROM edges WHERE source_id = ? OR target_id = ?",
        (n1.id, n1.id),
    )
    row = await cursor.fetchone()
    assert row["cnt"] == 0

    # n2 and n3 still exist
    assert (await db.get_node(n2.id)).name == "DB"
    assert (await db.get_node(n3.id)).name == "Cache"


async def test_delete_node_not_found(db: Database):
    """Deleting a non-existent node returns False."""
    result = await db.delete_node("00000000-0000-0000-0000-000000000000")
    assert result is False


# --- Edge creation ---


async def test_create_edge(db: Database):
    """Create an edge, verify all fields persist."""
    n1 = await db.create_node(
        NodeCreateInput(name="Frontend", type=NodeType.service)
    )
    n2 = await db.create_node(
        NodeCreateInput(name="API", type=NodeType.service)
    )
    edge = await db.create_edge(
        EdgeCreateInput(
            source_id=n1.id,
            target_id=n2.id,
            relationship=EdgeRelationship.calls,
            label="REST API",
            metadata={"protocol": "https"},
            status=EdgeStatus.active,
        )
    )

    assert len(edge.id) == 36
    assert edge.source_id == n1.id
    assert edge.target_id == n2.id
    assert edge.relationship == EdgeRelationship.calls
    assert edge.label == "REST API"
    assert edge.metadata == {"protocol": "https"}
    assert edge.status == EdgeStatus.active

    # Read back from DB
    fetched = await db.get_edge(edge.id)
    assert fetched.source_id == n1.id
    assert fetched.target_id == n2.id
    assert fetched.relationship == EdgeRelationship.calls
    assert fetched.label == "REST API"
    assert fetched.metadata["protocol"] == "https"


async def test_create_edge_invalid_source(db: Database):
    """Creating an edge with a non-existent source_id raises ValueError with meaningful message."""
    n2 = await db.create_node(
        NodeCreateInput(name="DB", type=NodeType.database)
    )
    with pytest.raises(ValueError, match="source node"):
        await db.create_edge(
            EdgeCreateInput(
                source_id="00000000-0000-0000-0000-000000000000",
                target_id=n2.id,
                relationship=EdgeRelationship.connects_to,
            )
        )


async def test_create_edge_invalid_target(db: Database):
    """Creating an edge with a non-existent target_id raises ValueError with meaningful message."""
    n1 = await db.create_node(
        NodeCreateInput(name="API", type=NodeType.service)
    )
    with pytest.raises(ValueError, match="target node"):
        await db.create_edge(
            EdgeCreateInput(
                source_id=n1.id,
                target_id="00000000-0000-0000-0000-000000000000",
                relationship=EdgeRelationship.connects_to,
            )
        )


# --- Edge deletion ---


async def test_delete_edge(db: Database):
    """Delete an edge, verify it's gone. Nodes still exist."""
    n1 = await db.create_node(
        NodeCreateInput(name="A", type=NodeType.service)
    )
    n2 = await db.create_node(
        NodeCreateInput(name="B", type=NodeType.service)
    )
    edge = await db.create_edge(
        EdgeCreateInput(
            source_id=n1.id,
            target_id=n2.id,
            relationship=EdgeRelationship.calls,
        )
    )

    deleted = await db.delete_edge(edge.id)
    assert deleted is True
    assert await db.get_edge(edge.id) is None

    # Nodes still exist
    assert (await db.get_node(n1.id)).name == "A"
    assert (await db.get_node(n2.id)).name == "B"


# --- Blueprint queries ---


async def test_get_blueprint_empty(db: Database):
    """Empty database returns empty lists and zero counts."""
    bp = await db.get_blueprint()
    assert bp["nodes"] == []
    assert bp["edges"] == []
    assert bp["summary"]["total_nodes"] == 0
    assert bp["summary"]["total_edges"] == 0


async def test_get_blueprint_full(db: Database):
    """Create nodes and edges, verify all are returned in the blueprint."""
    n1 = await db.create_node(
        NodeCreateInput(name="API", type=NodeType.service)
    )
    n2 = await db.create_node(
        NodeCreateInput(name="DB", type=NodeType.database)
    )
    n3 = await db.create_node(
        NodeCreateInput(name="Cache", type=NodeType.cache)
    )
    await db.create_edge(
        EdgeCreateInput(
            source_id=n1.id, target_id=n2.id, relationship=EdgeRelationship.connects_to
        )
    )
    await db.create_edge(
        EdgeCreateInput(
            source_id=n1.id, target_id=n3.id, relationship=EdgeRelationship.reads_from
        )
    )

    bp = await db.get_blueprint()
    assert bp["summary"]["total_nodes"] == 3
    assert bp["summary"]["total_edges"] == 2
    node_names = {n["name"] for n in bp["nodes"]}
    assert node_names == {"API", "DB", "Cache"}


async def test_get_blueprint_status_filter(db: Database):
    """Filter by status — only matching nodes returned, others excluded."""
    await db.create_node(
        NodeCreateInput(name="Built1", type=NodeType.service, status=NodeStatus.built)
    )
    await db.create_node(
        NodeCreateInput(name="Built2", type=NodeType.module, status=NodeStatus.built)
    )
    await db.create_node(
        NodeCreateInput(name="Planned1", type=NodeType.service, status=NodeStatus.planned)
    )
    await db.create_node(
        NodeCreateInput(name="Planned2", type=NodeType.route, status=NodeStatus.planned)
    )
    await db.create_node(
        NodeCreateInput(name="Broken1", type=NodeType.service, status=NodeStatus.broken)
    )

    bp = await db.get_blueprint(status_filter="built")
    names = {n["name"] for n in bp["nodes"]}
    assert names == {"Built1", "Built2"}
    assert "Planned1" not in names
    assert "Planned2" not in names
    assert "Broken1" not in names
    assert bp["summary"]["total_nodes"] == 2


async def test_get_blueprint_type_filter(db: Database):
    """Filter by type — only matching nodes returned, others excluded."""
    await db.create_node(
        NodeCreateInput(name="Svc1", type=NodeType.service)
    )
    await db.create_node(
        NodeCreateInput(name="Svc2", type=NodeType.service)
    )
    await db.create_node(
        NodeCreateInput(name="DB1", type=NodeType.database)
    )
    await db.create_node(
        NodeCreateInput(name="Tbl1", type=NodeType.table)
    )
    await db.create_node(
        NodeCreateInput(name="Route1", type=NodeType.route)
    )

    bp = await db.get_blueprint(type_filter="service")
    names = {n["name"] for n in bp["nodes"]}
    assert names == {"Svc1", "Svc2"}
    assert "DB1" not in names
    assert "Tbl1" not in names
    assert "Route1" not in names
    assert bp["summary"]["total_nodes"] == 2


async def test_get_blueprint_root_only(db: Database):
    """root_only=True returns only nodes with no parent."""
    parent = await db.create_node(
        NodeCreateInput(name="System", type=NodeType.system)
    )
    await db.create_node(
        NodeCreateInput(name="Child1", type=NodeType.service, parent_id=parent.id)
    )
    await db.create_node(
        NodeCreateInput(name="Child2", type=NodeType.database, parent_id=parent.id)
    )
    root2 = await db.create_node(
        NodeCreateInput(name="External", type=NodeType.external)
    )

    bp = await db.get_blueprint(root_only=True)
    names = {n["name"] for n in bp["nodes"]}
    assert names == {"System", "External"}
    assert "Child1" not in names
    assert "Child2" not in names
    assert bp["summary"]["total_nodes"] == 2


# --- Blueprint summary ---


async def test_get_blueprint_summary(db: Database):
    """Summary returns correct counts by type and status."""
    await db.create_node(
        NodeCreateInput(name="A", type=NodeType.service, status=NodeStatus.built)
    )
    await db.create_node(
        NodeCreateInput(name="B", type=NodeType.service, status=NodeStatus.built)
    )
    await db.create_node(
        NodeCreateInput(name="C", type=NodeType.database, status=NodeStatus.planned)
    )
    await db.create_node(
        NodeCreateInput(name="D", type=NodeType.table, status=NodeStatus.planned)
    )

    n1 = await db.create_node(
        NodeCreateInput(name="E", type=NodeType.route, status=NodeStatus.built)
    )
    n2 = await db.create_node(
        NodeCreateInput(name="F", type=NodeType.cache, status=NodeStatus.broken)
    )
    await db.create_edge(
        EdgeCreateInput(
            source_id=n1.id, target_id=n2.id, relationship=EdgeRelationship.reads_from
        )
    )

    summary = await db.get_blueprint_summary()
    assert summary["total_nodes"] == 6
    assert summary["total_edges"] == 1
    assert summary["counts_by_type"]["service"] == 2
    assert summary["counts_by_type"]["database"] == 1
    assert summary["counts_by_type"]["table"] == 1
    assert summary["counts_by_type"]["route"] == 1
    assert summary["counts_by_type"]["cache"] == 1
    assert summary["counts_by_status"]["built"] == 3
    assert summary["counts_by_status"]["planned"] == 2
    assert summary["counts_by_status"]["broken"] == 1
    assert len(summary["recent_changes"]) > 0


# --- Changelog ---


async def test_changelog_records_all_mutations(db: Database):
    """Every create/update/delete produces a changelog entry with correct action and details."""
    node = await db.create_node(
        NodeCreateInput(name="TestNode", type=NodeType.service)
    )
    await db.update_node(NodeUpdateInput(id=node.id, name="Renamed"))

    n2 = await db.create_node(
        NodeCreateInput(name="Other", type=NodeType.database)
    )
    edge = await db.create_edge(
        EdgeCreateInput(
            source_id=node.id,
            target_id=n2.id,
            relationship=EdgeRelationship.connects_to,
        )
    )
    await db.delete_edge(edge.id)
    await db.delete_node(node.id)

    # Query all changelog entries
    cursor = await db.db.execute("SELECT * FROM changelog ORDER BY id")
    rows = await cursor.fetchall()

    actions = [r["action"] for r in rows]
    assert "node_created" in actions
    assert "node_updated" in actions
    assert "edge_created" in actions
    assert "edge_deleted" in actions
    assert "node_deleted" in actions

    # Verify the node_created entry has the right details
    import json

    create_entry = next(r for r in rows if r["action"] == "node_created")
    details = json.loads(create_entry["details"])
    assert details["name"] == "TestNode"
    assert details["type"] == "service"


# --- Enum validation ---


async def test_invalid_node_type():
    """Pydantic rejects an invalid node type string."""
    with pytest.raises(Exception):
        NodeCreateInput(name="Bad", type="nonexistent_type")


async def test_invalid_edge_relationship():
    """Pydantic rejects an invalid relationship string."""
    with pytest.raises(Exception):
        EdgeCreateInput(
            source_id="a",
            target_id="b",
            relationship="nonexistent_relationship",
        )
