"""Natural-language keyword query engine for the Blueprint MCP graph."""

from __future__ import annotations

import re

from src.db import Database
from src.models import Edge, EdgeRelationship, Node, NodeStatus, NodeType


# ---------------------------------------------------------------------------
# Keyword → NodeType mapping (plural and singular forms)
# ---------------------------------------------------------------------------

_TYPE_ALIASES: dict[str, NodeType] = {}
for nt in NodeType:
    _TYPE_ALIASES[nt.value] = nt
    _TYPE_ALIASES[nt.value + "s"] = nt

# Common plural / alias overrides
_TYPE_ALIASES.update({
    "databases": NodeType.database,
    "tables": NodeType.table,
    "columns": NodeType.column,
    "routes": NodeType.route,
    "functions": NodeType.function,
    "modules": NodeType.module,
    "services": NodeType.service,
    "containers": NodeType.container,
    "queues": NodeType.queue,
    "caches": NodeType.cache,
    "apis": NodeType.api,
    "files": NodeType.file,
    "classes": NodeType.class_def,
    "class": NodeType.class_def,
    "structs": NodeType.struct,
    "views": NodeType.view,
    "tests": NodeType.test,
    "scripts": NodeType.script,
    "workers": NodeType.worker,
    "models": NodeType.model,
    "schemas": NodeType.schema,
    "enums": NodeType.enum_def,
    "enum": NodeType.enum_def,
    "utils": NodeType.util,
    "webhooks": NodeType.webhook,
    "migrations": NodeType.migration,
})

