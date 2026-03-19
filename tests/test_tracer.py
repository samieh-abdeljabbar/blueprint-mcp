"""Tests for Phase C1 + C2 — entry points and flow tracing."""

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
from src.tracer import list_entry_points, trace_flow


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


# --- Entry point tests ---


async def test_entry_points_route(db: Database):
    """A route node appears in entry_points."""
    route = await db.create_node(
        NodeCreateInput(name="GET /users", type=NodeType.route)
    )
    result = await list_entry_points(db)
    ep_ids = {ep["node_id"] for ep in result["entry_points"]}
    assert route.id in ep_ids


async def test_entry_points_api(db: Database):
    """An API node appears in entry_points."""
    api = await db.create_node(
        NodeCreateInput(name="REST API", type=NodeType.api)
    )
    result = await list_entry_points(db)
    ep_ids = {ep["node_id"] for ep in result["entry_points"]}
    assert api.id in ep_ids


async def test_entry_points_root_outgoing(db: Database):
    """Service with only outgoing edges (no incoming, no parent) → entry point."""
    svc = await db.create_node(
        NodeCreateInput(name="Gateway", type=NodeType.service)
    )
    target = await db.create_node(
        NodeCreateInput(name="Backend", type=NodeType.service)
    )
    await db.create_edge(
        EdgeCreateInput(
            source_id=svc.id, target_id=target.id, relationship=EdgeRelationship.calls
        )
    )
    result = await list_entry_points(db)
    ep_ids = {ep["node_id"] for ep in result["entry_points"]}
    assert svc.id in ep_ids


# --- Flow trace tests ---


async def test_linear_flow(db: Database):
    """A→B→C→D (calls edges) → 4 steps in order."""
    a = await db.create_node(NodeCreateInput(name="A", type=NodeType.route))
    b = await db.create_node(NodeCreateInput(name="B", type=NodeType.service))
    c = await db.create_node(NodeCreateInput(name="C", type=NodeType.service))
    d = await db.create_node(NodeCreateInput(name="D", type=NodeType.database))
    await db.create_edge(
        EdgeCreateInput(source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls)
    )
    await db.create_edge(
        EdgeCreateInput(source_id=b.id, target_id=c.id, relationship=EdgeRelationship.calls)
    )
    await db.create_edge(
        EdgeCreateInput(source_id=c.id, target_id=d.id, relationship=EdgeRelationship.calls)
    )
    result = await trace_flow(db, a.id)
    assert result["total_steps"] == 4
    step_names = [s["node_name"] for s in result["steps"]]
    assert step_names == ["A", "B", "C", "D"]


async def test_branch_detection(db: Database):
    """A→B, A→C → branch detected (total_branches >= 1)."""
    a = await db.create_node(NodeCreateInput(name="A", type=NodeType.route))
    b = await db.create_node(NodeCreateInput(name="B", type=NodeType.service))
    c = await db.create_node(NodeCreateInput(name="C", type=NodeType.service))
    await db.create_edge(
        EdgeCreateInput(source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls)
    )
    await db.create_edge(
        EdgeCreateInput(source_id=a.id, target_id=c.id, relationship=EdgeRelationship.calls)
    )
    result = await trace_flow(db, a.id)
    assert result["total_branches"] >= 1


async def test_dead_end(db: Database):
    """A→B (B has no outgoing, B is a service type not terminal) → dead_ends includes B's name."""
    a = await db.create_node(NodeCreateInput(name="A", type=NodeType.route))
    b = await db.create_node(NodeCreateInput(name="B", type=NodeType.service))
    await db.create_edge(
        EdgeCreateInput(source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls)
    )
    result = await trace_flow(db, a.id)
    assert "B" in result["dead_ends"]


