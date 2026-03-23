"""JavaScript/TypeScript scanner — regex-based analysis with import edges."""

from __future__ import annotations

import json
import os
import re
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
from src.scanner.js_frameworks import (
    detect_nextjs_layout,
    detect_nextjs_middleware,
    detect_nextjs_route,
    detect_nuxt_route,
    detect_vue_sfc,
)
from src.scanner.js_import_resolver import (
    extract_import_paths,
    module_name_from_path,
    parse_path_aliases,
    resolve_alias_import,
    resolve_import_path,
)
from src.scanner.js_patterns import (
    AXIOS_API_CALL,
    CLASS_EXTENDS,
    CLASS_STANDALONE,
    CONFIG_FILES,
    CREATE_CONTEXT,
    CUSTOM_HOOK,
    CUSTOM_HOOK_ARROW,
    DRIZZLE_TABLE,
    FETCH_API_CALL,
    FORWARD_REF,
    JS_EXTENSIONS,
    MIDDLEWARE_USE,
    NEXTJS_API_EXPORT,
    PRISMA_MODEL,
    REACT_ARROW_COMPONENT,
    REACT_EXPORT_DEFAULT,
    REACT_EXPORT_NAMED,
    REACT_MEMO,
    ROUTE_PATTERN,
    TAURI_INVOKE,
    TYPEORM_ENTITY,
    USE_DIRECTIVE,
    ZUSTAND_CREATE,
    ZUSTAND_USE_STORE,
)


