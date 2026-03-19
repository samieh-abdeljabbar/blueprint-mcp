# Blueprint MCP

**A living architectural map for your software projects.**

Blueprint MCP is a [Model Context Protocol](https://modelcontextprotocol.io/) server that gives Claude Code a persistent understanding of your project's architecture. It tracks every component — services, databases, APIs, routes, tables — their connections, and their build status in a local SQLite database that travels with your project. Scan existing codebases to auto-detect architecture, apply starter templates, find architectural issues, and visualize everything in an interactive graph viewer.

---

## Quick Install

### Prerequisites

- Python 3.11+
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI installed

### Setup

```bash
# Clone the repo
git clone https://github.com/samieh-abdeljabbar/blueprint-mcp.git
cd blueprint-mcp

# Create a virtual environment and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Add to Claude Code

**Per-project** (recommended for trying it out):

```bash
claude mcp add blueprint -- python -m src.server
```

**Global** (available in every project):

```bash
claude mcp add --scope global blueprint -- python -m src.server
```

### Verify Connection

Open Claude Code in your project directory and ask:

```
List the available blueprint templates
```

If Claude responds with template names (saas, api_service, fullstack, etc.), you're connected.

---

## Quick Start

After installing, try these commands inside Claude Code:

```
1. List the available blueprint templates

2. Apply the saas template for "My App"

3. Show me the blueprint summary

4. Find architectural issues in the blueprint

5. Open the blueprint viewer
```

This creates a full SaaS architecture with 12 components and 8 connections, analyzes it for issues, and opens an interactive visualization in your browser.

---

## All MCP Tools Reference

Blueprint MCP exposes 15 tools organized into 7 categories.

### Node Management

| Tool | Parameters | Description |
|------|-----------|-------------|
| `register_node` | `name` (required), `type` (required), `status="built"`, `parent_id`, `description`, `metadata`, `source_file`, `source_line` | Register a new component (service, database, route, etc.) |
| `update_node` | `id` (required), `name`, `status`, `description`, `metadata`, `source_file`, `source_line` | Update an existing node's properties. Metadata is merged, not replaced |
| `remove_node` | `id` (required) | Delete a node and cascade to all children and connections |
| `get_node` | `id` (required), `depth=1` | Retrieve a node with its children (up to `depth` levels) and edges |

**Node types:** `system`, `service`, `database`, `table`, `column`, `api`, `route`, `function`, `module`, `container`, `queue`, `cache`, `external`, `config`, `file`

**Node statuses:** `planned`, `in_progress`, `built`, `broken`, `deprecated`

### Connection Management

| Tool | Parameters | Description |
|------|-----------|-------------|
| `register_connection` | `source_id` (required), `target_id` (required), `relationship` (required), `label`, `metadata`, `status="active"` | Create a relationship between two nodes |
| `remove_connection` | `id` (required) | Remove a connection |

**Relationships:** `connects_to`, `reads_from`, `writes_to`, `depends_on`, `authenticates`, `calls`, `inherits`, `contains`, `exposes`

### Blueprint Queries

| Tool | Parameters | Description |
|------|-----------|-------------|
| `get_blueprint` | `status_filter`, `type_filter`, `root_only=false` | Get the full graph — all nodes, edges, and summary stats |
| `get_blueprint_summary` | *(none)* | Quick overview: counts by type/status, total nodes/edges, 20 recent changes |

### Templates

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_templates` | *(none)* | List all available starter templates |
| `apply_template` | `template` (required), `project_name="My Project"` | Scaffold a full architecture from a template |

### Scanner

| Tool | Parameters | Description |
|------|-----------|-------------|
| `scan_codebase` | `path="."`, `languages`, `deep=false` | Auto-detect architecture from existing code |
| `scan_file` | `path` (required) | Scan a single file and update the blueprint |

### Analyzer

| Tool | Parameters | Description |
|------|-----------|-------------|
| `find_issues` | `severity` (optional: `critical`, `warning`, `info`) | Detect architectural problems in the blueprint |
| `get_changes` | `since` (required, ISO 8601 timestamp) | Get changelog entries since a given time |

### Viewer

| Tool | Parameters | Description |
|------|-----------|-------------|
| `open_viewer` | `port=3333` | Launch the interactive graph viewer in a browser |

---

## Templates

Six starter templates cover common architectures. All nodes are created with `status: planned` so you can track progress as you build.

| Template | Display Name | Description | Nodes | Edges |
|----------|-------------|-------------|-------|-------|
| `saas` | SaaS Application | Auth, billing, API, database, cache, queue, frontend, email | 12 | 8 |
| `api_service` | API Microservice | Standalone API with database, auth, health check, config | 9 | 6 |
| `fullstack` | Full-Stack Web App | Frontend, backend API, database with 5 tables, cache, CDN | 13 | 9 |
| `data_pipeline` | Data Pipeline | ETL/ELT with ingestion, transformation, warehouse, monitoring | 9 | 7 |
| `desktop_app` | Desktop Application | Tauri/Electron shell, UI, local database, IPC, auto-updater | 8 | 5 |
| `multi_entity_business` | Multi-Entity Business Platform | Multi-location business with POS, payroll, compliance, BI | 20 | 17 |

### Example: Applying a Template

Ask Claude Code:

```
Apply the api_service template for "User Service"
```

This creates:

```
User Service (system)
├── API Server (api)
│   ├── Health Check (route)
│   └── Auth Middleware (module)
├── Primary Database (database)
│   ├── items (table)
│   ├── users (table)
│   └── audit_log (table)
└── Config (config)

Edges:
  API Server → Primary Database (connects_to)
  Auth Middleware → users (reads_from)
  API Server → items (reads_from)
  API Server → audit_log (writes_to)
  Health Check → Primary Database (reads_from)
  API Server → Config (depends_on)
```

All 9 nodes start as `planned`. As you build each component, Claude Code updates their status to `built`.

---

## Scanner

The scanner auto-detects architecture from existing codebases. It's non-destructive (adds and updates nodes, never deletes) and idempotent (running twice doesn't create duplicates).

