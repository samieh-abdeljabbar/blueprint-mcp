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

# ---- Phase 1: Declaration patterns ----
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

# ---- Phase 2: Reference patterns ----
RE_PROPERTY_TYPE = re.compile(
    r'(?:var|let)\s+\w+\s*:\s*\[?(\w+)\]?',
)
RE_OBSERVED_OBJECT = re.compile(
    r'@(?:ObservedObject|StateObject)\s+(?:var|let)\s+\w+\s*(?::\s*(\w+)|=\s*(\w+)\s*\()',
)
RE_ENVIRONMENT_OBJECT = re.compile(
    r'@EnvironmentObject\s+(?:var|let)\s+\w+\s*:\s*(\w+)',
)
RE_BINDING = re.compile(
    r'@Binding\s+(?:var|let)\s+\w+\s*:\s*(\w+)',
)
RE_INIT_CALL = re.compile(
    r'\b([A-Z]\w+)\s*\(',
)
RE_EXTENSION = re.compile(
    r'^extension\s+(\w+)\s*:\s*([^{]+)\s*\{',
    re.MULTILINE,
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
# Framework types to ignore for dependency edges (not user-defined)
FRAMEWORK_TYPES = {
    "String", "Int", "Double", "Float", "Bool", "Data", "Date", "URL",
    "UUID", "Array", "Dictionary", "Set", "Optional", "Result",
    "CGFloat", "CGPoint", "CGSize", "CGRect",
    "Color", "Font", "Image", "Text", "Button", "NavigationView",
    "NavigationStack", "NavigationLink", "List", "VStack", "HStack",
    "ZStack", "ForEach", "Section", "Form", "Group", "GeometryReader",
    "ScrollView", "TabView", "Sheet", "Alert",
    "some", "Any", "AnyObject", "Never", "Void",
    "Scene", "WindowGroup", "Published",
} | STDLIB_PROTOCOLS | VIEW_PROTOCOLS | OBSERVABLE_PROTOCOLS


class SwiftScanner(BaseScanner):
    async def scan(self, path: str) -> ScanResult:
        start = time.time()
        self._protocol_node_ids: dict[str, str] = {}
        self._class_node_ids: dict[str, str] = {}
        self._deferred_conformance: list[tuple[str, str, str]] = []  # (child_id, parent_name, type)
        self._deferred_references: list[tuple[str, str, str]] = []  # (source_id, target_id, edge_type)

        # Parse Package.swift if present
        await self._scan_package_swift(path)

        # Phase 1: Scan all files for type declarations (nodes)
        swift_files: list[str] = []
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
                swift_files.append(full)

        # Phase 2: Scan references (edges from property types, wrappers, init calls)
        for full in swift_files:
            await self._scan_references(full, path)

        # Phase 3: Create all deferred edges
        await self._create_deferred_edges()

        # Phase 4: Create directory hierarchy
        await self._create_directory_parents(path)

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
        """Phase 1: Scan for type declarations and create nodes."""
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
            if struct_name in self._class_node_ids:  # Already created (e.g., by @main)
                continue
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

    async def _scan_references(self, filepath: str, project_root: str):
        """Phase 2: Scan for type references, property wrappers, and init calls."""
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                source = f.read()
        except OSError:
            return

        known_types = set(self._class_node_ids.keys()) | set(self._protocol_node_ids.keys())

        # Find the primary node for this file (first type declared in it)
        file_source_id = self._find_file_source_id(rel_path)
        if not file_source_id:
            return

        seen_targets: set[str] = set()

        def _try_add_edge(type_name: str | None, edge_type: str):
            if not type_name or type_name in seen_targets:
                return
            if type_name not in known_types or type_name in FRAMEWORK_TYPES:
                return
            target_id = self._class_node_ids.get(type_name) or self._protocol_node_ids.get(type_name)
            if target_id and target_id != file_source_id:
                seen_targets.add(type_name)
                self._deferred_references.append((file_source_id, target_id, edge_type))

        # @StateObject / @ObservedObject -> depends_on
        for match in RE_OBSERVED_OBJECT.finditer(source):
            _try_add_edge(match.group(1) or match.group(2), "depends_on")

        # @EnvironmentObject -> depends_on
        for match in RE_ENVIRONMENT_OBJECT.finditer(source):
            _try_add_edge(match.group(1), "depends_on")

        # @Binding -> depends_on
        for match in RE_BINDING.finditer(source):
            _try_add_edge(match.group(1), "depends_on")

        # Property type references: var x: SomeType -> depends_on
        for match in RE_PROPERTY_TYPE.finditer(source):
            _try_add_edge(match.group(1), "depends_on")

        # Initializer calls: SomeType() -> uses
        for match in RE_INIT_CALL.finditer(source):
            _try_add_edge(match.group(1), "uses")

        # Extension conformance: extension X: ProtocolY
        for match in RE_EXTENSION.finditer(source):
            type_name = match.group(1)
            conformances_str = match.group(2)
            type_id = self._class_node_ids.get(type_name)
            if type_id and conformances_str:
                for proto in [c.strip() for c in conformances_str.split(",")]:
                    if proto and proto not in STDLIB_PROTOCOLS and proto not in VIEW_PROTOCOLS and proto not in FRAMEWORK_TYPES:
                        self._deferred_conformance.append((type_id, proto, "implements"))

    def _find_file_source_id(self, rel_path: str) -> str | None:
        """Find the primary node ID for a given source file."""
        node_ids = self._file_node_ids.get(rel_path, [])
        return node_ids[0] if node_ids else None

    async def _create_deferred_edges(self):
        # Conformance/inheritance edges
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

        # Reference edges (property types, wrappers, init calls)
        seen_edges: set[tuple[str, str]] = set()
        for source_id, target_id, edge_type in self._deferred_references:
            edge_key = (source_id, target_id)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            rel = EdgeRelationship.uses if edge_type == "uses" else EdgeRelationship.depends_on
            await self._track_edge(EdgeCreateInput(
                source_id=source_id,
                target_id=target_id,
                relationship=rel,
            ))


def _parse_conformances(conformances_str: str | None) -> set[str]:
    """Parse Swift protocol conformance list: 'View, Identifiable' -> {'View', 'Identifiable'}"""
    if not conformances_str:
        return set()
    return {c.strip() for c in conformances_str.split(",") if c.strip()}
