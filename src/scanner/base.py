"""Abstract base class for all scanners."""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod

import pathspec

from src.db import Database
from src.models import (
    EdgeCreateInput,
    NodeCreateInput,
    NodeStatus,
    NodeType,
    ScanError,
    ScanResult,
)

# Always ignored directories regardless of .gitignore
ALWAYS_IGNORE = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".env", ".tox", ".mypy_cache",
    ".build", "target", ".terraform", "Pods", "DerivedData",
}

# Top-level directories too broad to be useful parents in the X-Ray viewer
SKIP_TOP_LEVEL_DIRS = {"src", "Sources", "Source", "lib", "pkg", "cmd", "app", "internal"}


class BaseScanner(ABC):
    def __init__(
        self,
        db: Database,
        root_id: str,
        gitignore_spec: pathspec.PathSpec | None = None,
        deep: bool = False,
    ):
        self.db = db
        self.root_id = root_id
        self.gitignore_spec = gitignore_spec
        self.deep = deep
        self._nodes_created = 0
        self._nodes_updated = 0
        self._edges_created = 0
        self._errors: list[ScanError] = []
        self._files_scanned = 0
        self._file_node_ids: dict[str, list[str]] = {}  # source_file -> [node_ids]

    @abstractmethod
    async def scan(self, path: str) -> ScanResult:
        ...

    def should_ignore(self, filepath: str, project_root: str) -> bool:
        rel = os.path.relpath(filepath, project_root)
        parts = rel.split(os.sep)
        for part in parts:
            if part in ALWAYS_IGNORE:
                return True
        if self.gitignore_spec and self.gitignore_spec.match_file(rel):
            return True
        return False

    async def _track_node(self, inp: NodeCreateInput) -> tuple[str, str]:
        node, action = await self.db.find_or_create_node(inp)
        if action == "created":
            self._nodes_created += 1
        elif action == "updated":
            self._nodes_updated += 1
        if inp.source_file:
            self._file_node_ids.setdefault(inp.source_file, []).append(node.id)
        return node.id, action

    async def _track_edge(self, inp: EdgeCreateInput) -> str:
        edge, action = await self.db.find_or_create_edge(inp)
        if action == "created":
            self._edges_created += 1
        return action

    def _add_error(self, file: str, message: str, line: int | None = None):
        self._errors.append(ScanError(file=file, line=line, message=message))

    def _build_result(self, scanner_name: str, start_time: float) -> ScanResult:
        return ScanResult(
            scanner_name=scanner_name,
            nodes_created=self._nodes_created,
            nodes_updated=self._nodes_updated,
            edges_created=self._edges_created,
            errors=self._errors,
            files_scanned=self._files_scanned,
            duration_ms=(time.time() - start_time) * 1000,
        )

    async def _create_directory_parents(self, project_root: str) -> None:
        """Create parent module nodes for directories containing 2+ source files.

        Uses self._file_node_ids (auto-populated by _track_node) to build
        a directory hierarchy for the X-Ray viewer.
        """
        dir_files: dict[str, list[tuple[str, str]]] = {}
        seen_files: set[str] = set()

        for rel_path, node_ids in self._file_node_ids.items():
            rel_dir = os.path.dirname(rel_path)
            if not rel_dir or rel_dir == ".":
                continue
            for node_id in node_ids:
                dir_files.setdefault(rel_dir, []).append((rel_path, node_id))
            seen_files.add(rel_path)

        # Count unique files per directory
        dir_file_counts: dict[str, int] = {}
        for rel_path in seen_files:
            rel_dir = os.path.dirname(rel_path)
            if rel_dir and rel_dir != ".":
                dir_file_counts[rel_dir] = dir_file_counts.get(rel_dir, 0) + 1

        # Process deepest directories first
        sorted_dirs = sorted(
            dir_file_counts.keys(), key=lambda d: d.count(os.sep), reverse=True
        )
        dir_node_ids: dict[str, str] = {}

        for rel_dir in sorted_dirs:
            if dir_file_counts[rel_dir] < 2:
                continue

            dir_name = os.path.basename(rel_dir)

            # Skip common top-level directories that are too broad
            if dir_name in SKIP_TOP_LEVEL_DIRS and os.path.dirname(rel_dir) in ("", "."):
                continue

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
                if node_id != parent_node_id:
                    await self.db.update_node_parent(node_id, parent_node_id)
