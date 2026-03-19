"""Impact analysis — BFS cascade from a node to find affected components."""

from __future__ import annotations

from collections import defaultdict, deque

from src.db import Database


async def impact_analysis(
    db: Database, node_id: str, depth: int = -1, direction: str = "downstream"
) -> dict:
    """Trace the impact of a change to a node through the graph."""
    nodes = await db.get_all_nodes()
    edges = await db.get_all_edges()

    node_map = {n.id: n for n in nodes}
    source_node = node_map.get(node_id)
    if not source_node:
        return {"error": f"Node '{node_id}' not found"}

    # Build adjacency maps
    downstream: dict[str, list[tuple[str, str]]] = defaultdict(list)  # node_id -> [(target_id, relationship)]
    upstream: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for e in edges:
        downstream[e.source_id].append((e.target_id, e.relationship.value))
        upstream[e.target_id].append((e.source_id, e.relationship.value))

    # Select direction
    if direction == "upstream":
        adj = upstream
    elif direction == "both":
        adj = defaultdict(list)
        for k, v in downstream.items():
            adj[k].extend(v)
        for k, v in upstream.items():
            adj[k].extend(v)
    else:
        adj = downstream

    # BFS
    visited: set[str] = {node_id}
    queue: deque[tuple[str, int]] = deque([(node_id, 0)])
    impact_chain: dict[int, list[dict]] = defaultdict(list)
    all_paths: list[list[str]] = []
    current_paths: dict[str, list[str]] = {node_id: [node_id]}

    while queue:
        current_id, current_depth = queue.popleft()
        if depth != -1 and current_depth >= depth:
            continue

        for neighbor_id, relationship in adj.get(current_id, []):
            if neighbor_id not in visited and neighbor_id in node_map:
                visited.add(neighbor_id)
                next_depth = current_depth + 1
                neighbor = node_map[neighbor_id]
                impact_chain[next_depth].append({
                    "node_id": neighbor.id,
                    "node_name": neighbor.name,
                    "node_type": neighbor.type.value,
                    "relationship": relationship,
                    "via": node_map[current_id].name,
                })
                queue.append((neighbor_id, next_depth))

                path = current_paths[current_id] + [neighbor_id]
                current_paths[neighbor_id] = path
                all_paths.append(path)

    # Build sorted chain
    chain = []
    for d in sorted(impact_chain.keys()):
        chain.append({"depth": d, "nodes": impact_chain[d]})

    # Find critical paths (longest)
    critical_paths = []
    if all_paths:
        max_len = max(len(p) for p in all_paths)
        for p in all_paths:
            if len(p) == max_len:
                critical_paths.append([
                    {"node_id": nid, "node_name": node_map[nid].name}
                    for nid in p
                ])

    total_affected = len(visited) - 1  # Exclude source

    # Build summary
    if total_affected == 0:
        summary = f"Changing '{source_node.name}' has no downstream impact."
    else:
        depth_count = len(impact_chain)
        summary = (
            f"Changing '{source_node.name}' affects {total_affected} component(s) "
            f"across {depth_count} depth level(s)."
        )

    return {
        "source_node": {
            "id": source_node.id,
            "name": source_node.name,
            "type": source_node.type.value,
        },
        "direction": direction,
        "impact_chain": chain,
        "total_affected": total_affected,
        "critical_paths": critical_paths,
        "summary": summary,
    }
