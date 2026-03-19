"""Cost and resource annotations for blueprint nodes."""
from __future__ import annotations

import json
from src.db import Database


async def annotate_node(db: Database, node_id: str, key: str, value: str) -> dict:
    """Add or update an annotation on a node."""
    try:
        return await db.upsert_annotation(node_id, key, value)
    except ValueError as e:
        return {"error": str(e)}


async def get_annotations(db: Database, node_id: str | None = None, key: str | None = None) -> dict:
    """Get annotations, optionally filtered."""
    annotations = await db.get_annotations(node_id, key)
    return {"annotations": annotations, "total": len(annotations)}


async def cost_report(db: Database) -> dict:
    """Aggregate cost annotations into a summary report."""
    # Get all cost-related annotations
    all_anns = await db.get_annotations()

    total_cost = 0.0
    by_provider = {}
    by_node_type = {}
    itemized = []

    # Build node lookup for types
    nodes = await db.get_all_nodes()
    node_map = {n.id: n for n in nodes}

    # Group by node to build itemized list
    node_costs = {}  # node_id -> {cost, provider, name, type}

    for ann in all_anns:
        nid = ann["node_id"]
        if nid not in node_costs:
            node = node_map.get(nid)
            node_costs[nid] = {"name": node.name if node else nid, "type": node.type.value if node else "unknown"}

        if ann["key"] == "monthly_cost":
            try:
                cost = float(ann["value"])
                node_costs[nid]["cost"] = cost
                total_cost += cost
            except (ValueError, TypeError):
                pass
        elif ann["key"] == "provider":
            node_costs[nid]["provider"] = ann["value"]

    for nid, info in node_costs.items():
        cost = info.get("cost", 0)
        provider = info.get("provider", "unknown")
        node_type = info["type"]

        if cost > 0:
            itemized.append({"node": info["name"], "provider": provider, "monthly_cost": cost})
            by_provider[provider] = by_provider.get(provider, 0) + cost
            by_node_type[node_type] = by_node_type.get(node_type, 0) + cost

    return {
        "total_monthly_cost": total_cost,
        "by_provider": by_provider,
        "by_node_type": by_node_type,
        "itemized": itemized,
    }