class JavaScriptScanner(BaseScanner):
    async def scan(self, path: str) -> ScanResult:
        start = time.time()
        # Track module node IDs by relative path for import edge creation
        self._module_node_ids: dict[str, str] = {}
        # Track layout node IDs by directory for contains edges
        self._layout_node_ids: dict[str, str] = {}
        # Track page node IDs by directory for contains edges
        self._page_node_ids: dict[str, list[str]] = {}
        # Track class node IDs by name for inheritance edges
        self._class_node_ids: dict[str, str] = {}
        # Deferred edges to create after all files scanned
        self._deferred_import_edges: list[tuple[str, str]] = []
        self._deferred_inherit_edges: list[tuple[str, str]] = []
        # Route node IDs by API path for API call edge creation
        self._route_node_ids: dict[str, str] = {}
        # Deferred API call edges (source_rel_path, api_path)
        self._deferred_api_edges: list[tuple[str, str]] = []
        # Deferred Tauri invoke edges (source_rel_path, command_name)
        self._deferred_invoke_edges: list[tuple[str, str]] = []
        # Zustand store tracking
        self._store_node_ids: dict[str, str] = {}
        self._deferred_store_edges: list[tuple[str, str]] = []
        # Path alias resolution
        self._path_aliases = parse_path_aliases(path)

        # Read package.json first for service node
        await self._scan_package_json(path)

        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [
                d for d in dirnames if not self.should_ignore(os.path.join(dirpath, d), path)
            ]
            for fname in filenames:
                ext = os.path.splitext(fname)[1]
                full = os.path.join(dirpath, fname)

                if self.should_ignore(full, path):
                    continue

                if ext in JS_EXTENSIONS or fname.endswith(".vue"):
                    await self._scan_file(full, path)
                    self._files_scanned += 1
                elif fname.endswith(".prisma"):
                    await self._scan_prisma_file(full, path)
                    self._files_scanned += 1

        # Create directory hierarchy (before edges, after all nodes)
        await self._create_directory_parents(path)

        # Create deferred edges
        await self._create_deferred_edges()

        return self._build_result("javascript_scanner", start)

    async def _scan_package_json(self, project_root: str):
        pkg_path = os.path.join(project_root, "package.json")
        if not os.path.isfile(pkg_path):
            return
        try:
            with open(pkg_path) as f:
                pkg = json.load(f)
            name = pkg.get("name", os.path.basename(project_root))
            version = pkg.get("version", "")
            await self._track_node(NodeCreateInput(
                name=name,
                type=NodeType.service,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"version": version, "source": "package.json"},
                source_file="package.json",
            ))
        except (json.JSONDecodeError, OSError) as e:
            self._add_error("package.json", str(e))

    async def _scan_file(self, filepath: str, project_root: str):
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                source = f.read()
        except OSError as e:
            self._add_error(rel_path, str(e))
            return

        # Detect rendering directive ('use client' / 'use server')
        rendering = None
        directive_match = USE_DIRECTIVE.search(source)
        if directive_match:
            rendering = directive_match.group(1)

        # Check for framework-specific file conventions
        await self._detect_framework_conventions(rel_path, source, filepath, project_root)

        # Detect config files
        basename = os.path.basename(filepath)
        if basename in CONFIG_FILES:
            await self._track_node(NodeCreateInput(
                name=basename,
                type=NodeType.config,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"config_type": os.path.splitext(basename)[0]},
                source_file=rel_path,
            ))

        # Detect Express/Fastify routes
        for match in ROUTE_PATTERN.finditer(source):
            method = match.group(1).upper()
            route_path = match.group(2)
            route_name = f"{method} {route_path}"
            line = source[:match.start()].count("\n") + 1
            node_id, _ = await self._track_node(NodeCreateInput(
                name=route_name,
                type=NodeType.route,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"method": method, "path": route_path, "framework": "express"},
                source_file=rel_path,
                source_line=line,
            ))
            self._route_node_ids[route_path] = node_id

        # Detect React components (all patterns)
        await self._detect_components(source, rel_path, rendering=rendering)

        # Detect React-specific patterns (hooks, context, forwardRef, memo)
        await self._detect_react_patterns(source, rel_path, rendering=rendering)

        # Detect class definitions and inheritance
        await self._detect_classes(source, rel_path)

        # Detect middleware (app.use)
        await self._detect_middleware(source, rel_path)

        # Detect Drizzle tables
        for match in DRIZZLE_TABLE.finditer(source):
            table_name = match.group(1)
            line = source[:match.start()].count("\n") + 1
            await self._track_node(NodeCreateInput(
                name=table_name,
                type=NodeType.table,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"source": "drizzle"},
                source_file=rel_path,
                source_line=line,
            ))

        # Detect TypeORM entities
        for match in TYPEORM_ENTITY.finditer(source):
            entity_name = match.group(1)
            if entity_name:
                line = source[:match.start()].count("\n") + 1
                await self._track_node(NodeCreateInput(
                    name=entity_name.lower(),
                    type=NodeType.table,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    metadata={"source": "typeorm"},
                    source_file=rel_path,
                    source_line=line,
                ))

        # Detect Vue SFCs
        if filepath.endswith(".vue"):
            vue_info = detect_vue_sfc(rel_path)
            if vue_info:
                node_id, _ = await self._track_node(NodeCreateInput(
                    name=vue_info["name"],
                    type=NodeType.module,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    metadata={"framework": "vue", "component": True},
                    source_file=rel_path,
                ))
                self._module_node_ids[rel_path] = node_id

        # Detect API calls (fetch/axios to /api/...)
        await self._detect_api_calls(source, rel_path)

        # Detect Zustand store usage
        await self._detect_store_usage(source, rel_path)

        # Detect import edges
        await self._detect_imports(source, filepath, rel_path, project_root)

    async def _detect_framework_conventions(
        self, rel_path: str, source: str, filepath: str, project_root: str
    ):
        """Detect Next.js/Nuxt route conventions from file paths."""

        # Next.js App Router pages and API routes
        route_info = detect_nextjs_route(rel_path)
        if route_info:
            if route_info["type"] == "api":
                # Detect exported HTTP method handlers
                methods = NEXTJS_API_EXPORT.findall(source)
                if methods:
                    for method in methods:
                        route_name = f"{method.upper()} {route_info['route']}"
                        node_id, _ = await self._track_node(NodeCreateInput(
                            name=route_name,
                            type=NodeType.route,
                            status=NodeStatus.built,
                            parent_id=self.root_id,
                            metadata={
                                "method": method.upper(),
                                "path": route_info["route"],
                                "framework": "nextjs",
                                "router": route_info["router"],
                                "api": True,
                            },
                            source_file=rel_path,
                        ))
                        self._route_node_ids[route_info["route"]] = node_id
                else:
                    # No explicit exports — create a generic route
                    node_id, _ = await self._track_node(NodeCreateInput(
                        name=route_info["route"],
                        type=NodeType.route,
                        status=NodeStatus.built,
                        parent_id=self.root_id,
                        metadata={
                            "path": route_info["route"],
                            "framework": "nextjs",
                            "router": route_info["router"],
                            "api": True,
                        },
                        source_file=rel_path,
                    ))
                    self._route_node_ids[route_info["route"]] = node_id
            else:
                # Page route
                node_id, _ = await self._track_node(NodeCreateInput(
                    name=route_info["route"],
                    type=NodeType.route,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    metadata={
                        "path": route_info["route"],
                        "framework": "nextjs",
                        "router": route_info["router"],
                    },
                    source_file=rel_path,
                ))
                # Track for layout->page contains edges
                page_dir = os.path.dirname(rel_path)
                self._page_node_ids.setdefault(page_dir, []).append(node_id)

        # Nuxt pages
        nuxt_info = detect_nuxt_route(rel_path)
        if nuxt_info:
            await self._track_node(NodeCreateInput(
                name=nuxt_info["route"],
                type=NodeType.route,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={
                    "path": nuxt_info["route"],
                    "framework": "nuxt",
                },
                source_file=rel_path,
            ))

        # Next.js layouts
        layout_info = detect_nextjs_layout(rel_path)
        if layout_info:
            node_id, _ = await self._track_node(NodeCreateInput(
                name=layout_info["name"],
                type=NodeType.module,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={
                    "framework": "nextjs",
                    "layout": True,
                },
                source_file=rel_path,
            ))
            layout_dir = os.path.dirname(rel_path)
            self._layout_node_ids[layout_dir] = node_id

        # Next.js middleware
        if detect_nextjs_middleware(rel_path):
            await self._track_node(NodeCreateInput(
                name="middleware",
                type=NodeType.middleware,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"framework": "nextjs"},
                source_file=rel_path,
            ))

    async def _detect_components(self, source: str, rel_path: str, rendering: str | None = None):
        """Detect React components from export patterns."""
        seen_names: set[str] = set()

        for pattern in (REACT_EXPORT_DEFAULT, REACT_EXPORT_NAMED, REACT_ARROW_COMPONENT):
            for match in pattern.finditer(source):
                comp_name = match.group(1)
                if comp_name in seen_names:
                    continue
                seen_names.add(comp_name)

                line = source[:match.start()].count("\n") + 1
                metadata: dict = {"framework": "react", "component": True}
                if rendering:
                    metadata["rendering"] = rendering
                node_id, _ = await self._track_node(NodeCreateInput(
                    name=comp_name,
                    type=NodeType.module,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    metadata=metadata,
                    source_file=rel_path,
                    source_line=line,
                ))
                self._module_node_ids[rel_path] = node_id

    async def _detect_classes(self, source: str, rel_path: str):
        """Detect class definitions and inheritance."""
        seen_classes: set[str] = set()

        # Classes with extends (creates inheritance edge)
        for match in CLASS_EXTENDS.finditer(source):
            child_name = match.group(1)
            parent_name = match.group(2)
            line = source[:match.start()].count("\n") + 1
            seen_classes.add(child_name)

            child_id, _ = await self._track_node(NodeCreateInput(
                name=child_name,
                type=NodeType.class_def,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"extends": parent_name},
                source_file=rel_path,
                source_line=line,
            ))
            self._class_node_ids[child_name] = child_id
            self._deferred_inherit_edges.append((child_name, parent_name))

        # Standalone classes (no extends)
        for match in CLASS_STANDALONE.finditer(source):
            class_name = match.group(1)
            if class_name in seen_classes:
                continue
            seen_classes.add(class_name)
            line = source[:match.start()].count("\n") + 1

            node_id, _ = await self._track_node(NodeCreateInput(
                name=class_name,
                type=NodeType.class_def,
                status=NodeStatus.built,
                parent_id=self.root_id,
                source_file=rel_path,
                source_line=line,
            ))
            self._class_node_ids[class_name] = node_id

    async def _detect_middleware(self, source: str, rel_path: str):
        """Detect Express-style middleware usage."""
        for match in MIDDLEWARE_USE.finditer(source):
            mw_name = match.group(1)
            # Skip common non-middleware patterns
            if mw_name in ("express", "cors", "helmet", "morgan", "path"):
                continue
            line = source[:match.start()].count("\n") + 1
            await self._track_node(NodeCreateInput(
                name=mw_name,
                type=NodeType.middleware,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"framework": "express"},
                source_file=rel_path,
                source_line=line,
            ))

    async def _detect_imports(
        self, source: str, filepath: str, rel_path: str, project_root: str
    ):
        """Detect import statements and create depends_on edges for local imports."""
        import_paths = extract_import_paths(source, self._path_aliases)

        for import_path in import_paths:
            if import_path.startswith("."):
                resolved = resolve_import_path(import_path, filepath, project_root)
            else:
                resolved = resolve_alias_import(import_path, project_root, self._path_aliases)
            if resolved is None:
                continue

            # Ensure source module node exists
            if rel_path not in self._module_node_ids:
                src_name = module_name_from_path(rel_path)
                src_id, _ = await self._track_node(NodeCreateInput(
                    name=src_name,
                    type=NodeType.module,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    source_file=rel_path,
                ))
                self._module_node_ids[rel_path] = src_id

            # Ensure target module node exists
            if resolved not in self._module_node_ids:
                tgt_name = module_name_from_path(resolved)
                tgt_id, _ = await self._track_node(NodeCreateInput(
                    name=tgt_name,
                    type=NodeType.module,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    source_file=resolved,
                ))
                self._module_node_ids[resolved] = tgt_id

            self._deferred_import_edges.append((rel_path, resolved))

    async def _detect_react_patterns(
        self, source: str, rel_path: str, rendering: str | None = None
    ):
        """Detect React-specific patterns: Zustand stores, hooks, context, forwardRef, memo."""
        seen_names: set[str] = set()

        # Zustand stores (before hooks — useXStore matches both patterns, Zustand is more specific)
        for match in ZUSTAND_CREATE.finditer(source):
            store_name = match.group(1)
            if store_name in seen_names:
                continue
            seen_names.add(store_name)
            line = source[:match.start()].count("\n") + 1
            node_id, _ = await self._track_node(NodeCreateInput(
                name=store_name,
                type=NodeType.module,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"pattern": "zustand_store", "state_management": True},
                source_file=rel_path,
                source_line=line,
            ))
            self._module_node_ids[rel_path] = node_id
            self._store_node_ids[store_name] = node_id

        # Custom hooks (useX)
        for pattern in (CUSTOM_HOOK, CUSTOM_HOOK_ARROW):
            for match in pattern.finditer(source):
                hook_name = match.group(1)
                if hook_name in seen_names:
                    continue
                seen_names.add(hook_name)
                line = source[:match.start()].count("\n") + 1
                metadata: dict = {"framework": "react", "pattern": "hook"}
                if rendering:
                    metadata["rendering"] = rendering
                node_id, _ = await self._track_node(NodeCreateInput(
                    name=hook_name,
                    type=NodeType.function,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    metadata=metadata,
                    source_file=rel_path,
                    source_line=line,
                ))
                self._module_node_ids[rel_path] = node_id

        # createContext
        for match in CREATE_CONTEXT.finditer(source):
            ctx_name = match.group(1)
            if ctx_name in seen_names:
                continue
            seen_names.add(ctx_name)
            line = source[:match.start()].count("\n") + 1
            metadata = {"framework": "react", "pattern": "context_provider"}
            if rendering:
                metadata["rendering"] = rendering
            node_id, _ = await self._track_node(NodeCreateInput(
                name=ctx_name,
                type=NodeType.module,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata=metadata,
                source_file=rel_path,
                source_line=line,
            ))

        # forwardRef
        for match in FORWARD_REF.finditer(source):
            ref_name = match.group(1)
            if ref_name in seen_names:
                continue
            seen_names.add(ref_name)
            line = source[:match.start()].count("\n") + 1
            metadata = {"framework": "react", "pattern": "forwardRef"}
            if rendering:
                metadata["rendering"] = rendering
            node_id, _ = await self._track_node(NodeCreateInput(
                name=ref_name,
                type=NodeType.module,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata=metadata,
                source_file=rel_path,
                source_line=line,
            ))
            self._module_node_ids[rel_path] = node_id

        # React.memo
        for match in REACT_MEMO.finditer(source):
            memo_name = match.group(1)
            if memo_name in seen_names:
                continue
            seen_names.add(memo_name)
            line = source[:match.start()].count("\n") + 1
            metadata = {"framework": "react", "pattern": "memo"}
            if rendering:
                metadata["rendering"] = rendering
            node_id, _ = await self._track_node(NodeCreateInput(
                name=memo_name,
                type=NodeType.module,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata=metadata,
                source_file=rel_path,
                source_line=line,
            ))
            self._module_node_ids[rel_path] = node_id

    async def _detect_store_usage(self, source: str, rel_path: str):
        """Detect Zustand useXStore() calls and defer depends_on edges.

        Collects all usage unconditionally — filtering against known stores
        happens in _create_deferred_edges after all files are scanned.
        """
        for match in ZUSTAND_USE_STORE.finditer(source):
            store_name = match.group(1)
            self._deferred_store_edges.append((rel_path, store_name))

    async def _detect_api_calls(self, source: str, rel_path: str):
        """Detect fetch/axios calls to /api/... paths and Tauri invoke() calls."""
        for pattern in (FETCH_API_CALL, AXIOS_API_CALL):
            for match in pattern.finditer(source):
                api_path = match.group(1)
                self._deferred_api_edges.append((rel_path, api_path))

        # Tauri invoke("command_name") -> deferred edge to Rust command
        # Only detect invoke() in files that import from @tauri-apps
        if re.search(r"""from\s+['"]@tauri-apps/""", source):
            for match in TAURI_INVOKE.finditer(source):
                cmd_name = match.group(1)
                self._deferred_invoke_edges.append((rel_path, cmd_name))

    async def _scan_prisma_file(self, filepath: str, project_root: str):
        """Scan .prisma files for model definitions."""
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                source = f.read()
        except OSError as e:
            self._add_error(rel_path, str(e))
            return

        for match in PRISMA_MODEL.finditer(source):
            model_name = match.group(1)
            line = source[:match.start()].count("\n") + 1
            await self._track_node(NodeCreateInput(
                name=model_name.lower(),
                type=NodeType.table,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"orm_class": model_name, "source": "prisma"},
                source_file=rel_path,
                source_line=line,
            ))

    async def _create_directory_parents(self, project_root: str):
        """Create parent module nodes for directories that contain multiple components."""
        dir_counts: dict[str, int] = {}
        dir_files: dict[str, list[tuple[str, str]]] = {}

        for rel_path, node_id in self._module_node_ids.items():
            rel_dir = os.path.dirname(rel_path)
            if not rel_dir or rel_dir == ".":
                continue
            if rel_dir not in dir_counts:
                dir_counts[rel_dir] = 0
                dir_files[rel_dir] = []
            dir_counts[rel_dir] += 1
            dir_files[rel_dir].append((rel_path, node_id))

        # Process deepest directories first so children get correct parents
        sorted_dirs = sorted(
            dir_counts.keys(), key=lambda d: d.count(os.sep), reverse=True
        )
        dir_node_ids: dict[str, str] = {}

        for rel_dir in sorted_dirs:
            if dir_counts[rel_dir] < 2:
                continue

            dir_name = os.path.basename(rel_dir)

            # Skip 'src' at top level — too broad to be a useful parent
            if dir_name == "src" and rel_dir == "src":
                continue

            # Find this directory's parent directory node (if it exists)
            parent_dir = os.path.dirname(rel_dir)
            parent_id = dir_node_ids.get(parent_dir, self.root_id)

            node_id, _ = await self._track_node(NodeCreateInput(
                name=dir_name,
                type=NodeType.module,
                status=NodeStatus.built,
                parent_id=parent_id,
                description=f"Directory: {rel_dir}",
                metadata={"directory": True, "path": rel_dir},
            ))
            dir_node_ids[rel_dir] = node_id

        # Re-parent existing nodes to their directory parent
        for rel_dir, files in dir_files.items():
            parent_node_id = dir_node_ids.get(rel_dir)
            if not parent_node_id:
                continue
            for _rel_path, node_id in files:
                # Don't self-parent (directory node may reuse a file node)
                if node_id != parent_node_id:
                    await self.db.update_node_parent(node_id, parent_node_id)

    async def _create_deferred_edges(self):
        """Create all deferred edges after scanning is complete."""
        # Import edges
        seen_edges: set[tuple[str, str]] = set()
        for src_path, tgt_path in self._deferred_import_edges:
            src_id = self._module_node_ids.get(src_path)
            tgt_id = self._module_node_ids.get(tgt_path)
            if src_id and tgt_id and src_id != tgt_id:
                edge_key = (src_id, tgt_id)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    await self._track_edge(EdgeCreateInput(
                        source_id=src_id,
                        target_id=tgt_id,
                        relationship=EdgeRelationship.depends_on,
                    ))

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

        # Layout -> page contains edges
        for layout_dir, layout_id in self._layout_node_ids.items():
            page_ids = self._page_node_ids.get(layout_dir, [])
            for page_id in page_ids:
                await self._track_edge(EdgeCreateInput(
                    source_id=layout_id,
                    target_id=page_id,
                    relationship=EdgeRelationship.contains,
                ))

        # API call edges (fetch/axios -> route)
        for src_path, api_path in self._deferred_api_edges:
            src_id = self._module_node_ids.get(src_path)
            tgt_id = self._route_node_ids.get(api_path)
            if src_id and tgt_id:
                edge_key = (src_id, tgt_id)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    await self._track_edge(EdgeCreateInput(
                        source_id=src_id,
                        target_id=tgt_id,
                        relationship=EdgeRelationship.uses,
                    ))

        # Zustand store usage edges
        for src_path, store_name in self._deferred_store_edges:
            src_id = self._module_node_ids.get(src_path)
            tgt_id = self._store_node_ids.get(store_name)
            if src_id and tgt_id and src_id != tgt_id:
                edge_key = (src_id, tgt_id)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    await self._track_edge(EdgeCreateInput(
                        source_id=src_id,
                        target_id=tgt_id,
                        relationship=EdgeRelationship.depends_on,
                    ))

        # Tauri invoke() edges -> calls to #[tauri::command] Rust functions
        if self._deferred_invoke_edges:
            all_nodes = await self.db.get_all_nodes()
            tauri_cmds = {
                n.name: n.id for n in all_nodes
                if n.metadata and n.metadata.get("tauri_command")
            }
            for src_path, cmd_name in self._deferred_invoke_edges:
                src_id = self._module_node_ids.get(src_path)
                tgt_id = tauri_cmds.get(cmd_name)
                if src_id and tgt_id:
                    edge_key = (src_id, tgt_id)
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        await self._track_edge(EdgeCreateInput(
                            source_id=src_id,
                            target_id=tgt_id,
                            relationship=EdgeRelationship.calls,
                        ))
