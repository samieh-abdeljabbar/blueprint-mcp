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

# Django model base classes
DJANGO_MODEL_BASES = {"Model", "models.Model"}

# Django view base classes
DJANGO_VIEW_BASES = {
    "View", "TemplateView", "ListView", "DetailView", "CreateView",
    "UpdateView", "DeleteView", "FormView", "RedirectView",
    "APIView", "GenericAPIView", "ModelViewSet", "ViewSet",
}

# Pydantic base classes
PYDANTIC_BASES = {"BaseModel", "BaseSettings"}

# Protocol/ABC base classes
PROTOCOL_BASES = {"Protocol", "ABC", "ABCMeta"}

# Enum base classes
ENUM_BASES = {"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"}

# Celery task decorators
CELERY_TASK_DECORATORS = {"shared_task", "task"}

# Config file names
CONFIG_FILENAMES = {"settings.py", "config.py", "conf.py"}


class PythonScanner(BaseScanner):
    async def scan(self, path: str) -> ScanResult:
        start = time.time()
        # Map of module relative paths to their node IDs (for import tracking)
        self._module_ids: dict[str, str] = {}
        # Track class node IDs by name for inheritance edges
        self._class_node_ids: dict[str, str] = {}
        # Track view node IDs by name for URL pattern delegation
        self._view_node_ids: dict[str, str] = {}
        # Deferred inheritance edges
        self._deferred_inherit_edges: list[tuple[str, str]] = []
        # Deferred URL delegate edges: (route_id, view_name)
        self._deferred_url_delegates: list[tuple[str, str]] = []

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

        # Create deferred edges
        await self._create_deferred_edges()

        # Create directory hierarchy
        await self._create_directory_parents(path)

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
        basename = os.path.basename(filepath)

        # File-level detections
        await self._detect_file_level(basename, rel_path)

        # Detect framework apps, routes, SQLAlchemy models, imports
        await self._detect_apps(tree, rel_path, project_root)
        await self._detect_routes(tree, rel_path, project_root)
        await self._detect_sqlalchemy_models(tree, rel_path, project_root)
        await self._detect_imports(tree, rel_path, module_name, project_root)

        # New detections
        await self._detect_classes_and_types(tree, rel_path, basename)
        await self._detect_standalone_functions(tree, rel_path, basename)

        # Django-specific
        if self._is_django_file(basename, tree):
            await self._detect_django_models(tree, rel_path)
            await self._detect_django_views(tree, rel_path, basename)
            await self._detect_django_urls(tree, rel_path)

    async def _detect_file_level(self, basename: str, rel_path: str):
        """Detect test files, config files from filename conventions."""
        name_no_ext = os.path.splitext(basename)[0]

        # Test files
        if basename.startswith("test_") or basename.endswith("_test.py"):
            await self._track_node(NodeCreateInput(
                name=name_no_ext,
                type=NodeType.test,
                status=NodeStatus.built,
                parent_id=self.root_id,
                source_file=rel_path,
            ))

        # Config files
        if basename in CONFIG_FILENAMES:
            await self._track_node(NodeCreateInput(
                name=name_no_ext,
                type=NodeType.config,
                status=NodeStatus.built,
                parent_id=self.root_id,
                source_file=rel_path,
            ))

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
                    metadata: dict = {
                        "method": method,
                        "path": path,
                        "function_name": node.name,
                    }
                    # Check for websocket
                    if self._is_websocket_decorator(dec):
                        metadata["protocol"] = "websocket"
                    await self._track_node(NodeCreateInput(
                        name=route_name,
                        type=NodeType.route,
                        status=NodeStatus.built,
                        parent_id=app_id,
                        metadata=metadata,
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
        http_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "WEBSOCKET"}
        if method_name not in http_methods:
            return None

        if isinstance(func.value, ast.Name):
            # Accept any variable as potential app/router
            pass

        # Extract path from first positional arg
        if dec.args:
            arg = dec.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return method_name, arg.value
        return None

    def _is_websocket_decorator(self, dec: ast.expr) -> bool:
        """Check if decorator is a websocket handler."""
        if not isinstance(dec, ast.Call):
            return False
        func = dec.func
        if isinstance(func, ast.Attribute):
            return func.attr.lower() == "websocket"
        return False

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

    async def _detect_classes_and_types(
        self, tree: ast.AST, rel_path: str, basename: str
    ):
        """Detect classes, Pydantic models, dataclasses, enums, protocols, ABCs."""
        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            # Skip if already detected as SQLAlchemy model
            if self._has_tablename(node):
                continue

            base_names = self._get_base_names(node)
            decorators = self._get_decorator_names(node)

            # Pydantic models
            if base_names & PYDANTIC_BASES:
                node_id, _ = await self._track_node(NodeCreateInput(
                    name=node.name,
                    type=NodeType.model,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    metadata={"pydantic": True},
                    source_file=rel_path,
                    source_line=node.lineno,
                ))
                self._class_node_ids[node.name] = node_id
                # Inheritance edges for custom Pydantic bases
                for base in base_names - PYDANTIC_BASES:
                    self._deferred_inherit_edges.append((node.name, base))
                continue

            # Dataclasses
            if "dataclass" in decorators:
                await self._track_node(NodeCreateInput(
                    name=node.name,
                    type=NodeType.model,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    metadata={"dataclass": True},
                    source_file=rel_path,
                    source_line=node.lineno,
                ))
                continue

            # Enums
            if base_names & ENUM_BASES:
                await self._track_node(NodeCreateInput(
                    name=node.name,
                    type=NodeType.enum_def,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    source_file=rel_path,
                    source_line=node.lineno,
                ))
                continue

            # Protocols and ABCs
            if base_names & PROTOCOL_BASES or "abstractmethod" in decorators or self._has_abstractmethod(node):
                node_id, _ = await self._track_node(NodeCreateInput(
                    name=node.name,
                    type=NodeType.protocol,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    source_file=rel_path,
                    source_line=node.lineno,
                ))
                self._class_node_ids[node.name] = node_id
                continue

            # Django model bases are handled separately
            if base_names & DJANGO_MODEL_BASES:
                continue
            if base_names & DJANGO_VIEW_BASES:
                continue

            # Generic class definition
            if node.bases:  # has base classes
                node_id, _ = await self._track_node(NodeCreateInput(
                    name=node.name,
                    type=NodeType.class_def,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    source_file=rel_path,
                    source_line=node.lineno,
                ))
                self._class_node_ids[node.name] = node_id
                for base in base_names:
                    self._deferred_inherit_edges.append((node.name, base))

    async def _detect_standalone_functions(
        self, tree: ast.AST, rel_path: str, basename: str
    ):
        """Detect module-level functions (not methods, not route handlers)."""
        route_funcs = self._get_route_function_names(tree)

        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            # Skip private functions in non-deep mode
            if not self.deep and node.name.startswith("_"):
                continue

            # Skip route handlers (already detected)
            if node.name in route_funcs:
                continue

            # Check for Celery task decorators
            dec_names = self._get_decorator_names_from_node(node)
            if dec_names & CELERY_TASK_DECORATORS:
                await self._track_node(NodeCreateInput(
                    name=node.name,
                    type=NodeType.worker,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    metadata={"celery_task": True},
                    source_file=rel_path,
                    source_line=node.lineno,
                ))
                continue

            # Regular standalone function
            func_name = f"{rel_path}:{node.name}"
            await self._track_node(NodeCreateInput(
                name=func_name,
                type=NodeType.function,
                status=NodeStatus.built,
                parent_id=self.root_id,
                source_file=rel_path,
                source_line=node.lineno,
            ))

    def _is_django_file(self, basename: str, tree: ast.AST) -> bool:
        """Check if this file is part of a Django project."""
        # Check for django imports
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("django"):
                    return True
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("django"):
                        return True
        return False

    async def _detect_django_models(self, tree: ast.AST, rel_path: str):
        """Detect Django model classes."""
        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            base_names = self._get_base_names(node)
            if not (base_names & DJANGO_MODEL_BASES):
                continue

            # Skip if already detected as SQLAlchemy
            if self._has_tablename(node):
                continue

            # Get db_table from Meta class if present
            table_name = node.name.lower()
            for item in node.body:
                if isinstance(item, ast.ClassDef) and item.name == "Meta":
                    for meta_item in item.body:
                        if isinstance(meta_item, ast.Assign):
                            for target in meta_item.targets:
                                if isinstance(target, ast.Name) and target.id == "db_table":
                                    if isinstance(meta_item.value, ast.Constant):
                                        table_name = meta_item.value.value

            node_id, _ = await self._track_node(NodeCreateInput(
                name=table_name,
                type=NodeType.table,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"orm_class": node.name, "framework": "django"},
                source_file=rel_path,
                source_line=node.lineno,
            ))
            self._class_node_ids[node.name] = node_id

    async def _detect_django_views(
        self, tree: ast.AST, rel_path: str, basename: str
    ):
        """Detect Django view functions and classes."""
        if "views" not in basename and "viewsets" not in basename:
            return

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef):
                # Function-based view: has 'request' as first arg
                if node.args.args and node.args.args[0].arg == "request":
                    view_id, _ = await self._track_node(NodeCreateInput(
                        name=node.name,
                        type=NodeType.view,
                        status=NodeStatus.built,
                        parent_id=self.root_id,
                        metadata={"framework": "django", "view_type": "function"},
                        source_file=rel_path,
                        source_line=node.lineno,
                    ))
                    self._view_node_ids[node.name] = view_id

            elif isinstance(node, ast.ClassDef):
                base_names = self._get_base_names(node)
                if base_names & DJANGO_VIEW_BASES:
                    view_id, _ = await self._track_node(NodeCreateInput(
                        name=node.name,
                        type=NodeType.view,
                        status=NodeStatus.built,
                        parent_id=self.root_id,
                        metadata={"framework": "django", "view_type": "class"},
                        source_file=rel_path,
                        source_line=node.lineno,
                    ))
                    self._view_node_ids[node.name] = view_id

    async def _detect_django_urls(self, tree: ast.AST, rel_path: str):
        """Detect Django URL patterns: path('url/', view)."""
        if not os.path.basename(rel_path).startswith("urls"):
            return

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            func_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr

            if func_name not in ("path", "re_path", "url"):
                continue

            if len(node.args) < 2:
                continue

            # First arg: URL pattern
            url_arg = node.args[0]
            if not isinstance(url_arg, ast.Constant) or not isinstance(url_arg.value, str):
                continue
            url_path = url_arg.value

            # Second arg: view reference
            view_name = self._extract_view_name(node.args[1])

            route_name = f"/{url_path}" if not url_path.startswith("/") else url_path
            route_id, _ = await self._track_node(NodeCreateInput(
                name=route_name,
                type=NodeType.route,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"framework": "django", "view": view_name},
                source_file=rel_path,
                source_line=node.lineno,
            ))

            # Defer delegates edge creation (views may not be scanned yet)
            if view_name:
                clean_name = view_name.split(".")[-1] if "." in view_name else view_name
                clean_name = clean_name.replace(".as_view()", "").replace(".as_view", "")
                self._deferred_url_delegates.append((route_id, clean_name))

    def _extract_view_name(self, node: ast.expr) -> str:
        """Extract view function/class name from URL pattern argument."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parts = []
            current = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        if isinstance(node, ast.Call):
            # views.BookListView.as_view()
            return self._extract_view_name(node.func)
        return ""

    # --- Helper methods ---

    def _get_base_names(self, node: ast.ClassDef) -> set[str]:
        """Extract base class names from a ClassDef node."""
        names = set()
        for base in node.bases:
            if isinstance(base, ast.Name):
                names.add(base.id)
            elif isinstance(base, ast.Attribute):
                # e.g., models.Model -> "models.Model"
                parts = []
                current = base
                while isinstance(current, ast.Attribute):
                    parts.append(current.attr)
                    current = current.value
                if isinstance(current, ast.Name):
                    parts.append(current.id)
                names.add(".".join(reversed(parts)))
                # Also add just the attribute for matching
                names.add(base.attr)
        return names

    def _get_decorator_names(self, node: ast.ClassDef) -> set[str]:
        """Extract decorator names from a ClassDef."""
        names = set()
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                names.add(dec.id)
            elif isinstance(dec, ast.Attribute):
                names.add(dec.attr)
            elif isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Name):
                    names.add(dec.func.id)
                elif isinstance(dec.func, ast.Attribute):
                    names.add(dec.func.attr)
        return names

    def _get_decorator_names_from_node(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> set[str]:
        """Extract decorator names from a function definition."""
        names = set()
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                names.add(dec.id)
            elif isinstance(dec, ast.Attribute):
                names.add(dec.attr)
            elif isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Name):
                    names.add(dec.func.id)
                elif isinstance(dec.func, ast.Attribute):
                    names.add(dec.func.attr)
        return names

    def _has_abstractmethod(self, node: ast.ClassDef) -> bool:
        """Check if class has any @abstractmethod decorated methods."""
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in item.decorator_list:
                    if isinstance(dec, ast.Name) and dec.id == "abstractmethod":
                        return True
                    if isinstance(dec, ast.Attribute) and dec.attr == "abstractmethod":
                        return True
        return False

    def _has_tablename(self, node: ast.ClassDef) -> bool:
        """Check if class has __tablename__ (SQLAlchemy)."""
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "__tablename__":
                        return True
        return False

    def _get_route_function_names(self, tree: ast.AST) -> set[str]:
        """Get names of functions that have route decorators."""
        names = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if self._parse_route_decorator(dec):
                    names.add(node.name)
        return names

    async def _create_deferred_edges(self):
        """Create deferred edges after all files scanned."""
        # Inheritance edges
        for child_name, parent_name in self._deferred_inherit_edges:
            child_id = self._class_node_ids.get(child_name)
            parent_id = self._class_node_ids.get(parent_name)
            if child_id and parent_id:
                await self._track_edge(EdgeCreateInput(
                    source_id=child_id,
                    target_id=parent_id,
                    relationship=EdgeRelationship.inherits,
                ))

        # Django URL -> view delegates edges
        for route_id, view_name in self._deferred_url_delegates:
            view_id = self._view_node_ids.get(view_name)
            if view_id:
                await self._track_edge(EdgeCreateInput(
                    source_id=route_id,
                    target_id=view_id,
                    relationship=EdgeRelationship.delegates,
                ))
