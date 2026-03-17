# Blueprint MCP — Claude Code Plan Mode Prompt

## Project Overview

Build **Blueprint MCP**, a Model Context Protocol server that acts as a living architectural map of any software project. It tracks every component, connection, database, API route, and service — updating in real-time as Claude Code builds. It also provides starter templates for common project types so developers can see what needs to be built before a single line of code is written.

Think of it as a project's nervous system — it knows what exists, what's planned, what's connected, and what's broken.

---

## Architecture

```
blueprint-mcp/
├── CLAUDE.md                     # Claude Code project instructions
├── README.md                     # Project documentation
├── pyproject.toml                # Python project config (uv/pip)
├── requirements.txt              # Dependencies
├── src/
│   ├── __init__.py
│   ├── server.py                 # FastMCP server entry point
│   ├── db.py                     # SQLite database layer
│   ├── models.py                 # Pydantic models for nodes, edges, metadata
│   ├── scanner/
│   │   ├── __init__.py
│   │   ├── base.py               # Base scanner interface
│   │   ├── python_scanner.py     # Python project scanner (FastAPI, Django, Flask)
│   │   ├── javascript_scanner.py # JS/TS project scanner (React, Next, Express)
│   │   ├── database_scanner.py   # SQL/ORM schema scanner
│   │   ├── docker_scanner.py     # Docker/docker-compose scanner
│   │   └── file_scanner.py       # Generic file tree scanner
│   ├── templates/
│   │   ├── __init__.py
│   │   ├── registry.py           # Template registry and loader
│   │   ├── saas.json             # SaaS app template
│   │   ├── api_service.json      # API microservice template
│   │   ├── fullstack.json        # Full-stack web app template
│   │   ├── data_pipeline.json    # Data/ETL pipeline template
│   │   ├── multi_entity_business.json  # Multi-location business template
│   │   └── desktop_app.json      # Tauri/Electron desktop app template
│   ├── analyzer.py               # Connection analyzer & issue detector
│   └── viewer/
│       ├── __init__.py
│       └── serve.py              # Local web viewer launcher
├── viewer/                       # React frontend (ReactFlow-based)
│   ├── package.json
│   ├── index.html
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── BlueprintCanvas.tsx    # Main ReactFlow canvas
│   │   │   ├── NodeDetail.tsx         # Drill-down panel
│   │   │   ├── StatusLegend.tsx       # Status color legend
│   │   │   ├── TemplateSelector.tsx   # Template picker UI
│   │   │   └── IssuePanel.tsx         # Broken connections / issues
│   │   ├── hooks/
│   │   │   └── useBlueprintData.ts    # Polling/SSE hook for live data
│   │   └── types.ts
│   └── vite.config.ts
├── tests/
│   ├── test_server.py
│   ├── test_scanner.py
│   ├── test_analyzer.py
│   └── test_templates.py
└── .mcp.json                     # MCP config for Claude Code (self-referencing)
```

---

## Tech Stack

- **MCP Server**: Python 3.11+ with FastMCP (`mcp[cli]`)
- **Database**: SQLite (single `.blueprint.db` file in project root)
- **Models**: Pydantic v2 for all data structures
- **Scanner**: AST parsing (`ast` module for Python, `@babel/parser` or regex for JS/TS)
- **Viewer**: React + TypeScript + ReactFlow + Vite
- **Layout Engine**: ELK.js (via `elkjs`) for auto-layout

---

## Data Schema

### SQLite Tables

