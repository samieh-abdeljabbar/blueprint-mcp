"""Tests for src.stale — stale node detection."""

import pytest

from src.stale import find_stale
from src.db import Database
from src.models import NodeCreateInput, NodeType, NodeStatus


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


async def test_missing_file_detected(db: Database):
    """A node whose source_file doesn't exist on disk appears in missing_files."""
    await db.create_node(
        NodeCreateInput(
            name="Ghost Service",
            type=NodeType.service,
            source_file="/tmp/absolutely_does_not_exist_xyz123.py",
        )
    )

    result = await find_stale(db, days_threshold=30, check_git=False)

    assert len(result["missing_files"]) == 1
    entry = result["missing_files"][0]
    assert entry["node_name"] == "Ghost Service"
    assert entry["expected_file"] == "/tmp/absolutely_does_not_exist_xyz123.py"


async def test_stale_planned_detected(db: Database):
    """A planned node with a backdated created_at appears in stale_planned."""
    node = await db.create_node(
        NodeCreateInput(
            name="Old Plan",
            type=NodeType.module,
            status=NodeStatus.planned,
        )
    )

    # Manually backdate created_at so it looks old
    await db.db.execute(
        "UPDATE nodes SET created_at = '2020-01-01T00:00:00' WHERE id = ?",
        (node.id,),
    )
    await db.db.commit()

    result = await find_stale(db, days_threshold=30, check_git=False)

    assert len(result["stale_planned"]) == 1
    entry = result["stale_planned"][0]
    assert entry["node_name"] == "Old Plan"
    assert entry["days_waiting"] > 365  # well over a year old


async def test_existing_file_not_in_missing(db: Database, tmp_path):
    """A node pointing to a real file does NOT appear in missing_files."""
    real_file = tmp_path / "real_module.py"
    real_file.write_text("# hello")

    await db.create_node(
        NodeCreateInput(
            name="Real Module",
            type=NodeType.module,
            source_file=str(real_file),
        )
    )

    result = await find_stale(db, days_threshold=30, check_git=False)

    missing_names = [e["node_name"] for e in result["missing_files"]]
    assert "Real Module" not in missing_names
