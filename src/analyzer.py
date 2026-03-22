"""Graph analyzer — detects architectural issues in the blueprint."""

from __future__ import annotations

import os
from collections import defaultdict

from src.db import Database
from src.models import Edge, Issue, IssueSeverity, Node


async def analyze(
    db: Database, severity: IssueSeverity | None = None
) -> list[Issue]:
    nodes, edges = await _load_graph(db)
    issues: list[Issue] = []
    issues.extend(_check_orphaned_tables(nodes, edges))
    issues.extend(_check_broken_edges(edges))
    issues.extend(_check_missing_database(nodes, edges))
    issues.extend(_check_circular_dependencies(nodes, edges))
    issues.extend(_check_unimplemented_planned(nodes))
    issues.extend(_check_missing_auth(nodes, edges))
    issues.extend(_check_single_point_of_failure(nodes, edges))
    issues.extend(_check_stale_nodes(nodes, db.db_path))
    issues.extend(_check_unused_modules(nodes, edges))
    issues.extend(_check_missing_descriptions(nodes))
    if severity:
        issues = [i for i in issues if i.severity == severity]
    return issues


async def _load_graph(db: Database) -> tuple[list[Node], list[Edge]]:
    bp = await db.get_blueprint()
    nodes = [Node(**n) for n in bp["nodes"]]
    edges = [Edge(**e) for e in bp["edges"]]
    return nodes, edges


def _check_orphaned_tables(nodes: list[Node], edges: list[Edge]) -> list[Issue]:
    """Table nodes with no reads_from/writes_to/connects_to edges."""
    issues = []
    table_ids = {n.id for n in nodes if n.type.value == "table"}
    connected_rels = {"reads_from", "writes_to", "connects_to"}

    connected_tables = set()
    for e in edges:
        if e.relationship.value in connected_rels:
            if e.source_id in table_ids:
                connected_tables.add(e.source_id)
            if e.target_id in table_ids:
                connected_tables.add(e.target_id)

    for n in nodes:
        if n.type.value == "table" and n.id not in connected_tables:
            issues.append(Issue(
                severity=IssueSeverity.critical,
                type="orphaned_table",
                message=f"Table '{n.name}' has no data connections (reads_from/writes_to/connects_to)",
                node_ids=[n.id],
                suggestion=f"Connect '{n.name}' to a service or API that reads from or writes to it",
            ))
    return issues


def _check_broken_edges(edges: list[Edge]) -> list[Issue]:
    """Edges with status='broken'."""
    issues = []
    for e in edges:
        if e.status.value == "broken":
            issues.append(Issue(
                severity=IssueSeverity.critical,
                type="broken_reference",
                message=f"Edge {e.id} ({e.relationship.value}) is marked as broken",
                node_ids=[e.source_id, e.target_id],
                suggestion="Investigate and repair or remove the broken connection",
            ))
    return issues


def _check_missing_database(nodes: list[Node], edges: list[Edge]) -> list[Issue]:
    """Services with route children but no edge to any database."""
    issues = []
    node_map = {n.id: n for n in nodes}
    db_ids = {n.id for n in nodes if n.type.value == "database"}

    # Find services that have route children
    service_ids_with_routes = set()
    for n in nodes:
        if n.type.value == "route" and n.parent_id:
            parent = node_map.get(n.parent_id)
            if parent and parent.type.value == "service":
                service_ids_with_routes.add(parent.id)

    # Check if those services connect to a database
    services_with_db = set()
    for e in edges:
        if e.source_id in service_ids_with_routes and e.target_id in db_ids:
            services_with_db.add(e.source_id)
        if e.target_id in service_ids_with_routes and e.source_id in db_ids:
            services_with_db.add(e.target_id)

    for sid in service_ids_with_routes - services_with_db:
        svc = node_map[sid]
        issues.append(Issue(
            severity=IssueSeverity.critical,
            type="missing_database",
            message=f"Service '{svc.name}' has routes but no database connection",
            node_ids=[sid],
            suggestion=f"Connect '{svc.name}' to a database node",
        ))
    return issues