```sql
-- Core node table: every component in the project
CREATE TABLE nodes (
    id TEXT PRIMARY KEY,                  -- UUID
    name TEXT NOT NULL,                   -- Display name ("users table", "auth endpoint")
    type TEXT NOT NULL,                   -- system | service | database | table | column |
                                          -- api | route | function | module | container |
                                          -- queue | cache | external | config | file
    status TEXT NOT NULL DEFAULT 'planned', -- planned | in_progress | built | broken | deprecated
    parent_id TEXT,                        -- Parent node ID for drill-down nesting
    description TEXT,                      -- What this node does
    metadata TEXT,                         -- JSON blob for type-specific data:
                                          --   table: { columns: [...], primary_key: "id" }
                                          --   route: { method: "POST", path: "/api/users", params: [...] }
                                          --   function: { signature: "def foo(x: int) -> str", file: "src/main.py", line: 42 }
                                          --   service: { port: 8000, framework: "fastapi" }
    source_file TEXT,                     -- Mapped file path relative to project root
    source_line INTEGER,                  -- Line number in source file
    template_origin TEXT,                 -- Which template this came from (NULL if manually created)
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (parent_id) REFERENCES nodes(id) ON DELETE CASCADE
);

-- Connections between nodes
CREATE TABLE edges (
    id TEXT PRIMARY KEY,                  -- UUID
    source_id TEXT NOT NULL,              -- From node
    target_id TEXT NOT NULL,              -- To node
    relationship TEXT NOT NULL,           -- connects_to | reads_from | writes_to | depends_on |
                                          -- authenticates | calls | inherits | contains | exposes
    label TEXT,                           -- Human-readable label ("via REST", "foreign key")
    metadata TEXT,                        -- JSON blob for extra data
    status TEXT NOT NULL DEFAULT 'active', -- active | broken | planned
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (source_id) REFERENCES nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES nodes(id) ON DELETE CASCADE
);

-- Change log for tracking what happened when
CREATE TABLE changelog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,                 -- node_created | node_updated | node_deleted |
                                          -- edge_created | edge_deleted | scan_completed |
                                          -- template_applied | issue_detected | issue_resolved
    target_type TEXT NOT NULL,            -- node | edge | blueprint
    target_id TEXT,
    details TEXT,                         -- JSON description of what changed
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Project metadata
CREATE TABLE project_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Indexes
CREATE INDEX idx_nodes_parent ON nodes(parent_id);
CREATE INDEX idx_nodes_type ON nodes(type);
CREATE INDEX idx_nodes_status ON nodes(status);
CREATE INDEX idx_edges_source ON edges(source_id);
CREATE INDEX idx_edges_target ON edges(target_id);
CREATE INDEX idx_changelog_timestamp ON changelog(timestamp);
```

---

## MCP Tool Definitions

### Node Management

#### `register_node`
Register a new component in the blueprint. Call this whenever you create something — a file, a database table, an API route, a service.

**Parameters:**
```json
{
    "name": "string (required) — Display name",
    "type": "string (required) — One of: system, service, database, table, column, api, route, function, module, container, queue, cache, external, config, file",
    "status": "string (optional, default: 'built') — One of: planned, in_progress, built, broken, deprecated",
    "parent_id": "string (optional) — ID of parent node for nesting",
    "description": "string (optional) — What this does",
    "metadata": "object (optional) — Type-specific data (columns for tables, method/path for routes, etc.)",
    "source_file": "string (optional) — File path relative to project root",
    "source_line": "integer (optional) — Line number"
}
```

**Returns:** `{ "id": "uuid", "name": "...", "status": "..." }`

#### `update_node`
Update an existing node's status, metadata, or details.

**Parameters:**
```json
{
    "id": "string (required) — Node ID",
    "name": "string (optional)",
    "status": "string (optional)",
    "description": "string (optional)",
    "metadata": "object (optional) — Merges with existing",
    "source_file": "string (optional)",
    "source_line": "integer (optional)"
}
```

#### `remove_node`
Remove a node and all its children/connections.

**Parameters:**
```json
{
    "id": "string (required) — Node ID to remove"
}
```

#### `get_node`
Get a single node with its children and connections.

**Parameters:**
```json
{
    "id": "string (required) — Node ID",
    "depth": "integer (optional, default: 1) — How many levels of children to include"
}
```

### Connection Management

#### `register_connection`
Register a relationship between two nodes.

**Parameters:**
```json
{
    "source_id": "string (required) — From node ID",
    "target_id": "string (required) — To node ID",
    "relationship": "string (required) — One of: connects_to, reads_from, writes_to, depends_on, authenticates, calls, inherits, contains, exposes",
    "label": "string (optional) — Human-readable description",
    "status": "string (optional, default: 'active') — One of: active, broken, planned"
}
```

#### `remove_connection`
Remove a connection between nodes.

**Parameters:**
```json
{
    "id": "string (required) — Edge ID to remove"
}
```

### Blueprint Retrieval

#### `get_blueprint`
Get the full project blueprint — all nodes and connections.

**Parameters:**
```json
{
    "status_filter": "string (optional) — Filter by node status",
    "type_filter": "string (optional) — Filter by node type",
    "root_only": "boolean (optional, default: false) — Only top-level nodes"
}
```

