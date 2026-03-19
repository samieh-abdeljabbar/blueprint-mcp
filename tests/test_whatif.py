"""Tests for Phase C3 — what-if scenario simulation."""

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
from src.whatif import what_if


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


async def test_remove_with_dependents(db: Database):
    """Node B connected to A, C, D → what_if(B.id, 'remove') → directly_affected has 3 entries."""
    a = await db.create_node(NodeCreateInput(name="A", type=NodeType.service))
    b = await db.create_node(NodeCreateInput(name="B", type=NodeType.service))
    c = await db.create_node(NodeCreateInput(name="C", type=NodeType.service))
    d = await db.create_node(NodeCreateInput(name="D", type=NodeType.service))
    await db.create_edge(
        EdgeCreateInput(source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls)
    )
    await db.create_edge(
        EdgeCreateInput(source_id=b.id, target_id=c.id, relationship=EdgeRelationship.calls)
    )
    await db.create_edge(
        EdgeCreateInput(source_id=b.id, target_id=d.id, relationship=EdgeRelationship.calls)
    )
    result = await what_if(db, b.id, "remove")
    assert len(result["directly_affected"]) == 3
    affected_names = {d["node_name"] for d in result["directly_affected"]}
    assert "A" in affected_names
    assert "C" in affected_names
    assert "D" in affected_names


async def test_break_with_error_handler(db: Database):
    """A→B + A→ErrorHandler → what_if(B.id, 'break') → A has error handling."""
    a = await db.create_node(NodeCreateInput(name="A", type=NodeType.service))
    b = await db.create_node(NodeCreateInput(name="B", type=NodeType.service))
    error_handler = await db.create_node(
        NodeCreateInput(name="ErrorHandler", type=NodeType.service)
    )
    await db.create_edge(
        EdgeCreateInput(source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls)
    )
    await db.create_edge(
        EdgeCreateInput(
            source_id=a.id, target_id=error_handler.id, relationship=EdgeRelationship.calls
        )
    )
    result = await what_if(db, b.id, "break")
    # Find A in directly_affected
    a_entry = next(
        (d for d in result["directly_affected"] if d["node_name"] == "A"), None
    )
    assert a_entry is not None
    # Check it has error handling — either via has_error_handling field or impact text
    has_handling = a_entry.get("has_error_handling", False) or "Has error handling" in a_entry.get("impact", "")
    assert has_handling


async def test_break_without_handler(db: Database):
    """A→B (no error handling) → what_if(B.id, 'break') → A mentions NO error handling."""
    a = await db.create_node(NodeCreateInput(name="A", type=NodeType.service))
    b = await db.create_node(NodeCreateInput(name="B", type=NodeType.service))
    await db.create_edge(
        EdgeCreateInput(source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls)
    )
    result = await what_if(db, b.id, "break")
    a_entry = next(
        (d for d in result["directly_affected"] if d["node_name"] == "A"), None
    )
    assert a_entry is not None
    no_handling = (
        a_entry.get("has_error_handling") is False
        or "NO error handling" in a_entry.get("impact", "")
    )
    assert no_handling


async def test_disconnect_orphans(db: Database):
    """A→B→C (linear) → what_if(B.id, 'disconnect') → C becomes unreachable."""
    a = await db.create_node(NodeCreateInput(name="A", type=NodeType.service))
    b = await db.create_node(NodeCreateInput(name="B", type=NodeType.service))
    c = await db.create_node(NodeCreateInput(name="C", type=NodeType.service))
    await db.create_edge(
        EdgeCreateInput(source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls)
    )
    await db.create_edge(
        EdgeCreateInput(source_id=b.id, target_id=c.id, relationship=EdgeRelationship.calls)
    )
    result = await what_if(db, b.id, "disconnect")
    affected_names = {d["node_name"] for d in result["directly_affected"]}
    assert "C" in affected_names


async def test_overload_with_cache(db: Database):
    """Service→cache edge + service as target → what_if(service.id, 'overload') → resilience_score > 0."""
    svc = await db.create_node(
        NodeCreateInput(name="APIService", type=NodeType.service)
    )
    cache = await db.create_node(
        NodeCreateInput(name="Redis", type=NodeType.cache)
    )
    await db.create_edge(
        EdgeCreateInput(
            source_id=svc.id, target_id=cache.id, relationship=EdgeRelationship.connects_to
        )
    )
    result = await what_if(db, svc.id, "overload")
    assert result["resilience_score"] > 0
