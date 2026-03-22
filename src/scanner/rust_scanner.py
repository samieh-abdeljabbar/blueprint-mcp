"""Rust scanner — regex-based analysis of Rust files and Cargo.toml."""

from __future__ import annotations

import os
import re
import time

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

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
STRUCT_PATTERN = re.compile(r'^\s*(?:pub(?:\(crate\))?\s+)?struct\s+(\w+)', re.MULTILINE)
ENUM_PATTERN = re.compile(r'^\s*(?:pub(?:\(crate\))?\s+)?enum\s+(\w+)', re.MULTILINE)
TRAIT_PATTERN = re.compile(r'^\s*(?:pub(?:\(crate\))?\s+)?trait\s+(\w+)', re.MULTILINE)
IMPL_PATTERN = re.compile(
    r'^\s*impl(?:<[^>]*>)?\s+(\w+)(?:\s+for\s+(\w+))?',
    re.MULTILINE,
)
FN_PATTERN = re.compile(
    r'^\s*(?:pub(?:\(crate\))?\s+)?(?:async\s+)?fn\s+(\w+)',
    re.MULTILINE,
)
MOD_PATTERN = re.compile(r'^\s*(?:pub(?:\(crate\))?\s+)?mod\s+(\w+)\s*[;{]', re.MULTILINE)
USE_CRATE = re.compile(r'^\s*use\s+crate::(\w+)', re.MULTILINE)
ROUTE_MACRO = re.compile(
    r'#\[(get|post|put|delete|patch)\("([^"]+)"\)\]',
    re.IGNORECASE,
)
TAURI_COMMAND = re.compile(
    r'#\[tauri::command\](?:\s*#\[.*?\])*\s*(?:pub(?:\(crate\))?\s+)?(?:async\s+)?fn\s+(\w+)',
    re.MULTILINE | re.DOTALL,
)

RUST_EXTENSIONS = {".rs"}


class RustScanner(BaseScanner):
    async def scan(self, path: str) -> ScanResult:
        start = time.time()
        self._type_node_ids: dict[str, str] = {}
        self._mod_node_ids: dict[str, str] = {}
        self._deferred_impl_edges: list[tuple[str, str]] = []  # (trait, struct)
        self._deferred_mod_edges: list[tuple[str, str]] = []  # (file_path, mod_name)

        # For Tauri projects, scan src-tauri/ if Cargo.toml is not at root
        scan_root = path
        tauri_dir = os.path.join(path, "src-tauri")
        if not os.path.isfile(os.path.join(path, "Cargo.toml")) and os.path.isdir(tauri_dir):
            scan_root = tauri_dir

        # Parse Cargo.toml
        await self._scan_cargo_toml(scan_root)

        for dirpath, dirnames, filenames in os.walk(scan_root):
            dirnames[:] = [
                d for d in dirnames
                if not self.should_ignore(os.path.join(dirpath, d), scan_root)
            ]
            for fname in filenames:
                if os.path.splitext(fname)[1] not in RUST_EXTENSIONS:
                    continue
                full = os.path.join(dirpath, fname)
                if self.should_ignore(full, scan_root):
                    continue
                await self._scan_file(full, scan_root)
                self._files_scanned += 1

        # Create deferred edges
        await self._create_deferred_edges()

        # Create directory hierarchy
        await self._create_directory_parents(scan_root)

        return self._build_result("rust_scanner", start)

    async def _scan_cargo_toml(self, project_root: str):
        cargo_path = os.path.join(project_root, "Cargo.toml")
        if not os.path.isfile(cargo_path):
            return
        try:
            with open(cargo_path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            self._add_error("Cargo.toml", str(e))
            return

        self._files_scanned += 1

        # Package info -> service node
        package = data.get("package", {})
        if package:
            name = package.get("name", os.path.basename(project_root))
            version = package.get("version", "")
            await self._track_node(NodeCreateInput(
                name=name,
                type=NodeType.service,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"version": version, "source": "Cargo.toml"},
                source_file="Cargo.toml",
            ))

        # Dependencies -> external nodes
        for dep_section in ("dependencies", "dev-dependencies"):
            deps = data.get(dep_section, {})
            for dep_name in deps:
                await self._track_node(NodeCreateInput(
                    name=dep_name,
                    type=NodeType.external,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    metadata={"source": "Cargo.toml", "section": dep_section},
                    source_file="Cargo.toml",
                ))

    async def _scan_file(self, filepath: str, project_root: str):
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                source = f.read()
        except OSError as e:
            self._add_error(rel_path, str(e))
            return

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

        # Detect enums
        for match in ENUM_PATTERN.finditer(source):
            name = match.group(1)
            line = source[:match.start()].count("\n") + 1
            node_id, _ = await self._track_node(NodeCreateInput(
                name=name,
                type=NodeType.enum_def,
                status=NodeStatus.built,
                parent_id=self.root_id,
                source_file=rel_path,
                source_line=line,
            ))
            self._type_node_ids[name] = node_id

        # Detect traits
        for match in TRAIT_PATTERN.finditer(source):
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

        # Detect impl blocks (trait implementations)
        for match in IMPL_PATTERN.finditer(source):
            trait_or_type = match.group(1)
            for_type = match.group(2)
            if for_type:
                # impl Trait for Struct
                self._deferred_impl_edges.append((trait_or_type, for_type))

        # Detect route macros (actix/axum)
        for match in ROUTE_MACRO.finditer(source):
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

        # Detect #[tauri::command] functions
        for match in TAURI_COMMAND.finditer(source):
            cmd_name = match.group(1)
            line = source[:match.start()].count("\n") + 1
            node_id, _ = await self._track_node(NodeCreateInput(
                name=cmd_name,
                type=NodeType.route,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"tauri_command": True, "ipc": True},
                source_file=rel_path,
                source_line=line,
            ))
            self._type_node_ids[cmd_name] = node_id

        # Detect mod declarations
        for match in MOD_PATTERN.finditer(source):
            mod_name = match.group(1)
            node_id, _ = await self._track_node(NodeCreateInput(
                name=mod_name,
                type=NodeType.module,
                status=NodeStatus.built,
                parent_id=self.root_id,
                source_file=rel_path,
            ))
            self._mod_node_ids[mod_name] = node_id

        # Detect use crate:: dependencies
        for match in USE_CRATE.finditer(source):
            mod_name = match.group(1)
            self._deferred_mod_edges.append((rel_path, mod_name))

    async def _create_deferred_edges(self):
        # impl Trait for Struct -> implements edge
        for trait_name, struct_name in self._deferred_impl_edges:
            trait_id = self._type_node_ids.get(trait_name)
            struct_id = self._type_node_ids.get(struct_name)
            if trait_id and struct_id:
                await self._track_edge(EdgeCreateInput(
                    source_id=struct_id,
                    target_id=trait_id,
                    relationship=EdgeRelationship.implements,
                ))

        # use crate::mod -> depends_on edge
        seen: set[tuple[str, str]] = set()
        for file_path, mod_name in self._deferred_mod_edges:
            mod_id = self._mod_node_ids.get(mod_name)
            if mod_id and (file_path, mod_name) not in seen:
                seen.add((file_path, mod_name))
                # Create source module node if needed
                src_name = os.path.splitext(os.path.basename(file_path))[0]
                src_id, _ = await self._track_node(NodeCreateInput(
                    name=src_name,
                    type=NodeType.module,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    source_file=file_path,
                ))
                if src_id != mod_id:
                    await self._track_edge(EdgeCreateInput(
                        source_id=src_id,
                        target_id=mod_id,
                        relationship=EdgeRelationship.depends_on,
                    ))
