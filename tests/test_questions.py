"""Tests for Phase B1 — project questions (gap detection)."""

import pytest

from src.db import Database
from src.models import (
    EdgeCreateInput,
    EdgeRelationship,
    NodeCreateInput,
    NodeType,
)
from src.questions import get_project_questions


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


async def test_no_auth_critical(db: Database):
    """No auth nodes at all → returns at least one critical question about auth."""
    await db.create_node(
        NodeCreateInput(name="GET /users", type=NodeType.route)
    )
    result = await get_project_questions(db)
    critical_qs = [
        q for q in result["questions"]
        if q["severity"] == "critical" and "auth" in q["question"].lower()
    ]
    assert len(critical_qs) >= 1


async def test_route_without_auth_warning(db: Database):
    """Auth middleware exists but route has no authenticates edge → warning."""
    auth = await db.create_node(
        NodeCreateInput(name="Auth Middleware", type=NodeType.middleware)
    )
    route = await db.create_node(
        NodeCreateInput(name="GET /admin", type=NodeType.route)
    )
    # No authenticates edge between them
    result = await get_project_questions(db)
    warning_qs = [
        q for q in result["questions"]
        if q["severity"] == "warning" and route.name in q["question"]
    ]
    assert len(warning_qs) >= 1


async def test_no_database_critical(db: Database):
    """Service exists but no database → critical question about data storage."""
    await db.create_node(
        NodeCreateInput(name="UserService", type=NodeType.service)
    )
    result = await get_project_questions(db)
    critical_qs = [
        q for q in result["questions"]
        if q["severity"] == "critical" and "data" in q["question"].lower()
    ]
    assert len(critical_qs) >= 1


async def test_table_no_writers(db: Database):
    """Table with no writes_to edges → question naming the table."""
    db_node = await db.create_node(
        NodeCreateInput(name="PostgreSQL", type=NodeType.database)
    )
    table = await db.create_node(
        NodeCreateInput(name="orders", type=NodeType.table, parent_id=db_node.id)
    )
    result = await get_project_questions(db)
    table_qs = [
        q for q in result["questions"]
        if "orders" in q["question"]
    ]
    assert len(table_qs) >= 1


async def test_no_test_nodes(db: Database):
    """Service + route but no test nodes → testing question."""
    await db.create_node(
        NodeCreateInput(name="API Service", type=NodeType.service)
    )
    await db.create_node(
        NodeCreateInput(name="GET /health", type=NodeType.route)
    )
    result = await get_project_questions(db)
    test_qs = [
        q for q in result["questions"]
        if "test" in q["question"].lower()
    ]
    assert len(test_qs) >= 1


async def test_orphaned_nodes(db: Database):
    """2 nodes with no edges and no parent/child → warning for each orphan."""
    await db.create_node(
        NodeCreateInput(name="Orphan1", type=NodeType.service)
    )
    await db.create_node(
        NodeCreateInput(name="Orphan2", type=NodeType.service)
    )
    result = await get_project_questions(db)
    orphan_qs = [
        q for q in result["questions"]
        if q["severity"] == "warning" and (
            "Orphan1" in q["question"] or "Orphan2" in q["question"]
        )
    ]
    assert len(orphan_qs) >= 2


async def test_external_with_many_dependents(db: Database):
    """External node with 3+ dependents → fallback question."""
    ext = await db.create_node(
        NodeCreateInput(name="Stripe API", type=NodeType.external)
    )
    for i in range(3):
        svc = await db.create_node(
            NodeCreateInput(name=f"Service{i}", type=NodeType.service)
        )
        await db.create_edge(
            EdgeCreateInput(
                source_id=svc.id,
                target_id=ext.id,
                relationship=EdgeRelationship.calls,
            )
        )
    result = await get_project_questions(db)
    fallback_qs = [
        q for q in result["questions"]
        if "Stripe API" in q["question"] or "Stripe API" in q["context"]
    ]
    assert len(fallback_qs) >= 1


async def test_category_filter(db: Database):
    """Filter by 'security' category → only security questions returned."""
    # This setup triggers both security (no auth) and data (no db) questions
    await db.create_node(
        NodeCreateInput(name="GET /data", type=NodeType.route)
    )
    result = await get_project_questions(db, category="security")
    for q in result["questions"]:
        assert q["category"] == "security"


async def test_questions_have_required_fields(db: Database):
    """Every question has non-empty fix_prompt and learn_more."""
    await db.create_node(
        NodeCreateInput(name="API", type=NodeType.service)
    )
    result = await get_project_questions(db)
    assert result["total"] > 0
    for q in result["questions"]:
        assert q["fix_prompt"], f"Question '{q['question']}' has empty fix_prompt"
        assert q["learn_more"], f"Question '{q['question']}' has empty learn_more"


async def test_highlight_nodes_real_ids(db: Database):
    """For questions with highlight_nodes, each ID matches a real node."""
    db_node = await db.create_node(
        NodeCreateInput(name="PostgreSQL", type=NodeType.database)
    )
    table = await db.create_node(
        NodeCreateInput(name="users", type=NodeType.table, parent_id=db_node.id)
    )
    result = await get_project_questions(db)
    # Gather all node IDs in the DB
    all_nodes = await db.get_all_nodes()
    all_ids = {n.id for n in all_nodes}
    for q in result["questions"]:
        for nid in q.get("highlight_nodes", []):
            assert nid in all_ids, f"highlight_nodes ID '{nid}' not found in DB"


async def test_desktop_skips_auth_questions(db: Database):
    """Desktop/Tauri projects skip auth-related questions."""
    await db.set_project_meta("project_type", "tauri")
    await db.create_node(
        NodeCreateInput(name="GET /users", type=NodeType.route)
    )
    result = await get_project_questions(db)
    auth_qs = [
        q for q in result["questions"]
        if q["category"] == "security" and "auth" in q["question"].lower()
    ]
    assert len(auth_qs) == 0


async def test_empty_blueprint(db: Database):
    """Empty DB → no questions, total=0."""
    result = await get_project_questions(db)
    assert result["total"] == 0
    assert result["questions"] == []
    assert result["summary"]["critical"] == 0
    assert result["summary"]["warning"] == 0
    assert result["summary"]["info"] == 0
