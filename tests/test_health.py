"""Tests for the health report module."""

import pytest

from src.db import Database
from src.health import health_report
from src.models import (
    EdgeCreateInput,
    EdgeRelationship,
    NodeCreateInput,
    NodeStatus,
    NodeType,
)


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


async def test_perfect_node_scores_high(db: Database):
    """A node with description, source_file, metadata, built status, edge, and child should score 85+."""
    parent = await db.create_node(
        NodeCreateInput(
            name="Auth Service",
            type=NodeType.service,
            status=NodeStatus.built,
            description="Handles authentication and authorization",
            metadata={"language": "python"},
            source_file=__file__,  # use this test file so os.path.isfile is True
        )
    )

    # Add a child node
    child = await db.create_node(
        NodeCreateInput(
            name="login",
            type=NodeType.function,
            status=NodeStatus.built,
            parent_id=parent.id,
        )
    )

    # Add an edge so the parent has at least one connection
    await db.create_edge(
        EdgeCreateInput(
            source_id=parent.id,
            target_id=child.id,
            relationship=EdgeRelationship.contains,
        )
    )

    result = await health_report(db, node_id=parent.id)

    assert result["node_id"] == parent.id
    assert result["score"] >= 85
    assert result["grade"] in ("A", "B")
    assert result["breakdown"]["description"] == 15
    assert result["breakdown"]["source_file"] == 15
    assert result["breakdown"]["source_file_exists"] == 10
    assert result["breakdown"]["has_edges"] == 20
    assert result["breakdown"]["status_built"] == 15
    assert result["breakdown"]["status_not_broken"] == 10
    assert result["breakdown"]["has_children"] == 10
    assert result["breakdown"]["has_metadata"] == 5


async def test_empty_node_scores_low(db: Database):
    """A minimal node with planned status and nothing else should score low."""
    node = await db.create_node(
        NodeCreateInput(
            name="placeholder",
            type=NodeType.module,
            status=NodeStatus.planned,
        )
    )

    result = await health_report(db, node_id=node.id)

    assert result["score"] < 40
    assert result["grade"] in ("F", "D")
    # Only status_not_broken should earn points (planned is not broken/deprecated)
    assert result["breakdown"]["description"] == 0
    assert result["breakdown"]["source_file"] == 0
    assert result["breakdown"]["has_edges"] == 0
    assert result["breakdown"]["status_built"] == 0
    assert result["breakdown"]["status_not_broken"] == 10
    assert result["breakdown"]["has_children"] == 0
    assert result["breakdown"]["has_metadata"] == 0


async def test_project_mixed_nodes(db: Database):
    """Project with a mix of good and bad nodes produces a reasonable overall score and correct grade."""
    # Good node
    good = await db.create_node(
        NodeCreateInput(
            name="API Gateway",
            type=NodeType.service,
            status=NodeStatus.built,
            description="Main entry point",
            source_file=__file__,
            metadata={"port": 8080},
        )
    )

    # Mediocre node
    mediocre = await db.create_node(
        NodeCreateInput(
            name="Logger",
            type=NodeType.module,
            status=NodeStatus.built,
        )
    )

    # Bad node
    bad = await db.create_node(
        NodeCreateInput(
            name="LegacyDB",
            type=NodeType.database,
            status=NodeStatus.broken,
        )
    )

    # Connect good -> mediocre so they aren't both orphans
    await db.create_edge(
        EdgeCreateInput(
            source_id=good.id,
            target_id=mediocre.id,
            relationship=EdgeRelationship.calls,
        )
    )

    result = await health_report(db)

    assert result["total_nodes"] == 3
    assert result["overall_score"] < 60  # broken + orphan nodes drag score down
    assert result["grade"] in ("D", "F")
    assert result["node_scores"]["healthy"] + result["node_scores"]["needs_attention"] + result["node_scores"]["critical"] == 3
    # Verify specific issues are flagged
    issues_str = " ".join(result["top_issues"])
    assert "broken" in issues_str
    assert "orphan" in issues_str


async def test_single_node_health_returns_breakdown(db: Database):
    """Passing node_id returns a breakdown dict with per-category points."""
    node = await db.create_node(
        NodeCreateInput(
            name="Payments",
            type=NodeType.service,
            status=NodeStatus.in_progress,
            description="Handles billing",
        )
    )

    result = await health_report(db, node_id=node.id)

    assert "breakdown" in result
    assert isinstance(result["breakdown"], dict)
    expected_keys = {
        "description",
        "source_file",
        "source_file_exists",
        "has_edges",
        "status_built",
        "status_not_broken",
        "has_children",
        "has_metadata",
    }
    assert set(result["breakdown"].keys()) == expected_keys
    # description is present so it should earn 15
    assert result["breakdown"]["description"] == 15
    # status is in_progress, not built
    assert result["breakdown"]["status_built"] == 0
    # in_progress is not broken/deprecated
    assert result["breakdown"]["status_not_broken"] == 10
    assert result["node_name"] == "Payments"
    assert result["grade"] in ("A", "B", "C", "D", "F")


async def test_empty_project_returns_zero(db: Database):
    """An empty project should return score 0 and grade F."""
    result = await health_report(db)

    assert result["overall_score"] == 0
    assert result["grade"] == "F"
    assert result["total_nodes"] == 0
    assert result["node_scores"] == {"healthy": 0, "needs_attention": 0, "critical": 0}
    assert result["top_issues"] == []
    assert result["recommendations"] == []
