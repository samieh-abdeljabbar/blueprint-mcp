"""Tests for Phase B2 — review prompt generation."""

import pytest

from src.db import Database
from src.models import (
    EdgeCreateInput,
    EdgeRelationship,
    NodeCreateInput,
    NodeType,
)
from src.review import get_review_prompt


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


async def test_review_contains_node_names(db: Database):
    """Service + database + edge → review_prompt contains both node names."""
    svc = await db.create_node(
        NodeCreateInput(name="OrderService", type=NodeType.service)
    )
    dbn = await db.create_node(
        NodeCreateInput(name="OrderDB", type=NodeType.database)
    )
    await db.create_edge(
        EdgeCreateInput(
            source_id=svc.id,
            target_id=dbn.id,
            relationship=EdgeRelationship.connects_to,
        )
    )
    result = await get_review_prompt(db)
    assert "OrderService" in result["review_prompt"]
    assert "OrderDB" in result["review_prompt"]


async def test_review_focus_security(db: Database):
    """Focus='security' → REVIEW QUESTIONS section only has security items."""
    route = await db.create_node(
        NodeCreateInput(name="GET /secret", type=NodeType.route)
    )
    await db.create_node(
        NodeCreateInput(name="MainDB", type=NodeType.database)
    )
    result = await get_review_prompt(db, focus="security")
    # Extract the REVIEW QUESTIONS section
    prompt = result["review_prompt"]
    sections = prompt.split("# REVIEW QUESTIONS")
    assert len(sections) >= 2, "Expected REVIEW QUESTIONS section"
    review_section = sections[-1]
    # Each line with a category tag should be [security]
    import re
    categories = re.findall(r"\[(\w+)\]", review_section)
    for cat in categories:
        assert cat == "security", f"Found non-security category '{cat}' in REVIEW QUESTIONS"


async def test_review_scoped_to_subtree(db: Database):
    """Scoped to parent → ARCHITECTURE LAYERS section contains children names but NOT unrelated node."""
    parent = await db.create_node(
        NodeCreateInput(name="PaymentSystem", type=NodeType.system)
    )
    child1 = await db.create_node(
        NodeCreateInput(name="PaymentGateway", type=NodeType.service, parent_id=parent.id)
    )
    child2 = await db.create_node(
        NodeCreateInput(name="InvoiceDB", type=NodeType.database, parent_id=parent.id)
    )
    unrelated = await db.create_node(
        NodeCreateInput(name="TotallyUnrelatedWidget", type=NodeType.service)
    )
    result = await get_review_prompt(db, node_id=parent.id)
    prompt = result["review_prompt"]
    # The ARCHITECTURE LAYERS section should contain the subtree only
    layers_section = prompt.split("# ARCHITECTURE LAYERS")[-1].split("# CONNECTIONS MAP")[0]
    assert "PaymentSystem" in layers_section
    assert "PaymentGateway" in layers_section
    assert "InvoiceDB" in layers_section
    assert "TotallyUnrelatedWidget" not in layers_section


async def test_review_empty_blueprint(db: Database):
    """Empty DB → review_prompt mentions '0' components, sections >= 1."""
    result = await get_review_prompt(db)
    prompt = result["review_prompt"].lower()
    assert "total components: 0" in prompt or "0 component" in prompt
    assert result["sections"] >= 1
