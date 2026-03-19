"""Export blueprint as Mermaid diagrams or Markdown documentation."""

from __future__ import annotations

from src.db import Database


async def export_mermaid(db: Database, scope: str | None = None) -> dict:
    """Export the blueprint as a Mermaid graph definition."""
    nodes = await db.get_all_nodes()
    edges = await db.get_all_edges()

    if scope:
        subtree_ids = _get_subtree_ids(scope, nodes)
        nodes = [n for n in nodes if n.id in subtree_ids]
        edge_ids = {n.id for n in nodes}
        edges = [e for e in edges if e.source_id in edge_ids and e.target_id in edge_ids]

    node_map = {n.id: n for n in nodes}

    lines = ["graph TD"]

    # classDef by status
    lines.append("    classDef planned fill:#ffd700,stroke:#b8860b")
    lines.append("    classDef in_progress fill:#87ceeb,stroke:#4682b4")
    lines.append("    classDef built fill:#90ee90,stroke:#228b22")
    lines.append("    classDef broken fill:#ff6347,stroke:#cc0000")
    lines.append("    classDef deprecated fill:#d3d3d3,stroke:#808080")

    # Find parent nodes (for subgraphs)
    parent_ids = {n.parent_id for n in nodes if n.parent_id and n.parent_id in node_map}
    rendered_in_subgraph: set[str] = set()

    for pid in parent_ids:
        parent = node_map[pid]
        safe_pid = _safe_id(pid)
        children = [n for n in nodes if n.parent_id == pid]
        lines.append(f"    subgraph {safe_pid}[{parent.name}]")
        for child in children:
            safe_cid = _safe_id(child.id)
            lines.append(f"        {safe_cid}[{child.name}]")
            lines.append(f"        class {safe_cid} {child.status.value}")
            rendered_in_subgraph.add(child.id)
        lines.append("    end")
        lines.append(f"    class {safe_pid} {parent.status.value}")
        rendered_in_subgraph.add(pid)

    # Render non-subgraph nodes
    for n in nodes:
        if n.id not in rendered_in_subgraph:
            safe_id = _safe_id(n.id)
            lines.append(f"    {safe_id}[{n.name}]")
            lines.append(f"    class {safe_id} {n.status.value}")

    # Render edges
    arrow_map = {
        "connects_to": "-->",
        "reads_from": "-.->",
        "writes_to": "==>",
        "depends_on": "-->",
        "authenticates": "-->",
        "calls": "-->",
        "inherits": "-->",
        "contains": "-->",
        "exposes": "-->",
    }

    for e in edges:
        src = _safe_id(e.source_id)
        tgt = _safe_id(e.target_id)
        arrow = arrow_map.get(e.relationship.value, "-->")
        label = e.label or e.relationship.value
        lines.append(f"    {src} {arrow}|{label}| {tgt}")

    mermaid = "\n".join(lines)

    return {
        "format": "mermaid",
        "content": mermaid,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


async def export_markdown(db: Database, scope: str | None = None) -> dict:
    """Export the blueprint as a structured Markdown document."""
    nodes = await db.get_all_nodes()
    edges = await db.get_all_edges()

    if scope:
        subtree_ids = _get_subtree_ids(scope, nodes)
        nodes = [n for n in nodes if n.id in subtree_ids]
        edge_ids = {n.id for n in nodes}
        edges = [e for e in edges if e.source_id in edge_ids and e.target_id in edge_ids]

    node_map = {n.id: n for n in nodes}

    lines = ["# Architecture Blueprint", ""]

    # Summary
    type_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for n in nodes:
        t = n.type.value
        s = n.status.value
        type_counts[t] = type_counts.get(t, 0) + 1
        status_counts[s] = status_counts.get(s, 0) + 1

    lines.append("## Summary")
    lines.append(f"- **Total components:** {len(nodes)}")
    lines.append(f"- **Total connections:** {len(edges)}")
    lines.append("")

    # Architecture layers
    lines.append("## Architecture Layers")
    roots = [n for n in nodes if n.parent_id is None]
    for root in roots:
        lines.extend(_render_md_tree(root, nodes, indent=0))
    lines.append("")

    # Connections
    lines.append("## Connections")
    for e in edges:
        src = node_map.get(e.source_id)
        tgt = node_map.get(e.target_id)
        if src and tgt:
            label = f" ({e.label})" if e.label else ""
            lines.append(f"- **{src.name}** --[{e.relationship.value}]--> **{tgt.name}**{label}")
    lines.append("")

    # Health
    lines.append("## Health")
    for status, count in sorted(status_counts.items()):
        lines.append(f"- {status}: {count}")
    lines.append("")

    markdown = "\n".join(lines)

    return {
        "format": "markdown",
        "content": markdown,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def _safe_id(uuid_str: str) -> str:
    """Convert UUID to a safe Mermaid node ID."""
    return "n" + uuid_str.replace("-", "")


def _get_subtree_ids(root_id: str, nodes) -> set[str]:
    ids = {root_id}
    changed = True
    while changed:
        changed = False
        for n in nodes:
            if n.parent_id in ids and n.id not in ids:
                ids.add(n.id)
                changed = True
    return ids


def _render_md_tree(node, all_nodes, indent: int) -> list[str]:
    prefix = "  " * indent + "- "
    status_icon = {"built": "+", "planned": "?", "in_progress": "~", "broken": "!", "deprecated": "-"}.get(node.status.value, " ")
    desc = f" — {node.description}" if node.description else ""
    lines = [f"{prefix}[{status_icon}] **{node.name}** ({node.type.value}){desc}"]
    children = [n for n in all_nodes if n.parent_id == node.id]
    for child in children:
        lines.extend(_render_md_tree(child, all_nodes, indent + 1))
    return lines