# Status keywords
_STATUS_KEYWORDS: dict[str, NodeStatus] = {
    "broken": NodeStatus.broken,
    "planned": NodeStatus.planned,
    "in_progress": NodeStatus.in_progress,
    "in progress": NodeStatus.in_progress,
    "built": NodeStatus.built,
    "deprecated": NodeStatus.deprecated,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Lower-case and collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _find_node_by_name(name_fragment: str, nodes: list[Node]) -> list[Node]:
    """Return nodes whose name contains *name_fragment* (case-insensitive)."""
    fragment = name_fragment.lower()
    return [n for n in nodes if fragment in n.name.lower()]


def _node_dicts(nodes: list[Node]) -> list[dict]:
    return [n.model_dump() for n in nodes]


def _edge_dicts(edges: list[Edge]) -> list[dict]:
    return [e.model_dump() for e in edges]


def _empty_result(interpretation: str, summary: str) -> dict:
    return {
        "matches": [],
        "edges": [],
        "summary": summary,
        "query_interpretation": interpretation,
    }


# ---------------------------------------------------------------------------
# Query strategies
# ---------------------------------------------------------------------------


def _strategy_connects_to(
    question: str, nodes: list[Node], edges: list[Edge]
) -> dict | None:
    """'what connects to X' → find edges where target matches X name."""
    match = re.search(r"what\s+connects?\s+to\s+(?:the\s+)?(.+)", question)
    if not match:
        return None

    target_fragment = match.group(1).strip().rstrip("?")
    node_map = {n.id: n for n in nodes}

    # Try to match target_fragment as a type first, then as a name
    target_nodes: list[Node] = []
    frag_lower = target_fragment.lower()
    if frag_lower in _TYPE_ALIASES:
        target_type = _TYPE_ALIASES[frag_lower]
        target_nodes = [n for n in nodes if n.type == target_type]
    if not target_nodes:
        target_nodes = _find_node_by_name(target_fragment, nodes)

    if not target_nodes:
        return _empty_result(
            f"Looking for nodes connected to '{target_fragment}'",
            f"No nodes matching '{target_fragment}' found in the blueprint.",
        )

    target_ids = {n.id for n in target_nodes}
    matched_edges = [e for e in edges if e.target_id in target_ids]
    source_ids = {e.source_id for e in matched_edges}
    source_nodes = [n for n in nodes if n.id in source_ids]

    return {
        "matches": _node_dicts(source_nodes + target_nodes),
        "edges": _edge_dicts(matched_edges),
        "summary": (
            f"Found {len(source_nodes)} node(s) connecting to "
            f"{len(target_nodes)} '{target_fragment}' node(s) "
            f"via {len(matched_edges)} edge(s)."
        ),
        "query_interpretation": f"Finding all nodes that connect to '{target_fragment}'",
    }


def _strategy_show_all(
    question: str, nodes: list[Node], edges: list[Edge]
) -> dict | None:
    """'show me all X' → type filter."""
    match = re.search(r"show\s+(?:me\s+)?all\s+(.+)", question)
    if not match:
        return None

    type_fragment = match.group(1).strip().rstrip("?")
    frag_lower = type_fragment.lower()

    if frag_lower not in _TYPE_ALIASES:
        return _empty_result(
            f"Looking for all nodes of type '{type_fragment}'",
            f"'{type_fragment}' does not match any known node type.",
        )

    target_type = _TYPE_ALIASES[frag_lower]
    matched = [n for n in nodes if n.type == target_type]

    if not matched:
        return _empty_result(
            f"Filtering nodes by type '{target_type.value}'",
            f"No '{target_type.value}' nodes exist in the blueprint.",
        )

    return {
        "matches": _node_dicts(matched),
        "edges": [],
        "summary": f"Found {len(matched)} node(s) of type '{target_type.value}'.",
        "query_interpretation": f"Filtering nodes by type '{target_type.value}'",
    }


def _strategy_depends_on(
    question: str, nodes: list[Node], edges: list[Edge]
) -> dict | None:
    """'what does X depend on' → outgoing depends_on edges from X."""
    match = re.search(r"what\s+does\s+(.+?)\s+depend\s+on", question)
    if not match:
        return None

    name_fragment = match.group(1).strip().rstrip("?")
    node_map = {n.id: n for n in nodes}

    source_nodes = _find_node_by_name(name_fragment, nodes)
    if not source_nodes:
        return _empty_result(
            f"Looking for dependencies of '{name_fragment}'",
            f"No nodes matching '{name_fragment}' found in the blueprint.",
        )

    source_ids = {n.id for n in source_nodes}
    dep_edges = [
        e for e in edges
        if e.source_id in source_ids and e.relationship == EdgeRelationship.depends_on
    ]
    dep_target_ids = {e.target_id for e in dep_edges}
    dep_nodes = [n for n in nodes if n.id in dep_target_ids]

    return {
        "matches": _node_dicts(dep_nodes),
        "edges": _edge_dicts(dep_edges),
        "summary": (
            f"'{name_fragment}' depends on {len(dep_nodes)} node(s) "
            f"via {len(dep_edges)} depends_on edge(s)."
        ),
        "query_interpretation": f"Finding dependencies of '{name_fragment}'",
    }


def _strategy_find_status(
    question: str, nodes: list[Node], edges: list[Edge]
) -> dict | None:
    """'find broken' / 'find planned' etc. → status filter."""
    for keyword, status in _STATUS_KEYWORDS.items():
        if keyword in question:
            matched = [n for n in nodes if n.status == status]
            if not matched:
                return _empty_result(
                    f"Filtering nodes by status '{status.value}'",
                    f"No nodes with status '{status.value}' found in the blueprint.",
                )
            return {
                "matches": _node_dicts(matched),
                "edges": [],
                "summary": f"Found {len(matched)} node(s) with status '{status.value}'.",
                "query_interpretation": f"Filtering nodes by status '{status.value}'",
            }
    return None


def _strategy_related_to(
    question: str, nodes: list[Node], edges: list[Edge]
) -> dict | None:
    """'related to X' → all edges where X is source or target."""
    match = re.search(r"related\s+to\s+(.+)", question)
    if not match:
        return None

    name_fragment = match.group(1).strip().rstrip("?")
    node_map = {n.id: n for n in nodes}

    center_nodes = _find_node_by_name(name_fragment, nodes)
    if not center_nodes:
        return _empty_result(
            f"Looking for nodes related to '{name_fragment}'",
            f"No nodes matching '{name_fragment}' found in the blueprint.",
        )

    center_ids = {n.id for n in center_nodes}
    related_edges = [
        e for e in edges if e.source_id in center_ids or e.target_id in center_ids
    ]
    related_ids: set[str] = set()
    for e in related_edges:
        related_ids.add(e.source_id)
        related_ids.add(e.target_id)

    related_nodes = [n for n in nodes if n.id in related_ids]

    return {
        "matches": _node_dicts(related_nodes),
        "edges": _edge_dicts(related_edges),
        "summary": (
            f"Found {len(related_nodes)} node(s) related to '{name_fragment}' "
            f"via {len(related_edges)} edge(s)."
        ),
        "query_interpretation": f"Finding all nodes related to '{name_fragment}'",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def query_blueprint(db: Database, question: str) -> dict:
    """Parse a natural-language *question* about the blueprint and return matching
    nodes/edges with a human-readable summary.

    Returns ``{"matches": [...], "edges": [...], "summary": str, "query_interpretation": str}``.
    """
    nodes = await db.get_all_nodes()
    edges = await db.get_all_edges()

    normalized = _normalize(question)

    # Try each strategy in priority order; first match wins.
    strategies = [
        _strategy_connects_to,
        _strategy_depends_on,
        _strategy_show_all,
        _strategy_find_status,
        _strategy_related_to,
    ]

    for strategy in strategies:
        result = strategy(normalized, nodes, edges)
        if result is not None:
            return result

    # Fallback: no strategy matched — try a fuzzy name search across all nodes
    words = [w for w in normalized.split() if len(w) > 2]
    for word in reversed(words):
        found = _find_node_by_name(word, nodes)
        if found:
            return {
                "matches": _node_dicts(found),
                "edges": [],
                "summary": f"Found {len(found)} node(s) matching '{word}'.",
                "query_interpretation": f"Fuzzy search for '{word}' in node names",
            }

    return _empty_result(
        f"Could not interpret: '{question}'",
        "No matches found. Try asking about specific node names, types (e.g. 'show me all routes'), "
        "statuses (e.g. 'find broken'), or relationships (e.g. 'what connects to the database').",
    )
