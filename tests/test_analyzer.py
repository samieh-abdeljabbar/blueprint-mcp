"""Analyzer tests — each test builds a specific broken state and asserts exact issue types."""

import os
import tempfile

import pytest

from src.analyzer import analyze
from src.db import Database
from src.models import (
    EdgeCreateInput,
    EdgeRelationship,
    EdgeStatus,
    IssueSeverity,
    NodeCreateInput,
    NodeStatus,
    NodeType,
)


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


# ===== Critical checks =====


async def test_orphaned_table(db: Database):
    """Table with no edges → orphaned_table, severity=critical."""
    await db.create_node(
        NodeCreateInput(name="users", type=NodeType.table)
    )
    issues = await analyze(db)
    orphaned = [i for i in issues if i.type == "orphaned_table"]
    assert len(orphaned) == 1
    assert orphaned[0].severity == IssueSeverity.critical
    assert "users" in orphaned[0].message


async def test_connected_table_not_orphaned(db: Database):
    """Table with reads_from edge → NO orphaned_table issue."""
    svc = await db.create_node(
        NodeCreateInput(name="API", type=NodeType.service)
    )
    tbl = await db.create_node(
        NodeCreateInput(name="users", type=NodeType.table)
    )
    await db.create_edge(EdgeCreateInput(
        source_id=svc.id, target_id=tbl.id, relationship=EdgeRelationship.reads_from
    ))
    issues = await analyze(db)
    orphaned = [i for i in issues if i.type == "orphaned_table"]
    assert len(orphaned) == 0


async def test_broken_edge(db: Database):
    """Edge with status=broken → broken_reference, severity=critical."""
    n1 = await db.create_node(
        NodeCreateInput(name="A", type=NodeType.service)
    )
    n2 = await db.create_node(
        NodeCreateInput(name="B", type=NodeType.service)
    )
    edge = await db.create_edge(EdgeCreateInput(
        source_id=n1.id, target_id=n2.id,
        relationship=EdgeRelationship.connects_to,
        status=EdgeStatus.active,
    ))
    # Set edge to broken via SQL
    await db.db.execute(
        "UPDATE edges SET status = 'broken' WHERE id = ?", (edge.id,)
    )
    await db.db.commit()

    issues = await analyze(db)
    broken = [i for i in issues if i.type == "broken_reference"]
    assert len(broken) == 1
    assert broken[0].severity == IssueSeverity.critical


async def test_missing_database(db: Database):
    """Service with route child, no DB → missing_database."""
    svc = await db.create_node(
        NodeCreateInput(name="API Server", type=NodeType.service)
    )
    await db.create_node(
        NodeCreateInput(
            name="GET /users", type=NodeType.route, parent_id=svc.id
        )
    )
    issues = await analyze(db)
    missing = [i for i in issues if i.type == "missing_database"]
    assert len(missing) == 1
    assert missing[0].severity == IssueSeverity.critical
    assert "API Server" in missing[0].message


async def test_service_with_db_no_missing_database(db: Database):
    """Service connected to DB → no missing_database issue."""
    svc = await db.create_node(
        NodeCreateInput(name="API Server", type=NodeType.service)
    )
    await db.create_node(
        NodeCreateInput(
            name="GET /users", type=NodeType.route, parent_id=svc.id
        )
    )
    db_node = await db.create_node(
        NodeCreateInput(name="PostgreSQL", type=NodeType.database)
    )
    await db.create_edge(EdgeCreateInput(
        source_id=svc.id, target_id=db_node.id,
        relationship=EdgeRelationship.connects_to,
    ))
    issues = await analyze(db)
    missing = [i for i in issues if i.type == "missing_database"]
    assert len(missing) == 0


