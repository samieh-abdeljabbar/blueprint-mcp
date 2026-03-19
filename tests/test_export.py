"""Tests for Phase E2 — Mermaid and Markdown export."""

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
from src.export import export_mermaid, export_markdown


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


async def test_mermaid_contains_nodes(db: Database):
    """3 nodes + 2 edges → export_mermaid → content contains all 3 names, starts with 'graph TD'."""
    a = await db.create_node(NodeCreateInput(name="Frontend", type=NodeType.service))
    b = await db.create_node(NodeCreateInput(name="Backend", type=NodeType.service))
    c = await db.create_node(NodeCreateInput(name="Database", type=NodeType.database))
    await db.create_edge(
        EdgeCreateInput(source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls)
    )
    await db.create_edge(
        EdgeCreateInput(source_id=b.id, target_id=c.id, relationship=EdgeRelationship.connects_to)
    )
    result = await export_mermaid(db)
    content = result["content"]
    assert content.startswith("graph TD")
    assert "Frontend" in content
    assert "Backend" in content
    assert "Database" in content


async def test_markdown_contains_nodes(db: Database):
    """3 nodes + 2 edges → export_markdown → content contains all 3 names and 'Architecture Blueprint'."""
    a = await db.create_node(NodeCreateInput(name="Frontend", type=NodeType.service))
    b = await db.create_node(NodeCreateInput(name="Backend", type=NodeType.service))
    c = await db.create_node(NodeCreateInput(name="Database", type=NodeType.database))
    await db.create_edge(
        EdgeCreateInput(source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls)
    )
    await db.create_edge(
        EdgeCreateInput(source_id=b.id, target_id=c.id, relationship=EdgeRelationship.connects_to)
    )
    result = await export_markdown(db)
    content = result["content"]
    assert "Architecture Blueprint" in content
    assert "Frontend" in content
    assert "Backend" in content
    assert "Database" in content


async def test_scoped_export(db: Database):
    """Parent with 2 children + unrelated node → scoped export contains children, NOT unrelated."""
    parent = await db.create_node(
        NodeCreateInput(name="PaymentSystem", type=NodeType.system)
    )
    child1 = await db.create_node(
        NodeCreateInput(name="PayGateway", type=NodeType.service, parent_id=parent.id)
    )
    child2 = await db.create_node(
        NodeCreateInput(name="PayDB", type=NodeType.database, parent_id=parent.id)
    )
    unrelated = await db.create_node(
        NodeCreateInput(name="TotallyUnrelatedThing", type=NodeType.service)
    )
    result = await export_mermaid(db, scope=parent.id)
    content = result["content"]
    assert "PaymentSystem" in content
    assert "PayGateway" in content
    assert "PayDB" in content
    assert "TotallyUnrelatedThing" not in content