def _check_circular_dependencies(
    nodes: list[Node], edges: list[Edge]
) -> list[Issue]:
    """DFS cycle detection on depends_on edges (3-color algorithm)."""
    issues = []
    # Build adjacency list for depends_on edges only
    adj: dict[str, list[str]] = defaultdict(list)
    node_map = {n.id: n for n in nodes}

    for e in edges:
        if e.relationship.value == "depends_on":
            adj[e.source_id].append(e.target_id)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n.id: WHITE for n in nodes}

    def dfs(u: str, path: list[str]) -> list[str] | None:
        color[u] = GRAY
        path.append(u)
        for v in adj.get(u, []):
            if v not in color:
                continue
            if color[v] == GRAY:
                # Found cycle — extract it
                if v in path:
                    cycle_start = path.index(v)
                    return path[cycle_start:]
                # v is GRAY from a previous DFS tree — skip
                continue
            if color[v] == WHITE:
                result = dfs(v, path)
                if result:
                    return result
        path.pop()
        color[u] = BLACK
        return None

    found_cycles: set[frozenset[str]] = set()
    for n in nodes:
        if color[n.id] == WHITE:
            cycle = dfs(n.id, [])
            if cycle:
                cycle_key = frozenset(cycle)
                if cycle_key not in found_cycles:
                    found_cycles.add(cycle_key)
                    names = [node_map[nid].name for nid in cycle if nid in node_map]

                    # Same-directory cycles (e.g., HalfEdge ↔ Vertex) are often
                    # intentional data structure patterns — downgrade to info
                    cycle_dirs = set()
                    for nid in cycle:
                        m = node_map.get(nid)
                        if m and m.source_file:
                            cycle_dirs.add(os.path.dirname(m.source_file))
                    if len(cycle_dirs) == 1 and cycle_dirs != {"", "."}:
                        severity = IssueSeverity.info
                        suggestion = (
                            "These types reference each other within the same module "
                            "— may be intentional for data structures"
                        )
                    else:
                        severity = IssueSeverity.critical
                        suggestion = "Break the cycle by removing or reversing one dependency"

                    issues.append(Issue(
                        severity=severity,
                        type="circular_dependency",
                        message=f"Circular dependency detected: {' → '.join(names)}",
                        node_ids=list(cycle),
                        suggestion=suggestion,
                    ))
    return issues


def _check_unimplemented_planned(nodes: list[Node]) -> list[Issue]:
    """Nodes with status='planned'."""
    issues = []
    for n in nodes:
        if n.status.value == "planned":
            issues.append(Issue(
                severity=IssueSeverity.warning,
                type="unimplemented_planned",
                message=f"'{n.name}' is still in planned status",
                node_ids=[n.id],
                suggestion=f"Implement '{n.name}' or update its status",
            ))
    return issues


def _check_missing_auth(nodes: list[Node], edges: list[Edge]) -> list[Issue]:
    """API/route nodes with no authenticates edge."""
    issues = []
    auth_targets = set()
    for e in edges:
        if e.relationship.value == "authenticates":
            auth_targets.add(e.target_id)
            auth_targets.add(e.source_id)

    for n in nodes:
        if n.type.value in ("api", "route") and n.id not in auth_targets:
            issues.append(Issue(
                severity=IssueSeverity.warning,
                type="missing_auth",
                message=f"'{n.name}' has no authentication",
                node_ids=[n.id],
                suggestion=f"Add authentication to '{n.name}'",
            ))
    return issues


def _check_single_point_of_failure(
    nodes: list[Node], edges: list[Edge]
) -> list[Issue]:
    """Tarjan's articulation point algorithm on undirected graph."""
    issues = []
    if len(nodes) < 3:
        return issues

    # Build undirected adjacency
    adj: dict[str, set[str]] = defaultdict(set)
    node_ids = {n.id for n in nodes}
    for e in edges:
        if e.source_id in node_ids and e.target_id in node_ids:
            adj[e.source_id].add(e.target_id)
            adj[e.target_id].add(e.source_id)

    node_map = {n.id: n for n in nodes}
    disc: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    ap: set[str] = set()
    timer = [0]

    def dfs(u: str):
        children = 0
        disc[u] = low[u] = timer[0]
        timer[0] += 1
        for v in adj.get(u, set()):
            if v not in disc:
                children += 1
                parent[v] = u
                dfs(v)
                low[u] = min(low[u], low[v])
                # u is AP if: (1) root with 2+ children, or (2) non-root with low[v] >= disc[u]
                if parent[u] is None and children > 1:
                    ap.add(u)
                if parent[u] is not None and low[v] >= disc[u]:
                    ap.add(u)
            elif v != parent.get(u):
                low[u] = min(low[u], disc[v])

    # Run on all connected components
    for n in nodes:
        if n.id not in disc and n.id in adj:
            parent[n.id] = None
            dfs(n.id)

    # Entry points and foundational types are always articulation points but flagging them is noise
    entry_point_types = {"system", "struct", "protocol", "enum_def"}
    entry_point_names = {"main", "app", "index", "root"}
    for nid in ap:
        n = node_map.get(nid)
        if not n:
            continue
        # Skip system-level nodes (project roots)
        if n.type.value in entry_point_types:
            continue
        # Skip common entry point names
        if n.name.lower() in entry_point_names:
            continue
        # Skip nodes explicitly marked as entry points
        if n.metadata and n.metadata.get("entry_point"):
            continue
        issues.append(Issue(
            severity=IssueSeverity.warning,
            type="single_point_of_failure",
            message=f"'{n.name}' is a single point of failure (articulation point)",
            node_ids=[nid],
            suggestion=f"Add redundancy for '{n.name}' to avoid single point of failure",
        ))
    return issues


