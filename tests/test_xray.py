"""Tests for Phase D — X-ray HTML visualization."""

import json

import pytest

from src.db import Database
from src.models import (
    EDGE_RELATIONSHIP_DESCRIPTIONS,
    NODE_STATUS_DESCRIPTIONS,
    NODE_TYPE_DESCRIPTIONS,
    EdgeCreateInput,
    EdgeRelationship,
    NodeCreateInput,
    NodeType,
)
from src.xray import _build_data_json, render_blueprint


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


async def test_html_contains_nodes(db: Database, tmp_path):
    """Create 2 nodes → render to temp file → HTML contains both node names."""
    await db.create_node(NodeCreateInput(name="AlphaService", type=NodeType.service))
    await db.create_node(NodeCreateInput(name="BetaDB", type=NodeType.database))
    output = str(tmp_path / "test.html")
    result = await render_blueprint(db, output_path=output)
    html = open(output).read()
    assert "AlphaService" in html
    assert "BetaDB" in html


async def test_html_has_d3_script(db: Database, tmp_path):
    """Render → HTML contains 'd3.v7.min.js'."""
    output = str(tmp_path / "test.html")
    await render_blueprint(db, output_path=output)
    html = open(output).read()
    assert "d3.v7.min.js" in html


async def test_data_counts_correct(db: Database, tmp_path):
    """3 nodes + 1 edge → result has node_count=3, edge_count=1."""
    a = await db.create_node(NodeCreateInput(name="A", type=NodeType.service))
    b = await db.create_node(NodeCreateInput(name="B", type=NodeType.service))
    c = await db.create_node(NodeCreateInput(name="C", type=NodeType.database))
    await db.create_edge(
        EdgeCreateInput(source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls)
    )
    output = str(tmp_path / "test.html")
    result = await render_blueprint(db, output_path=output)
    assert result["node_count"] == 3
    assert result["edge_count"] == 1


async def test_empty_blueprint_valid(db: Database, tmp_path):
    """Empty DB → renders valid HTML, no crash."""
    output = str(tmp_path / "test.html")
    result = await render_blueprint(db, output_path=output)
    html = open(output).read()
    assert "<!DOCTYPE html>" in html
    assert result["node_count"] == 0
    assert result["edge_count"] == 0


async def test_theme_affects_output(db: Database, tmp_path):
    """Render with theme='dark' → HTML contains dark theme indicator."""
    output = str(tmp_path / "test.html")
    result = await render_blueprint(db, output_path=output, theme="dark")
    html = open(output).read()
    assert result["theme"] == "dark"
    # Dark theme is set via data-theme attribute and uses dark CSS variables
    assert 'data-theme="dark"' in html


async def test_data_json_includes_descriptions(db: Database):
    """_build_data_json output includes all 3 description dicts with correct counts."""
    await db.create_node(NodeCreateInput(name="Svc", type=NodeType.service))
    data_str, _ = await _build_data_json(db)
    data = json.loads(data_str)
    assert data["node_type_descriptions"] == NODE_TYPE_DESCRIPTIONS
    assert data["node_status_descriptions"] == NODE_STATUS_DESCRIPTIONS
    assert data["edge_relationship_descriptions"] == EDGE_RELATIONSHIP_DESCRIPTIONS


# --- Stage 2: Legend + Help Panel tests ---


async def test_help_panel_has_legend_tab(db: Database, tmp_path):
    """Help panel HTML contains the legend tab button and Node Colors section."""
    output = str(tmp_path / "test.html")
    await render_blueprint(db, output_path=output)
    html = open(output).read()
    assert 'data-help-tab="legend"' in html
    assert "Node Colors" in html


async def test_help_panel_has_shortcuts_tab(db: Database, tmp_path):
    """Help panel HTML contains the shortcuts tab and existing shortcuts text."""
    output = str(tmp_path / "test.html")
    await render_blueprint(db, output_path=output)
    html = open(output).read()
    assert 'data-help-tab="shortcuts"' in html
    assert "collapse/expand" in html


async def test_legend_contains_all_categories(db: Database, tmp_path):
    """Legend contains all 9 category names from TYPE_CATEGORIES."""
    output = str(tmp_path / "test.html")
    await render_blueprint(db, output_path=output)
    html = open(output).read()
    categories = [
        "Infrastructure", "Services", "API", "Data", "Code",
        "Files", "Schema", "External", "Testing",
    ]
    for cat in categories:
        assert cat in html, f"Legend missing category: {cat}"


# --- Stage 3: Onboarding + Status Summary tests ---


async def test_status_summary_bar_present(db: Database, tmp_path):
    """HTML contains the status-summary bar element."""
    output = str(tmp_path / "test.html")
    await render_blueprint(db, output_path=output)
    html = open(output).read()
    assert 'id="status-summary"' in html


async def test_onboarding_overlay_present(db: Database, tmp_path):
    """HTML contains the onboarding initialization and Got it button."""
    output = str(tmp_path / "test.html")
    await render_blueprint(db, output_path=output)
    html = open(output).read()
    assert "initOnboarding" in html
    assert "Got it" in html


async def test_onboarding_uses_localstorage(db: Database, tmp_path):
    """HTML contains localStorage key for onboarding dismissal."""
    output = str(tmp_path / "test.html")
    await render_blueprint(db, output_path=output)
    html = open(output).read()
    assert "blueprint-xray-onboarded" in html
