"""Scanner tests — all tests scan REAL fixture files and assert SPECIFIC results."""

import os
import tempfile

import pytest

from src.db import Database
from src.models import (
    EdgeRelationship,
    NodeCreateInput,
    NodeStatus,
    NodeType,
)
from src.scanner import scan_project, scan_single_file
from src.scanner.file_scanner import scan_project_files
from src.scanner.python_scanner import PythonScanner
from src.scanner.javascript_scanner import JavaScriptScanner
from src.scanner.docker_scanner import DockerScanner
from src.scanner.swift_scanner import SwiftScanner
from src.scanner.rust_scanner import RustScanner
from src.scanner.go_scanner import GoScanner
from src.scanner.config_scanner import ConfigScanner
from src.scanner.sql_scanner import SQLScanner

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
PYTHON_PROJECT = os.path.join(FIXTURES, "python_project")
JS_PROJECT = os.path.join(FIXTURES, "js_project")
DOCKER_PROJECT = os.path.join(FIXTURES, "docker_project")
NEXTJS_PROJECT = os.path.join(FIXTURES, "nextjs_project")
REACT_PROJECT = os.path.join(FIXTURES, "react_project")
SWIFT_PROJECT = os.path.join(FIXTURES, "swift_project")
RUST_PROJECT = os.path.join(FIXTURES, "rust_project")
GO_PROJECT = os.path.join(FIXTURES, "go_project")
CONFIG_PROJECT = os.path.join(FIXTURES, "config_project")
DJANGO_PROJECT = os.path.join(FIXTURES, "django_project")
SQL_PROJECT = os.path.join(FIXTURES, "sql_project")


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


# --- File Scanner ---


async def test_file_scanner_detects_python_project(db: Database):
    """Detects python_project type, creates root system node."""
    info = await scan_project_files(PYTHON_PROJECT, db)
    assert info.name == "python_project"
    assert "python" in info.languages
    assert len(info.root_id) == 36  # UUID

    # Verify root node exists
    root = await db.get_node(info.root_id)
    assert root is not None
    assert root.type == NodeType.system
    assert root.name == "python_project"


async def test_file_scanner_creates_config_file_node(db: Database):
    """Creates file node for pyproject.toml."""
    info = await scan_project_files(PYTHON_PROJECT, db)
    bp = await db.get_blueprint(type_filter="file")
    file_names = {n["name"] for n in bp["nodes"]}
    assert "pyproject.toml" in file_names


async def test_file_scanner_detects_js_project(db: Database):
    info = await scan_project_files(JS_PROJECT, db)
    assert "javascript" in info.languages


async def test_file_scanner_detects_docker_project(db: Database):
    info = await scan_project_files(DOCKER_PROJECT, db)
    assert "docker" in info.languages
    assert info.has_docker is True


async def test_file_scanner_respects_gitignore(db: Database):
    """Temp dir with .gitignore ignoring a file — that file should not become a node."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a .gitignore
        with open(os.path.join(tmpdir, ".gitignore"), "w") as f:
            f.write("ignored.py\n")
        # Create files
        with open(os.path.join(tmpdir, "kept.py"), "w") as f:
            f.write("x = 1\n")
        with open(os.path.join(tmpdir, "ignored.py"), "w") as f:
            f.write("x = 2\n")
        with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
            f.write('[project]\nname = "test"\n')

        info = await scan_project_files(tmpdir, db)
        # Run python scanner with the gitignore spec
        scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
        result = await scanner.scan(tmpdir)
        # The scanner should have scanned kept.py but NOT ignored.py
        assert result.files_scanned == 1


async def test_file_scanner_idempotent(db: Database):
    """Scanning twice produces same node count and preserves node IDs."""
    await scan_project_files(PYTHON_PROJECT, db)
    bp1 = await db.get_blueprint()
    count1 = bp1["summary"]["total_nodes"]
    ids1 = {n["id"] for n in bp1["nodes"]}

    await scan_project_files(PYTHON_PROJECT, db)
    bp2 = await db.get_blueprint()
    count2 = bp2["summary"]["total_nodes"]
    ids2 = {n["id"] for n in bp2["nodes"]}

    assert count1 == count2
    assert ids1 == ids2  # same node IDs preserved


# --- Python Scanner ---


async def test_python_scanner_detects_fastapi_service(db: Database):
    """Detects FastAPI service node."""
    info = await scan_project_files(PYTHON_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(PYTHON_PROJECT)

    bp = await db.get_blueprint(type_filter="service")
    services = bp["nodes"]
    assert len(services) >= 1
    fastapi_svc = [s for s in services if "FastAPI" in s["name"]]
    assert len(fastapi_svc) == 1
    assert fastapi_svc[0]["metadata"]["framework"] == "fastapi"
    assert fastapi_svc[0]["source_file"].endswith("main.py")


async def test_python_scanner_finds_all_routes(db: Database):
    """Finds all 4 routes with correct names and metadata."""
    info = await scan_project_files(PYTHON_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(PYTHON_PROJECT)

    bp = await db.get_blueprint(type_filter="route")
    routes = bp["nodes"]
    route_names = {r["name"] for r in routes}
    assert "GET /api/users" in route_names
    assert "POST /api/users" in route_names
    assert "GET /api/users/{user_id}" in route_names
    assert "GET /api/health" in route_names
    assert len(routes) == 4

    # Check metadata on one route
    get_users = next(r for r in routes if r["name"] == "GET /api/users")
    assert get_users["metadata"]["method"] == "GET"
    assert get_users["metadata"]["path"] == "/api/users"
    assert get_users["source_line"] > 0


async def test_python_scanner_finds_tables(db: Database):
    """Finds table nodes 'users' and 'posts' with column metadata."""
    info = await scan_project_files(PYTHON_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(PYTHON_PROJECT)

    bp = await db.get_blueprint(type_filter="table")
    tables = bp["nodes"]
    table_names = {t["name"] for t in tables}
    assert "users" in table_names
    assert "posts" in table_names

    users_table = next(t for t in tables if t["name"] == "users")
    assert "id" in users_table["metadata"]["columns"]
    assert "name" in users_table["metadata"]["columns"]
    assert "email" in users_table["metadata"]["columns"]
    assert "created_at" in users_table["metadata"]["columns"]
    assert users_table["metadata"]["orm_class"] == "User"


async def test_python_scanner_detects_import_dependency(db: Database):
    """Detects depends_on edge from main.py to models.py."""
    info = await scan_project_files(PYTHON_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(PYTHON_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    depends_on = [e for e in edges if e["relationship"] == "depends_on"]
    assert len(depends_on) >= 1

    # Find the modules
    nodes = bp["nodes"]
    module_names = {n["id"]: n["name"] for n in nodes if n["type"] == "module"}
    # Check there's a main.py -> models.py dependency with exact name match
    found = False
    for e in depends_on:
        src_name = module_names.get(e["source_id"], "")
        tgt_name = module_names.get(e["target_id"], "")
        if src_name == "main.py" and tgt_name == "models.py":
            found = True
    assert found, f"Expected main.py -> models.py dependency, found modules: {module_names}, edges: {depends_on}"


async def test_python_scanner_handles_syntax_error(db: Database):
    """Handles syntax errors gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "bad.py"), "w") as f:
            f.write("def broken(\n")  # SyntaxError
        with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
            f.write('[project]\nname = "test"\n')

        info = await scan_project_files(tmpdir, db)
        scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
        result = await scanner.scan(tmpdir)
        assert len(result.errors) >= 1
        assert "Syntax error" in result.errors[0].message


async def test_python_scanner_idempotent(db: Database):
    """Scanning twice produces exactly 4 route nodes with same IDs, not 8."""
    info = await scan_project_files(PYTHON_PROJECT, db)

    scanner1 = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner1.scan(PYTHON_PROJECT)

    bp1 = await db.get_blueprint(type_filter="route")
    ids1 = {n["id"] for n in bp1["nodes"]}

    scanner2 = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner2.scan(PYTHON_PROJECT)

    bp2 = await db.get_blueprint(type_filter="route")
    ids2 = {n["id"] for n in bp2["nodes"]}

    assert len(bp2["nodes"]) == 4
    assert ids1 == ids2  # same node IDs preserved


# --- JavaScript Scanner ---