**Returns:** Full graph with nodes, edges, and summary stats.

#### `get_blueprint_summary`
Quick overview: counts by type, counts by status, recent changes.

**Parameters:** None

### Codebase Scanning

#### `scan_codebase`
Analyze the current project directory and auto-populate the blueprint from existing code.

**Parameters:**
```json
{
    "path": "string (optional, default: '.') — Project root to scan",
    "languages": "array (optional) — Force specific language scanners: ['python', 'javascript', 'typescript']",
    "deep": "boolean (optional, default: false) — Deep scan: parse function signatures, database schemas"
}
```

**Returns:** Summary of what was found and registered.

#### `scan_file`
Scan a single file and update the blueprint with any components found.

**Parameters:**
```json
{
    "path": "string (required) — File path relative to project root"
}
```

### Templates

#### `list_templates`
List all available project templates.

**Parameters:** None

**Returns:** Array of template names with descriptions and what nodes they include.

#### `apply_template`
Apply a project template, creating all planned nodes.

**Parameters:**
```json
{
    "template": "string (required) — Template name (e.g., 'saas', 'api_service', 'fullstack', 'multi_entity_business')",
    "project_name": "string (optional) — Name for the root system node",
    "customizations": "object (optional) — Template-specific overrides"
}
```

**Returns:** All created nodes with their IDs and planned status.

### Analysis

#### `find_issues`
Analyze the blueprint for problems — orphaned nodes, missing connections, broken references, planned nodes that should exist but don't.

**Parameters:**
```json
{
    "severity": "string (optional) — Filter: 'critical', 'warning', 'info'"
}
```

**Returns:**
```json
{
    "issues": [
        {
            "severity": "critical",
            "type": "orphaned_node",
            "message": "Database table 'sessions' has no connections — nothing reads or writes to it",
            "node_id": "...",
            "suggestion": "Connect to auth service or remove if unused"
        },
        {
            "severity": "warning",
            "type": "missing_dependency",
            "message": "Route POST /api/users references 'users' table but no connection exists",
            "source_id": "...",
            "target_id": "..."
        }
    ]
}
```

#### `get_changes`
Get what changed since a given timestamp.

**Parameters:**
```json
{
    "since": "string (required) — ISO timestamp"
}
```

### Viewer

#### `open_viewer`
Launch the local web viewer to visualize the blueprint.

**Parameters:**
```json
{
    "port": "integer (optional, default: 3333)"
}
```

---

## Template Format

Templates are JSON files with this structure:

