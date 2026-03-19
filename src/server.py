"""FastMCP server for Blueprint MCP — living architectural map."""

from __future__ import annotations

import os

from fastmcp import Context, FastMCP
from fastmcp.server.lifespan import lifespan
from pydantic import ValidationError

from src.db import Database, init_db
from src.models import EdgeCreateInput, NodeCreateInput, NodeUpdateInput


@lifespan
async def app_lifespan(server):
    project_dir = os.environ.get("BLUEPRINT_PROJECT_DIR")
    if project_dir:
        db_path = os.path.join(project_dir, ".blueprint.db")
        db = await init_db(db_path)
    else:
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
    path: str | None = None,
    languages: list[str] | None = None,
    deep: bool = False,
    ctx: Context = None,
) -> dict:
    """Scan a project directory and auto-populate the blueprint from existing code."""
    if path is None:
        path = os.environ.get("BLUEPRINT_PROJECT_DIR", ".")
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


# --- Phase B: Intelligence tools ---

from src.questions import get_project_questions as _get_project_questions


@mcp.tool
async def get_project_questions(
    category: str = "all", node_id: str | None = None, ctx: Context = None
) -> dict:
    """Analyze the blueprint and generate actionable questions about gaps, risks, and improvements."""
    db = _get_db(ctx)
    return await _get_project_questions(db, category, node_id)


from src.review import get_review_prompt as _get_review_prompt


@mcp.tool
async def get_review_prompt(
    focus: str = "all", node_id: str | None = None, ctx: Context = None
) -> dict:
    """Generate a structured review document with architecture overview, issues, and gaps."""
    db = _get_db(ctx)
    return await _get_review_prompt(db, focus, node_id)


from src.impact import impact_analysis as _impact_analysis


@mcp.tool
async def impact_analysis(
    node_id: str, depth: int = -1, direction: str = "downstream", ctx: Context = None
) -> dict:
    """Trace the impact of changing a node — find all affected components downstream, upstream, or both."""
    db = _get_db(ctx)
    return await _impact_analysis(db, node_id, depth, direction)


# --- Phase C: Flow tools ---

from src.tracer import list_entry_points as _list_entry_points


@mcp.tool
async def list_entry_points(ctx: Context = None) -> dict:
    """Find all entry points (routes, APIs, webhooks) in the blueprint."""
    db = _get_db(ctx)
    return await _list_entry_points(db)


from src.tracer import trace_flow as _trace_flow


@mcp.tool
async def trace_flow(
    start_node_id: str,
    trigger: str | None = None,
    max_depth: int = 20,
    include_error_paths: bool = True,
    ctx: Context = None,
) -> dict:
    """Trace a request/data flow through the system from a starting node, detecting gaps and dead ends."""
    db = _get_db(ctx)
    return await _trace_flow(db, start_node_id, trigger, max_depth, include_error_paths)


from src.whatif import what_if as _what_if


@mcp.tool
async def what_if(node_id: str, scenario: str, ctx: Context = None) -> dict:
    """Simulate a what-if scenario (remove, break, disconnect, overload) for a node."""
    db = _get_db(ctx)
    return await _what_if(db, node_id, scenario)


# --- Phase D: Viewer tools ---

from src.xray import render_blueprint as _render_blueprint


@mcp.tool
async def render_blueprint(
    output_path: str | None = None, theme: str = "light", ctx: Context = None
) -> dict:
    """Generate a self-contained HTML visualization of the blueprint with D3.js."""
    if output_path is None:
        project_dir = os.environ.get("BLUEPRINT_PROJECT_DIR", ".")
        output_path = os.path.join(project_dir, ".blueprint.html")
    db = _get_db(ctx)
    return await _render_blueprint(db, output_path, theme)


# --- Phase E: Snapshots & Export tools ---

from src.snapshots import (
    snapshot_blueprint as _snapshot_blueprint,
    list_snapshots as _list_snapshots,
    compare_snapshots as _compare_snapshots,
    restore_snapshot as _restore_snapshot,
)


@mcp.tool
async def snapshot_blueprint(
    name: str, description: str | None = None, ctx: Context = None
) -> dict:
    """Save a snapshot of the current blueprint state for later comparison."""
    db = _get_db(ctx)
    return await _snapshot_blueprint(db, name, description)


@mcp.tool
async def list_snapshots(ctx: Context = None) -> dict:
    """List all saved blueprint snapshots."""
    db = _get_db(ctx)
    return await _list_snapshots(db)


