"""Import path resolution and edge creation for JS/TS scanner."""

from __future__ import annotations

import json
import os
import re

from src.scanner.js_patterns import (
    CJS_REQUIRE,
    DYNAMIC_IMPORT,
    ES6_IMPORT,
    JS_EXTENSIONS,
    REEXPORT_ALL,
    REEXPORT_NAMED,
    RESOLVE_EXTENSIONS,
)


def _strip_jsonc(text: str) -> str:
    """Strip // and /* */ comments from JSONC, respecting string boundaries."""
    result: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        # String literal — copy verbatim, handling escapes
        if ch == '"':
            result.append(ch)
            i += 1
            while i < n and text[i] != '"':
                if text[i] == '\\':
                    result.append(text[i])
                    i += 1
                    if i < n:
                        result.append(text[i])
                        i += 1
                else:
                    result.append(text[i])
                    i += 1
            if i < n:  # closing quote
                result.append(text[i])
                i += 1
        # Line comment
        elif ch == '/' and i + 1 < n and text[i + 1] == '/':
            i += 2
            while i < n and text[i] != '\n':
                i += 1
        # Block comment
        elif ch == '/' and i + 1 < n and text[i + 1] == '*':
            i += 2
            while i < n and not (text[i] == '*' and i + 1 < n and text[i + 1] == '/'):
                i += 1
            i += 2  # skip closing */
        else:
            result.append(ch)
            i += 1
    # Strip trailing commas before } or ]
    return re.sub(r',(\s*[}\]])', r'\1', ''.join(result))


def parse_path_aliases(project_root: str) -> dict[str, str]:
    """Read tsconfig.json/jsconfig.json paths -> {prefix: absolute_dir}."""
    for config_name in ('tsconfig.json', 'jsconfig.json'):
        config_path = os.path.join(project_root, config_name)
        if not os.path.isfile(config_path):
            continue
        try:
            with open(config_path) as f:
                raw = f.read()
            data = json.loads(_strip_jsonc(raw))
            compiler = data.get('compilerOptions', {})
            base_url = compiler.get('baseUrl', '.')
            base_dir = os.path.normpath(os.path.join(project_root, base_url))
            paths = compiler.get('paths', {})
            aliases: dict[str, str] = {}
            for pattern, targets in paths.items():
                prefix = pattern.rstrip('*').rstrip('/')
                if targets:
                    target = targets[0].rstrip('*').rstrip('/')
                    aliases[prefix] = os.path.normpath(os.path.join(base_dir, target))
            return aliases
        except Exception:
            return {}
    return {}


def resolve_alias_import(
    import_path: str, project_root: str, aliases: dict[str, str]
) -> str | None:
    """Resolve an alias import like '@/lib/utils' to a file path."""
    for prefix, target_dir in aliases.items():
        clean_prefix = prefix.rstrip('/')
        if import_path == clean_prefix or import_path.startswith(clean_prefix + '/'):
            remainder = import_path[len(clean_prefix):].lstrip('/')
            base = os.path.join(target_dir, remainder) if remainder else target_dir
            # If path already has an extension and file exists
            if os.path.splitext(base)[1] and os.path.isfile(base):
                return os.path.relpath(base, project_root)
            for ext in RESOLVE_EXTENSIONS:
                candidate = base + ext
                if os.path.isfile(candidate):
                    return os.path.relpath(candidate, project_root)
    return None


def extract_import_paths(
    source: str, aliases: dict[str, str] | None = None
) -> list[str]:
    """Extract all import paths from JS/TS source code.

    Returns relative paths (starting with ./ or ../) and alias-prefixed paths.
    """
    paths: list[str] = []

    for pattern in (ES6_IMPORT, CJS_REQUIRE, DYNAMIC_IMPORT, REEXPORT_NAMED, REEXPORT_ALL):
        for match in pattern.finditer(source):
            path = match.group(1)
            if path.startswith("."):
                paths.append(path)
            elif aliases:
                for prefix in aliases:
                    clean = prefix.rstrip('/')
                    if path == clean or path.startswith(clean + '/'):
                        paths.append(path)
                        break

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
