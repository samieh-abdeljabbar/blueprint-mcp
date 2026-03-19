"""Tests for multi-project linking."""
import os
import pytest
from src.projects import link_projects, get_project_map


@pytest.fixture
def meta_path(tmp_path):
    return str(tmp_path / "meta.db")


async def test_link_and_retrieve(meta_path: str):
    """Link two projects → get_project_map returns the link."""
    result = await link_projects(
        source_project="ProjectA",
        source_node="api_service",
        target_project="ProjectB",
        target_node="data_pipeline",
        relationship="feeds_into",
        label="Daily sync",
        meta_path=meta_path,
    )
    assert "id" in result
    assert result["relationship"] == "feeds_into"

    pmap = await get_project_map(meta_path=meta_path)
    assert pmap["total_links"] == 1
    assert "ProjectA" in pmap["projects"]
    assert "ProjectB" in pmap["projects"]
    # Verify link content
    link = pmap["links"][0]
    assert link["relationship"] == "feeds_into"
    assert link["label"] == "Daily sync"
    assert "api_service" in link["from"]
    assert "data_pipeline" in link["to"]


async def test_project_filter(meta_path: str):
    """Create links between 3 projects → filter by one project returns only its links."""
    await link_projects("A", "n1", "B", "n2", "calls", meta_path=meta_path)
    await link_projects("B", "n3", "C", "n4", "reads_from", meta_path=meta_path)
    await link_projects("A", "n5", "C", "n6", "depends_on", meta_path=meta_path)

    pmap = await get_project_map(project="B", meta_path=meta_path)
    assert pmap["total_links"] == 2  # B appears in 2 links
    assert "B" in pmap["projects"]


async def test_empty_project_map(meta_path: str):
    """No links → empty project map."""
    pmap = await get_project_map(meta_path=meta_path)
    assert pmap["total_links"] == 0
    assert pmap["projects"] == []
    assert pmap["links"] == []