```json
{
    "name": "saas",
    "display_name": "SaaS Application",
    "description": "Full SaaS app with auth, billing, API, database, background jobs, and frontend",
    "nodes": [
        {
            "ref": "system",
            "name": "{{project_name}}",
            "type": "system",
            "description": "Root system node"
        },
        {
            "ref": "api_service",
            "name": "API Service",
            "type": "service",
            "parent_ref": "system",
            "description": "Main backend API server",
            "metadata": { "framework": "fastapi", "port": 8000 }
        },
        {
            "ref": "database",
            "name": "Database",
            "type": "database",
            "parent_ref": "system",
            "description": "Primary PostgreSQL database",
            "metadata": { "engine": "postgresql" }
        },
        {
            "ref": "users_table",
            "name": "users",
            "type": "table",
            "parent_ref": "database",
            "description": "User accounts table",
            "metadata": {
                "columns": [
                    { "name": "id", "type": "UUID", "primary_key": true },
                    { "name": "email", "type": "VARCHAR(255)", "unique": true },
                    { "name": "password_hash", "type": "TEXT" },
                    { "name": "created_at", "type": "TIMESTAMP" }
                ]
            }
        },
        {
            "ref": "auth",
            "name": "Authentication",
            "type": "module",
            "parent_ref": "api_service",
            "description": "Auth module: login, register, JWT tokens"
        },
        {
            "ref": "auth_login",
            "name": "POST /auth/login",
            "type": "route",
            "parent_ref": "auth",
            "description": "Login endpoint",
            "metadata": { "method": "POST", "path": "/auth/login" }
        },
        {
            "ref": "auth_register",
            "name": "POST /auth/register",
            "type": "route",
            "parent_ref": "auth",
            "description": "Registration endpoint",
            "metadata": { "method": "POST", "path": "/auth/register" }
        },
        {
            "ref": "frontend",
            "name": "Frontend",
            "type": "service",
            "parent_ref": "system",
            "description": "React frontend application",
            "metadata": { "framework": "react", "port": 3000 }
        },
        {
            "ref": "cache",
            "name": "Cache",
            "type": "cache",
            "parent_ref": "system",
            "description": "Redis cache layer",
            "metadata": { "engine": "redis" }
        },
        {
            "ref": "background_jobs",
            "name": "Background Jobs",
            "type": "queue",
            "parent_ref": "system",
            "description": "Async task queue (Celery/ARQ)",
            "metadata": { "engine": "arq" }
        },
        {
            "ref": "billing",
            "name": "Billing",
            "type": "module",
            "parent_ref": "api_service",
            "description": "Stripe billing integration"
        },
        {
            "ref": "email_service",
            "name": "Email Service",
            "type": "external",
            "parent_ref": "system",
            "description": "Transactional email provider (SendGrid/Postmark)"
        }
    ],
    "edges": [
        { "source_ref": "auth_login", "target_ref": "users_table", "relationship": "reads_from", "label": "Verify credentials" },
        { "source_ref": "auth_register", "target_ref": "users_table", "relationship": "writes_to", "label": "Create account" },
        { "source_ref": "frontend", "target_ref": "api_service", "relationship": "calls", "label": "REST API" },
        { "source_ref": "api_service", "target_ref": "database", "relationship": "connects_to", "label": "SQLAlchemy" },
        { "source_ref": "api_service", "target_ref": "cache", "relationship": "reads_from", "label": "Session/cache reads" },
        { "source_ref": "api_service", "target_ref": "background_jobs", "relationship": "connects_to", "label": "Enqueue tasks" },
        { "source_ref": "background_jobs", "target_ref": "email_service", "relationship": "calls", "label": "Send emails" },
        { "source_ref": "billing", "target_ref": "users_table", "relationship": "reads_from", "label": "Customer lookup" }
    ]
}
```

---

## Scanner Specifications

### Python Scanner (`python_scanner.py`)
- Walk all `.py` files
- Use `ast` module to parse
- Detect FastAPI/Flask/Django apps → register as `service` nodes
- Detect route decorators (`@app.get`, `@app.post`, `@router.*`) → register as `route` nodes
- Detect SQLAlchemy/Tortoise/Django models → register as `table` nodes with column metadata
- Detect class definitions → register as `module` nodes
- Detect function definitions in route files → register as `function` nodes
- Detect imports to map internal dependencies as edges

### JavaScript/TypeScript Scanner (`javascript_scanner.py`)
- Walk all `.js`, `.ts`, `.jsx`, `.tsx` files
- Regex-based detection (no full AST needed for v1)
- Detect Express/Fastify/Hono route definitions → `route` nodes
- Detect React component files → `module` nodes
- Detect Prisma/Drizzle/Sequelize schemas → `table` nodes
- Detect `package.json` for service metadata

### Database Scanner (`database_scanner.py`)
- Parse SQL migration files (`.sql`)
- Parse Alembic migration scripts
- Parse Prisma schema files (`.prisma`)
- Parse SQLAlchemy model classes
- Extract tables, columns, foreign keys, indexes
- Auto-create edges for foreign key relationships

### Docker Scanner (`docker_scanner.py`)
- Parse `Dockerfile` → register `container` nodes
- Parse `docker-compose.yml` → register `service` nodes with ports/env
- Detect service dependencies (depends_on) → register as edges
- Detect volume mounts, network connections

### File Scanner (`file_scanner.py`)
- Walk directory tree (respect .gitignore)
- Detect project type by presence of config files:
  - `pyproject.toml` / `requirements.txt` → Python
  - `package.json` → JavaScript/TypeScript
  - `Cargo.toml` → Rust
  - `docker-compose.yml` → Docker
  - `.env` → Environment config
- Create top-level `file` nodes for key config files
- Detect README, LICENSE, CI configs (.github/workflows)

---

## Analyzer Specifications (`analyzer.py`)

The analyzer checks the blueprint graph for issues:

### Critical Issues
- **Orphaned tables**: Database tables with zero connections (nothing reads/writes)
- **Broken references**: Edges pointing to deleted nodes
- **Missing database**: Routes that clearly interact with data but no database node exists
- **Circular dependencies**: Service A depends on B depends on A

