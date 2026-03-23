"""Rule-based project questions — detects gaps and generates actionable questions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

from src.db import Database
from src.models import Edge, Node, ProjectQuestion


async def get_project_questions(
    db: Database, category: str = "all", node_id: str | None = None
) -> dict:
    """Analyze the blueprint and generate actionable questions."""
    nodes = await db.get_all_nodes()
    edges = await db.get_all_edges()

    # If scoped to a node, filter to its subtree
    if node_id:
        subtree_ids = _get_subtree_ids(node_id, nodes)
        nodes = [n for n in nodes if n.id in subtree_ids]
        edge_ids = {n.id for n in nodes}
        edges = [e for e in edges if e.source_id in edge_ids or e.target_id in edge_ids]

    # Read project type for framework-aware filtering
    project_type = await db.get_project_meta("project_type") or "web"
    desktop_types = {"desktop", "tauri", "electron"}

    all_questions: list[ProjectQuestion] = []
    checkers = [
        ("security", _check_auth),
        ("data", _check_database),
        ("completeness", _check_testing),
        ("completeness", _check_error_handling),
        ("scaling", _check_scaling),
        ("architecture", _check_orphans),
        ("operations", _check_external_deps),
        ("completeness", _check_stale_planned),
        ("data", _check_data_flow),
        ("operations", _check_logging),
        ("security", _check_config),
    ]

    for cat, checker in checkers:
        if category == "all" or category == cat:
            # Skip web-specific security questions for desktop apps
            if cat == "security" and checker == _check_auth and project_type in desktop_types:
                continue
            all_questions.extend(checker(nodes, edges))

    summary = {"critical": 0, "warning": 0, "info": 0}
    for q in all_questions:
        summary[q.severity] += 1

    return {
        "questions": [q.model_dump() for q in all_questions],
        "summary": summary,
        "total": len(all_questions),
    }


def _get_subtree_ids(root_id: str, nodes: list[Node]) -> set[str]:
    """Get all node IDs in a subtree rooted at root_id."""
    ids = {root_id}
    changed = True
    while changed:
        changed = False
        for n in nodes:
            if n.parent_id in ids and n.id not in ids:
                ids.add(n.id)
                changed = True
    return ids


def _qid() -> str:
    return str(uuid.uuid4())[:8]


def _check_auth(nodes: list[Node], edges: list[Edge]) -> list[ProjectQuestion]:
    """Security: no auth nodes → critical; routes without auth edge → warning."""
    questions = []
    node_map = {n.id: n for n in nodes}

    # Check if any auth-related nodes exist
    auth_types = {"middleware"}
    auth_names = {"auth", "authentication", "authorization", "jwt", "oauth", "session"}
    has_auth_node = any(
        n.type.value in auth_types or any(kw in n.name.lower() for kw in auth_names)
        for n in nodes
    )

    if not has_auth_node and len(nodes) > 0:
        questions.append(ProjectQuestion(
            id=_qid(),
            category="security",
            severity="critical",
            question="Where is the authentication layer for this project?",
            context="No authentication nodes (middleware, auth service, JWT, OAuth) were found in the blueprint.",
            fix_prompt="Add an authentication node: register_node(name='Auth Middleware', type='middleware', description='Handles JWT/session auth')",
            learn_more="Authentication is a critical security layer. Without it, all routes are publicly accessible.",
            related_nodes=[],
            highlight_nodes=[],
        ))
        return questions  # No auth at all, skip per-route check

    # Check routes/APIs without authenticates edge
    auth_targets = set()
    for e in edges:
        if e.relationship.value == "authenticates":
            auth_targets.add(e.target_id)
            auth_targets.add(e.source_id)

    for n in nodes:
        if n.type.value in ("route", "api") and n.id not in auth_targets:
            questions.append(ProjectQuestion(
                id=_qid(),
                category="security",
                severity="warning",
                question=f"Is '{n.name}' intentionally unprotected?",
                context=f"Route/API '{n.name}' has no authenticates edge connecting it to an auth node.",
                fix_prompt=f"Add auth: register_connection(source_id='<auth_node_id>', target_id='{n.id}', relationship='authenticates')",
                learn_more="Unprotected routes may expose sensitive data or operations to unauthorized users.",
                related_nodes=[n.id],
                highlight_nodes=[n.id],
            ))

    return questions


def _check_database(nodes: list[Node], edges: list[Edge]) -> list[ProjectQuestion]:
    """Data: no DB → critical; tables with no writers/readers → warning/info."""
    questions = []
    node_map = {n.id: n for n in nodes}

    db_nodes = [n for n in nodes if n.type.value == "database"]
    if not db_nodes and len(nodes) > 0:
        questions.append(ProjectQuestion(
            id=_qid(),
            category="data",
            severity="critical",
            question="Where is data stored in this project?",
            context="No database nodes found in the blueprint.",
            fix_prompt="Add a database: register_node(name='PostgreSQL', type='database', description='Primary data store')",
            learn_more="Most applications need persistent storage. Even if using an external service, document it in the blueprint.",
            related_nodes=[],
            highlight_nodes=[],
        ))
        return questions

    # Tables with no writers
    table_nodes = [n for n in nodes if n.type.value == "table"]
    for t in table_nodes:
        has_writer = any(
            e.target_id == t.id and e.relationship.value in ("writes_to", "creates", "updates")
            for e in edges
        )
        has_reader = any(
            (e.source_id == t.id or e.target_id == t.id) and e.relationship.value == "reads_from"
            for e in edges
        )
        if not has_writer:
            questions.append(ProjectQuestion(
                id=_qid(),
                category="data",
                severity="warning",
                question=f"What writes to the '{t.name}' table?",
                context=f"Table '{t.name}' has no writes_to/creates/updates edges pointing to it.",
                fix_prompt=f"Connect a writer: register_connection(source_id='<service_id>', target_id='{t.id}', relationship='writes_to')",
                learn_more="Tables without writers may indicate incomplete modeling or dead schema.",
                related_nodes=[t.id],
                highlight_nodes=[t.id],
            ))
        if not has_reader:
            questions.append(ProjectQuestion(
                id=_qid(),
                category="data",
                severity="info",
                question=f"Is anyone reading from '{t.name}'?",
                context=f"Table '{t.name}' has no reads_from edges.",
                fix_prompt=f"Connect a reader: register_connection(source_id='{t.id}', target_id='<service_id>', relationship='reads_from')",
                learn_more="Tables without readers might be write-only audit logs, or they might indicate missing connections.",
                related_nodes=[t.id],
                highlight_nodes=[t.id],
            ))

    return questions


def _check_testing(nodes: list[Node], edges: list[Edge]) -> list[ProjectQuestion]:
    """Completeness: no test nodes/files → warning."""
    questions = []
    test_types = {"test"}
    test_names = {"test", "spec", "unittest", "pytest", "jest"}
    has_test = any(
        n.type.value in test_types or any(kw in n.name.lower() for kw in test_names)
        for n in nodes
    )

    if not has_test and len(nodes) > 0:
        questions.append(ProjectQuestion(
            id=_qid(),
            category="completeness",
            severity="warning",
            question="Where are the tests for this project?",
            context="No test nodes or test-related files found in the blueprint.",
            fix_prompt="Add test nodes: register_node(name='Unit Tests', type='test', description='pytest test suite')",
            learn_more="Tests are critical for maintaining code quality and catching regressions.",
            related_nodes=[],
            highlight_nodes=[],
        ))

    return questions


def _check_error_handling(nodes: list[Node], edges: list[Edge]) -> list[ProjectQuestion]:
    """Completeness: no error/handler nodes → warning."""
    questions = []
    error_names = {"error", "handler", "exception", "fallback", "retry", "circuit_breaker"}
    has_error_handling = any(
        any(kw in n.name.lower() for kw in error_names)
        for n in nodes
    )

    if not has_error_handling and len(nodes) > 0:
        questions.append(ProjectQuestion(
            id=_qid(),
            category="completeness",
            severity="warning",
            question="How does this project handle errors?",
            context="No error handling nodes (error handler, exception middleware, retry logic) found.",
            fix_prompt="Add error handling: register_node(name='Error Handler', type='middleware', description='Global error handling')",
            learn_more="Robust error handling prevents cascading failures and improves user experience.",
            related_nodes=[],
            highlight_nodes=[],
        ))

    return questions


def _check_scaling(nodes: list[Node], edges: list[Edge]) -> list[ProjectQuestion]:
    """Scaling: DB without cache → info."""
    questions = []
    db_nodes = [n for n in nodes if n.type.value == "database"]
    cache_nodes = [n for n in nodes if n.type.value == "cache"]

    if db_nodes and not cache_nodes:
        questions.append(ProjectQuestion(
            id=_qid(),
            category="scaling",
            severity="info",
            question="Would a caching layer improve performance?",
            context=f"Found {len(db_nodes)} database(s) but no cache nodes. Heavy read workloads may benefit from caching.",
            fix_prompt="Add cache: register_node(name='Redis Cache', type='cache', description='Read-through cache')",
            learn_more="Caching reduces database load and improves response times for frequently accessed data.",
            related_nodes=[n.id for n in db_nodes],
            highlight_nodes=[n.id for n in db_nodes],
        ))

    return questions


def _check_orphans(nodes: list[Node], edges: list[Edge]) -> list[ProjectQuestion]:
    """Architecture: nodes with zero edges → warning (each named)."""
    questions = []
    connected_ids = set()
    for e in edges:
        connected_ids.add(e.source_id)
        connected_ids.add(e.target_id)

    # Also exclude nodes that have children (they're connected via parent_id)
    parent_ids = {n.parent_id for n in nodes if n.parent_id}
    child_ids = {n.id for n in nodes if n.parent_id}

    for n in nodes:
        if n.id not in connected_ids and n.id not in parent_ids and n.id not in child_ids:
            questions.append(ProjectQuestion(
                id=_qid(),
                category="architecture",
                severity="warning",
                question=f"How does '{n.name}' connect to the rest of the system?",
                context=f"'{n.name}' ({n.type.value}) has no edges and no parent/child relationships.",
                fix_prompt=f"Connect it: register_connection(source_id='{n.id}', target_id='<other_id>', relationship='depends_on')",
                learn_more="Orphaned nodes may indicate incomplete modeling or dead components.",
                related_nodes=[n.id],
                highlight_nodes=[n.id],
            ))

    return questions


def _check_external_deps(nodes: list[Node], edges: list[Edge]) -> list[ProjectQuestion]:
    """Operations: external with 3+ dependents → warning."""
    questions = []
    node_map = {n.id: n for n in nodes}
    external_nodes = [n for n in nodes if n.type.value == "external"]

    for ext in external_nodes:
        dependents = set()
        for e in edges:
            if e.target_id == ext.id:
                dependents.add(e.source_id)
            if e.source_id == ext.id:
                dependents.add(e.target_id)

        if len(dependents) >= 3:
            dep_names = [node_map[d].name for d in dependents if d in node_map]
            questions.append(ProjectQuestion(
                id=_qid(),
                category="operations",
                severity="warning",
                question=f"What happens if '{ext.name}' goes down?",
                context=f"External dependency '{ext.name}' has {len(dependents)} dependents: {', '.join(dep_names)}. This is a concentration risk.",
                fix_prompt=f"Add fallback: register_node(name='{ext.name} Fallback', type='service', description='Fallback for {ext.name}')",
                learn_more="External dependencies with many dependents are single points of failure. Consider fallbacks or circuit breakers.",
                related_nodes=[ext.id] + list(dependents),
                highlight_nodes=[ext.id],
            ))

    return questions


def _check_stale_planned(nodes: list[Node], edges: list[Edge]) -> list[ProjectQuestion]:
    """Completeness: planned nodes >14 days old → info."""
    questions = []
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=14)

    for n in nodes:
        if n.status.value == "planned" and n.created_at:
            try:
                created = datetime.fromisoformat(n.created_at.replace("Z", "+00:00"))
                if created < threshold:
                    age_days = (now - created).days
                    questions.append(ProjectQuestion(
                        id=_qid(),
                        category="completeness",
                        severity="info",
                        question=f"Is '{n.name}' still planned after {age_days} days?",
                        context=f"'{n.name}' has been in 'planned' status since {n.created_at}.",
                        fix_prompt=f"Update status: update_node(id='{n.id}', status='in_progress') or remove if no longer needed",
                        learn_more="Stale planned items may indicate scope creep or abandoned features.",
                        related_nodes=[n.id],
                        highlight_nodes=[n.id],
                    ))
            except (ValueError, TypeError):
                pass

    return questions


def _check_data_flow(nodes: list[Node], edges: list[Edge]) -> list[ProjectQuestion]:
    """Data: route→table with no validation → warning."""
    questions = []
    node_map = {n.id: n for n in nodes}

    # Find routes that write to tables
    route_ids = {n.id for n in nodes if n.type.value == "route"}
    table_ids = {n.id for n in nodes if n.type.value == "table"}

    # Check for validation/middleware between routes and tables
    validation_names = {"validation", "validator", "schema", "sanitize", "middleware"}
    validation_ids = {
        n.id for n in nodes
        if any(kw in n.name.lower() for kw in validation_names)
    }

    for e in edges:
        if e.source_id in route_ids and e.target_id in table_ids:
            if e.relationship.value in ("writes_to", "creates", "updates"):
                route = node_map.get(e.source_id)
                table = node_map.get(e.target_id)
                # Check if route connects to any validation node
                has_validation = any(
                    (e2.source_id == e.source_id and e2.target_id in validation_ids) or
                    (e2.target_id == e.source_id and e2.source_id in validation_ids)
                    for e2 in edges
                )
                if not has_validation and route and table:
                    questions.append(ProjectQuestion(
                        id=_qid(),
                        category="data",
                        severity="warning",
                        question=f"Is input validated before '{route.name}' writes to '{table.name}'?",
                        context=f"Route '{route.name}' writes directly to table '{table.name}' with no validation node in between.",
                        fix_prompt=f"Add validation: register_node(name='Input Validator', type='middleware')",
                        learn_more="Direct route-to-table writes without validation can lead to data integrity issues and injection attacks.",
                        related_nodes=[route.id, table.id],
                        highlight_nodes=[route.id, table.id],
                    ))

    return questions


def _check_logging(nodes: list[Node], edges: list[Edge]) -> list[ProjectQuestion]:
    """Operations: no log/monitor nodes → info."""
    questions = []
    log_names = {"log", "logging", "monitor", "monitoring", "observability", "metrics", "tracing", "apm"}
    has_logging = any(
        any(kw in n.name.lower() for kw in log_names)
        for n in nodes
    )

    if not has_logging and len(nodes) > 0:
        questions.append(ProjectQuestion(
            id=_qid(),
            category="operations",
            severity="info",
            question="How is this project monitored?",
            context="No logging or monitoring nodes found in the blueprint.",
            fix_prompt="Add monitoring: register_node(name='Logging Service', type='service', description='Centralized logging')",
            learn_more="Logging and monitoring are essential for debugging production issues and understanding system behavior.",
            related_nodes=[],
            highlight_nodes=[],
        ))

    return questions


def _check_config(nodes: list[Node], edges: list[Edge]) -> list[ProjectQuestion]:
    """Security: no config/env/secret nodes → info."""
    questions = []
    config_names = {"config", "configuration", "env", "environment", "secret", "vault", "settings"}
    has_config = any(
        n.type.value == "config" or any(kw in n.name.lower() for kw in config_names)
        for n in nodes
    )

    if not has_config and len(nodes) > 0:
        questions.append(ProjectQuestion(
            id=_qid(),
            category="security",
            severity="info",
            question="How is configuration managed?",
            context="No config/environment/secret management nodes found in the blueprint.",
            fix_prompt="Add config: register_node(name='Environment Config', type='config', description='Environment variables and secrets')",
            learn_more="Proper configuration management prevents hardcoded secrets and simplifies deployment across environments.",
            related_nodes=[],
            highlight_nodes=[],
        ))

    return questions
