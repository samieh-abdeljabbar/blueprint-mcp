"""Multi-project linking — connect nodes across separate project blueprints."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import aiosqlite


PROJECT_LINKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS project_links (
    id TEXT PRIMARY KEY,
    source_project TEXT NOT NULL,
    source_node_name TEXT NOT NULL,
    target_project TEXT NOT NULL,
    target_node_name TEXT NOT NULL,
    relationship TEXT NOT NULL,
    label TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_project_links_source ON project_links(source_project);
CREATE INDEX IF NOT EXISTS idx_project_links_target ON project_links(target_project);
"""


async def _get_meta_db(meta_path: str | None = None) -> aiosqlite.Connection:
    if meta_path is None:
        meta_dir = os.path.expanduser("~/.blueprint")
        os.makedirs(meta_dir, exist_ok=True)
        meta_path = os.path.join(meta_dir, "meta.db")
    conn = await aiosqlite.connect(meta_path)
    conn.row_factory = aiosqlite.Row
    await conn.executescript(PROJECT_LINKS_SCHEMA)
    await conn.commit()
    return conn


async def link_projects(
    source_project: str,
    source_node: str,
    target_project: str,
    target_node: str,
    relationship: str,
    label: str | None = None,
    meta_path: str | None = None,
) -> dict:
    conn = await _get_meta_db(meta_path)
    try:
        link_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            """INSERT INTO project_links (id, source_project, source_node_name, target_project, target_node_name, relationship, label, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (link_id, source_project, source_node, target_project, target_node, relationship, label, now),
        )
        await conn.commit()
        return {
            "id": link_id,
            "source": f"{source_project} → {source_node}",
            "target": f"{target_project} → {target_node}",
            "relationship": relationship,
        }
    finally:
        await conn.close()


async def get_project_map(
    project: str | None = None,
    meta_path: str | None = None,
) -> dict:
    conn = await _get_meta_db(meta_path)
    try:
        if project:
            cursor = await conn.execute(
                "SELECT * FROM project_links WHERE source_project = ? OR target_project = ? ORDER BY created_at",
                (project, project),
            )
        else:
            cursor = await conn.execute("SELECT * FROM project_links ORDER BY created_at")
        rows = await cursor.fetchall()

        projects = set()
        links = []
        for r in rows:
            projects.add(r["source_project"])
            projects.add(r["target_project"])
            links.append({
                "id": r["id"],
                "from": f"{r['source_project']} → {r['source_node_name']}",
                "to": f"{r['target_project']} → {r['target_node_name']}",
                "relationship": r["relationship"],
                "label": r["label"],
            })

        return {
            "projects": sorted(projects),
            "links": links,
            "total_links": len(links),
        }
    finally:
        await conn.close()
