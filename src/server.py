"""FastMCP server for Blueprint MCP — living architectural map."""

from __future__ import annotations

from fastmcp import Context, FastMCP
from fastmcp.server.lifespan import lifespan
from pydantic import ValidationError

from src.db import Database, init_db
from src.models import EdgeCreateInput, NodeCreateInput, NodeUpdateInput


@lifespan
async def app_lifespan(server):
    db = await init_db()
    try:
        yield {"db": db}
    finally:
        await db.close()


mcp = FastMCP("Blueprint", lifespan=app_lifespan)


def _get_db(ctx: Context) -> Database:
    return ctx.lifespan_context["db"]


# --- Node tools ---


@mcp.tool
async def register_node(
    name: str,
    type: str,
    status: str = "built",
    parent_id: str | None = None,
    description: str | None = None,
    metadata: dict | None = None,
    source_file: str | None = None,
    source_line: int | None = None,
    ctx: Context = None,
) -> dict:
    """Register a new component in the blueprint. Call this whenever you create a file, database table, API route, or service."""
    try:
        inp = NodeCreateInput(
            name=name,
            type=type,
            status=status,
            parent_id=parent_id,
            description=description,
            metadata=metadata,
            source_file=source_file,
            source_line=source_line,
        )
    except ValidationError as e:
        return {"error": str(e)}

    db = _get_db(ctx)
    node = await db.create_node(inp)
    return {"id": node.id, "name": node.name, "type": node.type.value, "status": node.status.value}


@mcp.tool
async def update_node(
    id: str,
    name: str | None = None,
    status: str | None = None,
    description: str | None = None,
    metadata: dict | None = None,
    source_file: str | None = None,
    source_line: int | None = None,
    ctx: Context = None,
) -> dict:
    """Update an existing node's status, metadata, or details."""
    try:
        inp = NodeUpdateInput(
            id=id,
            name=name,
            status=status,
            description=description,
            metadata=metadata,
            source_file=source_file,
            source_line=source_line,
        )
    except ValidationError as e:
        return {"error": str(e)}

    db = _get_db(ctx)
    node = await db.update_node(inp)
    if node is None:
        return {"error": f"Node '{id}' not found"}
    return node.model_dump()


@mcp.tool
async def remove_node(id: str, ctx: Context = None) -> dict:
    """Remove a node and all its children and connections."""
    db = _get_db(ctx)
    deleted = await db.delete_node(id)
    if not deleted:
        return {"deleted": False, "error": f"Node '{id}' not found"}
    return {"deleted": True, "id": id}


@mcp.tool
async def get_node(id: str, depth: int = 1, ctx: Context = None) -> dict:
    """Get a single node with its children and connections."""
    db = _get_db(ctx)
    node = await db.get_node(id, depth)
    if node is None:
        return {"error": f"Node '{id}' not found"}
    return node.model_dump()


# --- Edge tools ---


@mcp.tool
async def register_connection(
    source_id: str,
    target_id: str,
    relationship: str,
    label: str | None = None,
    metadata: dict | None = None,
    status: str = "active",
    ctx: Context = None,
) -> dict:
    """Register a relationship between two nodes."""
    try:
        inp = EdgeCreateInput(
            source_id=source_id,
            target_id=target_id,
            relationship=relationship,
            label=label,
            metadata=metadata,
            status=status,
        )
    except ValidationError as e:
        return {"error": str(e)}

    db = _get_db(ctx)
    try:
        edge = await db.create_edge(inp)
    except ValueError as e:
        return {"error": str(e)}

    return {
        "id": edge.id,
        "source_id": edge.source_id,
        "target_id": edge.target_id,
        "relationship": edge.relationship.value,
    }


@mcp.tool
async def remove_connection(id: str, ctx: Context = None) -> dict:
    """Remove a connection between nodes."""
    db = _get_db(ctx)
    deleted = await db.delete_edge(id)
    if not deleted:
        return {"deleted": False, "error": f"Edge '{id}' not found"}
    return {"deleted": True, "id": id}


# --- Blueprint tools ---


@mcp.tool
async def get_blueprint(
    status_filter: str | None = None,
    type_filter: str | None = None,
    root_only: bool = False,
    ctx: Context = None,
) -> dict:
    """Get the full project blueprint — all nodes and connections."""
    db = _get_db(ctx)
    return await db.get_blueprint(status_filter, type_filter, root_only)


@mcp.tool
async def get_blueprint_summary(ctx: Context = None) -> dict:
    """Quick overview: counts by type, counts by status, recent changes."""
    db = _get_db(ctx)
    return await db.get_blueprint_summary()


# --- Template tools ---

from src.templates.registry import list_templates as _list_templates, apply_template as _apply_template


@mcp.tool
async def list_templates(ctx: Context = None) -> dict:
    """List all available project templates."""
    return {"templates": _list_templates(), "count": len(_list_templates())}


@mcp.tool
async def apply_template(template: str, project_name: str = "My Project", ctx: Context = None) -> dict:
    """Apply a project template to create all planned nodes and connections."""
    db = _get_db(ctx)
    try:
        result = await _apply_template(db, template, project_name)
    except ValueError as e:
        return {"error": str(e)}
    return result


# --- Scanner tools ---

from src.scanner import scan_project, scan_single_file


@mcp.tool
async def scan_codebase(
    path: str = ".",
    languages: list[str] | None = None,
    deep: bool = False,
    ctx: Context = None,
) -> dict:
    """Scan a project directory and auto-populate the blueprint from existing code."""
    db = _get_db(ctx)
    return await scan_project(path, db, languages=languages, deep=deep)


@mcp.tool
async def scan_file(path: str, ctx: Context = None) -> dict:
    """Scan a single file and update the blueprint with any components found."""
    db = _get_db(ctx)
    return await scan_single_file(path, db)


# --- Analyzer tools ---

from src.analyzer import analyze as _analyze
from src.models import IssueSeverity


@mcp.tool
async def find_issues(severity: str | None = None, ctx: Context = None) -> dict:
    """Analyze the blueprint for architectural issues."""
    db = _get_db(ctx)
    sev = None
    if severity:
        try:
            sev = IssueSeverity(severity)
        except ValueError:
            return {"error": f"Invalid severity: {severity}. Use critical, warning, or info."}
    issues = await _analyze(db, severity=sev)
    summary = {"critical": 0, "warning": 0, "info": 0}
    for issue in issues:
        summary[issue.severity.value] += 1
    return {
        "issues": [i.model_dump() for i in issues],
        "summary": summary,
    }


@mcp.tool
async def get_changes(since: str, ctx: Context = None) -> dict:
    """Get changelog entries since a given ISO 8601 timestamp."""
    db = _get_db(ctx)
    changes = await db.get_changes(since)
    return {
        "changes": [c.model_dump() for c in changes],
        "count": len(changes),
    }


# --- Viewer tool ---

import subprocess
import sys


@mcp.tool
async def open_viewer(port: int = 3333, ctx: Context = None) -> dict:
    """Open the blueprint viewer in a browser."""
    db = _get_db(ctx)
    db_path = db.db_path
    subprocess.Popen(
        [sys.executable, "-m", "src.viewer.serve", "--db-path", db_path, "--port", str(port), "--open"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {"status": "started", "url": f"http://localhost:{port}"}


if __name__ == "__main__":
    mcp.run()
