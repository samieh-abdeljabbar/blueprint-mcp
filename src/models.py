"""Pydantic v2 models for Blueprint MCP nodes, edges, and changelog."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class NodeType(str, Enum):
    system = "system"
    service = "service"
    database = "database"
    table = "table"
    column = "column"
    api = "api"
    route = "route"
    function = "function"
    module = "module"
    container = "container"
    queue = "queue"
    cache = "cache"
    external = "external"
    config = "config"
    file = "file"


class NodeStatus(str, Enum):
    planned = "planned"
    in_progress = "in_progress"
    built = "built"
    broken = "broken"
    deprecated = "deprecated"


class EdgeRelationship(str, Enum):
    connects_to = "connects_to"
    reads_from = "reads_from"
    writes_to = "writes_to"
    depends_on = "depends_on"
    authenticates = "authenticates"
    calls = "calls"
    inherits = "inherits"
    contains = "contains"
    exposes = "exposes"


class EdgeStatus(str, Enum):
    active = "active"
    broken = "broken"
    planned = "planned"


# --- Output models ---


class Edge(BaseModel):
    id: str
    source_id: str
    target_id: str
    relationship: EdgeRelationship
    label: str | None = None
    metadata: dict | None = None
    status: EdgeStatus = EdgeStatus.active
    created_at: str = ""


class Node(BaseModel):
    id: str
    name: str
    type: NodeType
    status: NodeStatus = NodeStatus.planned
    parent_id: str | None = None
    description: str | None = None
    metadata: dict | None = None
    source_file: str | None = None
    source_line: int | None = None
    template_origin: str | None = None
    created_at: str = ""
    updated_at: str = ""
    children: list[Node] | None = None
    edges: list[Edge] | None = None


class ChangelogEntry(BaseModel):
    id: int
    action: str
    target_type: str
    target_id: str | None = None
    details: dict | None = None
    timestamp: str = ""


# --- Input models ---


class NodeCreateInput(BaseModel):
    name: str
    type: NodeType
    status: NodeStatus = NodeStatus.built
    parent_id: str | None = None
    description: str | None = None
    metadata: dict | None = None
    source_file: str | None = None
    source_line: int | None = None
    template_origin: str | None = None


class NodeUpdateInput(BaseModel):
    id: str
    name: str | None = None
    status: NodeStatus | None = None
    description: str | None = None
    metadata: dict | None = None
    source_file: str | None = None
    source_line: int | None = None


class EdgeCreateInput(BaseModel):
    source_id: str
    target_id: str
    relationship: EdgeRelationship
    label: str | None = None
    metadata: dict | None = None
    status: EdgeStatus = EdgeStatus.active


# --- Template models ---


class TemplateNodeDef(BaseModel):
    ref: str
    name: str
    type: NodeType
    parent_ref: str | None = None
    description: str | None = None
    metadata: dict | None = None


class TemplateEdgeDef(BaseModel):
    source_ref: str
    target_ref: str
    relationship: EdgeRelationship
    label: str | None = None
    metadata: dict | None = None


class Template(BaseModel):
    name: str
    display_name: str
    description: str
    nodes: list[TemplateNodeDef]
    edges: list[TemplateEdgeDef]


# --- Scanner models ---


class ScanError(BaseModel):
    file: str
    line: int | None = None
    message: str


class ScanResult(BaseModel):
    scanner_name: str
    nodes_created: int = 0
    nodes_updated: int = 0
    edges_created: int = 0
    errors: list[ScanError] = []
    files_scanned: int = 0
    duration_ms: float = 0.0


# --- Analyzer models ---


class IssueSeverity(str, Enum):
    critical = "critical"
    warning = "warning"
    info = "info"


class Issue(BaseModel):
    severity: IssueSeverity
    type: str
    message: str
    node_ids: list[str]
    suggestion: str
