"""JavaScript/TypeScript scanner — regex-based analysis."""

from __future__ import annotations

import json
import os
import re
import time

from src.models import (
    NodeCreateInput,
    NodeStatus,
    NodeType,
    ScanResult,
)
from src.scanner.base import BaseScanner

# Regex patterns for route detection
# Matches: app.get('/path', ...), router.post('/path', ...) etc.
ROUTE_PATTERN = re.compile(
    r"""(?:app|router|server)\.(get|post|put|delete|patch)\(\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)

# React component patterns
# export default function ComponentName
REACT_EXPORT_DEFAULT = re.compile(
    r"""export\s+default\s+function\s+(\w+)"""
)
# export function ComponentName (PascalCase = component)
REACT_EXPORT_NAMED = re.compile(
    r"""export\s+function\s+([A-Z]\w+)"""
)

JS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


class JavaScriptScanner(BaseScanner):
    async def scan(self, path: str) -> ScanResult:
        start = time.time()

        # Read package.json first for service node
        await self._scan_package_json(path)

        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [
                d for d in dirnames if not self.should_ignore(os.path.join(dirpath, d), path)
            ]
            for fname in filenames:
                ext = os.path.splitext(fname)[1]
                if ext not in JS_EXTENSIONS:
                    continue
                full = os.path.join(dirpath, fname)
                if self.should_ignore(full, path):
                    continue
                await self._scan_file(full, path)
                self._files_scanned += 1

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

        # Detect routes
        for match in ROUTE_PATTERN.finditer(source):
            method = match.group(1).upper()
            route_path = match.group(2)
            route_name = f"{method} {route_path}"
            line = source[:match.start()].count("\n") + 1
            await self._track_node(NodeCreateInput(
                name=route_name,
                type=NodeType.route,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"method": method, "path": route_path},
                source_file=rel_path,
                source_line=line,
            ))

        # Detect React components
        for pattern in (REACT_EXPORT_DEFAULT, REACT_EXPORT_NAMED):
            for match in pattern.finditer(source):
                comp_name = match.group(1)
                line = source[:match.start()].count("\n") + 1
                await self._track_node(NodeCreateInput(
                    name=comp_name,
                    type=NodeType.module,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    metadata={"framework": "react", "component": True},
                    source_file=rel_path,
                    source_line=line,
                ))

        # Detect Prisma models in .prisma files
        if filepath.endswith(".prisma"):
            for match in re.finditer(r"model\s+(\w+)\s*\{", source):
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
