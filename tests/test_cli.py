"""Tests for CLI entry point."""

import os
import sys
import pytest
from unittest.mock import patch

from src.cli import main


def test_init_creates_db(tmp_path):
    """blueprint-mcp init creates .blueprint.db and .gitignore."""
    original = os.getcwd()
    os.chdir(tmp_path)
    try:
        main(["init"])
        assert os.path.exists(tmp_path / ".blueprint.db")
        gitignore = (tmp_path / ".gitignore").read_text()
        assert ".blueprint.db" in gitignore
    finally:
        os.chdir(original)


def test_health_returns_json(tmp_path):
    """blueprint-mcp health prints JSON with overall_score."""
    import asyncio
    from src.db import init_db
    from src.models import NodeCreateInput, NodeType

    db_path = str(tmp_path / ".blueprint.db")

    async def setup():
        db = await init_db(db_path)
        await db.create_node(NodeCreateInput(name="Svc", type=NodeType.service, description="test"))
        await db.close()

    asyncio.run(setup())

    original = os.getcwd()
    os.chdir(tmp_path)
    try:
        with patch("builtins.print") as mock_print:
            with patch.dict(os.environ, {"BLUEPRINT_DB": db_path}):
                main(["health"])
                output = mock_print.call_args[0][0]
                assert "overall_score" in output
    finally:
        os.chdir(original)


def test_health_fail_below_exits(tmp_path):
    """blueprint-mcp health --fail-below 100 exits with code 1 on imperfect project."""
    import asyncio
    from src.db import init_db
    from src.models import NodeCreateInput, NodeType

    db_path = str(tmp_path / ".blueprint.db")

    async def setup():
        db = await init_db(db_path)
        await db.create_node(NodeCreateInput(name="Bare", type=NodeType.service))
        await db.close()

    asyncio.run(setup())

    original = os.getcwd()
    os.chdir(tmp_path)
    try:
        with patch.dict(os.environ, {"BLUEPRINT_DB": db_path}):
            with pytest.raises(SystemExit) as exc_info:
                main(["health", "--fail-below", "100"])
            assert exc_info.value.code == 1
    finally:
        os.chdir(original)


def test_export_mermaid(tmp_path):
    """blueprint-mcp export --format mermaid prints mermaid output."""
    import asyncio
    from src.db import init_db
    from src.models import NodeCreateInput, NodeType

    db_path = str(tmp_path / ".blueprint.db")

    async def setup():
        db = await init_db(db_path)
        await db.create_node(NodeCreateInput(name="API", type=NodeType.service))
        await db.close()

    asyncio.run(setup())

    original = os.getcwd()
    os.chdir(tmp_path)
    try:
        with patch.dict(os.environ, {"BLUEPRINT_DB": db_path}):
            with patch("builtins.print") as mock_print:
                main(["export", "--format", "mermaid"])
                output = mock_print.call_args[0][0]
                assert "graph TD" in output
                assert "API" in output
    finally:
        os.chdir(original)
