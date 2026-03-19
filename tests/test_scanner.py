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

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
PYTHON_PROJECT = os.path.join(FIXTURES, "python_project")
JS_PROJECT = os.path.join(FIXTURES, "js_project")
DOCKER_PROJECT = os.path.join(FIXTURES, "docker_project")


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
