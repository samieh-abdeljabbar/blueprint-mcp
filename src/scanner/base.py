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
    ScanError,
    ScanResult,
)

# Always ignored directories regardless of .gitignore
ALWAYS_IGNORE = {".git", "node_modules", "__pycache__", ".venv", "venv", ".env", ".tox", ".mypy_cache"}


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
