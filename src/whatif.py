"""What-if scenario simulation — model the impact of hypothetical changes."""

from __future__ import annotations

from collections import defaultdict, deque

from src.db import Database
from src.tracer import list_entry_points


async def what_if(db: Database, node_id: str, scenario: str) -> dict:
    """Simulate a what-if scenario for a node."""
    nodes = await db.get_all_nodes()
    edges = await db.get_all_edges()

    node_map = {n.id: n for n in nodes}
    target_node = node_map.get(node_id)
    if not target_node:
        return {"error": f"Node '{node_id}' not found"}

    handlers = {
        "remove": _simulate_remove,
        "break": _simulate_break,
        "disconnect": _simulate_disconnect,
        "overload": _simulate_overload,
    }

    handler = handlers.get(scenario)
    if not handler:
        return {"error": f"Unknown scenario '{scenario}'. Use: remove, break, disconnect, overload"}

    result = await handler(db, target_node, nodes, edges, node_map)
    return result


async def _simulate_remove(db, target_node, nodes, edges, node_map) -> dict:
    """What if this node is removed? Find everything that loses a connection or becomes orphaned."""
    directly_affected = []
    indirectly_affected = []

    # Find nodes directly connected
    for e in edges:
        if e.source_id == target_node.id and e.target_id in node_map:
            n = node_map[e.target_id]
            directly_affected.append({
                "node_id": n.id,
                "node_name": n.name,
                "impact": f"Loses {e.relationship.value} connection from {target_node.name}",
            })
        elif e.target_id == target_node.id and e.source_id in node_map:
            n = node_map[e.source_id]
            directly_affected.append({
                "node_id": n.id,
                "node_name": n.name,
                "impact": f"Loses {e.relationship.value} connection to {target_node.name}",
            })

    # Find children that would be orphaned
    children = [n for n in nodes if n.parent_id == target_node.id]
    for child in children:
        directly_affected.append({
            "node_id": child.id,
            "node_name": child.name,
            "impact": f"Orphaned — parent '{target_node.name}' removed",
        })

    # Find indirectly affected (nodes connected to directly affected)
    direct_ids = {d["node_id"] for d in directly_affected}
    for e in edges:
        if e.source_id in direct_ids and e.target_id not in direct_ids and e.target_id != target_node.id:
            n = node_map.get(e.target_id)
            if n and n.id not in {ia["node_id"] for ia in indirectly_affected}:
                indirectly_affected.append({
                    "node_id": n.id,
                    "node_name": n.name,
                    "impact": f"Indirectly affected via {node_map.get(e.source_id, target_node).name}",
                })

    recommendations = []
    if directly_affected:
        recommendations.append(f"Reconnect {len(directly_affected)} directly affected component(s) before removing '{target_node.name}'")
    if children:
        recommendations.append(f"Reassign {len(children)} child node(s) to a new parent")

    return {
        "scenario": "remove",
        "target_node": {"id": target_node.id, "name": target_node.name, "type": target_node.type.value},
        "directly_affected": directly_affected,
        "indirectly_affected": indirectly_affected,
        "broken_flows": [],
        "resilience_score": _calc_resilience(directly_affected, indirectly_affected, nodes),
        "recommendations": recommendations,
        "summary": f"Removing '{target_node.name}' directly affects {len(directly_affected)} and indirectly affects {len(indirectly_affected)} component(s).",
    }


async def _simulate_break(db, target_node, nodes, edges, node_map) -> dict:
    """What if this node breaks? Check for error handling/fallbacks per dependent."""
    directly_affected = []
    broken_flows = []

    for e in edges:
        if e.target_id == target_node.id and e.source_id in node_map:
            dependent = node_map[e.source_id]
            # Check if dependent has error handling
            has_handler = _has_error_handling(dependent, edges, node_map)
            impact = "Has error handling" if has_handler else "NO error handling — will cascade"
            directly_affected.append({
                "node_id": dependent.id,
                "node_name": dependent.name,
                "impact": impact,
                "has_error_handling": has_handler,
            })
            if not has_handler:
                broken_flows.append({
                    "from": dependent.name,
                    "to": target_node.name,
                    "reason": f"No fallback when '{target_node.name}' is broken",
                })

    # Also check nodes that depend on this one via source
    for e in edges:
        if e.source_id == target_node.id and e.target_id in node_map:
            dependent = node_map[e.target_id]
            if dependent.id not in {d["node_id"] for d in directly_affected}:
                has_handler = _has_error_handling(dependent, edges, node_map)
                directly_affected.append({
                    "node_id": dependent.id,
                    "node_name": dependent.name,
                    "impact": "Has error handling" if has_handler else "NO error handling — will cascade",
                    "has_error_handling": has_handler,
                })

    unprotected = [d for d in directly_affected if not d.get("has_error_handling", False)]
    recommendations = []
    if unprotected:
        names = [d["node_name"] for d in unprotected]
        recommendations.append(f"Add error handling to: {', '.join(names)}")
    recommendations.append(f"Consider adding a health check for '{target_node.name}'")

    return {
        "scenario": "break",
        "target_node": {"id": target_node.id, "name": target_node.name, "type": target_node.type.value},
        "directly_affected": directly_affected,
        "indirectly_affected": [],
        "broken_flows": broken_flows,
        "resilience_score": _calc_resilience(directly_affected, [], nodes),
        "recommendations": recommendations,
        "summary": f"If '{target_node.name}' breaks, {len(directly_affected)} component(s) are affected. {len(unprotected)} have no error handling.",
    }


