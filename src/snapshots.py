"""Snapshot management — save and compare blueprint states."""

from __future__ import annotations

import json

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


async def restore_snapshot(db: Database, snapshot_id: str, confirm: bool = False) -> dict:
    """Restore a snapshot, replacing all current nodes and edges."""
    if confirm is not True:
        return {"error": "Must pass confirm=True to restore. This replaces all current nodes and edges."}

    snap = await db.get_snapshot(snapshot_id)
    if not snap:
        return {"error": f"Snapshot '{snapshot_id}' not found"}

    # Delete all current nodes and edges
    await db.db.execute("DELETE FROM edges")
    await db.db.execute("DELETE FROM nodes")

    # Re-insert nodes from snapshot data
    for node in snap["node_data"]:
        await db.db.execute(
            """INSERT INTO nodes (id, name, type, status, parent_id, description, metadata, source_file, source_line, template_origin, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                node["id"],
                node["name"],
                node["type"],
                node["status"],
                node.get("parent_id"),
                node.get("description"),
                json.dumps(node["metadata"]) if node.get("metadata") is not None else None,
                node.get("source_file"),
                node.get("source_line"),
                node.get("template_origin"),
                node.get("created_at"),
                node.get("updated_at"),
            ),
        )

    # Re-insert edges from snapshot data
    for edge in snap["edge_data"]:
        await db.db.execute(
            """INSERT INTO edges (id, source_id, target_id, relationship, label, metadata, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                edge["id"],
                edge["source_id"],
                edge["target_id"],
                edge["relationship"],
                edge.get("label"),
                json.dumps(edge["metadata"]) if edge.get("metadata") is not None else None,
                edge.get("status", "active"),
                edge.get("created_at"),
            ),
        )

    # Log changelog entry and commit
    await db.log_change("snapshot_restored", "snapshot", snapshot_id, {"name": snap["name"]})
    await db.db.commit()

    return {
        "restored": True,
        "snapshot_name": snap["name"],
        "node_count": len(snap["node_data"]),
        "edge_count": len(snap["edge_data"]),
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