@mcp.tool
async def compare_snapshots(
    snapshot_id: str, compare_to: str | None = None, ctx: Context = None
) -> dict:
    """Compare a snapshot against another snapshot or the current blueprint state."""
    db = _get_db(ctx)
    return await _compare_snapshots(db, snapshot_id, compare_to)


from src.export import (
    export_mermaid as _export_mermaid,
    export_markdown as _export_markdown,
    export_json as _export_json,
    export_csv as _export_csv,
    export_dot as _export_dot,
)


@mcp.tool
async def export_mermaid(scope: str | None = None, ctx: Context = None) -> dict:
    """Export the blueprint as a Mermaid diagram definition."""
    db = _get_db(ctx)
    return await _export_mermaid(db, scope)


@mcp.tool
async def export_markdown(scope: str | None = None, ctx: Context = None) -> dict:
    """Export the blueprint as a structured Markdown document."""
    db = _get_db(ctx)
    return await _export_markdown(db, scope)


# --- Phase 6-10: New tools ---

# Phase 6B: Natural Language Query

from src.query import query_blueprint as _query_blueprint


@mcp.tool
async def query_blueprint(question: str, ctx: Context = None) -> dict:
    """Ask a natural language question about the blueprint — e.g. 'what connects to the database?' or 'show me all routes'."""
    db = _get_db(ctx)
    return await _query_blueprint(db, question)


# Phase 7A: Restore Snapshot


@mcp.tool
async def restore_snapshot(
    snapshot_id: str, confirm: bool = False, ctx: Context = None
) -> dict:
    """Restore the blueprint to a previous snapshot state. Pass confirm=True to execute."""
    db = _get_db(ctx)
    return await _restore_snapshot(db, snapshot_id, confirm)


# Phase 8A: Health Scoring

from src.health import health_report as _health_report


@mcp.tool
async def health_report(node_id: str | None = None, ctx: Context = None) -> dict:
    """Score blueprint health (0-100) for a single node or the whole project."""
    db = _get_db(ctx)
    return await _health_report(db, node_id)


# Phase 8B: Stale Detection

from src.stale import find_stale as _find_stale


@mcp.tool
async def find_stale(
    days_threshold: int = 30, check_git: bool = True, ctx: Context = None
) -> dict:
    """Detect stale source files, old planned nodes, and missing files."""
    db = _get_db(ctx)
    return await _find_stale(db, days_threshold, check_git)


# Phase 9A: Additional Export Formats


@mcp.tool
async def export_json(scope: str | None = None, ctx: Context = None) -> dict:
    """Export the blueprint as a portable JSON blob."""
    db = _get_db(ctx)
    return await _export_json(db, scope)


@mcp.tool
async def export_csv(scope: str | None = None, ctx: Context = None) -> dict:
    """Export the blueprint nodes as CSV."""
    db = _get_db(ctx)
    return await _export_csv(db, scope)


@mcp.tool
async def export_dot(scope: str | None = None, ctx: Context = None) -> dict:
    """Export the blueprint as a Graphviz DOT diagram."""
    db = _get_db(ctx)
    return await _export_dot(db, scope)


# Phase 9B: Multi-Project Linking

from src.projects import link_projects as _link_projects, get_project_map as _get_project_map


@mcp.tool
async def link_projects(
    source_project: str,
    source_node: str,
    target_project: str,
    target_node: str,
    relationship: str,
    label: str | None = None,
    ctx: Context = None,
) -> dict:
    """Create a cross-project link between nodes in different blueprints."""
    return await _link_projects(source_project, source_node, target_project, target_node, relationship, label)


@mcp.tool
async def get_project_map(project: str | None = None, ctx: Context = None) -> dict:
    """Show all linked projects and their cross-project connections."""
    return await _get_project_map(project)


# Phase 10A: Annotations

from src.annotations import (
    annotate_node as _annotate_node,
    get_annotations as _get_annotations,
    cost_report as _cost_report,
)


@mcp.tool
async def annotate_node(
    node_id: str, key: str, value: str, ctx: Context = None
) -> dict:
    """Add or update an annotation (cost, provider, tier, etc.) on a node."""
    db = _get_db(ctx)
    return await _annotate_node(db, node_id, key, value)


@mcp.tool
async def get_annotations(
    node_id: str | None = None, key: str | None = None, ctx: Context = None
) -> dict:
    """Get annotations for a node or all annotations across the project."""
    db = _get_db(ctx)
    return await _get_annotations(db, node_id, key)


@mcp.tool
async def cost_report(ctx: Context = None) -> dict:
    """Summarize all cost-related annotations by provider and node type."""
    db = _get_db(ctx)
    return await _cost_report(db)


if __name__ == "__main__":
    mcp.run()