async def test_circular_stops(db: Database):
    """A→B→A → cycle detected (one step has is_cycle=True), doesn't hang."""
    a = await db.create_node(NodeCreateInput(name="A", type=NodeType.service))
    b = await db.create_node(NodeCreateInput(name="B", type=NodeType.service))
    await db.create_edge(
        EdgeCreateInput(source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls)
    )
    await db.create_edge(
        EdgeCreateInput(source_id=b.id, target_id=a.id, relationship=EdgeRelationship.calls)
    )
    result = await trace_flow(db, a.id)
    cycle_steps = [s for s in result["steps"] if s["is_cycle"]]
    assert len(cycle_steps) >= 1


async def test_unprotected_write_gap(db: Database):
    """Route→Table with writes_to, no auth edge → gap of type UNPROTECTED_WRITE."""
    route = await db.create_node(
        NodeCreateInput(name="POST /orders", type=NodeType.route)
    )
    table = await db.create_node(
        NodeCreateInput(name="orders", type=NodeType.table)
    )
    await db.create_edge(
        EdgeCreateInput(
            source_id=route.id, target_id=table.id, relationship=EdgeRelationship.writes_to
        )
    )
    result = await trace_flow(db, route.id)
    all_gaps = []
    for s in result["steps"]:
        all_gaps.extend(s["gaps"])
    gap_types = [g["type"] for g in all_gaps]
    assert "UNPROTECTED_WRITE" in gap_types


async def test_protected_write_no_gap(db: Database):
    """Route→Table with writes_to + auth node authenticates route → no UNPROTECTED_WRITE gap."""
    auth = await db.create_node(
        NodeCreateInput(name="Auth", type=NodeType.middleware)
    )
    route = await db.create_node(
        NodeCreateInput(name="POST /orders", type=NodeType.route)
    )
    table = await db.create_node(
        NodeCreateInput(name="orders", type=NodeType.table)
    )
    await db.create_edge(
        EdgeCreateInput(
            source_id=auth.id, target_id=route.id, relationship=EdgeRelationship.authenticates
        )
    )
    await db.create_edge(
        EdgeCreateInput(
            source_id=route.id, target_id=table.id, relationship=EdgeRelationship.writes_to
        )
    )
    result = await trace_flow(db, route.id)
    all_gaps = []
    for s in result["steps"]:
        all_gaps.extend(s["gaps"])
    gap_types = [g["type"] for g in all_gaps]
    assert "UNPROTECTED_WRITE" not in gap_types


async def test_no_fallback_gap(db: Database):
    """Service→External (calls edge), no fallback → gap of type NO_FALLBACK."""
    svc = await db.create_node(
        NodeCreateInput(name="PaymentService", type=NodeType.service)
    )
    ext = await db.create_node(
        NodeCreateInput(name="Stripe", type=NodeType.external)
    )
    await db.create_edge(
        EdgeCreateInput(
            source_id=svc.id, target_id=ext.id, relationship=EdgeRelationship.calls
        )
    )
    result = await trace_flow(db, svc.id)
    all_gaps = []
    for s in result["steps"]:
        all_gaps.extend(s["gaps"])
    gap_types = [g["type"] for g in all_gaps]
    assert "NO_FALLBACK" in gap_types


async def test_max_depth_limit(db: Database):
    """A→B→C→D, max_depth=2 → at most 2-3 steps (stops early)."""
    a = await db.create_node(NodeCreateInput(name="A", type=NodeType.route))
    b = await db.create_node(NodeCreateInput(name="B", type=NodeType.service))
    c = await db.create_node(NodeCreateInput(name="C", type=NodeType.service))
    d = await db.create_node(NodeCreateInput(name="D", type=NodeType.database))
    await db.create_edge(
        EdgeCreateInput(source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls)
    )
    await db.create_edge(
        EdgeCreateInput(source_id=b.id, target_id=c.id, relationship=EdgeRelationship.calls)
    )
    await db.create_edge(
        EdgeCreateInput(source_id=c.id, target_id=d.id, relationship=EdgeRelationship.calls)
    )
    result = await trace_flow(db, a.id, max_depth=2)
    assert result["total_steps"] <= 3
