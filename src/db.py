"""SQLite database layer for Blueprint MCP."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

import aiosqlite

from src.models import (
    ChangelogEntry,
    Edge,
    EdgeCreateInput,
    EdgeRelationship,
    Node,
    NodeCreateInput,
    NodeType,
    NodeUpdateInput,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    parent_id TEXT,
    description TEXT,
    metadata TEXT,
    source_file TEXT,
    source_line INTEGER,
    template_origin TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (parent_id) REFERENCES nodes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relationship TEXT NOT NULL,
    label TEXT,
    metadata TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (source_id) REFERENCES nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES nodes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS changelog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,
    details TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS project_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_nodes_status ON nodes(status);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_changelog_timestamp ON changelog(timestamp);
CREATE INDEX IF NOT EXISTS idx_nodes_name_type ON nodes(name, type);

CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    node_data TEXT NOT NULL,
    edge_data TEXT NOT NULL,
    node_count INTEGER NOT NULL,
    edge_count INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS annotations (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE CASCADE,
    UNIQUE(node_id, key)
);
CREATE INDEX IF NOT EXISTS idx_annotations_node ON annotations(node_id);
CREATE INDEX IF NOT EXISTS idx_annotations_key ON annotations(key);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _json_dumps(obj: dict | None) -> str | None:
    if obj is None:
        return None
    return json.dumps(obj)


def _json_loads(text: str | None) -> dict | None:
    if text is None:
        return None
    return json.loads(text)


def _row_to_node(row: aiosqlite.Row) -> Node:
    return Node(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        status=row["status"],
        parent_id=row["parent_id"],
        description=row["description"],
        metadata=_json_loads(row["metadata"]),
        source_file=row["source_file"],
        source_line=row["source_line"],
        template_origin=row["template_origin"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_edge(row: aiosqlite.Row) -> Edge:
    return Edge(
        id=row["id"],
        source_id=row["source_id"],
        target_id=row["target_id"],
        relationship=row["relationship"],
        label=row["label"],
        metadata=_json_loads(row["metadata"]),
        status=row["status"],
        created_at=row["created_at"],
    )


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA foreign_keys=ON")
        await self.db.executescript(SCHEMA_SQL)
        await self.db.commit()

    async def close(self) -> None:
        if self.db:
            await self.db.close()

    # --- Bulk queries ---

    async def get_all_nodes(self) -> list[Node]:
        """Return all nodes as model instances."""
        cursor = await self.db.execute("SELECT * FROM nodes ORDER BY created_at")
        rows = await cursor.fetchall()
        return [_row_to_node(r) for r in rows]

    async def get_all_edges(self) -> list[Edge]:
        """Return all edges as model instances."""
        cursor = await self.db.execute("SELECT * FROM edges ORDER BY created_at")
        rows = await cursor.fetchall()
        return [_row_to_edge(r) for r in rows]

    # --- Snapshot CRUD ---

    async def create_snapshot(self, name: str, description: str | None = None) -> dict:
        snapshot_id = _new_id()
        now = _now()
        nodes = await self.get_all_nodes()
        edges = await self.get_all_edges()
        node_data = json.dumps([n.model_dump() for n in nodes])
        edge_data = json.dumps([e.model_dump() for e in edges])
        await self.db.execute(
            """INSERT INTO snapshots (id, name, description, node_data, edge_data, node_count, edge_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (snapshot_id, name, description, node_data, edge_data, len(nodes), len(edges), now),
        )
        await self.db.commit()
        return {
            "id": snapshot_id,
            "name": name,
            "description": description,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "created_at": now,
        }

    async def list_snapshots(self) -> list[dict]:
        cursor = await self.db.execute(
            "SELECT id, name, description, node_count, edge_count, created_at FROM snapshots ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "node_count": r["node_count"],
                "edge_count": r["edge_count"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    async def get_snapshot(self, snapshot_id: str) -> dict | None:
        cursor = await self.db.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "node_data": json.loads(row["node_data"]),
            "edge_data": json.loads(row["edge_data"]),
            "node_count": row["node_count"],
            "edge_count": row["edge_count"],
            "created_at": row["created_at"],
        }

    # --- Changelog ---

    async def log_change(
        self,
        action: str,
        target_type: str,
        target_id: str | None,
        details: dict | None = None,
    ) -> None:
        await self.db.execute(
            "INSERT INTO changelog (action, target_type, target_id, details, timestamp) VALUES (?, ?, ?, ?, ?)",
            (action, target_type, target_id, _json_dumps(details), _now()),
        )
        await self.db.commit()

    # --- Node CRUD ---

    async def create_node(self, inp: NodeCreateInput) -> Node:
        node_id = _new_id()
        now = _now()
        await self.db.execute(
            """INSERT INTO nodes (id, name, type, status, parent_id, description, metadata, source_file, source_line, template_origin, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                node_id,
                inp.name,
                inp.type.value,
                inp.status.value,
                inp.parent_id,
                inp.description,
                _json_dumps(inp.metadata),
                inp.source_file,
                inp.source_line,
                inp.template_origin,
                now,
                now,
            ),
        )
        await self.db.commit()
        await self.log_change(
            "node_created",
            "node",
            node_id,
            {"name": inp.name, "type": inp.type.value},
        )
        return Node(
            id=node_id,
            name=inp.name,
            type=inp.type,
            status=inp.status,
            parent_id=inp.parent_id,
            description=inp.description,
            metadata=inp.metadata,
            source_file=inp.source_file,
            source_line=inp.source_line,
            template_origin=inp.template_origin,
            created_at=now,
            updated_at=now,
        )

    async def get_node(self, node_id: str, depth: int = 1) -> Node | None:
        cursor = await self.db.execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        node = _row_to_node(row)

        # Fetch children
        if depth > 0:
            children_cursor = await self.db.execute(
                "SELECT * FROM nodes WHERE parent_id = ?", (node_id,)
            )
            children_rows = await children_cursor.fetchall()
            children = []
            for child_row in children_rows:
                if depth > 1:
                    child = await self.get_node(child_row["id"], depth - 1)
                    if child:
                        children.append(child)
                else:
                    children.append(_row_to_node(child_row))
            node.children = children if children else None

        # Fetch edges
        edge_cursor = await self.db.execute(
            "SELECT * FROM edges WHERE source_id = ? OR target_id = ?",
            (node_id, node_id),
        )
        edge_rows = await edge_cursor.fetchall()
        edges = [_row_to_edge(r) for r in edge_rows]
        node.edges = edges if edges else None

        return node

    async def update_node(self, inp: NodeUpdateInput) -> Node | None:
        # Check node exists
        existing = await self.get_node(inp.id, depth=0)
        if existing is None:
            return None

        updates: list[str] = []
        values: list = []
        changed: dict = {}

        if inp.name is not None:
            updates.append("name = ?")
            values.append(inp.name)
            changed["name"] = inp.name
        if inp.status is not None:
            updates.append("status = ?")
            values.append(inp.status.value)
            changed["status"] = inp.status.value
        if inp.description is not None:
            updates.append("description = ?")
            values.append(inp.description)
            changed["description"] = inp.description
        if inp.metadata is not None:
            # Merge with existing metadata
            merged = dict(existing.metadata or {})
            merged.update(inp.metadata)
            updates.append("metadata = ?")
            values.append(_json_dumps(merged))
            changed["metadata"] = merged
        if inp.source_file is not None:
            updates.append("source_file = ?")
            values.append(inp.source_file)
            changed["source_file"] = inp.source_file
        if inp.source_line is not None:
            updates.append("source_line = ?")
            values.append(inp.source_line)
            changed["source_line"] = inp.source_line

        if not updates:
            return existing

        now = _now()
        updates.append("updated_at = ?")
        values.append(now)
        values.append(inp.id)

        sql = f"UPDATE nodes SET {', '.join(updates)} WHERE id = ?"
        await self.db.execute(sql, values)
        await self.db.commit()
        await self.log_change("node_updated", "node", inp.id, changed)

        return await self.get_node(inp.id, depth=0)

    async def update_node_parent(self, node_id: str, parent_id: str) -> None:
        """Update a node's parent_id."""
        now = _now()
        await self.db.execute(
            "UPDATE nodes SET parent_id = ?, updated_at = ? WHERE id = ?",
            (parent_id, now, node_id),
        )
        await self.db.commit()

    # ------------------------------------------------------------------
    # Project Meta (key-value store for project-level configuration)
    # ------------------------------------------------------------------

    async def get_project_meta(self, key: str) -> str | None:
        """Get a project metadata value by key."""
        cursor = await self.db.execute(
            "SELECT value FROM project_meta WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def set_project_meta(self, key: str, value: str) -> None:
        """Set a project metadata value (insert or replace)."""
        await self.db.execute(
            "INSERT OR REPLACE INTO project_meta (key, value) VALUES (?, ?)",
            (key, value),
        )
        await self.db.commit()

    async def get_all_project_meta(self) -> dict[str, str]:
        """Get all project metadata as a dict."""
        cursor = await self.db.execute("SELECT key, value FROM project_meta")
        rows = await cursor.fetchall()
        return {row[0]: row[1] for row in rows}

    async def delete_node(self, node_id: str) -> bool:
        # Fetch for changelog before deleting
        cursor = await self.db.execute(
            "SELECT name, type FROM nodes WHERE id = ?", (node_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return False

        await self.db.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        await self.db.commit()
        await self.log_change(
            "node_deleted",
            "node",
            node_id,
            {"name": row["name"], "type": row["type"]},
        )
        return True

    # --- Dedup helpers (scanner) ---

    async def find_node(
        self, name: str, node_type: str, parent_id: str | None = None
    ) -> Node | None:
        if parent_id:
            cursor = await self.db.execute(
                "SELECT * FROM nodes WHERE name = ? AND type = ? AND parent_id = ?",
                (name, node_type, parent_id),
            )
        else:
            cursor = await self.db.execute(
                "SELECT * FROM nodes WHERE name = ? AND type = ? AND parent_id IS NULL",
                (name, node_type),
            )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_node(row)

    async def find_or_create_node(
        self, inp: NodeCreateInput
    ) -> tuple[Node, str]:
        existing = await self.find_node(
            inp.name, inp.type.value, inp.parent_id
        )
        # Fallback: if not found by parent_id, try matching by source_file
        # (handles nodes whose parent was changed by directory grouping)
        if not existing and inp.source_file:
            cursor = await self.db.execute(
                "SELECT * FROM nodes WHERE name = ? AND type = ? AND source_file = ?",
                (inp.name, inp.type.value, inp.source_file),
            )
            row = await cursor.fetchone()
            if row:
                existing = _row_to_node(row)
        if existing:
            # Update metadata / source info if provided
            updates = NodeUpdateInput(id=existing.id)
            changed = False
            if inp.metadata:
                updates.metadata = inp.metadata
                changed = True
            if inp.source_file:
                updates.source_file = inp.source_file
                changed = True
            if inp.source_line is not None:
                updates.source_line = inp.source_line
                changed = True
            if inp.description and not existing.description:
                updates.description = inp.description
                changed = True
            if changed:
                node = await self.update_node(updates)
                return node, "updated"
            return existing, "existing"
        node = await self.create_node(inp)
        return node, "created"

    async def find_or_create_edge(
        self, inp: EdgeCreateInput
    ) -> tuple[Edge, str]:
        cursor = await self.db.execute(
            "SELECT * FROM edges WHERE source_id = ? AND target_id = ? AND relationship = ?",
            (inp.source_id, inp.target_id, inp.relationship.value),
        )
        row = await cursor.fetchone()
        if row:
            return _row_to_edge(row), "existing"
        edge = await self.create_edge(inp)
        return edge, "created"

    # --- Changelog query ---

    async def get_changes(self, since: str) -> list[ChangelogEntry]:
        cursor = await self.db.execute(
            "SELECT * FROM changelog WHERE timestamp >= ? ORDER BY timestamp ASC",
            (since,),
        )
        rows = await cursor.fetchall()
        return [
            ChangelogEntry(
                id=r["id"],
                action=r["action"],
                target_type=r["target_type"],
                target_id=r["target_id"],
                details=_json_loads(r["details"]),
                timestamp=r["timestamp"],
            )
            for r in rows
        ]

    # --- Edge CRUD ---

    async def create_edge(self, inp: EdgeCreateInput) -> Edge:
        # Validate endpoints exist
        for label, nid in [("source", inp.source_id), ("target", inp.target_id)]:
            cursor = await self.db.execute(
                "SELECT id FROM nodes WHERE id = ?", (nid,)
            )
            if await cursor.fetchone() is None:
                raise ValueError(
                    f"Cannot create edge: {label} node '{nid}' does not exist"
                )

        edge_id = _new_id()
        now = _now()
        await self.db.execute(
            """INSERT INTO edges (id, source_id, target_id, relationship, label, metadata, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                edge_id,
                inp.source_id,
                inp.target_id,
                inp.relationship.value,
                inp.label,
                _json_dumps(inp.metadata),
                inp.status.value,
                now,
            ),
        )
        await self.db.commit()
        await self.log_change(
            "edge_created",
            "edge",
            edge_id,
            {
                "source_id": inp.source_id,
                "target_id": inp.target_id,
                "relationship": inp.relationship.value,
            },
        )
        return Edge(
            id=edge_id,
            source_id=inp.source_id,
            target_id=inp.target_id,
            relationship=inp.relationship,
            label=inp.label,
            metadata=inp.metadata,
            status=inp.status,
            created_at=now,
        )

    async def get_edge(self, edge_id: str) -> Edge | None:
        cursor = await self.db.execute(
            "SELECT * FROM edges WHERE id = ?", (edge_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_edge(row)

    async def delete_edge(self, edge_id: str) -> bool:
        cursor = await self.db.execute(
            "SELECT source_id, target_id, relationship FROM edges WHERE id = ?",
            (edge_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return False

        await self.db.execute("DELETE FROM edges WHERE id = ?", (edge_id,))
        await self.db.commit()
        await self.log_change(
            "edge_deleted",
            "edge",
            edge_id,
            {
                "source_id": row["source_id"],
                "target_id": row["target_id"],
                "relationship": row["relationship"],
            },
        )
        return True

    # --- Blueprint queries ---

    async def get_blueprint(
        self,
        status_filter: str | None = None,
        type_filter: str | None = None,
        root_only: bool = False,
    ) -> dict:
        conditions: list[str] = []
        params: list = []

        if status_filter:
            conditions.append("status = ?")
            params.append(status_filter)
        if type_filter:
            conditions.append("type = ?")
            params.append(type_filter)
        if root_only:
            conditions.append("parent_id IS NULL")

        where = ""
        if conditions:
            where = " WHERE " + " AND ".join(conditions)

        node_cursor = await self.db.execute(f"SELECT * FROM nodes{where}", params)
        node_rows = await node_cursor.fetchall()
        nodes = [_row_to_node(r) for r in node_rows]

        # Get node IDs for edge filtering
        node_ids = {n.id for n in nodes}

        edge_cursor = await self.db.execute("SELECT * FROM edges")
        edge_rows = await edge_cursor.fetchall()
        edges = [
            _row_to_edge(r)
            for r in edge_rows
            if r["source_id"] in node_ids and r["target_id"] in node_ids
        ]

        return {
            "nodes": [n.model_dump() for n in nodes],
            "edges": [e.model_dump() for e in edges],
            "summary": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
            },
        }

    async def get_blueprint_summary(self) -> dict:
        # Counts by type
        type_cursor = await self.db.execute(
            "SELECT type, COUNT(*) as cnt FROM nodes GROUP BY type"
        )
        type_rows = await type_cursor.fetchall()
        counts_by_type = {r["type"]: r["cnt"] for r in type_rows}

        # Counts by status
        status_cursor = await self.db.execute(
            "SELECT status, COUNT(*) as cnt FROM nodes GROUP BY status"
        )
        status_rows = await status_cursor.fetchall()
        counts_by_status = {r["status"]: r["cnt"] for r in status_rows}

        # Totals
        node_count_cursor = await self.db.execute("SELECT COUNT(*) as cnt FROM nodes")
        node_count = (await node_count_cursor.fetchone())["cnt"]

        edge_count_cursor = await self.db.execute("SELECT COUNT(*) as cnt FROM edges")
        edge_count = (await edge_count_cursor.fetchone())["cnt"]

        # Recent changes
        changelog_cursor = await self.db.execute(
            "SELECT * FROM changelog ORDER BY timestamp DESC LIMIT 20"
        )
        changelog_rows = await changelog_cursor.fetchall()
        recent_changes = [
            ChangelogEntry(
                id=r["id"],
                action=r["action"],
                target_type=r["target_type"],
                target_id=r["target_id"],
                details=_json_loads(r["details"]),
                timestamp=r["timestamp"],
            ).model_dump()
            for r in changelog_rows
        ]

        return {
            "counts_by_type": counts_by_type,
            "counts_by_status": counts_by_status,
            "total_nodes": node_count,
            "total_edges": edge_count,
            "recent_changes": recent_changes,
        }


    # --- Annotation CRUD ---

    async def upsert_annotation(self, node_id: str, key: str, value: str) -> dict:
        """Insert or update an annotation on a node."""
        # Verify node exists
        cursor = await self.db.execute("SELECT id FROM nodes WHERE id = ?", (node_id,))
        if await cursor.fetchone() is None:
            raise ValueError(f"Node '{node_id}' not found")

        ann_id = _new_id()
        now = _now()
        await self.db.execute(
            """INSERT INTO annotations (id, node_id, key, value, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(node_id, key) DO UPDATE SET value = excluded.value, created_at = excluded.created_at""",
            (ann_id, node_id, key, value, now),
        )
        await self.db.commit()
        return {"node_id": node_id, "key": key, "value": value}

    async def get_annotations(self, node_id: str | None = None, key: str | None = None) -> list[dict]:
        """Get annotations filtered by node_id and/or key."""
        conditions = []
        params = []
        if node_id:
            conditions.append("node_id = ?")
            params.append(node_id)
        if key:
            conditions.append("key = ?")
            params.append(key)

        where = ""
        if conditions:
            where = " WHERE " + " AND ".join(conditions)

        cursor = await self.db.execute(f"SELECT * FROM annotations{where}", params)
        rows = await cursor.fetchall()
        return [
            {"id": r["id"], "node_id": r["node_id"], "key": r["key"], "value": r["value"], "created_at": r["created_at"]}
            for r in rows
        ]

    async def delete_annotation(self, node_id: str, key: str) -> bool:
        """Delete a specific annotation."""
        cursor = await self.db.execute(
            "DELETE FROM annotations WHERE node_id = ? AND key = ?", (node_id, key)
        )
        await self.db.commit()
        return cursor.rowcount > 0


async def init_db(db_path: str | None = None) -> Database:
    if db_path is None:
        db_path = os.environ.get("BLUEPRINT_DB", ".blueprint.db")
    db = Database(db_path)
    await db.connect()
    return db
