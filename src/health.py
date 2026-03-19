"""Health report module — scores individual nodes and overall project health."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from src.db import Database
from src.models import Edge, Node


def _score_node(node: Node, edges: list[Edge], all_nodes: list[Node]) -> dict:
    """Score a single node on a 0-100 scale, returning per-category breakdown."""
    breakdown: dict[str, int] = {}

    # Has description: +15
    if node.description:
        breakdown["description"] = 15
    else:
        breakdown["description"] = 0

    # Has source_file: +15
    if node.source_file:
        breakdown["source_file"] = 15
    else:
        breakdown["source_file"] = 0

    # Source file exists on disk: +10
    if node.source_file and os.path.isfile(node.source_file):
        breakdown["source_file_exists"] = 10
    else:
        breakdown["source_file_exists"] = 0

    # Has at least one edge: +20
    node_edge_count = sum(
        1 for e in edges if e.source_id == node.id or e.target_id == node.id
    )
    if node_edge_count > 0:
        breakdown["has_edges"] = 20
    else:
        breakdown["has_edges"] = 0

    # Status is 'built': +15
    if node.status.value == "built":
        breakdown["status_built"] = 15
    else:
        breakdown["status_built"] = 0

    # Status is NOT 'broken' or 'deprecated': +10
    if node.status.value not in ("broken", "deprecated"):
        breakdown["status_not_broken"] = 10
    else:
        breakdown["status_not_broken"] = 0

    # Has children: +10
    has_children = any(n.parent_id == node.id for n in all_nodes)
    if has_children:
        breakdown["has_children"] = 10
    else:
        breakdown["has_children"] = 0

    # Has metadata: +5
    if node.metadata:
        breakdown["has_metadata"] = 5
    else:
        breakdown["has_metadata"] = 0

    return breakdown


def _grade(score: int) -> str:
    """Map a 0-100 score to a letter grade."""
    if score >= 90:
        return "A"
    elif score >= 75:
        return "B"
    elif score >= 60:
        return "C"
    elif score >= 40:
        return "D"
    else:
        return "F"


async def health_report(db: Database, node_id: str | None = None) -> dict:
    """Generate a health report for a single node or the entire project.

    Args:
        db: The Blueprint database instance.
        node_id: If provided, return health for just this node.

    Returns:
        A dict with scoring details (see module docstring for format).
    """
    all_nodes = await db.get_all_nodes()
    all_edges = await db.get_all_edges()

    # --- Single-node report ---
    if node_id is not None:
        target = None
        for n in all_nodes:
            if n.id == node_id:
                target = n
                break
        if target is None:
            return {"error": f"Node '{node_id}' not found"}

        breakdown = _score_node(target, all_edges, all_nodes)
        score = sum(breakdown.values())
        return {
            "node_id": target.id,
            "node_name": target.name,
            "score": score,
            "grade": _grade(score),
            "breakdown": breakdown,
        }

    # --- Project-level report ---
    if not all_nodes:
        return {
            "overall_score": 0,
            "grade": "F",
            "total_nodes": 0,
            "node_scores": {"healthy": 0, "needs_attention": 0, "critical": 0},
            "top_issues": [],
            "recommendations": [],
        }

    # Score every node
    node_scores: list[int] = []
    for n in all_nodes:
        breakdown = _score_node(n, all_edges, all_nodes)
        node_scores.append(sum(breakdown.values()))

    avg_score = sum(node_scores) / len(node_scores)

    # Build node_ids set for quick lookup in edge membership
    node_ids_with_edges: set[str] = set()
    for e in all_edges:
        node_ids_with_edges.add(e.source_id)
        node_ids_with_edges.add(e.target_id)

    # Penalties
    orphan_count = sum(1 for n in all_nodes if n.id not in node_ids_with_edges)
    broken_count = sum(1 for n in all_nodes if n.status.value == "broken")

    now = datetime.now(timezone.utc)
    stale_planned_count = 0
    for n in all_nodes:
        if n.status.value == "planned" and n.created_at:
            try:
                created = datetime.fromisoformat(n.created_at.replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                if (now - created).days > 30:
                    stale_planned_count += 1
            except (ValueError, TypeError):
                pass

    penalty = (orphan_count * 2) + (broken_count * 3) + (stale_planned_count * 1)

    # Analyzer bonus
    analyzer_bonus = 0
    try:
        from src.analyzer import analyze as _analyze

        issues = await _analyze(db)
        if len(issues) == 0:
            analyzer_bonus = 10
    except Exception:
        pass

    overall = avg_score - penalty + analyzer_bonus
    overall = max(0, min(100, int(round(overall))))

    # Bucket node scores
    healthy = sum(1 for s in node_scores if s >= 90)
    needs_attention = sum(1 for s in node_scores if 60 <= s < 90)
    critical = sum(1 for s in node_scores if s < 60)

    # Build top issues list
    top_issues: list[str] = []
    if orphan_count:
        top_issues.append(f"{orphan_count} orphan node(s) with no connections")
    if broken_count:
        top_issues.append(f"{broken_count} node(s) in broken status")
    if stale_planned_count:
        top_issues.append(
            f"{stale_planned_count} planned node(s) older than 30 days"
        )
    if critical:
        top_issues.append(f"{critical} node(s) scored below 60 (critical)")

    # Recommendations
    recommendations: list[str] = []
    if orphan_count:
        recommendations.append(
            "Connect orphan nodes to the rest of the architecture with edges"
        )
    if broken_count:
        recommendations.append(
            "Investigate and fix broken nodes or mark them as deprecated"
        )
    if stale_planned_count:
        recommendations.append(
            "Review stale planned nodes — build them or remove if no longer needed"
        )
    no_desc = sum(1 for n in all_nodes if not n.description)
    if no_desc:
        recommendations.append(
            f"Add descriptions to {no_desc} node(s) to improve documentation"
        )

    return {
        "overall_score": overall,
        "grade": _grade(overall),
        "total_nodes": len(all_nodes),
        "node_scores": {
            "healthy": healthy,
            "needs_attention": needs_attention,
            "critical": critical,
        },
        "top_issues": top_issues,
        "recommendations": recommendations,
    }