async def test_circular_dependency_3_nodes(db: Database):
    """A→B→C→A depends_on → circular_dependency with all 3 node IDs."""
    a = await db.create_node(
        NodeCreateInput(name="ServiceA", type=NodeType.service)
    )
    b = await db.create_node(
        NodeCreateInput(name="ServiceB", type=NodeType.service)
    )
    c = await db.create_node(
        NodeCreateInput(name="ServiceC", type=NodeType.service)
    )
    await db.create_edge(EdgeCreateInput(
        source_id=a.id, target_id=b.id, relationship=EdgeRelationship.depends_on
    ))
    await db.create_edge(EdgeCreateInput(
        source_id=b.id, target_id=c.id, relationship=EdgeRelationship.depends_on
    ))
    await db.create_edge(EdgeCreateInput(
        source_id=c.id, target_id=a.id, relationship=EdgeRelationship.depends_on
    ))

    issues = await analyze(db)
    cycles = [i for i in issues if i.type == "circular_dependency"]
    assert len(cycles) >= 1
    cycle = cycles[0]
    assert cycle.severity == IssueSeverity.critical
    assert len(cycle.node_ids) == 3
    # All names should be in message
    assert "ServiceA" in cycle.message
    assert "ServiceB" in cycle.message
    assert "ServiceC" in cycle.message


async def test_circular_dependency_2_nodes(db: Database):
    """A↔B depends_on → circular_dependency."""
    a = await db.create_node(
        NodeCreateInput(name="Alpha", type=NodeType.service)
    )
    b = await db.create_node(
        NodeCreateInput(name="Beta", type=NodeType.service)
    )
    await db.create_edge(EdgeCreateInput(
        source_id=a.id, target_id=b.id, relationship=EdgeRelationship.depends_on
    ))
    await db.create_edge(EdgeCreateInput(
        source_id=b.id, target_id=a.id, relationship=EdgeRelationship.depends_on
    ))

    issues = await analyze(db)
    cycles = [i for i in issues if i.type == "circular_dependency"]
    assert len(cycles) >= 1
    cycle = cycles[0]
    assert cycle.severity == IssueSeverity.critical
    assert len(cycle.node_ids) == 2
    assert "Alpha" in cycle.message
    assert "Beta" in cycle.message


async def test_dag_no_circular_dependency(db: Database):
    """DAG (A→B, A→C, B→C) → NO circular_dependency."""
    a = await db.create_node(
        NodeCreateInput(name="A", type=NodeType.service)
    )
    b = await db.create_node(
        NodeCreateInput(name="B", type=NodeType.service)
    )
    c = await db.create_node(
        NodeCreateInput(name="C", type=NodeType.service)
    )
    await db.create_edge(EdgeCreateInput(
        source_id=a.id, target_id=b.id, relationship=EdgeRelationship.depends_on
    ))
    await db.create_edge(EdgeCreateInput(
        source_id=a.id, target_id=c.id, relationship=EdgeRelationship.depends_on
    ))
    await db.create_edge(EdgeCreateInput(
        source_id=b.id, target_id=c.id, relationship=EdgeRelationship.depends_on
    ))
    issues = await analyze(db)
    cycles = [i for i in issues if i.type == "circular_dependency"]
    assert len(cycles) == 0


# ===== Warning checks =====


async def test_unimplemented_planned(db: Database):
    """Planned node → unimplemented_planned, severity=warning."""
    await db.create_node(
        NodeCreateInput(name="Auth Module", type=NodeType.module, status=NodeStatus.planned)
    )
    issues = await analyze(db)
    planned = [i for i in issues if i.type == "unimplemented_planned"]
    assert len(planned) >= 1
    assert planned[0].severity == IssueSeverity.warning
    assert "Auth Module" in planned[0].message


async def test_missing_auth_on_route(db: Database):
    """Route with no authenticates edge → missing_auth, severity=warning."""
    await db.create_node(
        NodeCreateInput(name="GET /admin", type=NodeType.route)
    )
    issues = await analyze(db)
    auth = [i for i in issues if i.type == "missing_auth"]
    assert len(auth) >= 1
    assert auth[0].severity == IssueSeverity.warning
    assert "GET /admin" in auth[0].message