### Supported Languages

| Language | Detection Method | What It Finds |
|----------|-----------------|---------------|
| **Python** | AST parsing | FastAPI/Flask apps, route decorators (`@app.get`, `@app.post`), SQLAlchemy models with columns, import dependencies |
| **JavaScript/TypeScript** | Regex matching | Express routes (`app.get`, `router.post`), React components, Prisma models, package.json metadata |
| **Docker** | YAML/text parsing | Dockerfile base images and exposed ports, docker-compose services, database images, `depends_on` edges |

### Scanning a Project

Ask Claude Code:

```
Scan this codebase and populate the blueprint
```

Or be specific:

```
Scan this project for Python and Docker components
```

### What Gets Created

For a FastAPI project with SQLAlchemy models and Docker:

```
my-project (system)
├── FastAPI app (service)          ← from app = FastAPI()
│   ├── GET /api/users (route)    ← from @app.get("/api/users")
│   ├── POST /api/users (route)   ← from @app.post("/api/users")
│   └── GET /api/health (route)   ← from @app.get("/api/health")
├── users (table)                  ← from class User with __tablename__
│   └── columns: [id, name, email, created_at]
├── posts (table)                  ← from class Post with __tablename__
├── web (service)                  ← from docker-compose.yml
├── db (database)                  ← postgres image auto-detected
└── redis (database)               ← redis image auto-detected

Edges:
  web → db (depends_on)            ← from docker-compose depends_on
  web → redis (depends_on)
  main.py → models.py (depends_on) ← from import statement
```

The scanner respects `.gitignore` and always skips `.git/`, `node_modules/`, `__pycache__/`, and `.venv/`.

---

## Analyzer

The analyzer runs 10 checks against your blueprint graph and reports issues at three severity levels.

### Checks

