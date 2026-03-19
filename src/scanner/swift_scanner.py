"""Swift/SwiftUI scanner — regex-based analysis of Swift files."""

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
STRUCT_PATTERN = re.compile(
    r'^\s*(?:public\s+|private\s+|internal\s+|open\s+)?struct\s+(\w+)(?:\s*:\s*(.+?))?\s*\{',
    re.MULTILINE,
)
CLASS_PATTERN = re.compile(
    r'^\s*(?:public\s+|private\s+|internal\s+|open\s+)?(?:final\s+)?class\s+(\w+)(?:\s*:\s*(.+?))?\s*\{',
    re.MULTILINE,
)
PROTOCOL_PATTERN = re.compile(
    r'^\s*(?:public\s+|private\s+|internal\s+)?protocol\s+(\w+)',
    re.MULTILINE,
)
ENUM_PATTERN = re.compile(
    r'^\s*(?:public\s+|private\s+|internal\s+)?enum\s+(\w+)',
    re.MULTILINE,
)
FUNC_PATTERN = re.compile(
    r'^(?:public\s+|private\s+)?func\s+(\w+)\s*\(',
    re.MULTILINE,
)
IMPORT_PATTERN = re.compile(
    r'^\s*import\s+(\w+)',
    re.MULTILINE,
)
MAIN_APP = re.compile(
    r'@main\s+(?:\w+\s+)*?struct\s+(\w+)',
    re.DOTALL,
)

SWIFT_EXTENSIONS = {".swift"}

# Known SwiftUI view protocols
VIEW_PROTOCOLS = {"View", "App"}
# Known observable protocols
OBSERVABLE_PROTOCOLS = {"ObservableObject", "Observable"}
# Swift standard protocols to ignore for conformance edges
STDLIB_PROTOCOLS = {
    "Codable", "Decodable", "Encodable", "Hashable", "Equatable",
    "Comparable", "Identifiable", "CustomStringConvertible", "Error",
    "CaseIterable", "RawRepresentable", "Sendable",
}