async def test_route_with_auth_no_missing(db: Database):
    """Route with authenticates edge → no missing_auth."""
    route = await db.create_node(
        NodeCreateInput(name="GET /admin", type=NodeType.route)
    )
    auth = await db.create_node(
        NodeCreateInput(name="JWT Auth", type=NodeType.module)
    )
    await db.create_edge(EdgeCreateInput(
        source_id=auth.id, target_id=route.id,
        relationship=EdgeRelationship.authenticates,
    ))
    issues = await analyze(db)
    missing = [i for i in issues if i.type == "missing_auth"]
    # Should not flag the authenticated route
    flagged_ids = set()
    for m in missing:
        flagged_ids.update(m.node_ids)
    assert route.id not in flagged_ids


async def test_single_point_of_failure(db: Database):
    """Articulation point → single_point_of_failure for the bridge node."""
    # A -- B -- C (B is articulation point)
    a = await db.create_node(
        NodeCreateInput(name="Frontend", type=NodeType.service)
    )
    b = await db.create_node(
        NodeCreateInput(name="Gateway", type=NodeType.service)
    )
    c = await db.create_node(
        NodeCreateInput(name="Backend", type=NodeType.service)
    )
    await db.create_edge(EdgeCreateInput(
        source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls
    ))
    await db.create_edge(EdgeCreateInput(
        source_id=b.id, target_id=c.id, relationship=EdgeRelationship.calls
    ))
    issues = await analyze(db)
    spof = [i for i in issues if i.type == "single_point_of_failure"]
    assert len(spof) >= 1
    spof_names = set()
    for s in spof:
        for nid in s.node_ids:
            node = await db.get_node(nid)
            if node:
                spof_names.add(node.name)
    assert "Gateway" in spof_names


async def test_spof_skips_entry_points(db: Database):
    """System nodes and entry points should not be flagged as SPOF."""
    # A(system) -- B(module) -- C(module)  => A is AP but should be skipped
    a = await db.create_node(
        NodeCreateInput(name="MyProject", type=NodeType.system)
    )
    b = await db.create_node(
        NodeCreateInput(name="Core", type=NodeType.module)
    )
    c = await db.create_node(
        NodeCreateInput(name="Utils", type=NodeType.module)
    )
    await db.create_edge(EdgeCreateInput(
        source_id=a.id, target_id=b.id, relationship=EdgeRelationship.contains
    ))
    await db.create_edge(EdgeCreateInput(
        source_id=b.id, target_id=c.id, relationship=EdgeRelationship.depends_on
    ))
    issues = await analyze(db)
    spof = [i for i in issues if i.type == "single_point_of_failure"]
    spof_names = set()
    for s in spof:
        for nid in s.node_ids:
            node = await db.get_node(nid)
            if node:
                spof_names.add(node.name)
    # System node "MyProject" should NOT be flagged
    assert "MyProject" not in spof_names


async def test_spof_skips_main_app_names(db: Database):
    """Nodes named 'main' or 'App' should not be flagged as SPOF."""
    a = await db.create_node(
        NodeCreateInput(name="App", type=NodeType.module)
    )
    b = await db.create_node(
        NodeCreateInput(name="Router", type=NodeType.module)
    )
    c = await db.create_node(
        NodeCreateInput(name="Dashboard", type=NodeType.module)
    )
    await db.create_edge(EdgeCreateInput(
        source_id=a.id, target_id=b.id, relationship=EdgeRelationship.calls
    ))
    await db.create_edge(EdgeCreateInput(
        source_id=b.id, target_id=c.id, relationship=EdgeRelationship.calls
    ))
    issues = await analyze(db)
    spof = [i for i in issues if i.type == "single_point_of_failure"]
    spof_names = set()
    for s in spof:
        for nid in s.node_ids:
            node = await db.get_node(nid)
            if node:
                spof_names.add(node.name)
    # "App" is a common entry point name — should be skipped
    assert "App" not in spof_names


async def test_stale_node(db: Database):
    """Node with nonexistent source_file → stale_node."""
    await db.create_node(
        NodeCreateInput(
            name="OldService", type=NodeType.service,
            source_file="/nonexistent/path/old_service.py"
        )
    )
    issues = await analyze(db)
    stale = [i for i in issues if i.type == "stale_node"]
    assert len(stale) >= 1
    assert stale[0].severity == IssueSeverity.warning
    assert "OldService" in stale[0].message


