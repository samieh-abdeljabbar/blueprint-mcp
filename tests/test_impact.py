"""Tests for Phase B3 — impact analysis."""

import pytest

from src.db import Database
from src.models import (
    EdgeCreateInput,
    EdgeRelationship,
    NodeCreateInput,
    NodeType,
)
from src.impact import impact_analysis


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


async def test_linear_chain(db: Database):
    """A→B→C (calls edges) → impact from A → B at depth 1, C at depth 2, total_affected=2."""
    a = await db.create_node(NodeCreateInput(name="A", type=NodeType.service))
    b = await db.create_node(NodeCreateInput(name="B", type=NodeType.service))
    c = await db.create_node(NodeCreateInput(name="C", type=NodeType.service))
    await db.create_edge(
        EdgeCreateInput(source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls)
    )
    await db.create_edge(
        EdgeCreateInput(source_id=b.id, target_id=c.id, relationship=EdgeRelationship.calls)
    )
    result = await impact_analysis(db, a.id)
    assert result["total_affected"] == 2
    # B at depth 1
    depth1_names = [n["node_name"] for n in result["impact_chain"][0]["nodes"]]
    assert "B" in depth1_names
    # C at depth 2
    depth2_names = [n["node_name"] for n in result["impact_chain"][1]["nodes"]]
    assert "C" in depth2_names


async def test_fan_out(db: Database):
    """A→B, A→C, A→D → all three at depth 1, total_affected=3."""
    a = await db.create_node(NodeCreateInput(name="A", type=NodeType.service))
    b = await db.create_node(NodeCreateInput(name="B", type=NodeType.service))
    c = await db.create_node(NodeCreateInput(name="C", type=NodeType.service))
    d = await db.create_node(NodeCreateInput(name="D", type=NodeType.service))
    for target in [b, c, d]:
        await db.create_edge(
            EdgeCreateInput(
                source_id=a.id, target_id=target.id, relationship=EdgeRelationship.calls
            )
        )
    result = await impact_analysis(db, a.id)
    assert result["total_affected"] == 3
    depth1_names = {n["node_name"] for n in result["impact_chain"][0]["nodes"]}
    assert depth1_names == {"B", "C", "D"}


async def test_circular_no_infinite_loop(db: Database):
    """A→B→A (circular) → returns without hanging, total_affected=1."""
    a = await db.create_node(NodeCreateInput(name="A", type=NodeType.service))
    b = await db.create_node(NodeCreateInput(name="B", type=NodeType.service))
    await db.create_edge(
        EdgeCreateInput(source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls)
    )
    await db.create_edge(
        EdgeCreateInput(source_id=b.id, target_id=a.id, relationship=EdgeRelationship.calls)
    )
    result = await impact_analysis(db, a.id)
    assert result["total_affected"] == 1  # Only B (A is source, not counted)


async def test_upstream(db: Database):
    """C←B←A, direction='upstream' from C → finds B and A."""
    a = await db.create_node(NodeCreateInput(name="A", type=NodeType.service))
    b = await db.create_node(NodeCreateInput(name="B", type=NodeType.service))
    c = await db.create_node(NodeCreateInput(name="C", type=NodeType.service))
    await db.create_edge(
        EdgeCreateInput(source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls)
    )
    await db.create_edge(
        EdgeCreateInput(source_id=b.id, target_id=c.id, relationship=EdgeRelationship.calls)
    )
    result = await impact_analysis(db, c.id, direction="upstream")
    assert result["total_affected"] == 2
    all_names = set()
    for level in result["impact_chain"]:
        for n in level["nodes"]:
            all_names.add(n["node_name"])
    assert "A" in all_names
    assert "B" in all_names


async def test_isolated_node(db: Database):
    """Single node, no edges → total_affected=0."""
    a = await db.create_node(NodeCreateInput(name="Lone", type=NodeType.service))
    result = await impact_analysis(db, a.id)
    assert result["total_affected"] == 0
    assert result["impact_chain"] == []


async def test_depth_limit(db: Database):
    """A→B→C→D, depth=1 → only B found, total_affected=1."""
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
        EdgeCreateInput(source_id=c.id, target_id=d.id, relationship=EdgeRelationship.calls)
    )
    result = await impact_analysis(db, a.id, depth=1)
    assert result["total_affected"] == 1
    all_names = set()
    for level in result["impact_chain"]:
        for n in level["nodes"]:
            all_names.add(n["node_name"])
    assert "B" in all_names
    assert "C" not in all_names
    assert "D" not in all_names


async def test_direction_both(db: Database):
    """A→B→C with X→A → direction='both' from A → finds B, C downstream and X upstream."""
    x = await db.create_node(NodeCreateInput(name="X", type=NodeType.service))
    a = await db.create_node(NodeCreateInput(name="A", type=NodeType.service))
    b = await db.create_node(NodeCreateInput(name="B", type=NodeType.service))
    c = await db.create_node(NodeCreateInput(name="C", type=NodeType.service))
    await db.create_edge(
        EdgeCreateInput(source_id=x.id, target_id=a.id, relationship=EdgeRelationship.calls)
    )
    await db.create_edge(
        EdgeCreateInput(source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls)
    )
    await db.create_edge(
        EdgeCreateInput(source_id=b.id, target_id=c.id, relationship=EdgeRelationship.calls)
    )
    result = await impact_analysis(db, a.id, direction="both")
    all_names = set()
    for level in result["impact_chain"]:
        for n in level["nodes"]:
            all_names.add(n["node_name"])
    assert "B" in all_names
    assert "C" in all_names
    assert "X" in all_names
