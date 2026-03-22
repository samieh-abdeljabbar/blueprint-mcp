"""Scanner orchestrator — coordinates all scanners for a project."""

from __future__ import annotations

import os

from src.db import Database
from src.models import ScanResult
from src.scanner.file_scanner import scan_project_files
from src.scanner.python_scanner import PythonScanner
from src.scanner.javascript_scanner import JavaScriptScanner
from src.scanner.docker_scanner import DockerScanner
from src.scanner.swift_scanner import SwiftScanner
from src.scanner.rust_scanner import RustScanner
from src.scanner.go_scanner import GoScanner
from src.scanner.config_scanner import ConfigScanner
from src.scanner.sql_scanner import SQLScanner

# Map language names to scanner classes
SCANNER_MAP = {
    "python": PythonScanner,
    "rust": RustScanner,       # Before JS so Tauri commands exist for invoke() linking
    "swift": SwiftScanner,
    "go": GoScanner,
    "javascript": JavaScriptScanner,
    "docker": DockerScanner,
    "config": ConfigScanner,
    "sql": SQLScanner,
}


async def scan_project(
    path: str,
    db: Database,
    languages: list[str] | None = None,
    deep: bool = False,
) -> dict:
    """Scan a project directory and auto-populate the blueprint.

    1. Run FileScanner to detect project type and create root node
    2. Auto-select scanners from detected languages (or use explicit list)
    3. Run each scanner sequentially
    4. Log scan_completed to changelog
    5. Return aggregated results
    """
    path = os.path.abspath(path)

    # Step 1: File scanner for project detection
    project_info = await scan_project_files(path, db)

    # Step 2: Determine which scanners to run
    if languages:
        scanner_names = [l for l in languages if l in SCANNER_MAP]
    else:
        # Use SCANNER_MAP key order (e.g., rust before js for Tauri IPC linking)
        detected = set(project_info.languages)
        scanner_names = [l for l in SCANNER_MAP if l in detected]

    # Step 3: Run each scanner
    results: list[ScanResult] = []
    for lang in scanner_names:
        scanner_cls = SCANNER_MAP[lang]
        scanner = scanner_cls(
            db=db,
            root_id=project_info.root_id,
            gitignore_spec=project_info.gitignore_spec,
            deep=deep,
        )
        result = await scanner.scan(path)
        results.append(result)

    # Step 4: Log to changelog
    total_nodes = sum(r.nodes_created for r in results)
    total_edges = sum(r.edges_created for r in results)
    await db.log_change(
        "scan_completed",
        "project",
        project_info.root_id,
        {
            "project": project_info.name,
            "languages": scanner_names,
            "nodes_created": total_nodes,
            "edges_created": total_edges,
        },
    )

    # Step 5: Aggregate results
    all_errors = []
    for r in results:
        all_errors.extend([e.model_dump() for e in r.errors])

    return {
        "project_name": project_info.name,
        "root_id": project_info.root_id,
        "languages_detected": project_info.languages,
        "scanners_run": [r.scanner_name for r in results],
        "total_nodes_created": total_nodes,
        "total_nodes_updated": sum(r.nodes_updated for r in results),
        "total_edges_created": total_edges,
        "total_files_scanned": sum(r.files_scanned for r in results),
        "errors": all_errors,
        "scanner_results": [r.model_dump() for r in results],
    }


async def scan_single_file(path: str, db: Database) -> dict:
    """Scan a single file and update the blueprint."""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return {"error": f"File not found: {path}"}

    ext = os.path.splitext(path)[1].lower()
    basename = os.path.basename(path)
    project_root = os.path.dirname(path)

    # Create a temporary root node for the file's project
    project_name = os.path.basename(project_root)
    from src.models import NodeCreateInput, NodeType, NodeStatus
    root_node, _ = await db.find_or_create_node(NodeCreateInput(
        name=project_name,
        type=NodeType.system,
        status=NodeStatus.built,
    ))

    # Dispatch to correct scanner
    scanner_cls = None
    if ext == ".py":
        scanner_cls = PythonScanner
    elif ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
        scanner_cls = JavaScriptScanner
    elif ext == ".swift":
        scanner_cls = SwiftScanner
    elif ext == ".rs":
        scanner_cls = RustScanner
    elif ext == ".go":
        scanner_cls = GoScanner
    elif ext == ".sql" or ext == ".prisma":
        scanner_cls = SQLScanner
    elif ext in (".tf", ".graphql", ".gql"):
        scanner_cls = ConfigScanner
    elif basename in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        scanner_cls = DockerScanner

    if scanner_cls is None:
        return {"error": f"No scanner for file type: {ext}", "file": path}

    scanner = scanner_cls(db=db, root_id=root_node.id)

    if scanner_cls == DockerScanner:
        result = await scanner.scan(project_root)
    else:
        # For Python/JS scanners, we scan the parent directory but only the single file
        result = await scanner.scan(project_root)

    return {
        "file": path,
        "scanner": result.scanner_name,
        "nodes_created": result.nodes_created,
        "nodes_updated": result.nodes_updated,
        "edges_created": result.edges_created,
        "errors": [e.model_dump() for e in result.errors],
    }