# ===== Info checks =====


async def test_unused_module(db: Database):
    """Module with no edges → unused_module, severity=info."""
    await db.create_node(
        NodeCreateInput(name="utils", type=NodeType.module)
    )
    issues = await analyze(db)
    unused = [i for i in issues if i.type == "unused_module"]
    assert len(unused) >= 1
    assert unused[0].severity == IssueSeverity.info
    assert "utils" in unused[0].message


async def test_connected_module_not_unused(db: Database):
    """Module with edge → no unused_module."""
    m = await db.create_node(
        NodeCreateInput(name="utils", type=NodeType.module)
    )
    svc = await db.create_node(
        NodeCreateInput(name="API", type=NodeType.service)
    )
    await db.create_edge(EdgeCreateInput(
        source_id=svc.id, target_id=m.id, relationship=EdgeRelationship.depends_on
    ))
    issues = await analyze(db)
    unused = [i for i in issues if i.type == "unused_module"]
    flagged_ids = set()
    for u in unused:
        flagged_ids.update(u.node_ids)
    assert m.id not in flagged_ids


async def test_missing_description(db: Database):
    """Node with no description → missing_description."""
    await db.create_node(
        NodeCreateInput(name="Mystery", type=NodeType.service)
    )
    issues = await analyze(db)
    missing = [i for i in issues if i.type == "missing_description"]
    assert len(missing) >= 1
    assert any("Mystery" in m.message for m in missing)


# ===== Filtering + misc =====


async def test_clean_blueprint_zero_issues(db: Database):
    """Clean blueprint with connected components → zero critical/warning issues of structural type."""
    svc = await db.create_node(
        NodeCreateInput(
            name="API", type=NodeType.service,
            description="Main API", status=NodeStatus.built,
        )
    )
    db_node = await db.create_node(
        NodeCreateInput(
            name="PostgreSQL", type=NodeType.database,
            description="Main database",
        )
    )
    tbl = await db.create_node(
        NodeCreateInput(
            name="users", type=NodeType.table,
            description="Users table",
        )
    )
    await db.create_edge(EdgeCreateInput(
        source_id=svc.id, target_id=db_node.id,
        relationship=EdgeRelationship.connects_to,
    ))
    await db.create_edge(EdgeCreateInput(
        source_id=svc.id, target_id=tbl.id,
        relationship=EdgeRelationship.reads_from,
    ))
    issues = await analyze(db, severity=IssueSeverity.critical)
    assert len(issues) == 0

    # Verify analyze() is not trivially returning [] — unfiltered should have warnings
    all_issues = await analyze(db)
    assert len(all_issues) > 0, "Expected at least some non-critical issues (e.g. SPOF)"


async def test_severity_filter_critical(db: Database):
    """severity=critical → only critical issues."""
    await db.create_node(
        NodeCreateInput(name="planned_thing", type=NodeType.module, status=NodeStatus.planned)
    )
    await db.create_node(
        NodeCreateInput(name="orphan_table", type=NodeType.table)
    )
    issues = await analyze(db, severity=IssueSeverity.critical)
    for i in issues:
        assert i.severity == IssueSeverity.critical


async def test_severity_filter_warning(db: Database):
    """severity=warning → only warning issues."""
    await db.create_node(
        NodeCreateInput(name="planned_thing", type=NodeType.module, status=NodeStatus.planned)
    )
    await db.create_node(
        NodeCreateInput(name="orphan_table", type=NodeType.table)
    )
    issues = await analyze(db, severity=IssueSeverity.warning)
    for i in issues:
        assert i.severity == IssueSeverity.warning


async def test_get_changes(db: Database):
    """db.get_changes returns correct entries, empty for future timestamp."""
    before = "2000-01-01T00:00:00"
    await db.create_node(
        NodeCreateInput(name="X", type=NodeType.service)
    )
    changes = await db.get_changes(before)
    assert len(changes) >= 1
    assert changes[0].action == "node_created"

    # Future timestamp → empty
    future = "2099-01-01T00:00:00"
    changes = await db.get_changes(future)
    assert len(changes) == 0