class SwiftScanner(BaseScanner):
    async def scan(self, path: str) -> ScanResult:
        start = time.time()
        self._protocol_node_ids: dict[str, str] = {}
        self._class_node_ids: dict[str, str] = {}
        self._deferred_conformance: list[tuple[str, str, str]] = []  # (child_id, parent_name, type)

        # Parse Package.swift if present
        await self._scan_package_swift(path)

        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [
                d for d in dirnames
                if not self.should_ignore(os.path.join(dirpath, d), path)
            ]
            for fname in filenames:
                if os.path.splitext(fname)[1] not in SWIFT_EXTENSIONS:
                    continue
                full = os.path.join(dirpath, fname)
                if self.should_ignore(full, path):
                    continue
                await self._scan_file(full, path)
                self._files_scanned += 1

        # Create deferred conformance/inheritance edges
        await self._create_deferred_edges()

        return self._build_result("swift_scanner", start)

    async def _scan_package_swift(self, project_root: str):
        pkg_path = os.path.join(project_root, "Package.swift")
        if not os.path.isfile(pkg_path):
            return
        try:
            with open(pkg_path) as f:
                source = f.read()
        except OSError as e:
            self._add_error("Package.swift", str(e))
            return

        self._files_scanned += 1

        # Extract .target and .executableTarget names
        target_pattern = re.compile(
            r'\.(?:target|executableTarget|testTarget)\(\s*name:\s*"(\w+)"'
        )
        for match in target_pattern.finditer(source):
            target_name = match.group(1)
            await self._track_node(NodeCreateInput(
                name=target_name,
                type=NodeType.module,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"source": "Package.swift", "spm_target": True},
                source_file="Package.swift",
            ))

    async def _scan_file(self, filepath: str, project_root: str):
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                source = f.read()
        except OSError as e:
            self._add_error(rel_path, str(e))
            return

        # Check for @main app entry point
        for match in MAIN_APP.finditer(source):
            app_name = match.group(1)
            node_id, _ = await self._track_node(NodeCreateInput(
                name=app_name,
                type=NodeType.service,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"entry_point": True, "framework": "swiftui"},
                source_file=rel_path,
            ))
            self._class_node_ids[app_name] = node_id

        # Detect protocols
        for match in PROTOCOL_PATTERN.finditer(source):
            proto_name = match.group(1)
            line = source[:match.start()].count("\n") + 1
            node_id, _ = await self._track_node(NodeCreateInput(
                name=proto_name,
                type=NodeType.protocol,
                status=NodeStatus.built,
                parent_id=self.root_id,
                source_file=rel_path,
                source_line=line,
            ))
            self._protocol_node_ids[proto_name] = node_id

        # Detect structs
        for match in STRUCT_PATTERN.finditer(source):
            struct_name = match.group(1)
            conformances_str = match.group(2)
            line = source[:match.start()].count("\n") + 1

            conformances = _parse_conformances(conformances_str)

            # Determine node type based on conformances
            if conformances & VIEW_PROTOCOLS:
                node_type = NodeType.view
                metadata = {"framework": "swiftui", "view": True}
            else:
                node_type = NodeType.struct
                metadata = {}

            if conformances:
                metadata["conformances"] = sorted(conformances)

            node_id, _ = await self._track_node(NodeCreateInput(
                name=struct_name,
                type=node_type,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata=metadata or None,
                source_file=rel_path,
                source_line=line,
            ))
            self._class_node_ids[struct_name] = node_id

            # Defer conformance edges
            for proto in conformances:
                if proto not in STDLIB_PROTOCOLS and proto not in VIEW_PROTOCOLS:
                    self._deferred_conformance.append((node_id, proto, "implements"))

        # Detect classes
        for match in CLASS_PATTERN.finditer(source):
            class_name = match.group(1)
            conformances_str = match.group(2)
            line = source[:match.start()].count("\n") + 1

            conformances = _parse_conformances(conformances_str)
            metadata: dict = {}

            if conformances & OBSERVABLE_PROTOCOLS:
                metadata["observable"] = True

            if conformances:
                metadata["conformances"] = sorted(conformances)

            node_id, _ = await self._track_node(NodeCreateInput(
                name=class_name,
                type=NodeType.class_def,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata=metadata or None,
                source_file=rel_path,
                source_line=line,
            ))
            self._class_node_ids[class_name] = node_id

            # First conformance could be superclass (Swift convention)
            if conformances:
                first = list(conformances)[0] if conformances_str else None
                # Parse the raw string to get order
                raw_list = [c.strip() for c in (conformances_str or "").split(",")]
                if raw_list:
                    first = raw_list[0]
                    # If first is not a known protocol, treat as superclass
                    if first and first[0].isupper() and first not in STDLIB_PROTOCOLS:
                        self._deferred_conformance.append((node_id, first, "inherits"))
                    for proto in raw_list[1:]:
                        if proto and proto not in STDLIB_PROTOCOLS and proto not in VIEW_PROTOCOLS:
                            self._deferred_conformance.append((node_id, proto, "implements"))

        # Detect enums
        for match in ENUM_PATTERN.finditer(source):
            enum_name = match.group(1)
            line = source[:match.start()].count("\n") + 1
            node_id, _ = await self._track_node(NodeCreateInput(
                name=enum_name,
                type=NodeType.enum_def,
                status=NodeStatus.built,
                parent_id=self.root_id,
                source_file=rel_path,
                source_line=line,
            ))
            self._class_node_ids[enum_name] = node_id

    async def _create_deferred_edges(self):
        for child_id, parent_name, edge_type in self._deferred_conformance:
            parent_id = (
                self._protocol_node_ids.get(parent_name)
                or self._class_node_ids.get(parent_name)
            )
            if parent_id:
                rel = EdgeRelationship.inherits if edge_type == "inherits" else EdgeRelationship.implements
                await self._track_edge(EdgeCreateInput(
                    source_id=child_id,
                    target_id=parent_id,
                    relationship=rel,
                ))


def _parse_conformances(conformances_str: str | None) -> set[str]:
    """Parse Swift protocol conformance list: 'View, Identifiable' -> {'View', 'Identifiable'}"""
    if not conformances_str:
        return set()
    return {c.strip() for c in conformances_str.split(",") if c.strip()}
