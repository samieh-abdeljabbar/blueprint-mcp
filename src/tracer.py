"""Flow tracing — entry point discovery and step-by-step flow analysis."""

from __future__ import annotations

from collections import defaultdict

from src.db import Database
from src.models import EntryPoint, FlowGap, FlowStep


async def list_entry_points(db: Database) -> dict:
    """Find all entry points in the blueprint."""
    nodes = await db.get_all_nodes()
    edges = await db.get_all_edges()

    node_map = {n.id: n for n in nodes}
    entry_types = {"route", "api", "webhook", "view"}

    # Build incoming/outgoing maps
    incoming: dict[str, int] = defaultdict(int)
    outgoing: dict[str, int] = defaultdict(int)
    for e in edges:
        incoming[e.target_id] += 1
        outgoing[e.source_id] += 1

    entries: list[EntryPoint] = []
    seen = set()

    for n in nodes:
        is_entry = False
        reason = ""

        if n.type.value in entry_types:
            is_entry = True
            reason = f"{n.type.value} endpoint"
        elif outgoing.get(n.id, 0) > 0 and incoming.get(n.id, 0) == 0 and n.parent_id is None:
            is_entry = True
            reason = "root node with outgoing connections"

        if is_entry and n.id not in seen:
            seen.add(n.id)
            trigger = _suggest_trigger(n)
            entries.append(EntryPoint(
                node_id=n.id,
                node_name=n.name,
                node_type=n.type.value,
                description=n.description or reason,
                connections_out=outgoing.get(n.id, 0),
                suggested_trigger=trigger,
            ))

    return {
        "entry_points": [ep.model_dump() for ep in entries],
        "total": len(entries),
    }


def _suggest_trigger(node) -> str:
    name_lower = node.name.lower()
    if "login" in name_lower or "auth" in name_lower:
        return "User login request"
    if "signup" in name_lower or "register" in name_lower:
        return "New user registration"
    if "webhook" in name_lower:
        return "External webhook event"
    if node.type.value == "route":
        return f"HTTP request to {node.name}"
    if node.type.value == "api":
        return f"API call to {node.name}"
    return f"Trigger {node.name}"


async def trace_flow(
    db: Database,
    start_node_id: str,
    trigger: str | None = None,
    max_depth: int = 20,
    include_error_paths: bool = True,
) -> dict:
    """Trace a request/data flow through the system starting from a node."""
    nodes = await db.get_all_nodes()
    edges = await db.get_all_edges()

    node_map = {n.id: n for n in nodes}
    start_node = node_map.get(start_node_id)
    if not start_node:
        return {"error": f"Node '{start_node_id}' not found"}

    # Build outgoing edge map
    outgoing: dict[str, list] = defaultdict(list)
    for e in edges:
        outgoing[e.source_id].append(e)

    # BFS trace
    visited: set[str] = set()
    steps: list[FlowStep] = []
    dead_ends: list[str] = []
    queue = [(start_node_id, None, None, 0)]  # (node_id, relationship, edge_label, step_num)
    step_counter = 0
    total_branches = 0

    while queue:
        current_id, rel, edge_label, depth = queue.pop(0)

        if depth >= max_depth:
            continue

        is_cycle = current_id in visited
        if is_cycle:
            node = node_map.get(current_id)
            if node:
                steps.append(FlowStep(
                    step=step_counter,
                    node_id=current_id,
                    node_name=node.name,
                    node_type=node.type.value,
                    relationship=rel,
                    edge_label=edge_label,
                    is_cycle=True,
                ))
                step_counter += 1
            continue

        visited.add(current_id)
        node = node_map.get(current_id)
        if not node:
            continue

        out_edges = outgoing.get(current_id, [])
        branches = len(out_edges)
        if branches > 1:
            total_branches += 1

        # Detect gaps
        gaps = _detect_gaps(node, out_edges, edges, node_map, include_error_paths)

        steps.append(FlowStep(
            step=step_counter,
            node_id=current_id,
            node_name=node.name,
            node_type=node.type.value,
            relationship=rel,
            edge_label=edge_label,
            branches=branches,
            gaps=gaps,
        ))
        step_counter += 1

        if not out_edges:
            dead_ends.append(node.name)

        for e in out_edges:
            if e.target_id in node_map:
                queue.append((e.target_id, e.relationship.value, e.label, depth + 1))

    flow_name = trigger or f"Flow from {start_node.name}"
    gaps_found = sum(len(s.gaps) for s in steps)

    return {
        "flow_name": flow_name,
        "start_node": {
            "id": start_node.id,
            "name": start_node.name,
            "type": start_node.type.value,
        },
        "total_steps": len(steps),
        "total_branches": total_branches,
        "gaps_found": gaps_found,
        "steps": [s.model_dump() for s in steps],
        "dead_ends": dead_ends,
        "flow_summary": f"{flow_name}: {len(steps)} steps, {total_branches} branches, {gaps_found} gaps, {len(dead_ends)} dead ends",
    }


def _detect_gaps(
    node, out_edges: list, all_edges: list, node_map: dict, include_error_paths: bool
) -> list[FlowGap]:
    """Detect quality gaps at a node."""
    gaps = []

    # DEAD_END — no outgoing edges and not a terminal type
    terminal_types = {"database", "table", "cache", "queue", "external", "config"}
    if not out_edges and node.type.value not in terminal_types:
        gaps.append(FlowGap(
            type="DEAD_END",
            node_id=node.id,
            node_name=node.name,
            message=f"'{node.name}' has no outgoing connections — flow stops here",
            severity="warning",
        ))

    # NO_ERROR_HANDLING — node calls something but has no error handler
    if include_error_paths and out_edges:
        has_error = any(
            e.relationship.value in ("observes", "delegates") or
            (e.target_id in node_map and "error" in node_map[e.target_id].name.lower())
            for e in out_edges
        )
        if not has_error and node.type.value in ("service", "route", "api", "function"):
            gaps.append(FlowGap(
                type="NO_ERROR_HANDLING",
                node_id=node.id,
                node_name=node.name,
                message=f"'{node.name}' has no error handling path",
                severity="info",
            ))

    # UNPROTECTED_WRITE — writes to DB/table with no auth edge
    for e in out_edges:
        if e.relationship.value in ("writes_to", "creates", "updates"):
            target = node_map.get(e.target_id)
            if target and target.type.value in ("database", "table"):
                # Check if node has auth
                has_auth = any(
                    ae.relationship.value == "authenticates" and
                    (ae.target_id == node.id or ae.source_id == node.id)
                    for ae in all_edges
                )
                if not has_auth:
                    gaps.append(FlowGap(
                        type="UNPROTECTED_WRITE",
                        node_id=node.id,
                        node_name=node.name,
                        message=f"'{node.name}' writes to '{target.name}' without authentication",
                        severity="warning",
                    ))

    # NO_FALLBACK — calls external with no fallback
    for e in out_edges:
        target = node_map.get(e.target_id)
        if target and target.type.value == "external":
            has_fallback = any(
                oe.relationship.value in ("delegates", "observes") or
                (oe.target_id in node_map and
                 any(kw in node_map[oe.target_id].name.lower() for kw in ("fallback", "retry", "circuit")))
                for oe in out_edges if oe.target_id != target.id
            )
            if not has_fallback:
                gaps.append(FlowGap(
                    type="NO_FALLBACK",
                    node_id=node.id,
                    node_name=node.name,
                    message=f"'{node.name}' calls external '{target.name}' with no fallback",
                    severity="warning",
                ))

    return gaps