| Check | Severity | What It Detects |
|-------|----------|-----------------|
| Orphaned tables | Critical | Tables with no `reads_from`, `writes_to`, or `connects_to` edges |
| Broken references | Critical | Edges marked with `status: broken` |
| Missing database | Critical | Services that have routes but no connection to any database |
| Circular dependencies | Critical | Cycles in `depends_on` edges (detected via DFS 3-color algorithm) |
| Unimplemented planned | Warning | Nodes still in `planned` status |
| Missing authentication | Warning | API/route nodes with no `authenticates` edge |
| Single point of failure | Warning | Nodes whose removal would disconnect the graph (Tarjan's algorithm) |
| Stale nodes | Warning | Nodes referencing source files that no longer exist on disk |
| Unused modules | Info | Module nodes with no connections to any other component |
| Missing descriptions | Info | Nodes without descriptions |

### Example Output

Ask Claude Code:

```
Find critical issues in the blueprint
```

Response:

```json
{
  "issues": [
    {
      "severity": "critical",
      "type": "orphaned_table",
      "message": "Table 'audit_log' has no data connections",
      "node_ids": ["a1b2c3..."],
      "suggestion": "Connect 'audit_log' to a service that reads from or writes to it"
    },
    {
      "severity": "critical",
      "type": "circular_dependency",
      "message": "Circular dependency detected: AuthService → UserService → AuthService",
      "node_ids": ["d4e5f6...", "g7h8i9..."],
      "suggestion": "Break the cycle by removing or reversing one dependency"
    }
  ],
  "summary": { "critical": 2, "warning": 0, "info": 0 }
}
```

---

## Viewer

The viewer is an interactive graph visualization built with React and ReactFlow.

### Launching

Ask Claude Code:

```
Open the blueprint viewer
```

Or run directly:

```bash
# Build the frontend (first time only)
cd viewer && npm install && npm run build && cd ..

# Start the server
python -m src.viewer.serve --db-path .blueprint.db --port 3333 --open
```

### What It Shows

- **Interactive graph** with drag, zoom, and pan — auto-laid out using ELK.js hierarchical layout
- **Color-coded nodes** by status:
  - Blue = planned
  - Amber = in progress
  - Green = built
  - Red = broken
  - Gray = deprecated
- **Node detail panel** (click any node) — shows type, status, description, metadata, source file, children, and connections
- **Status legend** with live counts per status
- **Template filter** dropdown to isolate nodes from a specific template
- **Issue panel** showing architectural problems from the analyzer
- **Minimap** for navigation in large graphs

### Development Mode

For frontend development with hot reload:

```bash
# Terminal 1: Start the API server
python -m src.viewer.serve --db-path .blueprint.db --dev

# Terminal 2: Start Vite dev server
cd viewer && npm run dev
```

The Vite dev server proxies `/api` requests to `localhost:3333`.

---

## Using Blueprint in Your Workflow

### New Project: Template → Build → Scan → Verify

```
1. "Apply the fullstack template for 'Acme App'"
   → Creates 13 planned components

2. Build your project, telling Claude Code as you go:
   "Register the users table as built"
   "Update the API Server status to in_progress"

3. "Scan this codebase to pick up anything we missed"
   → Auto-detects routes, models, Docker services

4. "Find issues in the blueprint"
   → Catches orphaned tables, missing auth, circular deps
```

### Existing Project: Scan → Review → Fix

```
1. "Scan this codebase and populate the blueprint"
   → Auto-detects your architecture

2. "Show me the blueprint summary"
   → See what was found: services, routes, tables, etc.

3. "Find critical issues"
   → Surfaces problems like missing database connections

4. "Open the viewer"
   → Visualize the full architecture graph
```

### Auto-Register Components with CLAUDE.md

Add this snippet to your project's `CLAUDE.md` to make Claude Code automatically keep the blueprint updated:

```markdown
## Blueprint

This project uses Blueprint MCP to track architecture.

When you create, modify, or delete any of the following, update the blueprint:
- Database tables or models → register as `table` nodes
- API routes or endpoints → register as `route` nodes
- Services or microservices → register as `service` nodes
- Docker containers → register as `container` nodes

After completing a feature, run `find_issues` to check for architectural problems.
```

---

## Adding to Global Config

To make Blueprint MCP available in every project, add it to your global Claude Code settings:

```bash
claude mcp add --scope global blueprint -- python -m src.server
```

Or manually edit `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "blueprint": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "src.server"],
      "env": {
        "BLUEPRINT_DB": ".blueprint.db"
      }
    }
  }
}
```

The `.blueprint.db` SQLite file is created in whatever directory you're working in, so each project gets its own blueprint.

---

## Development

### Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

The test suite includes 92 tests across 4 files:

| File | Tests | Coverage |
|------|-------|----------|
| `test_server.py` | 21 | Node/edge CRUD, blueprint queries, changelog |
| `test_templates.py` | 28 | Template loading, validation, application |
| `test_scanner.py` | 23 | File/Python/JS/Docker scanners, idempotency |
| `test_analyzer.py` | 20 | All 10 checks with positive and negative cases |

### Adding a New Scanner

1. Create `src/scanner/{name}_scanner.py`
2. Extend `BaseScanner` and implement `async def scan(self, path: str) -> ScanResult`
3. Use `self._track_node()` and `self._track_edge()` for deduplication
4. Register in `src/scanner/__init__.py` by adding to `SCANNER_MAP`
5. Add test fixtures in `tests/fixtures/` and tests in `tests/test_scanner.py`

### Adding a New Template

1. Create `src/templates/{name}.json` following this structure:

```json
{
  "name": "my_template",
  "display_name": "My Template",
  "description": "What this template scaffolds",
  "nodes": [
    { "ref": "root", "name": "{{project_name}}", "type": "system" },
    { "ref": "api", "name": "API Server", "type": "service", "parent_ref": "root" }
  ],
  "edges": [
    { "source_ref": "api", "target_ref": "db", "relationship": "connects_to" }
  ]
}
```

2. The template is auto-discovered — no registration needed
3. Use `ref` strings for internal references (converted to UUIDs on apply)
4. Parents must appear before children in the `nodes` array
5. Add tests in `tests/test_templates.py`

### Adding a New MCP Tool

1. Add Pydantic model in `src/models.py` if needed
2. Add database method in `src/db.py`
3. Add tool function in `src/server.py` with the `@mcp.tool` decorator
4. Add tests in `tests/`

---

## Architecture

Blueprint MCP is built with:

- **[FastMCP](https://github.com/jlowin/fastmcp)** — Python framework for building MCP servers. Handles tool registration, parameter validation, and stdio transport
- **SQLite** (via [aiosqlite](https://github.com/omnilib/aiosqlite)) — The blueprint database is a single `.blueprint.db` file that lives in your project root. Portable, no server needed
- **[Pydantic v2](https://docs.pydantic.dev/)** — Strict typing on all inputs and outputs. Every tool parameter is validated before hitting the database
- **AST parsing** — Python scanner uses the `ast` module for accurate detection of frameworks, routes, and models
- **[Starlette](https://www.starlette.io/) + [uvicorn](https://www.uvicorn.org/)** — Lightweight HTTP server for the viewer API
- **[React](https://react.dev/) + [ReactFlow](https://reactflow.dev/) + [ELK.js](https://github.com/kieler/elkjs)** — Interactive graph visualization with automatic hierarchical layout

### Project Structure

```
blueprint-mcp/
├── src/
│   ├── server.py              # FastMCP server — all 15 tool definitions
│   ├── db.py                  # SQLite database layer (async)
│   ├── models.py              # Pydantic v2 models for all data types
│   ├── analyzer.py            # 10 architectural checks
│   ├── scanner/
│   │   ├── __init__.py        # Orchestrator — coordinates all scanners
│   │   ├── base.py            # Abstract base with dedup helpers
│   │   ├── file_scanner.py    # Project detection + config files
│   │   ├── python_scanner.py  # AST-based Python analysis
│   │   ├── javascript_scanner.py  # Regex-based JS/TS analysis
│   │   └── docker_scanner.py  # Dockerfile + docker-compose parsing
│   ├── templates/
│   │   ├── registry.py        # Template loading + application
│   │   └── *.json             # 6 starter templates
│   └── viewer/
│       └── serve.py           # Starlette HTTP server
├── viewer/                    # React + ReactFlow frontend
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/        # 6 React components
│   │   ├── hooks/             # Data fetching hook
│   │   └── utils/             # Layout + colors
│   └── package.json
├── tests/                     # 92 tests across 4 files
└── pyproject.toml
```
