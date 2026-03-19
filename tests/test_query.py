"""Tests for natural-language blueprint query engine."""

import pytest

from src.db import Database
from src.models import (
    EdgeCreateInput,
    EdgeRelationship,
    NodeCreateInput,
    NodeStatus,
    NodeType,
)
from src.query import query_blueprint


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


async def test_what_connects_to_database(db: Database):
    """'what connects to the database' returns nodes with edges targeting a database node."""
    api = await db.create_node(
        NodeCreateInput(name="API Service", type=NodeType.service)
    )
    worker = await db.create_node(
        NodeCreateInput(name="Background Worker", type=NodeType.worker)
    )
    db_node = await db.create_node(
        NodeCreateInput(name="PostgreSQL", type=NodeType.database)
    )
    unrelated = await db.create_node(
        NodeCreateInput(name="Frontend", type=NodeType.service)
    )
    await db.create_edge(
        EdgeCreateInput(
            source_id=api.id,
            target_id=db_node.id,
            relationship=EdgeRelationship.connects_to,
        )
    )
    await db.create_edge(
        EdgeCreateInput(
            source_id=worker.id,
            target_id=db_node.id,
            relationship=EdgeRelationship.writes_to,
        )
    )

    result = await query_blueprint(db, "what connects to the database")

    assert result["query_interpretation"]
    assert result["summary"]

    match_names = {m["name"] for m in result["matches"]}
    # The sources (API Service, Background Worker) and the target (PostgreSQL) should appear
    assert "API Service" in match_names
    assert "Background Worker" in match_names
    assert "PostgreSQL" in match_names
    # Unrelated node should NOT appear
    assert "Frontend" not in match_names
    # Edges should be returned
    assert len(result["edges"]) == 2


async def test_show_me_all_routes(db: Database):
    """'show me all routes' returns only route-type nodes."""
    await db.create_node(
        NodeCreateInput(name="GET /users", type=NodeType.route)
    )
    await db.create_node(
        NodeCreateInput(name="POST /orders", type=NodeType.route)
    )
    await db.create_node(
        NodeCreateInput(name="API Service", type=NodeType.service)
    )
    await db.create_node(
        NodeCreateInput(name="PostgreSQL", type=NodeType.database)
    )

    result = await query_blueprint(db, "show me all routes")

    match_names = {m["name"] for m in result["matches"]}
    assert match_names == {"GET /users", "POST /orders"}
    # Every returned match must be of type route
    for m in result["matches"]:
        assert m["type"] == "route"
    assert "route" in result["query_interpretation"].lower()


async def test_what_does_auth_depend_on(db: Database):
    """'what does auth depend on' returns outgoing depends_on targets from auth node."""
    auth = await db.create_node(
        NodeCreateInput(name="Auth Service", type=NodeType.service)
    )
    user_db = await db.create_node(
        NodeCreateInput(name="User Database", type=NodeType.database)
    )
    jwt_lib = await db.create_node(
        NodeCreateInput(name="JWT Library", type=NodeType.module)
    )
    cache = await db.create_node(
        NodeCreateInput(name="Redis Cache", type=NodeType.cache)
    )
    # Auth depends_on user_db and jwt_lib
    await db.create_edge(
        EdgeCreateInput(
            source_id=auth.id,
            target_id=user_db.id,
            relationship=EdgeRelationship.depends_on,
        )
    )
    await db.create_edge(
        EdgeCreateInput(
            source_id=auth.id,
            target_id=jwt_lib.id,
            relationship=EdgeRelationship.depends_on,
        )
    )
    # Auth connects_to cache (not depends_on — should NOT appear)
    await db.create_edge(
        EdgeCreateInput(
            source_id=auth.id,
            target_id=cache.id,
            relationship=EdgeRelationship.connects_to,
        )
    )

    result = await query_blueprint(db, "what does auth depend on")

    match_names = {m["name"] for m in result["matches"]}
    assert "User Database" in match_names
    assert "JWT Library" in match_names
    # Redis Cache is connected but NOT via depends_on
    assert "Redis Cache" not in match_names
    assert len(result["edges"]) == 2
    for e in result["edges"]:
        assert e["relationship"] == "depends_on"


async def test_find_broken_things(db: Database):
    """'find broken things' returns only nodes with broken status."""
    await db.create_node(
        NodeCreateInput(name="Healthy API", type=NodeType.service, status=NodeStatus.built)
    )
    await db.create_node(
        NodeCreateInput(name="Broken Auth", type=NodeType.service, status=NodeStatus.broken)
    )
    await db.create_node(
        NodeCreateInput(name="Broken DB Link", type=NodeType.database, status=NodeStatus.broken)
    )
    await db.create_node(
        NodeCreateInput(name="Planned Feature", type=NodeType.module, status=NodeStatus.planned)
    )

    result = await query_blueprint(db, "find broken things")

    match_names = {m["name"] for m in result["matches"]}
    assert match_names == {"Broken Auth", "Broken DB Link"}
    for m in result["matches"]:
        assert m["status"] == "broken"
    assert "broken" in result["query_interpretation"].lower()


async def test_no_matches_returns_helpful_summary(db: Database):
    """Question about nonexistent thing returns empty matches with a helpful summary."""
    await db.create_node(
        NodeCreateInput(name="API Service", type=NodeType.service)
    )

    result = await query_blueprint(db, "what connects to the unicorn")

    assert result["matches"] == []
    assert result["edges"] == []
    assert result["summary"]  # non-empty helpful message
    assert len(result["summary"]) > 10  # not just a placeholder
    assert result["query_interpretation"]
