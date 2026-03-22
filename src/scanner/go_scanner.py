"""Go scanner — regex-based analysis of Go files and go.mod."""

from __future__ import annotations

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

# Regex patterns
PACKAGE_PATTERN = re.compile(r'^package\s+(\w+)', re.MULTILINE)
STRUCT_PATTERN = re.compile(r'^type\s+(\w+)\s+struct\s*\{', re.MULTILINE)
INTERFACE_PATTERN = re.compile(r'^type\s+(\w+)\s+interface\s*\{', re.MULTILINE)
FUNC_PATTERN = re.compile(r'^func\s+(\w+)\s*\(', re.MULTILINE)
METHOD_PATTERN = re.compile(r'^func\s+\(\w+\s+\*?(\w+)\)\s+(\w+)\s*\(', re.MULTILINE)
IMPORT_PATTERN = re.compile(r'"([^"]+)"')
HTTP_HANDLE = re.compile(
    r'(?:HandleFunc|Handle|GET|POST|PUT|DELETE|PATCH|Get|Post|Put|Delete|Patch)\(\s*"([^"]+)"',
)

GO_EXTENSIONS = {".go"}


class GoScanner(BaseScanner):
    async def scan(self, path: str) -> ScanResult:
        start = time.time()
        self._type_node_ids: dict[str, str] = {}
        self._package_node_ids: dict[str, str] = {}

        # Parse go.mod
        await self._scan_go_mod(path)

        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [
                d for d in dirnames
                if not self.should_ignore(os.path.join(dirpath, d), path)
            ]
            for fname in filenames:
                if os.path.splitext(fname)[1] not in GO_EXTENSIONS:
                    continue
                # Skip test files in non-deep mode
                if not self.deep and fname.endswith("_test.go"):
                    continue
                full = os.path.join(dirpath, fname)
                if self.should_ignore(full, path):
                    continue
                await self._scan_file(full, path)
                self._files_scanned += 1

        # Create directory hierarchy
        await self._create_directory_parents(path)

        return self._build_result("go_scanner", start)

    async def _scan_go_mod(self, project_root: str):
        mod_path = os.path.join(project_root, "go.mod")
        if not os.path.isfile(mod_path):
            return
        try:
            with open(mod_path) as f:
                content = f.read()
        except OSError as e:
            self._add_error("go.mod", str(e))
            return

        self._files_scanned += 1

        # Module name -> service node
        mod_match = re.search(r'^module\s+(\S+)', content, re.MULTILINE)
        if mod_match:
            mod_name = mod_match.group(1)
            # Use last segment as display name
            display_name = mod_name.split("/")[-1]
            await self._track_node(NodeCreateInput(
                name=display_name,
                type=NodeType.service,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"module_path": mod_name, "source": "go.mod"},
                source_file="go.mod",
            ))

        # Go version
        go_match = re.search(r'^go\s+(\S+)', content, re.MULTILINE)

        # Dependencies -> external nodes
        in_require = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped == "require (":
                in_require = True
                continue
            if stripped == ")":
                in_require = False
                continue
            if in_require and stripped and not stripped.startswith("//"):
                parts = stripped.split()
                if parts:
                    dep_path = parts[0]
                    dep_name = dep_path.split("/")[-1]
                    await self._track_node(NodeCreateInput(
                        name=dep_name,
                        type=NodeType.external,
                        status=NodeStatus.built,
                        parent_id=self.root_id,
                        metadata={"module_path": dep_path, "source": "go.mod"},
                        source_file="go.mod",
                    ))

    async def _scan_file(self, filepath: str, project_root: str):
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                source = f.read()
        except OSError as e:
            self._add_error(rel_path, str(e))
            return

        # Detect package
        pkg_match = PACKAGE_PATTERN.search(source)
        if pkg_match:
            pkg_name = pkg_match.group(1)
            if pkg_name != "main" and pkg_name not in self._package_node_ids:
                node_id, _ = await self._track_node(NodeCreateInput(
                    name=pkg_name,
                    type=NodeType.module,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    metadata={"go_package": True},
                    source_file=rel_path,
                ))
                self._package_node_ids[pkg_name] = node_id

        # Detect structs
        for match in STRUCT_PATTERN.finditer(source):
            name = match.group(1)
            line = source[:match.start()].count("\n") + 1
            node_id, _ = await self._track_node(NodeCreateInput(
                name=name,
                type=NodeType.struct,
                status=NodeStatus.built,
                parent_id=self.root_id,
                source_file=rel_path,
                source_line=line,
            ))
            self._type_node_ids[name] = node_id

        # Detect interfaces
        for match in INTERFACE_PATTERN.finditer(source):
            name = match.group(1)
            line = source[:match.start()].count("\n") + 1
            node_id, _ = await self._track_node(NodeCreateInput(
                name=name,
                type=NodeType.protocol,
                status=NodeStatus.built,
                parent_id=self.root_id,
                source_file=rel_path,
                source_line=line,
            ))
            self._type_node_ids[name] = node_id

        # Detect standalone functions (not methods)
        for match in FUNC_PATTERN.finditer(source):
            func_name = match.group(1)
            if func_name == "main" or func_name == "init":
                continue
            line = source[:match.start()].count("\n") + 1
            await self._track_node(NodeCreateInput(
                name=f"{rel_path}:{func_name}",
                type=NodeType.function,
                status=NodeStatus.built,
                parent_id=self.root_id,
                source_file=rel_path,
                source_line=line,
            ))

        # Detect HTTP handlers
        for match in HTTP_HANDLE.finditer(source):
            route_path = match.group(1)
            line = source[:match.start()].count("\n") + 1
            await self._track_node(NodeCreateInput(
                name=route_path,
                type=NodeType.route,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"path": route_path},
                source_file=rel_path,
                source_line=line,
            ))
