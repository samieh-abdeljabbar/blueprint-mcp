"""Import path resolution and edge creation for JS/TS scanner."""

from __future__ import annotations

import os
import re

from src.scanner.js_patterns import (
    CJS_REQUIRE,
    DYNAMIC_IMPORT,
    ES6_IMPORT,
    JS_EXTENSIONS,
    RESOLVE_EXTENSIONS,
)


def extract_import_paths(source: str) -> list[str]:
    """Extract all import paths from JS/TS source code.

    Returns only relative paths (starting with ./ or ../).
    """
    paths: list[str] = []

    for pattern in (ES6_IMPORT, CJS_REQUIRE, DYNAMIC_IMPORT):
        for match in pattern.finditer(source):
            path = match.group(1)
            if path.startswith("."):
                paths.append(path)

    return paths


def resolve_import_path(
    import_path: str,
    importing_file: str,
    project_root: str,
) -> str | None:
    """Resolve a relative import path to an actual file in the project.

    Args:
        import_path: The import string (e.g., './components/Header')
        importing_file: Absolute path of the file containing the import
        project_root: Absolute path to the project root

    Returns:
        Relative path to the resolved file, or None if not found.
    """
    importing_dir = os.path.dirname(importing_file)
    base = os.path.normpath(os.path.join(importing_dir, import_path))

    # If path already has an extension and file exists
    if os.path.splitext(base)[1] and os.path.isfile(base):
        return os.path.relpath(base, project_root)

    # Try each extension
    for ext in RESOLVE_EXTENSIONS:
        candidate = base + ext
        if os.path.isfile(candidate):
            return os.path.relpath(candidate, project_root)

    return None


def module_name_from_path(rel_path: str) -> str:
    """Derive a module/component name from a relative file path.

    'components/Header.tsx' -> 'Header'
    'src/hooks/useAuth.ts' -> 'useAuth'
    'src/hooks/index.ts' -> 'hooks'
    """
    basename = os.path.basename(rel_path)
    name_no_ext = os.path.splitext(basename)[0]

    # index files use the parent directory name
    if name_no_ext == "index":
        parent = os.path.basename(os.path.dirname(rel_path))
        return parent if parent else name_no_ext

    return name_no_ext
