"""Tests for annotations and cost reporting."""
import pytest
from src.db import Database
from src.models import NodeCreateInput, NodeType
from src.annotations import annotate_node, get_annotations, cost_report


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


async def test_annotate_and_retrieve(db: Database):
    """Annotate a node -> get_annotations returns it."""
    node = await db.create_node(NodeCreateInput(name="API", type=NodeType.service))
    await annotate_node(db, node.id, "provider", "AWS")
    result = await get_annotations(db, node_id=node.id)
    assert result["total"] == 1
    assert result["annotations"][0]["key"] == "provider"
    assert result["annotations"][0]["value"] == "AWS"


async def test_upsert_annotation(db: Database):
    """Annotating same key twice -> updates value, not duplicate."""
    node = await db.create_node(NodeCreateInput(name="DB", type=NodeType.database))
    await annotate_node(db, node.id, "monthly_cost", "50")
    await annotate_node(db, node.id, "monthly_cost", "75")
    result = await get_annotations(db, node_id=node.id)
    assert result["total"] == 1
    assert result["annotations"][0]["value"] == "75"


async def test_cost_report(db: Database):
    """Multiple nodes with cost annotations -> cost_report aggregates correctly."""
    n1 = await db.create_node(NodeCreateInput(name="API", type=NodeType.service))
    n2 = await db.create_node(NodeCreateInput(name="DB", type=NodeType.database))
    await annotate_node(db, n1.id, "monthly_cost", "100")
    await annotate_node(db, n1.id, "provider", "AWS")
    await annotate_node(db, n2.id, "monthly_cost", "50")
    await annotate_node(db, n2.id, "provider", "DigitalOcean")

    report = await cost_report(db)
    assert report["total_monthly_cost"] == 150.0
    assert report["by_provider"]["AWS"] == 100.0
    assert report["by_provider"]["DigitalOcean"] == 50.0
    assert len(report["itemized"]) == 2


async def test_annotate_nonexistent_node(db: Database):
    """Annotating a non-existent node -> error returned."""
    result = await annotate_node(db, "00000000-0000-0000-0000-000000000000", "key", "val")
    assert "error" in result
