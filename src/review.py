"""Generate LLM-optimized review prompts from the blueprint."""

from __future__ import annotations

from src.db import Database
from src.analyzer import analyze
from src.questions import get_project_questions


async def get_review_prompt(
    db: Database, focus: str = "all", node_id: str | None = None
) -> dict:
    """Generate a structured review document for the blueprint."""
    nodes = await db.get_all_nodes()
    edges = await db.get_all_edges()

    # If scoped to a node, filter subtree
    if node_id:
        subtree_ids = _get_subtree_ids(node_id, nodes)
        nodes = [n for n in nodes if n.id in subtree_ids]
        edge_ids = {n.id for n in nodes}
        edges = [e for e in edges if e.source_id in edge_ids or e.target_id in edge_ids]

    node_map = {n.id: n for n in nodes}

    sections = []

    # SYSTEM OVERVIEW
    type_counts: dict[str, int] = {}
    for n in nodes:
        t = n.type.value
        type_counts[t] = type_counts.get(t, 0) + 1

    overview_lines = [
        "# SYSTEM OVERVIEW",
        f"Total components: {len(nodes)}",
        f"Total connections: {len(edges)}",
        "Component breakdown:",
    ]
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        overview_lines.append(f"  - {t}: {c}")
    sections.append("\n".join(overview_lines))

    # ARCHITECTURE LAYERS
    roots = [n for n in nodes if n.parent_id is None]
    layer_lines = ["# ARCHITECTURE LAYERS"]
    for root in roots:
        layer_lines.extend(_render_tree(root, nodes, indent=0))
    sections.append("\n".join(layer_lines))

    # CONNECTIONS MAP
    conn_lines = ["# CONNECTIONS MAP"]
    for e in edges:
        src = node_map.get(e.source_id)
        tgt = node_map.get(e.target_id)
        if src and tgt:
            label = f" [{e.label}]" if e.label else ""
            conn_lines.append(f"  {src.name} --({e.relationship.value})--> {tgt.name}{label}")
    sections.append("\n".join(conn_lines))

    # CURRENT ISSUES
    issues = await analyze(db)
    issue_lines = ["# CURRENT ISSUES"]
    if issues:
        for issue in issues:
            node_names = [node_map[nid].name for nid in issue.node_ids if nid in node_map]
            issue_lines.append(f"  [{issue.severity.value.upper()}] {issue.message}")
            if node_names:
                issue_lines.append(f"    Nodes: {', '.join(node_names)}")
            issue_lines.append(f"    Suggestion: {issue.suggestion}")
    else:
        issue_lines.append("  No issues detected.")
    sections.append("\n".join(issue_lines))

    # GAPS DETECTED
    questions_result = await get_project_questions(db, category="all", node_id=node_id)
    gap_lines = ["# GAPS DETECTED"]
    questions = questions_result["questions"]
    if questions:
        for q in questions:
            gap_lines.append(f"  [{q['severity'].upper()}] {q['question']}")
            gap_lines.append(f"    {q['context']}")
    else:
        gap_lines.append("  No gaps detected.")
    sections.append("\n".join(gap_lines))

    # REVIEW QUESTIONS
    review_lines = ["# REVIEW QUESTIONS"]
    if focus != "all":
        questions = [q for q in questions if q["category"] == focus]
    if questions:
        for q in questions:
            review_lines.append(f"  - [{q['category']}] {q['question']}")
    else:
        review_lines.append("  No review questions for the selected focus.")
    sections.append("\n".join(review_lines))

    review_text = "\n\n".join(sections)

    return {
        "review_prompt": review_text,
        "sections": len(sections),
        "total_issues": len(issues),
        "total_questions": len(questions_result["questions"]),
    }


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


def _render_tree(node, all_nodes, indent: int) -> list[str]:
    prefix = "  " * indent + ("└── " if indent > 0 else "")
    lines = [f"{prefix}{node.name} ({node.type.value}) [{node.status.value}]"]
    children = [n for n in all_nodes if n.parent_id == node.id]
    for child in children:
        lines.extend(_render_tree(child, all_nodes, indent + 1))
    return lines
