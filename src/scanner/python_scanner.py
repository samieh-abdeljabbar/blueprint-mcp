"""Python scanner — AST-based analysis of Python files."""

from __future__ import annotations

import ast
import os
import time

from src.models import (
    EdgeCreateInput,
    EdgeRelationship,
    NodeCreateInput,
    NodeStatus,
    NodeType,
    ScanResult,
)
from src.scanner.base import BaseScanner

# Frameworks detected by assignment patterns
FRAMEWORK_PATTERNS = {
    "FastAPI": "fastapi",
    "Flask": "flask",
}


class PythonScanner(BaseScanner):
    async def scan(self, path: str) -> ScanResult:
        start = time.time()
        # Map of module relative paths to their node IDs (for import tracking)
        self._module_ids: dict[str, str] = {}

        for dirpath, dirnames, filenames in os.walk(path):
            # Filter ignored dirs in-place
            dirnames[:] = [
                d for d in dirnames if not self.should_ignore(os.path.join(dirpath, d), path)
            ]
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                full = os.path.join(dirpath, fname)
                if self.should_ignore(full, path):
                    continue
                await self._scan_file(full, path)
                self._files_scanned += 1

        return self._build_result("python_scanner", start)

    async def _scan_file(self, filepath: str, project_root: str):
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                source = f.read()
            tree = ast.parse(source, filename=filepath)
        except SyntaxError as e:
            self._add_error(rel_path, f"Syntax error: {e.msg}", e.lineno)
            return

        # Track this module
        module_name = os.path.splitext(rel_path)[0].replace(os.sep, ".")

        # Detect framework apps, routes, SQLAlchemy models, imports
        await self._detect_apps(tree, rel_path, project_root)
        await self._detect_routes(tree, rel_path, project_root)
        await self._detect_sqlalchemy_models(tree, rel_path, project_root)
        await self._detect_imports(tree, rel_path, module_name, project_root)

    async def _detect_apps(self, tree: ast.AST, rel_path: str, project_root: str):
        """Detect FastAPI() or Flask(__name__) app creation."""
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not isinstance(node.value, ast.Call):
                continue
            call = node.value
            func_name = ""
            if isinstance(call.func, ast.Name):
                func_name = call.func.id
            elif isinstance(call.func, ast.Attribute):
                func_name = call.func.attr

            if func_name in FRAMEWORK_PATTERNS:
                framework = FRAMEWORK_PATTERNS[func_name]
                service_name = f"{func_name} app"
                node_id, _ = await self._track_node(NodeCreateInput(
                    name=service_name,
                    type=NodeType.service,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    metadata={"framework": framework},
                    source_file=rel_path,
                    source_line=node.lineno,
                ))
                # Store for route parenting
                self._app_node_id = node_id
                self._app_var_names = [
                    t.id for t in node.targets if isinstance(t, ast.Name)
                ]

    async def _detect_routes(self, tree: ast.AST, rel_path: str, project_root: str):
        """Detect @app.get('/path') style route decorators."""
        app_id = getattr(self, "_app_node_id", self.root_id)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                route_info = self._parse_route_decorator(dec)
                if route_info:
                    method, path = route_info
                    route_name = f"{method} {path}"
                    await self._track_node(NodeCreateInput(
                        name=route_name,
                        type=NodeType.route,
                        status=NodeStatus.built,
                        parent_id=app_id,
                        metadata={
                            "method": method,
                            "path": path,
                            "function_name": node.name,
                        },
                        source_file=rel_path,
                        source_line=node.lineno,
                    ))

    def _parse_route_decorator(self, dec: ast.expr) -> tuple[str, str] | None:
        """Extract (METHOD, path) from a decorator like @app.get('/path')."""
        if not isinstance(dec, ast.Call):
            return None
        func = dec.func
        if not isinstance(func, ast.Attribute):
            return None

        method_name = func.attr.upper()
        http_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
        if method_name not in http_methods:
            return None

        # Check the object is an app/router variable
        app_vars = getattr(self, "_app_var_names", [])
        if isinstance(func.value, ast.Name):
            # Accept any variable as potential app/router
            pass

        # Extract path from first positional arg
        if dec.args:
            arg = dec.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return method_name, arg.value
        return None

    async def _detect_sqlalchemy_models(
        self, tree: ast.AST, rel_path: str, project_root: str
    ):
        """Detect SQLAlchemy model classes with __tablename__."""
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            tablename = None
            columns = []

            for item in node.body:
                # __tablename__ = "users"
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id == "__tablename__":
                            if isinstance(item.value, ast.Constant):
                                tablename = item.value.value

                    # Column() assignments
                    if isinstance(item.value, ast.Call):
                        func = item.value.func
                        func_name = ""
                        if isinstance(func, ast.Name):
                            func_name = func.id
                        elif isinstance(func, ast.Attribute):
                            func_name = func.attr
                        if func_name == "Column":
                            for target in item.targets:
                                if isinstance(target, ast.Name):
                                    columns.append(target.id)

                # Mapped[] style (SA 2.0)
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    columns.append(item.target.id)

            if tablename:
                await self._track_node(NodeCreateInput(
                    name=tablename,
                    type=NodeType.table,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    metadata={
                        "orm_class": node.name,
                        "columns": columns,
                    },
                    source_file=rel_path,
                    source_line=node.lineno,
                ))

    async def _detect_imports(
        self, tree: ast.AST, rel_path: str, module_name: str, project_root: str
    ):
        """Track import dependencies between project modules."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                # Only track relative/local imports
                imported = node.module
                # Check if it could be a local module
                parts = imported.split(".")
                possible_path = os.path.join(project_root, *parts) + ".py"
                possible_pkg = os.path.join(project_root, *parts, "__init__.py")
                if os.path.exists(possible_path) or os.path.exists(possible_pkg):
                    # Create module nodes and edge
                    src_id, _ = await self._track_node(NodeCreateInput(
                        name=os.path.basename(rel_path),
                        type=NodeType.module,
                        status=NodeStatus.built,
                        parent_id=self.root_id,
                        source_file=rel_path,
                    ))
                    target_file = parts[-1] + ".py"
                    tgt_id, _ = await self._track_node(NodeCreateInput(
                        name=target_file,
                        type=NodeType.module,
                        status=NodeStatus.built,
                        parent_id=self.root_id,
                        source_file=os.path.join(*parts) + ".py",
                    ))
                    await self._track_edge(EdgeCreateInput(
                        source_id=src_id,
                        target_id=tgt_id,
                        relationship=EdgeRelationship.depends_on,
                    ))