### Warnings
- **Unimplemented planned nodes**: Nodes in `planned` status with no children
- **Missing auth**: API routes with no connection to auth module
- **Single point of failure**: Service with only one connection path
- **Stale nodes**: Nodes with source files that no longer exist

### Info
- **Unused modules**: Code modules not connected to any route/service
- **Missing descriptions**: Nodes without descriptions
- **Schema drift**: Table metadata doesn't match what scanner finds in code

---

## Implementation Order

### Phase 1 — Core MCP Server (Build First)
1. `src/models.py` — Pydantic models
2. `src/db.py` — SQLite layer with all CRUD operations
3. `src/server.py` — FastMCP server with these tools:
   - `register_node`
   - `update_node`
   - `remove_node`
   - `get_node`
   - `register_connection`
   - `remove_connection`
   - `get_blueprint`
   - `get_blueprint_summary`
4. Tests for all CRUD operations

### Phase 2 — Templates
5. `src/templates/registry.py` — Template loader
6. `src/templates/saas.json` — First template
7. `src/templates/api_service.json`
8. `src/templates/fullstack.json`
9. `src/templates/multi_entity_business.json`
10. MCP tools: `list_templates`, `apply_template`

### Phase 3 — Scanner
11. `src/scanner/file_scanner.py` — Basic file tree
12. `src/scanner/python_scanner.py` — Python/FastAPI
13. `src/scanner/javascript_scanner.py` — JS/TS/React
14. `src/scanner/database_scanner.py` — SQL/ORM schemas
15. `src/scanner/docker_scanner.py` — Docker
16. MCP tools: `scan_codebase`, `scan_file`

### Phase 4 — Analyzer
17. `src/analyzer.py` — Issue detection
18. MCP tools: `find_issues`, `get_changes`

### Phase 5 — Viewer
19. React app with ReactFlow
20. Node drill-down panel
21. Status color coding
22. Template selector
23. Issue panel
24. MCP tool: `open_viewer`

---

## Environment & Dependencies

### Python (`requirements.txt`)
```
mcp[cli]>=1.0.0
pydantic>=2.0.0
aiosqlite>=0.19.0
uvicorn>=0.27.0
pyyaml>=6.0
```

### Viewer (`viewer/package.json`)
```json
{
    "dependencies": {
        "react": "^18",
        "react-dom": "^18",
        "reactflow": "^11",
        "elkjs": "^0.9",
        "@types/react": "^18",
        "typescript": "^5"
    },
    "devDependencies": {
        "vite": "^5",
        "@vitejs/plugin-react": "^4"
    }
}
```

---

## Claude Code MCP Configuration

When this project is installed, add to any project's `.mcp.json`:

```json
{
    "mcpServers": {
        "blueprint": {
            "type": "stdio",
            "command": "python",
            "args": ["-m", "src.server"],
            "cwd": "/path/to/blueprint-mcp"
        }
    }
}
```

Or if installed as a package:

```json
{
    "mcpServers": {
        "blueprint": {
            "type": "stdio",
            "command": "blueprint-mcp",
            "args": ["--db", ".blueprint.db"]
        }
    }
}
```

---

## Behavioral Rules for Claude Code

When Blueprint MCP is connected, Claude Code should follow these practices:

1. **Always register what you build.** After creating a file, database table, API route, or service — call `register_node` with the details.
2. **Always register connections.** When one component talks to another, call `register_connection`.
3. **Check the blueprint before building.** Call `get_blueprint` to see what's planned and what exists.
4. **Update status as you work.** Move nodes from `planned` → `in_progress` → `built` as implementation progresses.
5. **Scan before starting on existing projects.** Call `scan_codebase` first on any project that already has code.
6. **Run `find_issues` periodically.** After major changes, check for broken connections or orphaned components.
7. **Use templates for new projects.** Call `list_templates` and `apply_template` when starting fresh.

---

## Success Criteria

- [ ] Claude Code can register nodes and connections as it builds
- [ ] `scan_codebase` correctly maps an existing FastAPI + PostgreSQL project
- [ ] Templates create full planned node trees with proper nesting
- [ ] `find_issues` detects orphaned tables and broken connections
- [ ] `get_blueprint` returns a complete, nested graph
- [ ] Viewer renders the graph with drill-down and color-coded status
- [ ] `.blueprint.db` file is portable — copy to another machine and it works
- [ ] Full round-trip: apply template → build from blueprint → scan to verify → find issues