def _check_stale_nodes(nodes: list[Node], db_path: str) -> list[Issue]:
    """Nodes where source_file doesn't exist on disk."""
    issues = []
    # Resolve relative to the directory containing the DB
    base_dir = os.path.dirname(os.path.abspath(db_path))
    # Also check common subdirectories (e.g., src-tauri/ for Tauri projects)
    sub_dirs = [base_dir]
    for entry in os.listdir(base_dir) if os.path.isdir(base_dir) else []:
        sub = os.path.join(base_dir, entry)
        if os.path.isdir(sub) and not entry.startswith("."):
            sub_dirs.append(sub)

    for n in nodes:
        if n.source_file:
            found = any(
                os.path.exists(os.path.join(d, n.source_file)) for d in sub_dirs
            )
            if found:
                continue
            full_path = os.path.join(base_dir, n.source_file)
            if not os.path.exists(full_path):
                issues.append(Issue(
                    severity=IssueSeverity.warning,
                    type="stale_node",
                    message=f"'{n.name}' references missing file: {n.source_file}",
                    node_ids=[n.id],
                    suggestion=f"Update or remove '{n.name}' — its source file no longer exists",
                ))
    return issues


def _check_unused_modules(nodes: list[Node], edges: list[Edge]) -> list[Issue]:
    """Module nodes not connected to any route or service."""
    issues = []
    module_ids = {n.id for n in nodes if n.type.value == "module"}
    connected_modules = set()
    for e in edges:
        if e.source_id in module_ids:
            connected_modules.add(e.source_id)
        if e.target_id in module_ids:
            connected_modules.add(e.target_id)

    node_map = {n.id: n for n in nodes}
    parent_ids = {n.parent_id for n in nodes if n.parent_id}
    for mid in module_ids - connected_modules:
        m = node_map[mid]
        # Skip directory group nodes — organizational, not code
        if m.metadata and m.metadata.get("directory"):
            continue
        # Skip nodes that have children (container/parent nodes)
        if mid in parent_ids:
            continue
        issues.append(Issue(
            severity=IssueSeverity.info,
            type="unused_module",
            message=f"Module '{m.name}' is not connected to any other component",
            node_ids=[mid],
            suggestion=f"Connect '{m.name}' or remove it if unused",
        ))
    return issues


def _check_missing_descriptions(nodes: list[Node]) -> list[Issue]:
    """Nodes with no description — filtered to only flag types where descriptions add value."""
    issues = []
    # Types where descriptions are expected vs not
    skip_types = {"file", "script", "config", "column", "migration", "external", "test",
                   "view", "struct", "enum_def", "protocol"}
    parent_ids = {n.parent_id for n in nodes if n.parent_id}
    for n in nodes:
        if n.description:
            continue
        if n.type.value in skip_types:
            continue
        # Skip directory group nodes — organizational, not code
        if n.metadata and n.metadata.get("directory"):
            continue
        # Skip container/parent nodes
        if n.id in parent_ids:
            continue
        issues.append(Issue(
            severity=IssueSeverity.info,
            type="missing_description",
            message=f"'{n.name}' has no description",
            node_ids=[n.id],
            suggestion=f"Add a description to '{n.name}' for better documentation",
        ))
    return issues
