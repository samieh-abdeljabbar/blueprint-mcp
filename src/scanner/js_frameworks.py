"""Next.js, Nuxt, and Vue file-convention detection for JS/TS scanner."""

from __future__ import annotations

import os
import re


def detect_nextjs_route(rel_path: str) -> dict | None:
    """Detect Next.js App Router or Pages Router routes from file path.

    Returns route info dict or None if not a route file.
    """
    parts = rel_path.replace(os.sep, "/").split("/")

    # App Router: app/**/page.tsx or app/**/route.ts
    if parts[0] == "app":
        basename = os.path.basename(rel_path)
        name_no_ext = os.path.splitext(basename)[0]

        if name_no_ext == "page":
            route_path = _app_dir_to_route(parts[1:])
            return {
                "type": "page",
                "route": route_path,
                "framework": "nextjs",
                "router": "app",
            }

        if name_no_ext == "route":
            route_path = _app_dir_to_route(parts[1:])
            return {
                "type": "api",
                "route": route_path,
                "framework": "nextjs",
                "router": "app",
                "api": True,
            }

    # Pages Router: pages/**/*.tsx (not _app, _document, api)
    if parts[0] == "pages":
        basename = os.path.basename(rel_path)
        name_no_ext = os.path.splitext(basename)[0]

        # Skip special Next.js pages
        if name_no_ext.startswith("_"):
            return None

        # pages/api/* are API routes
        if len(parts) > 1 and parts[1] == "api":
            route_path = _pages_dir_to_route(parts[1:])
            return {
                "type": "api",
                "route": route_path,
                "framework": "nextjs",
                "router": "pages",
                "api": True,
            }

        route_path = _pages_dir_to_route(parts[1:])
        return {
            "type": "page",
            "route": route_path,
            "framework": "nextjs",
            "router": "pages",
        }

    return None


def detect_nextjs_layout(rel_path: str) -> dict | None:
    """Detect Next.js layout files (app/**/layout.tsx)."""
    parts = rel_path.replace(os.sep, "/").split("/")
    if parts[0] != "app":
        return None

    basename = os.path.basename(rel_path)
    name_no_ext = os.path.splitext(basename)[0]

    if name_no_ext == "layout":
        route_path = _app_dir_to_route(parts[1:])
        layout_name = "RootLayout" if route_path == "/" else f"Layout:{route_path}"
        return {
            "name": layout_name,
            "route": route_path,
            "framework": "nextjs",
            "layout": True,
        }

    return None


def detect_nextjs_middleware(rel_path: str) -> bool:
    """Check if file is Next.js middleware (middleware.ts/js at root)."""
    parts = rel_path.replace(os.sep, "/").split("/")
    if len(parts) != 1:
        return False
    name_no_ext = os.path.splitext(parts[0])[0]
    return name_no_ext == "middleware"


def detect_nuxt_route(rel_path: str) -> dict | None:
    """Detect Nuxt pages directory routes."""
    parts = rel_path.replace(os.sep, "/").split("/")
    if parts[0] != "pages" or not rel_path.endswith(".vue"):
        return None

    route_path = _pages_dir_to_route(parts[1:])
    return {
        "type": "page",
        "route": route_path,
        "framework": "nuxt",
    }


def detect_vue_sfc(rel_path: str) -> dict | None:
    """Detect Vue Single File Components (.vue files)."""
    if not rel_path.endswith(".vue"):
        return None

    basename = os.path.basename(rel_path)
    name_no_ext = os.path.splitext(basename)[0]
    # Convert to PascalCase
    component_name = _to_pascal_case(name_no_ext)
    return {
        "name": component_name,
        "framework": "vue",
        "component": True,
    }


def _app_dir_to_route(path_parts: list[str]) -> str:
    """Convert app router path parts to route string.

    ['page.tsx'] -> '/'
    ['dashboard', 'page.tsx'] -> '/dashboard'
    ['dashboard', '[id]', 'page.tsx'] -> '/dashboard/[id]'
    """
    # Remove the filename (page.tsx, route.ts, layout.tsx)
    dir_parts = path_parts[:-1]
    if not dir_parts:
        return "/"

    # Filter out route groups (parenthesized segments)
    dir_parts = [p for p in dir_parts if not (p.startswith("(") and p.endswith(")"))]
    if not dir_parts:
        return "/"

    return "/" + "/".join(dir_parts)


def _pages_dir_to_route(path_parts: list[str]) -> str:
    """Convert pages router path parts to route string.

    ['index.tsx'] -> '/'
    ['about.tsx'] -> '/about'
    ['users', '[id].tsx'] -> '/users/[id]'
    """
    # Remove extension from last part
    parts = list(path_parts)
    if parts:
        parts[-1] = os.path.splitext(parts[-1])[0]

    # Remove 'index' at end
    if parts and parts[-1] == "index":
        parts = parts[:-1]

    if not parts:
        return "/"

    return "/" + "/".join(parts)


def _to_pascal_case(name: str) -> str:
    """Convert kebab-case or snake_case to PascalCase."""
    return re.sub(r'(?:^|[-_])(\w)', lambda m: m.group(1).upper(), name)