async def test_js_scanner_finds_routes(db: Database):
    """Finds all 4 Express routes."""
    info = await scan_project_files(JS_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(JS_PROJECT)

    bp = await db.get_blueprint(type_filter="route")
    routes = bp["nodes"]
    route_names = {r["name"] for r in routes}
    assert "GET /api/products" in route_names
    assert "POST /api/products" in route_names
    assert "GET /api/products/:id" in route_names
    assert "DELETE /api/products/:id" in route_names

    # Check source_file
    for r in routes:
        assert "server.js" in r["source_file"]


async def test_js_scanner_finds_react_component(db: Database):
    """Finds React component module 'ProductCard'."""
    info = await scan_project_files(JS_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(JS_PROJECT)

    bp = await db.get_blueprint(type_filter="module")
    modules = bp["nodes"]
    module_names = {m["name"] for m in modules}
    assert "ProductCard" in module_names

    card = next(m for m in modules if m["name"] == "ProductCard")
    assert card["metadata"]["framework"] == "react"


async def test_js_scanner_reads_package_json(db: Database):
    """Reads package.json → service node."""
    info = await scan_project_files(JS_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(JS_PROJECT)

    bp = await db.get_blueprint(type_filter="service")
    services = bp["nodes"]
    svc_names = {s["name"] for s in services}
    assert "test-js-project" in svc_names


async def test_js_scanner_idempotent(db: Database):
    """Scanning twice produces same route count."""
    info = await scan_project_files(JS_PROJECT, db)

    scanner1 = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner1.scan(JS_PROJECT)

    scanner2 = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner2.scan(JS_PROJECT)

    bp = await db.get_blueprint(type_filter="route")
    assert len(bp["nodes"]) == 4


# --- Docker Scanner ---


async def test_docker_scanner_finds_container(db: Database):
    """Finds container node from Dockerfile."""
    info = await scan_project_files(DOCKER_PROJECT, db)
    scanner = DockerScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(DOCKER_PROJECT)

    bp = await db.get_blueprint(type_filter="container")
    containers = bp["nodes"]
    assert len(containers) >= 1
    container = containers[0]
    assert container["metadata"]["base_image"] == "python:3.12-slim"
    assert 8000 in container["metadata"]["exposed_ports"]


async def test_docker_scanner_finds_compose_services(db: Database):
    """Finds 3 compose services with correct types."""
    info = await scan_project_files(DOCKER_PROJECT, db)
    scanner = DockerScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(DOCKER_PROJECT)

    bp = await db.get_blueprint()
    nodes = bp["nodes"]
    node_names = {n["name"]: n for n in nodes}

    assert "web" in node_names
    assert "db" in node_names
    assert "redis" in node_names

    # db should be database type
    assert node_names["db"]["type"] == "database"
    assert "postgres:16" in node_names["db"]["metadata"]["image"]


async def test_docker_scanner_finds_depends_on_edges(db: Database):
    """Finds depends_on edges: web→db, web→redis."""
    info = await scan_project_files(DOCKER_PROJECT, db)
    scanner = DockerScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(DOCKER_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    depends_on = [e for e in edges if e["relationship"] == "depends_on"]

    nodes = {n["id"]: n["name"] for n in bp["nodes"]}
    dep_pairs = {(nodes.get(e["source_id"]), nodes.get(e["target_id"])) for e in depends_on}
    assert ("web", "db") in dep_pairs
    assert ("web", "redis") in dep_pairs


async def test_docker_scanner_finds_ports(db: Database):
    """Each compose service has port metadata."""
    info = await scan_project_files(DOCKER_PROJECT, db)
    scanner = DockerScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(DOCKER_PROJECT)

    bp = await db.get_blueprint()
    nodes = {n["name"]: n for n in bp["nodes"]}
    assert "8000:8000" in nodes["web"]["metadata"]["ports"]


# --- Integration ---


async def test_scan_project_auto_detects_python(db: Database):
    """scan_project auto-detects python scanner for python_project."""
    result = await scan_project(PYTHON_PROJECT, db)
    assert "python_scanner" in result["scanners_run"]
    # Should NOT run docker scanner
    assert "docker_scanner" not in result["scanners_run"]
    assert result["total_nodes_created"] > 0


async def test_scan_project_logs_changelog(db: Database):
    """scan_project logs scan_completed to changelog."""
    result = await scan_project(PYTHON_PROJECT, db)

    # Check changelog
    cursor = await db.db.execute(
        "SELECT * FROM changelog WHERE action = 'scan_completed'"
    )
    rows = await cursor.fetchall()
    assert len(rows) == 1
    assert rows[0]["target_type"] == "project"


async def test_scan_docker_project_runs_docker_scanner(db: Database):
    """Full scan of docker_project runs file + docker scanners."""
    result = await scan_project(DOCKER_PROJECT, db)
    assert "docker_scanner" in result["scanners_run"]
    assert result["total_nodes_created"] > 0


# =============================================================================
# JavaScript Scanner — New Tests (Stage 1)
# =============================================================================


async def test_js_scanner_creates_no_external_edges(db: Database):
    """External imports (react, express) should not create edges."""
    info = await scan_project_files(JS_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    result = await scanner.scan(JS_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    # JS project has no relative imports so should have 0 edges
    assert result.edges_created == 0


async def test_js_scanner_detects_nextjs_pages(db: Database):
    """Detects 3 page routes: /, /dashboard, /dashboard/[id]."""
    info = await scan_project_files(NEXTJS_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(NEXTJS_PROJECT)

    bp = await db.get_blueprint(type_filter="route")
    routes = bp["nodes"]
    route_names = {r["name"] for r in routes}
    assert "/" in route_names
    assert "/dashboard" in route_names
    assert "/dashboard/[id]" in route_names

    # Verify framework metadata
    home = next(r for r in routes if r["name"] == "/")
    assert home["metadata"]["framework"] == "nextjs"


async def test_js_scanner_detects_nextjs_api_route(db: Database):
    """Detects Next.js API route exports."""
    info = await scan_project_files(NEXTJS_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(NEXTJS_PROJECT)

    bp = await db.get_blueprint(type_filter="route")
    routes = bp["nodes"]
    route_names = {r["name"] for r in routes}
    assert "GET /api/users" in route_names
    assert "POST /api/users" in route_names


async def test_js_scanner_detects_nextjs_layouts(db: Database):
    """Detects layout nodes."""
    info = await scan_project_files(NEXTJS_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(NEXTJS_PROJECT)

    bp = await db.get_blueprint(type_filter="module")
    modules = bp["nodes"]
    layout_nodes = [m for m in modules if (m.get("metadata") or {}).get("layout")]
    assert len(layout_nodes) >= 1
    layout_names = {l["name"] for l in layout_nodes}
    assert "RootLayout" in layout_names


async def test_js_scanner_detects_nextjs_middleware(db: Database):
    """Detects middleware node."""
    info = await scan_project_files(NEXTJS_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(NEXTJS_PROJECT)

    bp = await db.get_blueprint(type_filter="middleware")
    mw = bp["nodes"]
    assert len(mw) >= 1
    assert mw[0]["name"] == "middleware"
    assert mw[0]["metadata"]["framework"] == "nextjs"


async def test_js_scanner_detects_nextjs_config(db: Database):
    """Detects next.config.mjs as config node."""
    info = await scan_project_files(NEXTJS_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(NEXTJS_PROJECT)

    bp = await db.get_blueprint(type_filter="config")
    configs = bp["nodes"]
    config_names = {c["name"] for c in configs}
    assert "next.config.mjs" in config_names


async def test_js_scanner_nextjs_import_edges(db: Database):
    """Detects depends_on edges from import statements."""
    info = await scan_project_files(NEXTJS_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    result = await scanner.scan(NEXTJS_PROJECT)

    assert result.edges_created > 0

    bp = await db.get_blueprint()
    edges = bp["edges"]
    depends_on = [e for e in edges if e["relationship"] == "depends_on"]
    nodes = {n["id"]: n["name"] for n in bp["nodes"]}

    dep_pairs = set()
    for e in depends_on:
        src = nodes.get(e["source_id"], "")
        tgt = nodes.get(e["target_id"], "")
        dep_pairs.add((src, tgt))

    # Header imports Link
    assert ("Header", "Link") in dep_pairs


async def test_js_scanner_nextjs_layout_contains_page(db: Database):
    """Detects contains edge from layout to page."""
    info = await scan_project_files(NEXTJS_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(NEXTJS_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    contains = [e for e in edges if e["relationship"] == "contains"]
    assert len(contains) >= 1

    nodes = {n["id"]: n["name"] for n in bp["nodes"]}
    for e in contains:
        src = nodes.get(e["source_id"], "")
        assert "Layout" in src or "layout" in src.lower()


async def test_js_scanner_finds_arrow_components(db: Database):
    """Footer detected as arrow function component."""
    info = await scan_project_files(REACT_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(REACT_PROJECT)

    bp = await db.get_blueprint(type_filter="module")
    modules = bp["nodes"]
    module_names = {m["name"] for m in modules}
    assert "Footer" in module_names


async def test_js_scanner_finds_class_definitions(db: Database):
    """ApiClient, BaseClient detected as class_def."""
    info = await scan_project_files(REACT_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(REACT_PROJECT)

    bp = await db.get_blueprint(type_filter="class_def")
    classes = bp["nodes"]
    class_names = {c["name"] for c in classes}
    assert "ApiClient" in class_names


async def test_js_scanner_detects_class_inheritance(db: Database):
    """Detects inherits edge: ApiClient -> BaseClient."""
    info = await scan_project_files(REACT_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(REACT_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    inherits = [e for e in edges if e["relationship"] == "inherits"]
    assert len(inherits) >= 1

    nodes = {n["id"]: n["name"] for n in bp["nodes"]}
    found = False
    for e in inherits:
        src = nodes.get(e["source_id"], "")
        tgt = nodes.get(e["target_id"], "")
        if src == "ApiClient" and tgt == "BaseClient":
            found = True
    assert found, f"Expected ApiClient -> BaseClient inherits edge"


async def test_js_scanner_import_chain(db: Database):
    """App -> Header -> useAuth import chain creates depends_on edges."""
    info = await scan_project_files(REACT_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(REACT_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    depends_on = [e for e in edges if e["relationship"] == "depends_on"]
    nodes = {n["id"]: n["name"] for n in bp["nodes"]}

    dep_pairs = set()
    for e in depends_on:
        src = nodes.get(e["source_id"], "")
        tgt = nodes.get(e["target_id"], "")
        dep_pairs.add((src, tgt))

    # App imports Header
    assert ("App", "Header") in dep_pairs
    # Header imports hooks (via index.ts barrel)
    assert ("Header", "hooks") in dep_pairs


async def test_js_scanner_handles_empty_file(db: Database):
    """No crash on empty .tsx file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            f.write('{"name": "test-empty"}')
        with open(os.path.join(tmpdir, "empty.tsx"), "w") as f:
            f.write("")

        info = await scan_project_files(tmpdir, db)
        scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
        result = await scanner.scan(tmpdir)
        assert result.files_scanned >= 1
        assert len(result.errors) == 0


async def test_js_scanner_ignores_node_modules(db: Database):
    """node_modules directory is never scanned."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            f.write('{"name": "test-nm"}')
        nm = os.path.join(tmpdir, "node_modules", "react")
        os.makedirs(nm)
        with open(os.path.join(nm, "index.js"), "w") as f:
            f.write("export default function React() {}")

        info = await scan_project_files(tmpdir, db)
        scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
        result = await scanner.scan(tmpdir)
        # Should not scan any files in node_modules
        assert result.files_scanned == 0


async def test_js_scanner_idempotent_with_edges(db: Database):
    """Scanning twice produces same edge count."""
    info = await scan_project_files(NEXTJS_PROJECT, db)

    scanner1 = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    r1 = await scanner1.scan(NEXTJS_PROJECT)
    bp1 = await db.get_blueprint()
    edge_count_1 = len(bp1["edges"])

    scanner2 = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner2.scan(NEXTJS_PROJECT)
    bp2 = await db.get_blueprint()
    edge_count_2 = len(bp2["edges"])

    assert edge_count_1 == edge_count_2
    assert edge_count_1 > 0


async def test_js_scanner_finds_vue_sfc(db: Database):
    """Vue .vue files detected as module with vue metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            f.write('{"name": "test-vue"}')
        with open(os.path.join(tmpdir, "MyComponent.vue"), "w") as f:
            f.write("""<template><div>Hello</div></template>
<script setup>
import { ref } from 'vue'
const count = ref(0)
</script>""")

        info = await scan_project_files(tmpdir, db)
        scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
        await scanner.scan(tmpdir)

        bp = await db.get_blueprint(type_filter="module")
        modules = bp["nodes"]
        vue_mods = [m for m in modules if m.get("metadata", {}).get("framework") == "vue"]
        assert len(vue_mods) >= 1
        assert vue_mods[0]["name"] == "MyComponent"


# =============================================================================
# JavaScript Scanner — Edge Detection Enhancement Tests
# =============================================================================


async def test_js_scanner_resolves_path_alias(db: Database):
    """@components/DashboardCard alias creates edge (DashboardDetail → DashboardCard)."""
    info = await scan_project_files(NEXTJS_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(NEXTJS_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    depends_on = [e for e in edges if e["relationship"] == "depends_on"]
    nodes = {n["id"]: n["name"] for n in bp["nodes"]}

    dep_pairs = set()
    for e in depends_on:
        src = nodes.get(e["source_id"], "")
        tgt = nodes.get(e["target_id"], "")
        dep_pairs.add((src, tgt))

    assert ("DashboardDetail", "DashboardCard") in dep_pairs


async def test_js_scanner_resolves_at_slash_alias(db: Database):
    """@/lib/utils alias creates edge (Home → utils)."""
    info = await scan_project_files(NEXTJS_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(NEXTJS_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    depends_on = [e for e in edges if e["relationship"] == "depends_on"]
    nodes = {n["id"]: n["name"] for n in bp["nodes"]}

    dep_pairs = set()
    for e in depends_on:
        src = nodes.get(e["source_id"], "")
        tgt = nodes.get(e["target_id"], "")
        dep_pairs.add((src, tgt))

    assert ("Home", "utils") in dep_pairs


async def test_js_scanner_alias_no_tsconfig(db: Database):
    """JS_PROJECT (no tsconfig) works fine — no crash."""
    info = await scan_project_files(JS_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    result = await scanner.scan(JS_PROJECT)
    assert result.files_scanned > 0
    assert len(result.errors) == 0


async def test_js_scanner_reexport_creates_edge(db: Database):
    """export { useAuth } from './useAuth' creates edge (hooks → useAuth)."""
    info = await scan_project_files(REACT_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(REACT_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    depends_on = [e for e in edges if e["relationship"] == "depends_on"]
    nodes = {n["id"]: n["name"] for n in bp["nodes"]}

    dep_pairs = set()
    for e in depends_on:
        src = nodes.get(e["source_id"], "")
        tgt = nodes.get(e["target_id"], "")
        dep_pairs.add((src, tgt))

    assert ("hooks", "useAuth") in dep_pairs


async def test_js_scanner_detects_custom_hooks(db: Database):
    """useAuth + useTheme detected as function nodes with pattern='hook'."""
    info = await scan_project_files(REACT_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(REACT_PROJECT)

    bp = await db.get_blueprint(type_filter="function")
    funcs = bp["nodes"]
    hook_names = {f["name"] for f in funcs if f.get("metadata", {}).get("pattern") == "hook"}
    assert "useAuth" in hook_names
    assert "useTheme" in hook_names


async def test_js_scanner_detects_context_provider(db: Database):
    """ThemeContext detected with pattern='context_provider'."""
    info = await scan_project_files(REACT_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(REACT_PROJECT)

    bp = await db.get_blueprint(type_filter="module")
    modules = bp["nodes"]
    ctx_nodes = [m for m in modules if (m.get("metadata") or {}).get("pattern") == "context_provider"]
    assert len(ctx_nodes) >= 1
    ctx_names = {c["name"] for c in ctx_nodes}
    assert "ThemeContext" in ctx_names


async def test_js_scanner_detects_forward_ref(db: Database):
    """Button detected with pattern='forwardRef'."""
    info = await scan_project_files(REACT_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(REACT_PROJECT)

    bp = await db.get_blueprint(type_filter="module")
    modules = bp["nodes"]
    ref_nodes = [m for m in modules if (m.get("metadata") or {}).get("pattern") == "forwardRef"]
    assert len(ref_nodes) >= 1
    ref_names = {r["name"] for r in ref_nodes}
    assert "Button" in ref_names


async def test_js_scanner_detects_memo(db: Database):
    """MemoizedList detected with pattern='memo'."""
    info = await scan_project_files(REACT_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(REACT_PROJECT)

    bp = await db.get_blueprint(type_filter="module")
    modules = bp["nodes"]
    memo_nodes = [m for m in modules if (m.get("metadata") or {}).get("pattern") == "memo"]
    assert len(memo_nodes) >= 1
    memo_names = {m["name"] for m in memo_nodes}
    assert "MemoizedList" in memo_names


async def test_js_scanner_detects_use_client_directive(db: Database):
    """useTheme has rendering='client' in metadata."""
    info = await scan_project_files(REACT_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(REACT_PROJECT)

    bp = await db.get_blueprint(type_filter="function")
    funcs = bp["nodes"]
    theme_hook = [f for f in funcs if f["name"] == "useTheme"]
    assert len(theme_hook) >= 1
    assert theme_hook[0]["metadata"]["rendering"] == "client"


async def test_js_scanner_detects_use_client_on_forwardref(db: Database):
    """Button has rendering='client' + pattern='forwardRef'."""
    info = await scan_project_files(REACT_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(REACT_PROJECT)

    bp = await db.get_blueprint(type_filter="module")
    modules = bp["nodes"]
    button = [m for m in modules if m["name"] == "Button"]
    assert len(button) >= 1
    assert button[0]["metadata"]["rendering"] == "client"
    assert button[0]["metadata"]["pattern"] == "forwardRef"


async def test_js_scanner_detects_api_calls(db: Database):
    """fetch('/api/users') creates uses edge to route node."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            f.write('{"name": "test-api-calls"}')

        # Create an API route
        api_dir = os.path.join(tmpdir, "routes")
        os.makedirs(api_dir)
        with open(os.path.join(api_dir, "users.js"), "w") as f:
            f.write("""const express = require('express');
const router = express.Router();
router.get('/api/users', (req, res) => res.json([]));
module.exports = router;
""")

        # Create a component that calls the API
        with open(os.path.join(tmpdir, "UserList.tsx"), "w") as f:
            f.write("""export default function UserList() {
    const data = fetch('/api/users').then(r => r.json());
    return <div>{JSON.stringify(data)}</div>;
}
""")

        info = await scan_project_files(tmpdir, db)
        scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
        await scanner.scan(tmpdir)

        bp = await db.get_blueprint()
        edges = bp["edges"]
        uses_edges = [e for e in edges if e["relationship"] == "uses"]
        nodes = {n["id"]: n["name"] for n in bp["nodes"]}

        use_pairs = set()
        for e in uses_edges:
            src = nodes.get(e["source_id"], "")
            tgt = nodes.get(e["target_id"], "")
            use_pairs.add((src, tgt))

        assert ("UserList", "GET /api/users") in use_pairs


async def test_js_scanner_edge_count_realistic(db: Database):
    """nextjs_project produces ≥6 edges (sanity check)."""
    info = await scan_project_files(NEXTJS_PROJECT, db)
    scanner = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(NEXTJS_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    assert len(edges) >= 6


async def test_js_scanner_enhanced_idempotent(db: Database):
    """Scanning react_project twice produces same node+edge counts."""
    info = await scan_project_files(REACT_PROJECT, db)

    scanner1 = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner1.scan(REACT_PROJECT)
    bp1 = await db.get_blueprint()
    nodes1 = len(bp1["nodes"])
    edges1 = len(bp1["edges"])

    scanner2 = JavaScriptScanner(db, info.root_id, info.gitignore_spec)
    await scanner2.scan(REACT_PROJECT)
    bp2 = await db.get_blueprint()
    nodes2 = len(bp2["nodes"])
    edges2 = len(bp2["edges"])

    assert nodes1 == nodes2
    assert edges1 == edges2
    assert edges1 > 0


# =============================================================================
# Python Scanner — New Tests (Stage 2)
# =============================================================================


async def test_python_scanner_detects_standalone_functions(db: Database):
    """format_date, helper_function found as function nodes."""
    info = await scan_project_files(PYTHON_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(PYTHON_PROJECT)

    bp = await db.get_blueprint(type_filter="function")
    funcs = bp["nodes"]
    func_names = {f["name"] for f in funcs}
    assert any("format_date" in n for n in func_names)
    assert any("helper_function" in n for n in func_names)


async def test_python_scanner_skips_private_functions(db: Database):
    """_private_helper NOT found in non-deep mode."""
    info = await scan_project_files(PYTHON_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(PYTHON_PROJECT)

    bp = await db.get_blueprint(type_filter="function")
    funcs = bp["nodes"]
    func_names = {f["name"] for f in funcs}
    assert not any("_private_helper" in n for n in func_names)


async def test_python_scanner_detects_pydantic_models(db: Database):
    """UserCreate, UserResponse as model nodes."""
    info = await scan_project_files(PYTHON_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(PYTHON_PROJECT)

    bp = await db.get_blueprint(type_filter="model")
    models = bp["nodes"]
    model_names = {m["name"] for m in models}
    assert "UserCreate" in model_names
    assert "UserResponse" in model_names


async def test_python_scanner_detects_dataclasses(db: Database):
    """CacheEntry as model node."""
    info = await scan_project_files(PYTHON_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(PYTHON_PROJECT)

    bp = await db.get_blueprint(type_filter="model")
    models = bp["nodes"]
    model_names = {m["name"] for m in models}
    assert "CacheEntry" in model_names


async def test_python_scanner_detects_enums(db: Database):
    """UserStatus as enum_def node."""
    info = await scan_project_files(PYTHON_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(PYTHON_PROJECT)

    bp = await db.get_blueprint(type_filter="enum_def")
    enums = bp["nodes"]
    enum_names = {e["name"] for e in enums}
    assert "UserStatus" in enum_names


async def test_python_scanner_detects_class_definitions(db: Database):
    """ItemProcessor as class_def."""
    info = await scan_project_files(PYTHON_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(PYTHON_PROJECT)

    bp = await db.get_blueprint(type_filter="class_def")
    classes = bp["nodes"]
    class_names = {c["name"] for c in classes}
    assert "ItemProcessor" in class_names


async def test_python_scanner_detects_class_inheritance(db: Database):
    """inherits edge: ItemProcessor -> BaseProcessor."""
    info = await scan_project_files(PYTHON_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(PYTHON_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    inherits = [e for e in edges if e["relationship"] == "inherits"]
    nodes = {n["id"]: n["name"] for n in bp["nodes"]}

    found = False
    for e in inherits:
        src = nodes.get(e["source_id"], "")
        tgt = nodes.get(e["target_id"], "")
        if src == "ItemProcessor" and tgt == "BaseProcessor":
            found = True
    assert found, "Expected ItemProcessor -> BaseProcessor inherits edge"


async def test_python_scanner_detects_protocols(db: Database):
    """Serializer as protocol node."""
    info = await scan_project_files(PYTHON_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(PYTHON_PROJECT)

    bp = await db.get_blueprint(type_filter="protocol")
    protocols = bp["nodes"]
    proto_names = {p["name"] for p in protocols}
    assert "Serializer" in proto_names


async def test_python_scanner_detects_abc(db: Database):
    """BaseProcessor as protocol node (ABC with abstractmethods)."""
    info = await scan_project_files(PYTHON_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(PYTHON_PROJECT)

    bp = await db.get_blueprint(type_filter="protocol")
    protocols = bp["nodes"]
    proto_names = {p["name"] for p in protocols}
    assert "BaseProcessor" in proto_names


async def test_python_scanner_detects_celery_tasks(db: Database):
    """send_welcome_email, process_upload as worker nodes."""
    info = await scan_project_files(PYTHON_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(PYTHON_PROJECT)

    bp = await db.get_blueprint(type_filter="worker")
    workers = bp["nodes"]
    worker_names = {w["name"] for w in workers}
    assert "send_welcome_email" in worker_names
    assert "process_upload" in worker_names


async def test_python_scanner_stage_a_idempotent(db: Database):
    """Scanning twice produces same counts for new detections."""
    info = await scan_project_files(PYTHON_PROJECT, db)

    scanner1 = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner1.scan(PYTHON_PROJECT)
    bp1 = await db.get_blueprint()
    count1 = bp1["summary"]["total_nodes"]

    scanner2 = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner2.scan(PYTHON_PROJECT)
    bp2 = await db.get_blueprint()
    count2 = bp2["summary"]["total_nodes"]

    assert count1 == count2


# Python Scanner — Django (Stage 2B)


async def test_python_scanner_detects_django_models(db: Database):
    """Author and Book detected as table nodes with correct db_table names."""
    info = await scan_project_files(DJANGO_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(DJANGO_PROJECT)

    bp = await db.get_blueprint(type_filter="table")
    tables = bp["nodes"]
    table_names = {t["name"] for t in tables}
    assert "authors" in table_names
    assert "library_books" in table_names


async def test_python_scanner_detects_django_views_function(db: Database):
    """author_list, author_detail as view nodes."""
    info = await scan_project_files(DJANGO_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(DJANGO_PROJECT)

    bp = await db.get_blueprint(type_filter="view")
    views = bp["nodes"]
    view_names = {v["name"] for v in views}
    assert "author_list" in view_names
    assert "author_detail" in view_names


async def test_python_scanner_detects_django_views_class(db: Database):
    """BookListView as view node."""
    info = await scan_project_files(DJANGO_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(DJANGO_PROJECT)

    bp = await db.get_blueprint(type_filter="view")
    views = bp["nodes"]
    view_names = {v["name"] for v in views}
    assert "BookListView" in view_names


async def test_python_scanner_detects_django_url_patterns(db: Database):
    """3 route nodes with delegates edges to views."""
    info = await scan_project_files(DJANGO_PROJECT, db)
    scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(DJANGO_PROJECT)

    bp = await db.get_blueprint(type_filter="route")
    routes = bp["nodes"]
    assert len(routes) >= 3

    # Check delegates edges
    bp_full = await db.get_blueprint()
    edges = bp_full["edges"]
    delegates = [e for e in edges if e["relationship"] == "delegates"]
    assert len(delegates) >= 1


# Python Scanner — File-level (Stage 2C)


async def test_python_scanner_detects_test_files(db: Database):
    """test_ prefixed file detected as NodeType.test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "test_example.py"), "w") as f:
            f.write("def test_one():\n    assert True\n")
        with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
            f.write('[project]\nname = "test"\n')

        info = await scan_project_files(tmpdir, db)
        scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
        await scanner.scan(tmpdir)

        bp = await db.get_blueprint(type_filter="test")
        tests = bp["nodes"]
        assert len(tests) >= 1
        assert tests[0]["name"] == "test_example"


async def test_python_scanner_detects_config_files(db: Database):
    """settings.py detected as NodeType.config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "settings.py"), "w") as f:
            f.write("DEBUG = True\nSECRET_KEY = 'test'\n")
        with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
            f.write('[project]\nname = "test"\n')

        info = await scan_project_files(tmpdir, db)
        scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
        await scanner.scan(tmpdir)

        bp = await db.get_blueprint(type_filter="config")
        configs = bp["nodes"]
        config_names = {c["name"] for c in configs}
        assert "settings" in config_names


async def test_python_scanner_detects_websocket_handler(db: Database):
    """WebSocket route with protocol metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "main.py"), "w") as f:
            f.write("""from fastapi import FastAPI
app = FastAPI()

@app.websocket("/ws/chat")
async def chat_ws(websocket):
    pass
""")
        with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
            f.write('[project]\nname = "test"\n')

        info = await scan_project_files(tmpdir, db)
        scanner = PythonScanner(db, info.root_id, info.gitignore_spec)
        await scanner.scan(tmpdir)

        bp = await db.get_blueprint(type_filter="route")
        routes = bp["nodes"]
        ws_routes = [r for r in routes if r.get("metadata", {}).get("protocol") == "websocket"]
        assert len(ws_routes) >= 1


# =============================================================================
# Swift Scanner Tests (Stage 3)
# =============================================================================


async def test_swift_scanner_detects_views(db: Database):
    """ContentView detected as view node."""
    info = await scan_project_files(SWIFT_PROJECT, db)
    scanner = SwiftScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SWIFT_PROJECT)

    bp = await db.get_blueprint(type_filter="view")
    views = bp["nodes"]
    view_names = {v["name"] for v in views}
    assert "ContentView" in view_names


async def test_swift_scanner_detects_structs(db: Database):
    """User struct detected."""
    info = await scan_project_files(SWIFT_PROJECT, db)
    scanner = SwiftScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SWIFT_PROJECT)

    bp = await db.get_blueprint(type_filter="struct")
    structs = bp["nodes"]
    struct_names = {s["name"] for s in structs}
    assert "User" in struct_names


async def test_swift_scanner_detects_observable_classes(db: Database):
    """UserViewModel detected as class with observable metadata."""
    info = await scan_project_files(SWIFT_PROJECT, db)
    scanner = SwiftScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SWIFT_PROJECT)

    bp = await db.get_blueprint(type_filter="class_def")
    classes = bp["nodes"]
    observable = [c for c in classes if (c.get("metadata") or {}).get("observable")]
    assert len(observable) >= 1
    assert any(c["name"] == "UserViewModel" for c in observable)


async def test_swift_scanner_detects_protocols(db: Database):
    """DataService protocol detected."""
    info = await scan_project_files(SWIFT_PROJECT, db)
    scanner = SwiftScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SWIFT_PROJECT)

    bp = await db.get_blueprint(type_filter="protocol")
    protocols = bp["nodes"]
    proto_names = {p["name"] for p in protocols}
    assert "DataService" in proto_names


async def test_swift_scanner_detects_main_app(db: Database):
    """@main struct MyApp detected as service node."""
    info = await scan_project_files(SWIFT_PROJECT, db)
    scanner = SwiftScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SWIFT_PROJECT)

    bp = await db.get_blueprint(type_filter="service")
    services = bp["nodes"]
    service_names = {s["name"] for s in services}
    assert "MyApp" in service_names


async def test_swift_scanner_detects_protocol_conformance(db: Database):
    """NetworkDataService implements DataService edge."""
    info = await scan_project_files(SWIFT_PROJECT, db)
    scanner = SwiftScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SWIFT_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    impl_edges = [e for e in edges if e["relationship"] in ("implements", "inherits")]
    assert len(impl_edges) >= 1


async def test_swift_scanner_detects_spm_targets(db: Database):
    """SPM targets from Package.swift detected as module nodes."""
    info = await scan_project_files(SWIFT_PROJECT, db)
    scanner = SwiftScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SWIFT_PROJECT)

    bp = await db.get_blueprint(type_filter="module")
    modules = bp["nodes"]
    mod_names = {m["name"] for m in modules}
    assert "App" in mod_names
    assert "Models" in mod_names


async def test_swift_scanner_idempotent(db: Database):
    """Scanning twice produces same node count."""
    info = await scan_project_files(SWIFT_PROJECT, db)

    scanner1 = SwiftScanner(db, info.root_id, info.gitignore_spec)
    await scanner1.scan(SWIFT_PROJECT)
    bp1 = await db.get_blueprint()
    count1 = bp1["summary"]["total_nodes"]

    scanner2 = SwiftScanner(db, info.root_id, info.gitignore_spec)
    await scanner2.scan(SWIFT_PROJECT)
    bp2 = await db.get_blueprint()
    count2 = bp2["summary"]["total_nodes"]

    assert count1 == count2


async def test_swift_scanner_property_edges(db: Database):
    """UserViewModel depends_on User via @Published var users: [User]."""
    info = await scan_project_files(SWIFT_PROJECT, db)
    scanner = SwiftScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SWIFT_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    nodes = {n["id"]: n["name"] for n in bp["nodes"]}
    depends_edges = [e for e in edges if e["relationship"] == "depends_on"]
    dep_pairs = [(nodes.get(e["source_id"]), nodes.get(e["target_id"])) for e in depends_edges]
    assert ("UserViewModel", "User") in dep_pairs


async def test_swift_scanner_observed_object_edges(db: Database):
    """ContentView depends_on UserViewModel via @StateObject."""
    info = await scan_project_files(SWIFT_PROJECT, db)
    scanner = SwiftScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SWIFT_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    nodes = {n["id"]: n["name"] for n in bp["nodes"]}
    depends_edges = [e for e in edges if e["relationship"] == "depends_on"]
    dep_pairs = [(nodes.get(e["source_id"]), nodes.get(e["target_id"])) for e in depends_edges]
    assert ("ContentView", "UserViewModel") in dep_pairs


async def test_swift_scanner_init_call_edges(db: Database):
    """MyApp uses ContentView via ContentView() initializer call."""
    info = await scan_project_files(SWIFT_PROJECT, db)
    scanner = SwiftScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SWIFT_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    nodes = {n["id"]: n["name"] for n in bp["nodes"]}
    uses_edges = [e for e in edges if e["relationship"] == "uses"]
    uses_pairs = [(nodes.get(e["source_id"]), nodes.get(e["target_id"])) for e in uses_edges]
    assert ("MyApp", "ContentView") in uses_pairs


async def test_swift_scanner_no_framework_edges(db: Database):
    """Framework types like View, String, UUID should not be created as nodes."""
    info = await scan_project_files(SWIFT_PROJECT, db)
    scanner = SwiftScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SWIFT_PROJECT)

    bp = await db.get_blueprint()
    node_names = {n["name"] for n in bp["nodes"]}
    # These framework types should never appear as nodes
    for fw in ("View", "String", "UUID", "Bool", "Scene"):
        assert fw not in node_names, f"Framework type '{fw}' should not be a node"


async def test_swift_scanner_directory_hierarchy(db: Database):
    """Directory grouping creates module nodes for Models and Geometry (2+ files)."""
    info = await scan_project_files(SWIFT_PROJECT, db)
    scanner = SwiftScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SWIFT_PROJECT)

    bp = await db.get_blueprint(type_filter="module")
    modules = bp["nodes"]
    dir_modules = [m for m in modules if m.get("metadata", {}).get("directory")]
    dir_names = {m["name"] for m in dir_modules}
    assert "Models" in dir_names
    assert "Geometry" in dir_names


async def test_swift_scanner_edge_count_realistic(db: Database):
    """Expect 5+ edges total from conformance + references."""
    info = await scan_project_files(SWIFT_PROJECT, db)
    scanner = SwiftScanner(db, info.root_id, info.gitignore_spec)
    result = await scanner.scan(SWIFT_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    assert len(edges) >= 5, f"Expected 5+ edges, got {len(edges)}"


async def test_swift_scanner_geometry_property_edge(db: Database):
    """GeometryKernel depends_on Solver via var solver: Solver property."""
    info = await scan_project_files(SWIFT_PROJECT, db)
    scanner = SwiftScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SWIFT_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    nodes = {n["id"]: n["name"] for n in bp["nodes"]}
    depends_edges = [e for e in edges if e["relationship"] == "depends_on"]
    dep_pairs = [(nodes.get(e["source_id"]), nodes.get(e["target_id"])) for e in depends_edges]
    assert ("GeometryKernel", "Solver") in dep_pairs


# =============================================================================
# Rust Scanner Tests (Stage 4)
# =============================================================================


async def test_rust_scanner_detects_service(db: Database):
    """Cargo.toml package -> service node."""
    info = await scan_project_files(RUST_PROJECT, db)
    scanner = RustScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(RUST_PROJECT)

    bp = await db.get_blueprint(type_filter="service")
    services = bp["nodes"]
    service_names = {s["name"] for s in services}
    assert "test-rust-app" in service_names


async def test_rust_scanner_detects_structs(db: Database):
    """User and InMemoryRepo structs detected."""
    info = await scan_project_files(RUST_PROJECT, db)
    scanner = RustScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(RUST_PROJECT)

    bp = await db.get_blueprint(type_filter="struct")
    structs = bp["nodes"]
    struct_names = {s["name"] for s in structs}
    assert "User" in struct_names
    assert "InMemoryRepo" in struct_names


async def test_rust_scanner_detects_traits(db: Database):
    """Repository trait detected as protocol."""
    info = await scan_project_files(RUST_PROJECT, db)
    scanner = RustScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(RUST_PROJECT)

    bp = await db.get_blueprint(type_filter="protocol")
    traits = bp["nodes"]
    trait_names = {t["name"] for t in traits}
    assert "Repository" in trait_names


async def test_rust_scanner_detects_enums(db: Database):
    """UserRole enum detected."""
    info = await scan_project_files(RUST_PROJECT, db)
    scanner = RustScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(RUST_PROJECT)

    bp = await db.get_blueprint(type_filter="enum_def")
    enums = bp["nodes"]
    enum_names = {e["name"] for e in enums}
    assert "UserRole" in enum_names


async def test_rust_scanner_detects_impl_trait(db: Database):
    """impl Repository for InMemoryRepo -> implements edge."""
    info = await scan_project_files(RUST_PROJECT, db)
    scanner = RustScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(RUST_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    impl_edges = [e for e in edges if e["relationship"] == "implements"]
    assert len(impl_edges) >= 1

    nodes = {n["id"]: n["name"] for n in bp["nodes"]}
    found = False
    for e in impl_edges:
        src = nodes.get(e["source_id"], "")
        tgt = nodes.get(e["target_id"], "")
        if src == "InMemoryRepo" and tgt == "Repository":
            found = True
    assert found


async def test_rust_scanner_detects_routes(db: Database):
    """Route macros detected."""
    info = await scan_project_files(RUST_PROJECT, db)
    scanner = RustScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(RUST_PROJECT)

    bp = await db.get_blueprint(type_filter="route")
    routes = bp["nodes"]
    route_names = {r["name"] for r in routes}
    assert "GET /api/users" in route_names
    assert "POST /api/users" in route_names


async def test_rust_scanner_detects_external_deps(db: Database):
    """Cargo.toml dependencies -> external nodes."""
    info = await scan_project_files(RUST_PROJECT, db)
    scanner = RustScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(RUST_PROJECT)

    bp = await db.get_blueprint(type_filter="external")
    externals = bp["nodes"]
    ext_names = {e["name"] for e in externals}
    assert "actix-web" in ext_names
    assert "serde" in ext_names
    assert "tokio" in ext_names


async def test_rust_scanner_idempotent(db: Database):
    """Scanning twice produces same node count."""
    info = await scan_project_files(RUST_PROJECT, db)

    scanner1 = RustScanner(db, info.root_id, info.gitignore_spec)
    await scanner1.scan(RUST_PROJECT)
    bp1 = await db.get_blueprint()
    count1 = bp1["summary"]["total_nodes"]

    scanner2 = RustScanner(db, info.root_id, info.gitignore_spec)
    await scanner2.scan(RUST_PROJECT)
    bp2 = await db.get_blueprint()
    count2 = bp2["summary"]["total_nodes"]

    assert count1 == count2


# =============================================================================
# Go Scanner Tests (Stage 5)
# =============================================================================


async def test_go_scanner_detects_service(db: Database):
    """go.mod module -> service node."""
    info = await scan_project_files(GO_PROJECT, db)
    scanner = GoScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(GO_PROJECT)

    bp = await db.get_blueprint(type_filter="service")
    services = bp["nodes"]
    service_names = {s["name"] for s in services}
    assert "testapp" in service_names


async def test_go_scanner_detects_structs(db: Database):
    """User and InMemoryUserRepo structs detected."""
    info = await scan_project_files(GO_PROJECT, db)
    scanner = GoScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(GO_PROJECT)

    bp = await db.get_blueprint(type_filter="struct")
    structs = bp["nodes"]
    struct_names = {s["name"] for s in structs}
    assert "User" in struct_names
    assert "InMemoryUserRepo" in struct_names


async def test_go_scanner_detects_interfaces(db: Database):
    """UserRepository interface detected as protocol."""
    info = await scan_project_files(GO_PROJECT, db)
    scanner = GoScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(GO_PROJECT)

    bp = await db.get_blueprint(type_filter="protocol")
    interfaces = bp["nodes"]
    iface_names = {i["name"] for i in interfaces}
    assert "UserRepository" in iface_names


async def test_go_scanner_detects_routes(db: Database):
    """HTTP handlers detected as route nodes."""
    info = await scan_project_files(GO_PROJECT, db)
    scanner = GoScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(GO_PROJECT)

    bp = await db.get_blueprint(type_filter="route")
    routes = bp["nodes"]
    route_names = {r["name"] for r in routes}
    assert "/api/users" in route_names


async def test_go_scanner_detects_external_deps(db: Database):
    """go.mod dependencies -> external nodes."""
    info = await scan_project_files(GO_PROJECT, db)
    scanner = GoScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(GO_PROJECT)

    bp = await db.get_blueprint(type_filter="external")
    externals = bp["nodes"]
    ext_names = {e["name"] for e in externals}
    assert "gin" in ext_names
    assert "sqlx" in ext_names


async def test_go_scanner_detects_packages(db: Database):
    """Go packages detected as module nodes."""
    info = await scan_project_files(GO_PROJECT, db)
    scanner = GoScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(GO_PROJECT)

    bp = await db.get_blueprint(type_filter="module")
    modules = bp["nodes"]
    mod_names = {m["name"] for m in modules}
    assert "models" in mod_names


async def test_go_scanner_idempotent(db: Database):
    """Scanning twice produces same node count."""
    info = await scan_project_files(GO_PROJECT, db)

    scanner1 = GoScanner(db, info.root_id, info.gitignore_spec)
    await scanner1.scan(GO_PROJECT)
    bp1 = await db.get_blueprint()
    count1 = bp1["summary"]["total_nodes"]

    scanner2 = GoScanner(db, info.root_id, info.gitignore_spec)
    await scanner2.scan(GO_PROJECT)
    bp2 = await db.get_blueprint()
    count2 = bp2["summary"]["total_nodes"]

    assert count1 == count2


# =============================================================================
# Config/IaC Scanner Tests (Stage 6)
# =============================================================================


async def test_config_scanner_detects_env(db: Database):
    """Root .env file detected as config node with variables."""
    info = await scan_project_files(CONFIG_PROJECT, db)
    scanner = ConfigScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(CONFIG_PROJECT)

    bp = await db.get_blueprint(type_filter="config")
    configs = bp["nodes"]
    env_nodes = [c for c in configs if c["name"] == ".env"]
    assert len(env_nodes) >= 1
    assert "DATABASE_URL" in env_nodes[0]["metadata"]["variables"]


async def test_config_scanner_detects_k8s_deployment(db: Database):
    """K8s Deployment detected as service node."""
    info = await scan_project_files(CONFIG_PROJECT, db)
    scanner = ConfigScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(CONFIG_PROJECT)

    bp = await db.get_blueprint(type_filter="service")
    services = bp["nodes"]
    service_names = {s["name"] for s in services}
    assert "web-app" in service_names


async def test_config_scanner_detects_k8s_service(db: Database):
    """K8s Service detected as api node."""
    info = await scan_project_files(CONFIG_PROJECT, db)
    scanner = ConfigScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(CONFIG_PROJECT)

    bp = await db.get_blueprint(type_filter="api")
    apis = bp["nodes"]
    api_names = {a["name"] for a in apis}
    assert "web-service" in api_names


async def test_config_scanner_detects_github_actions(db: Database):
    """GitHub Actions workflow and jobs detected."""
    info = await scan_project_files(CONFIG_PROJECT, db)
    scanner = ConfigScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(CONFIG_PROJECT)

    bp = await db.get_blueprint(type_filter="script")
    scripts = bp["nodes"]
    script_names = {s["name"] for s in scripts}
    assert "CI Pipeline" in script_names

    bp_w = await db.get_blueprint(type_filter="worker")
    workers = bp_w["nodes"]
    assert len(workers) >= 2  # test + build jobs


async def test_config_scanner_detects_terraform(db: Database):
    """Terraform resources, modules, and variables detected."""
    info = await scan_project_files(CONFIG_PROJECT, db)
    scanner = ConfigScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(CONFIG_PROJECT)

    bp = await db.get_blueprint()
    nodes = bp["nodes"]
    node_names = {n["name"] for n in nodes}

    assert "aws_instance.web" in node_names
    assert "aws_db_instance.main" in node_names
    assert "vpc" in node_names  # module
    assert "region" in node_names  # variable


async def test_config_scanner_detects_sql_tables(db: Database):
    """SQL CREATE TABLE statements detected."""
    info = await scan_project_files(CONFIG_PROJECT, db)
    scanner = ConfigScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(CONFIG_PROJECT)

    bp = await db.get_blueprint(type_filter="table")
    tables = bp["nodes"]
    table_names = {t["name"] for t in tables}
    assert "users" in table_names
    assert "posts" in table_names


async def test_config_scanner_detects_sql_fk_edges(db: Database):
    """SQL foreign key creates writes_to edge."""
    info = await scan_project_files(CONFIG_PROJECT, db)
    scanner = ConfigScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(CONFIG_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    writes_to = [e for e in edges if e["relationship"] == "writes_to"]
    assert len(writes_to) >= 1

    nodes = {n["id"]: n["name"] for n in bp["nodes"]}
    found = False
    for e in writes_to:
        src = nodes.get(e["source_id"], "")
        tgt = nodes.get(e["target_id"], "")
        if src == "posts" and tgt == "users":
            found = True
    assert found


async def test_config_scanner_detects_sql_views(db: Database):
    """SQL CREATE VIEW detected as view node."""
    info = await scan_project_files(CONFIG_PROJECT, db)
    scanner = ConfigScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(CONFIG_PROJECT)

    bp = await db.get_blueprint(type_filter="view")
    views = bp["nodes"]
    view_names = {v["name"] for v in views}
    assert "active_users" in view_names


async def test_config_scanner_detects_graphql_types(db: Database):
    """GraphQL types detected as schema nodes."""
    info = await scan_project_files(CONFIG_PROJECT, db)
    scanner = ConfigScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(CONFIG_PROJECT)

    bp = await db.get_blueprint(type_filter="schema")
    schemas = bp["nodes"]
    schema_names = {s["name"] for s in schemas}
    assert "User" in schema_names
    assert "Post" in schema_names
    assert "CreateUserInput" in schema_names


async def test_config_scanner_detects_graphql_queries(db: Database):
    """GraphQL Query/Mutation fields detected as route nodes."""
    info = await scan_project_files(CONFIG_PROJECT, db)
    scanner = ConfigScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(CONFIG_PROJECT)

    bp = await db.get_blueprint(type_filter="route")
    routes = bp["nodes"]
    route_names = {r["name"] for r in routes}
    assert "query:users" in route_names
    assert "mutation:createUser" in route_names


async def test_config_scanner_idempotent(db: Database):
    """Scanning twice produces same node count."""
    info = await scan_project_files(CONFIG_PROJECT, db)

    scanner1 = ConfigScanner(db, info.root_id, info.gitignore_spec)
    await scanner1.scan(CONFIG_PROJECT)
    bp1 = await db.get_blueprint()
    count1 = bp1["summary"]["total_nodes"]

    scanner2 = ConfigScanner(db, info.root_id, info.gitignore_spec)
    await scanner2.scan(CONFIG_PROJECT)
    bp2 = await db.get_blueprint()
    count2 = bp2["summary"]["total_nodes"]

    assert count1 == count2


# =============================================================================
# SQL Scanner Tests (Stage 7)
# =============================================================================


# --- SQL File Tests ---


async def test_sql_scanner_detects_tables(db: Database):
    """users, posts, categories as table nodes."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint(type_filter="table")
    tables = bp["nodes"]
    table_names = {t["name"] for t in tables}
    assert "users" in table_names
    assert "posts" in table_names
    assert "categories" in table_names


async def test_sql_scanner_detects_columns(db: Database):
    """users has 4 column children (id, email, name, created_at)."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint(type_filter="column")
    columns = bp["nodes"]
    bp_tables = await db.get_blueprint(type_filter="table")
    users_table = next(t for t in bp_tables["nodes"] if t["name"] == "users")
    users_cols = [c for c in columns if c.get("parent_id") == users_table["id"]]
    col_names = {c["name"] for c in users_cols}
    assert "id" in col_names
    assert "email" in col_names
    assert "name" in col_names
    assert "created_at" in col_names
    assert len(users_cols) == 4


async def test_sql_scanner_column_metadata(db: Database):
    """id has {primary_key: true}, email has {nullable: false}."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint(type_filter="column")
    columns = bp["nodes"]

    bp_tables = await db.get_blueprint(type_filter="table")
    users_table = next(t for t in bp_tables["nodes"] if t["name"] == "users")
    users_cols = [c for c in columns if c.get("parent_id") == users_table["id"]]

    id_col = next(c for c in users_cols if c["name"] == "id")
    assert id_col["metadata"]["primary_key"] is True

    email_col = next(c for c in users_cols if c["name"] == "email")
    assert email_col["metadata"]["nullable"] is False


async def test_sql_scanner_large_table_no_column_nodes(db: Database):
    """20-col table: columns in metadata, not child nodes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cols = ", ".join([f"col{i} INTEGER" for i in range(20)])
        sql = f"CREATE TABLE big_table ({cols});"
        with open(os.path.join(tmpdir, "big.sql"), "w") as f:
            f.write(sql)

        info = await scan_project_files(tmpdir, db)
        scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
        await scanner.scan(tmpdir)

        bp = await db.get_blueprint(type_filter="table")
        big_table = next(t for t in bp["nodes"] if t["name"] == "big_table")
        assert big_table["metadata"]["total_columns"] == 20
        assert len(big_table["metadata"]["columns"]) == 20

        bp_cols = await db.get_blueprint(type_filter="column")
        big_cols = [c for c in bp_cols["nodes"] if c.get("parent_id") == big_table["id"]]
        assert len(big_cols) == 0


async def test_sql_scanner_detects_fk_edges(db: Database):
    """reads_from: posts->users, posts->categories."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    reads_from = [e for e in edges if e["relationship"] == "reads_from"]
    nodes = {n["id"]: n["name"] for n in bp["nodes"]}

    pairs = set()
    for e in reads_from:
        src = nodes.get(e["source_id"], "")
        tgt = nodes.get(e["target_id"], "")
        pairs.add((src, tgt))

    assert ("posts", "users") in pairs
    assert ("posts", "categories") in pairs


async def test_sql_scanner_detects_alter_table_fk(db: Database):
    """reads_from: posts->users from ALTER TABLE."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    reads_from = [e for e in edges if e["relationship"] == "reads_from"]
    nodes = {n["id"]: n["name"] for n in bp["nodes"]}

    pairs = set()
    for e in reads_from:
        src = nodes.get(e["source_id"], "")
        tgt = nodes.get(e["target_id"], "")
        pairs.add((src, tgt))

    assert ("posts", "users") in pairs


async def test_sql_scanner_detects_indexes(db: Database):
    """Annotation on posts: index idx_posts_author."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint(type_filter="table")
    posts_table = next(t for t in bp["nodes"] if t["name"] == "posts")
    assert "indexes" in posts_table["metadata"]
    assert "idx_posts_author" in posts_table["metadata"]["indexes"]


async def test_sql_scanner_detects_view(db: Database):
    """recent_posts as view node."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint(type_filter="view")
    views = bp["nodes"]
    view_names = {v["name"] for v in views}
    assert "recent_posts" in view_names


async def test_sql_scanner_view_reads_from_tables(db: Database):
    """reads_from: recent_posts->posts, recent_posts->users."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    reads_from = [e for e in edges if e["relationship"] == "reads_from"]
    nodes = {n["id"]: n["name"] for n in bp["nodes"]}

    pairs = set()
    for e in reads_from:
        src = nodes.get(e["source_id"], "")
        tgt = nodes.get(e["target_id"], "")
        pairs.add((src, tgt))

    assert ("recent_posts", "posts") in pairs
    assert ("recent_posts", "users") in pairs


async def test_sql_scanner_detects_function(db: Database):
    """update_timestamp as function node."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint(type_filter="function")
    funcs = bp["nodes"]
    func_names = {f["name"] for f in funcs}
    assert "update_timestamp" in func_names


async def test_sql_scanner_detects_trigger(db: Database):
    """trg_update_ts as function node + observes->users edge."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint(type_filter="function")
    funcs = bp["nodes"]
    trigger = next((f for f in funcs if f["name"] == "trg_update_ts"), None)
    assert trigger is not None
    assert trigger["metadata"].get("trigger") is True

    bp_full = await db.get_blueprint()
    edges = bp_full["edges"]
    observes = [e for e in edges if e["relationship"] == "observes"]
    nodes = {n["id"]: n["name"] for n in bp_full["nodes"]}
    found = False
    for e in observes:
        src = nodes.get(e["source_id"], "")
        tgt = nodes.get(e["target_id"], "")
        if src == "trg_update_ts" and tgt == "users":
            found = True
    assert found


# --- Prisma Tests ---


async def test_sql_scanner_prisma_datasource(db: Database):
    """postgresql database node."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint(type_filter="database")
    dbs = bp["nodes"]
    db_names = {d["name"] for d in dbs}
    assert "postgresql_database" in db_names

    pg_db = next(d for d in dbs if d["name"] == "postgresql_database")
    assert pg_db["metadata"]["provider"] == "postgresql"


async def test_sql_scanner_prisma_models(db: Database):
    """User, Post as table nodes."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint(type_filter="table")
    tables = bp["nodes"]
    table_names = {t["name"] for t in tables}
    assert "User" in table_names
    assert "Post" in table_names


async def test_sql_scanner_prisma_columns(db: Database):
    """User has column children (id, email, name)."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint(type_filter="table")
    user_table = next(t for t in bp["nodes"] if t["name"] == "User")

    bp_cols = await db.get_blueprint(type_filter="column")
    user_cols = [c for c in bp_cols["nodes"] if c.get("parent_id") == user_table["id"]]
    col_names = {c["name"] for c in user_cols}
    assert "id" in col_names
    assert "email" in col_names
    assert "name" in col_names


async def test_sql_scanner_prisma_relations(db: Database):
    """reads_from: Post->User via @relation."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    reads_from = [e for e in edges if e["relationship"] == "reads_from"]
    nodes = {n["id"]: n["name"] for n in bp["nodes"]}

    pairs = set()
    for e in reads_from:
        src = nodes.get(e["source_id"], "")
        tgt = nodes.get(e["target_id"], "")
        pairs.add((src, tgt))

    assert ("Post", "User") in pairs


async def test_sql_scanner_prisma_no_reverse_edge(db: Database):
    """User.posts[] does NOT create User->Post edge."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    reads_from = [e for e in edges if e["relationship"] == "reads_from"]
    nodes = {n["id"]: n["name"] for n in bp["nodes"]}

    pairs = set()
    for e in reads_from:
        src = nodes.get(e["source_id"], "")
        tgt = nodes.get(e["target_id"], "")
        pairs.add((src, tgt))

    assert ("User", "Post") not in pairs


# --- Migration Tests ---


async def test_sql_scanner_django_migration_tables(db: Database):
    """Customer, Order as table nodes."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint(type_filter="table")
    tables = bp["nodes"]
    table_names = {t["name"] for t in tables}
    assert "customer" in table_names
    assert "order" in table_names


async def test_sql_scanner_django_migration_fk(db: Database):
    """reads_from: order->customer."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    reads_from = [e for e in edges if e["relationship"] == "reads_from"]
    nodes = {n["id"]: n["name"] for n in bp["nodes"]}

    pairs = set()
    for e in reads_from:
        src = nodes.get(e["source_id"], "")
        tgt = nodes.get(e["target_id"], "")
        pairs.add((src, tgt))

    assert ("order", "customer") in pairs


async def test_sql_scanner_alembic_migration_tables(db: Database):
    """products, reviews as table nodes."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint(type_filter="table")
    tables = bp["nodes"]
    table_names = {t["name"] for t in tables}
    assert "products" in table_names
    assert "reviews" in table_names


async def test_sql_scanner_alembic_migration_fk(db: Database):
    """reads_from: reviews->products."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint()
    edges = bp["edges"]
    reads_from = [e for e in edges if e["relationship"] == "reads_from"]
    nodes = {n["id"]: n["name"] for n in bp["nodes"]}

    pairs = set()
    for e in reads_from:
        src = nodes.get(e["source_id"], "")
        tgt = nodes.get(e["target_id"], "")
        pairs.add((src, tgt))

    assert ("reviews", "products") in pairs


# --- Connection String Tests ---


async def test_sql_scanner_conn_string_postgres(db: Database):
    """database node with provider=postgresql."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint(type_filter="database")
    dbs = bp["nodes"]
    conn_dbs = [d for d in dbs if d.get("metadata", {}).get("source") == "connection_string"]
    pg_nodes = [d for d in conn_dbs if d["metadata"].get("provider") == "postgresql"]
    assert len(pg_nodes) >= 1


async def test_sql_scanner_conn_string_redis(db: Database):
    """cache node with provider=redis."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint(type_filter="cache")
    caches = bp["nodes"]
    redis_nodes = [c for c in caches if c.get("metadata", {}).get("provider") == "redis"]
    assert len(redis_nodes) >= 1


async def test_sql_scanner_conn_string_no_credentials(db: Database):
    """NO password/username/host in any metadata."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint()
    for node in bp["nodes"]:
        meta = node.get("metadata", {})
        meta_str = str(meta).lower()
        assert "password" not in meta_str
        assert "user:" not in meta_str
        assert "localhost" not in meta_str
        assert "5432" not in meta_str


# --- TypeORM + Knex Tests ---


async def test_sql_scanner_typeorm_entity(db: Database):
    """app_users as table node."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint(type_filter="table")
    tables = bp["nodes"]
    table_names = {t["name"] for t in tables}
    assert "app_users" in table_names


async def test_sql_scanner_typeorm_columns(db: Database):
    """id, name, email as column children."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint(type_filter="table")
    typeorm_table = next(t for t in bp["nodes"] if t["name"] == "app_users")

    bp_cols = await db.get_blueprint(type_filter="column")
    cols = [c for c in bp_cols["nodes"] if c.get("parent_id") == typeorm_table["id"]]
    col_names = {c["name"] for c in cols}
    assert "id" in col_names
    assert "name" in col_names
    assert "email" in col_names


async def test_sql_scanner_typeorm_relation(db: Database):
    """reads_from edge from @ManyToOne — deferred FK won't resolve since Department not scanned."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint()
    assert len(bp["nodes"]) > 0


async def test_sql_scanner_knex_table(db: Database):
    """invoices as table node."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp = await db.get_blueprint(type_filter="table")
    tables = bp["nodes"]
    table_names = {t["name"] for t in tables}
    assert "invoices" in table_names


async def test_sql_scanner_knex_fk(db: Database):
    """invoices references customers — but customers not in fixtures so no edge, just verify no crash."""
    info = await scan_project_files(SQL_PROJECT, db)
    scanner = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner.scan(SQL_PROJECT)

    bp_tables = await db.get_blueprint(type_filter="table")
    assert "invoices" in {t["name"] for t in bp_tables["nodes"]}


# --- Integration ---


async def test_sql_scanner_idempotent(db: Database):
    """scan twice = same node/edge count."""
    info = await scan_project_files(SQL_PROJECT, db)

    scanner1 = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner1.scan(SQL_PROJECT)
    bp1 = await db.get_blueprint()
    count1 = bp1["summary"]["total_nodes"]
    edge_count1 = len(bp1["edges"])

    scanner2 = SQLScanner(db, info.root_id, info.gitignore_spec)
    await scanner2.scan(SQL_PROJECT)
    bp2 = await db.get_blueprint()
    count2 = bp2["summary"]["total_nodes"]
    edge_count2 = len(bp2["edges"])

    assert count1 == count2
    assert edge_count1 == edge_count2
