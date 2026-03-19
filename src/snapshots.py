"""Snapshot management — save and compare blueprint states."""

from __future__ import annotations

from src.db import Database


async def snapshot_blueprint(db: Database, name: str, description: str | None = None) -> dict:
    """Create a snapshot of the current blueprint state."""
    return await db.create_snapshot(name, description)


async def list_snapshots(db: Database) -> dict:
    """List all saved snapshots."""
    snapshots = await db.list_snapshots()
    return {"snapshots": snapshots, "total": len(snapshots)}


async def compare_snapshots(
    db: Database, snapshot_id: str, compare_to: str | None = None
) -> dict:
    """Compare a snapshot against another snapshot or current state."""
    snap = await db.get_snapshot(snapshot_id)
    if not snap:
        return {"error": f"Snapshot '{snapshot_id}' not found"}

    if compare_to:
        other = await db.get_snapshot(compare_to)
        if not other:
            return {"error": f"Snapshot '{compare_to}' not found"}
        other_nodes = other["node_data"]
        other_edges = other["edge_data"]
        compare_label = other["name"]
    else:
        # Compare against current state
        nodes = await db.get_all_nodes()
        edges = await db.get_all_edges()
        other_nodes = [n.model_dump() for n in nodes]
        other_edges = [e.model_dump() for e in edges]
        compare_label = "current state"

    # Diff nodes
    snap_node_map = {n["id"]: n for n in snap["node_data"]}
    other_node_map = {n["id"]: n for n in other_nodes}

    added_nodes = []
    removed_nodes = []
    changed_nodes = []

    for nid, node in other_node_map.items():
        if nid not in snap_node_map:
            added_nodes.append({"id": nid, "name": node["name"], "type": node["type"]})

    for nid, node in snap_node_map.items():
        if nid not in other_node_map:
            removed_nodes.append({"id": nid, "name": node["name"], "type": node["type"]})
        elif nid in other_node_map:
            changes = _diff_dicts(node, other_node_map[nid], exclude={"created_at", "updated_at", "children", "edges"})
            if changes:
                changed_nodes.append({
                    "id": nid,
                    "name": node["name"],
                    "changes": changes,
                })

    # Diff edges
    snap_edge_map = {e["id"]: e for e in snap["edge_data"]}
    other_edge_map = {e["id"]: e for e in other_edges}

    added_edges = []
    removed_edges = []

    for eid, edge in other_edge_map.items():
        if eid not in snap_edge_map:
            added_edges.append({
                "id": eid,
                "source_id": edge["source_id"],
                "target_id": edge["target_id"],
                "relationship": edge["relationship"],
            })

    for eid, edge in snap_edge_map.items():
        if eid not in other_edge_map:
            removed_edges.append({
                "id": eid,
                "source_id": edge["source_id"],
                "target_id": edge["target_id"],
                "relationship": edge["relationship"],
            })

    return {
        "snapshot": snap["name"],
        "compared_to": compare_label,
        "nodes": {
            "added": added_nodes,
            "removed": removed_nodes,
            "changed": changed_nodes,
        },
        "edges": {
            "added": added_edges,
            "removed": removed_edges,
        },
        "summary": {
            "nodes_added": len(added_nodes),
            "nodes_removed": len(removed_nodes),
            "nodes_changed": len(changed_nodes),
            "edges_added": len(added_edges),
            "edges_removed": len(removed_edges),
        },
    }


def _diff_dicts(old: dict, new: dict, exclude: set | None = None) -> list[dict]:
    """Compare two dicts, return list of changes."""
    changes = []
    exclude = exclude or set()
    all_keys = set(old.keys()) | set(new.keys()) - exclude
    for key in all_keys:
        if key in exclude:
            continue
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val != new_val:
            changes.append({"field": key, "old": old_val, "new": new_val})
    return changes
