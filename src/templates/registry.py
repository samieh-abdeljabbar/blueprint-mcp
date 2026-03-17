"""Template registry — loading, validation, and application of project templates."""

from __future__ import annotations

import json
from pathlib import Path

from src.db import Database
from src.models import (
    EdgeCreateInput,
    EdgeStatus,
    NodeCreateInput,
    NodeStatus,
    Template,
)

_TEMPLATE_DIR = Path(__file__).parent
_cache: dict[str, Template] | None = None


def _validate_template(t: Template) -> None:
    """Validate ref uniqueness, parent ordering, and edge refs."""
    refs_seen: list[str] = []
    ref_set: set[str] = set()

    # Check unique refs
    for node in t.nodes:
        if node.ref in ref_set:
            raise ValueError(
                f"Template '{t.name}': duplicate ref '{node.ref}'"
            )
        ref_set.add(node.ref)
        refs_seen.append(node.ref)

    # Check parent_refs valid and listed before children
    for node in t.nodes:
        if node.parent_ref is not None:
            if node.parent_ref not in ref_set:
                raise ValueError(
                    f"Template '{t.name}': invalid parent_ref '{node.parent_ref}'"
                )
            if refs_seen.index(node.parent_ref) >= refs_seen.index(node.ref):
                raise ValueError(
                    f"Template '{t.name}': parent '{node.parent_ref}' must be listed before child '{node.ref}'"
                )

    # At least one root node
    root_nodes = [n for n in t.nodes if n.parent_ref is None]
    if not root_nodes:
        raise ValueError(f"Template '{t.name}': must have at least one root node")

    # Check edge refs
    for edge in t.edges:
        if edge.source_ref not in ref_set:
            raise ValueError(
                f"Template '{t.name}': invalid edge source_ref '{edge.source_ref}'"
            )
        if edge.target_ref not in ref_set:
            raise ValueError(
                f"Template '{t.name}': invalid edge target_ref '{edge.target_ref}'"
            )


def _load_templates() -> dict[str, Template]:
    """Load and validate all JSON templates from the template directory."""
    templates: dict[str, Template] = {}
    for path in sorted(_TEMPLATE_DIR.glob("*.json")):
        with open(path) as f:
            data = json.load(f)
        t = Template(**data)
        _validate_template(t)
        templates[t.name] = t
    return templates


def get_templates() -> dict[str, Template]:
    """Lazy-load and cache all templates."""
    global _cache
    if _cache is None:
        _cache = _load_templates()
    return _cache


def list_templates() -> list[dict]:
    """Return summary info for each template."""
    templates = get_templates()
    result = []
    for t in templates.values():
        node_types = sorted({n.type.value for n in t.nodes})
        result.append(
            {
                "name": t.name,
                "display_name": t.display_name,
                "description": t.description,
                "node_count": len(t.nodes),
                "edge_count": len(t.edges),
                "node_types": node_types,
            }
        )
    return result


async def apply_template(
    db: Database, name: str, project_name: str = "My Project"
) -> dict:
    """Apply a template: create all nodes and edges in the database."""
    templates = get_templates()
    if name not in templates:
        raise ValueError(f"Template '{name}' not found")

    t = templates[name]
    ref_map: dict[str, str] = {}

    # Create nodes in order (parents before children)
    for node_def in t.nodes:
        node_name = node_def.name.replace("{{project_name}}", project_name)
        parent_id = ref_map.get(node_def.parent_ref) if node_def.parent_ref else None

        inp = NodeCreateInput(
            name=node_name,
            type=node_def.type,
            status=NodeStatus.planned,
            parent_id=parent_id,
            description=node_def.description,
            metadata=node_def.metadata,
            template_origin=name,
        )
        node = await db.create_node(inp)
        ref_map[node_def.ref] = node.id

    # Create edges
    edges_created = 0
    for edge_def in t.edges:
        source_id = ref_map[edge_def.source_ref]
        target_id = ref_map[edge_def.target_ref]
        inp = EdgeCreateInput(
            source_id=source_id,
            target_id=target_id,
            relationship=edge_def.relationship,
            label=edge_def.label,
            metadata=edge_def.metadata,
            status=EdgeStatus.planned,
        )
        await db.create_edge(inp)
        edges_created += 1

    # Log to changelog
    await db.log_change(
        "template_applied",
        "template",
        None,
        {"template": name, "project_name": project_name},
    )

    return {
        "template": name,
        "project_name": project_name,
        "nodes_created": len(ref_map),
        "edges_created": edges_created,
        "ref_map": ref_map,
    }