async def _simulate_disconnect(db, target_node, nodes, edges, node_map) -> dict:
    """What if all edges to/from this node are removed? Find unreachable nodes."""
    # Remove all edges involving target
    filtered_edges = [e for e in edges if e.source_id != target_node.id and e.target_id != target_node.id]

    # Find entry points for reachability
    entry_result = await list_entry_points(db)
    entry_ids = {ep["node_id"] for ep in entry_result["entry_points"]}
    if not entry_ids:
        # Use root nodes as fallback
        entry_ids = {n.id for n in nodes if n.parent_id is None and n.id != target_node.id}

    # BFS from all entry points using filtered edges
    outgoing: dict[str, list[str]] = defaultdict(list)
    for e in filtered_edges:
        outgoing[e.source_id].append(e.target_id)

    reachable: set[str] = set()
    queue: deque[str] = deque()
    for eid in entry_ids:
        if eid != target_node.id:
            queue.append(eid)
            reachable.add(eid)

    while queue:
        current = queue.popleft()
        for neighbor in outgoing.get(current, []):
            if neighbor not in reachable and neighbor != target_node.id:
                reachable.add(neighbor)
                queue.append(neighbor)

    # Also add nodes reachable via parent_id (structural relationship)
    changed = True
    while changed:
        changed = False
        for n in nodes:
            if n.parent_id in reachable and n.id not in reachable and n.id != target_node.id:
                reachable.add(n.id)
                changed = True

    # Find orphaned nodes
    all_ids = {n.id for n in nodes} - {target_node.id}
    orphaned_ids = all_ids - reachable
    directly_affected = []
    for oid in orphaned_ids:
        n = node_map.get(oid)
        if n:
            directly_affected.append({
                "node_id": n.id,
                "node_name": n.name,
                "impact": "Becomes unreachable",
            })

    return {
        "scenario": "disconnect",
        "target_node": {"id": target_node.id, "name": target_node.name, "type": target_node.type.value},
        "directly_affected": directly_affected,
        "indirectly_affected": [],
        "broken_flows": [],
        "resilience_score": _calc_resilience(directly_affected, [], nodes),
        "recommendations": [f"Ensure alternative paths exist to {len(directly_affected)} orphaned node(s)"] if directly_affected else [],
        "summary": f"Disconnecting '{target_node.name}' leaves {len(directly_affected)} node(s) unreachable.",
    }


async def _simulate_overload(db, target_node, nodes, edges, node_map) -> dict:
    """What if this node is overloaded? Check for cache/queue/load balancer."""
    # Check for protective nodes
    protective_types = {"cache", "queue"}
    protective_names = {"load_balancer", "rate_limit", "throttle", "circuit_breaker"}

    has_cache = False
    has_queue = False
    has_lb = False

    for e in edges:
        connected_id = None
        if e.source_id == target_node.id:
            connected_id = e.target_id
        elif e.target_id == target_node.id:
            connected_id = e.source_id

        if connected_id and connected_id in node_map:
            connected = node_map[connected_id]
            if connected.type.value == "cache":
                has_cache = True
            if connected.type.value == "queue":
                has_queue = True
            if any(kw in connected.name.lower() for kw in protective_names):
                has_lb = True

    score = 0.0
    protections = []
    if has_cache:
        score += 0.35
        protections.append("cache")
    if has_queue:
        score += 0.35
        protections.append("queue")
    if has_lb:
        score += 0.30
        protections.append("load balancer / rate limiter")

    recommendations = []
    if not has_cache:
        recommendations.append(f"Add a cache in front of '{target_node.name}' to absorb read load")
    if not has_queue:
        recommendations.append(f"Add a message queue to buffer writes to '{target_node.name}'")
    if not has_lb:
        recommendations.append(f"Add rate limiting or load balancing for '{target_node.name}'")

    # Find dependents
    directly_affected = []
    for e in edges:
        if e.target_id == target_node.id and e.source_id in node_map:
            n = node_map[e.source_id]
            directly_affected.append({
                "node_id": n.id,
                "node_name": n.name,
                "impact": "May experience degraded performance or timeouts",
            })

    return {
        "scenario": "overload",
        "target_node": {"id": target_node.id, "name": target_node.name, "type": target_node.type.value},
        "directly_affected": directly_affected,
        "indirectly_affected": [],
        "broken_flows": [],
        "resilience_score": round(score, 2),
        "protections": protections,
        "recommendations": recommendations,
        "summary": f"'{target_node.name}' overload resilience: {score:.0%}. Protections: {', '.join(protections) if protections else 'none'}.",
    }


def _has_error_handling(node, edges, node_map) -> bool:
    """Check if a node has error handling connections."""
    error_names = {"error", "handler", "fallback", "retry", "circuit_breaker"}
    for e in edges:
        if e.source_id == node.id:
            target = node_map.get(e.target_id)
            if target and any(kw in target.name.lower() for kw in error_names):
                return True
            if e.relationship.value in ("observes", "delegates"):
                return True
    return False


def _calc_resilience(directly_affected, indirectly_affected, nodes) -> float:
    """Calculate resilience score (1.0 = no impact, 0.0 = total impact)."""
    total = len(nodes)
    if total == 0:
        return 1.0
    affected = len(directly_affected) + len(indirectly_affected)
    return round(max(0.0, 1.0 - (affected / total)), 2)
