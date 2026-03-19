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
    submodule = "submodule"
    class_def = "class_def"
    struct = "struct"
    protocol = "protocol"
    view = "view"
    test = "test"
    script = "script"
    middleware = "middleware"
    migration = "migration"
    webhook = "webhook"
    worker = "worker"
    model = "model"
    schema = "schema"
    enum_def = "enum_def"
    util = "util"


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
    observes = "observes"
    creates = "creates"
    produces = "produces"
    consumes = "consumes"
    delegates = "delegates"
    controls = "controls"
    uses = "uses"
    updates = "updates"
    implements = "implements"
    emits = "emits"


class EdgeStatus(str, Enum):
    active = "active"
    broken = "broken"
    planned = "planned"


# --- Description dictionaries ---

NODE_TYPE_DESCRIPTIONS: dict[str, str] = {
    "system": "Top-level container representing the entire application or project",
    "service": "A running process or microservice that handles business logic",
    "database": "Persistent data store such as PostgreSQL, MySQL, or MongoDB",
    "table": "A structured collection of rows within a database",
    "column": "A single field or attribute within a database table",
    "api": "An interface exposing functionality over HTTP or another protocol",
    "route": "A specific URL path mapped to a handler within an API",
    "function": "A callable unit of logic that performs a single task",
    "module": "A file or package grouping related code together",
    "container": "A deployment unit such as a Docker container or pod",
    "queue": "An async message buffer decoupling producers from consumers",
    "cache": "A fast-access temporary store for frequently read data",
    "external": "A third-party system or service outside your control",
    "config": "Configuration file or environment settings",
    "file": "A general-purpose source or data file in the project",
    "submodule": "A nested repository or vendored dependency",
    "class_def": "An object-oriented class definition with methods and state",
    "struct": "A lightweight value type grouping related fields together",
    "protocol": "An interface or trait defining a contract for implementors",
    "view": "A UI component or template that renders visible output",
    "test": "An automated test verifying correctness of other components",
    "script": "A standalone executable file for tasks like migrations or CLI",
    "middleware": "Request processing layer that intercepts calls before handlers",
    "migration": "A versioned database schema change applied in sequence",
    "webhook": "An HTTP callback triggered by an external event",
    "worker": "A background process consuming tasks from a queue",
    "model": "A data structure representing a domain entity or DTO",
    "schema": "A formal definition of data shape used for validation",
    "enum_def": "A fixed set of named constants for type-safe value selection",
    "util": "A shared helper module providing common utility functions",
}

NODE_STATUS_DESCRIPTIONS: dict[str, str] = {
    "planned": "Designed but not yet implemented",
    "in_progress": "Currently being built or modified",
    "built": "Fully implemented and operational",
    "broken": "Exists but is failing or non-functional",
    "deprecated": "Scheduled for removal — avoid new dependencies",
}

EDGE_RELATIONSHIP_DESCRIPTIONS: dict[str, str] = {
    "connects_to": "General connection between components",
    "reads_from": "Reads data from this source (database, cache, file)",
    "writes_to": "Writes or persists data to this target",
    "depends_on": "Requires this to function -- cannot work without it",
    "authenticates": "Handles auth verification through this service",
    "calls": "Directly invokes functions or methods on this target",
    "inherits": "Extends or subclasses this component",
    "contains": "Parent-child: this is nested inside or owned by",
    "exposes": "Makes functionality available externally (API, endpoint)",
    "observes": "Watches for changes or events from this source",
    "creates": "Instantiates or constructs instances of this target",
    "produces": "Generates output consumed by downstream components",
    "consumes": "Receives and processes input from this source",
    "delegates": "Forwards responsibility to this target to handle",
    "controls": "Manages lifecycle or behavior of this target",
    "uses": "Utilizes functionality from this target as a dependency",
    "updates": "Modifies state or data in this target",
    "implements": "Provides the concrete implementation of this interface",
    "emits": "Sends events or signals that others can listen to",
}


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


# --- Questions models ---


class ProjectQuestion(BaseModel):
    id: str
    category: str
    severity: str
    question: str
    context: str
    fix_prompt: str
    learn_more: str
    related_nodes: list[str] = []
    highlight_nodes: list[str] = []


# --- Flow models ---


class FlowGap(BaseModel):
    type: str
    node_id: str
    node_name: str
    message: str
    severity: str = "warning"


class FlowStep(BaseModel):
    step: int
    node_id: str
    node_name: str
    node_type: str
    relationship: str | None = None
    edge_label: str | None = None
    branches: int = 0
    gaps: list[FlowGap] = []
    is_cycle: bool = False


class EntryPoint(BaseModel):
    node_id: str
    node_name: str
    node_type: str
    description: str | None = None
    connections_out: int = 0
    suggested_trigger: str = ""
