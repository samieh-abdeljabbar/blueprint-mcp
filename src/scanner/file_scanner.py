"""File scanner — detects project type, creates root system node and file nodes."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import pathspec

from src.db import Database
from src.models import NodeCreateInput, NodeType, NodeStatus, ScanResult
from src.scanner.base import BaseScanner, ALWAYS_IGNORE


# Config files that indicate project type
LANGUAGE_INDICATORS = {
    "python": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"],
    "javascript": ["package.json", "yarn.lock", "pnpm-lock.yaml"],
    "docker": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"],
    "swift": ["Package.swift", "Podfile", "Cartfile"],
    "rust": ["Cargo.toml", "Cargo.lock"],
    "go": ["go.mod", "go.sum"],
    "config": [".env", "main.tf", "variables.tf"],
    "sql": ["schema.prisma"],
}


@dataclass
class ProjectInfo:
    name: str
    root_id: str
    languages: list[str] = field(default_factory=list)
    has_docker: bool = False
    gitignore_spec: pathspec.PathSpec | None = None


class FileScanner(BaseScanner):
    async def scan(self, path: str) -> ScanResult:
        start = time.time()
        self._files_scanned = 0
        # Just count key config files we find
        for entry in os.listdir(path):
            full = os.path.join(path, entry)
            if os.path.isfile(full) and not self.should_ignore(full, path):
                self._files_scanned += 1
                # Create file nodes for config files
                is_config = False
                for lang, indicators in LANGUAGE_INDICATORS.items():
                    if entry in indicators:
                        is_config = True
                        break
                if is_config or entry in (".gitignore", "Makefile", "README.md"):
                    await self._track_node(NodeCreateInput(
                        name=entry,
                        type=NodeType.file,
                        status=NodeStatus.built,
                        parent_id=self.root_id,
                        source_file=os.path.relpath(full, path),
                    ))
        return self._build_result("file_scanner", start)


def _load_gitignore(project_path: str) -> pathspec.PathSpec | None:
    gitignore_path = os.path.join(project_path, ".gitignore")
    if os.path.isfile(gitignore_path):
        with open(gitignore_path) as f:
            return pathspec.PathSpec.from_lines("gitignore", f)
    return None


def _detect_languages(project_path: str) -> list[str]:
    languages = []
    entries = set(os.listdir(project_path))
    for lang, indicators in LANGUAGE_INDICATORS.items():
        if any(ind in entries for ind in indicators):
            languages.append(lang)

    # Detect Rust in src-tauri/ (Tauri desktop apps)
    if "rust" not in languages:
        tauri_cargo = os.path.join(project_path, "src-tauri", "Cargo.toml")
        if os.path.isfile(tauri_cargo):
            languages.append("rust")

    # Detect sql language from directory presence
    if "sql" not in languages:
        sql_dirs = {"prisma", "migrations", "alembic"}
        if sql_dirs & entries:
            languages.append("sql")
        else:
            # Check for .sql files at root
            for entry in entries:
                if entry.endswith(".sql"):
                    languages.append("sql")
                    break

    return languages


async def scan_project_files(
    path: str, db: Database
) -> ProjectInfo:
    """Run the file scanner and return project info for downstream scanners."""
    project_name = os.path.basename(os.path.abspath(path))
    languages = _detect_languages(path)
    has_docker = "docker" in languages
    gitignore_spec = _load_gitignore(path)

    # Create root system node
    root_node, _ = await db.find_or_create_node(NodeCreateInput(
        name=project_name,
        type=NodeType.system,
        status=NodeStatus.built,
        description=f"Project root: {project_name}",
    ))

    # Run file scanner for config files
    scanner = FileScanner(db, root_node.id, gitignore_spec)
    await scanner.scan(path)

    return ProjectInfo(
        name=project_name,
        root_id=root_node.id,
        languages=languages,
        has_docker=has_docker,
        gitignore_spec=gitignore_spec,
    )
