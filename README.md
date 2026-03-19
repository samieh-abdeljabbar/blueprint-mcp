# Blueprint MCP

**A living architectural map for your software projects.**

Blueprint MCP is a [Model Context Protocol](https://modelcontextprotocol.io/) server that gives Claude Code a persistent understanding of your project's architecture. It tracks every component — services, databases, APIs, routes, tables, functions — their connections, and their build status in a local SQLite database that travels with your project.

Scan existing codebases to auto-detect architecture, apply starter templates, find architectural issues, trace data flows, simulate what-if scenarios, and export to Mermaid, Graphviz, JSON, CSV, or Markdown.

**38 MCP tools | 309 tests | 6 templates | 9 language scanners | 10 architectural checks**

---

## Table of Contents

- [Installation](#installation)
- [Global Setup (Recommended)](#global-setup-recommended)
- [Quick Start](#quick-start)
- [All 38 MCP Tools](#all-38-mcp-tools)
- [Templates](#templates)
- [Scanner](#scanner)
- [Analyzer](#analyzer)
- [CLI](#cli)
- [Using Blueprint in Your Workflow](#using-blueprint-in-your-workflow)
- [Development](#development)
- [Architecture](#architecture)

---

## Installation

### Prerequisites

- **Python 3.11+** — check with `python3 --version`
- **Git** — to clone the repository
- **[Claude Code](https://docs.anthropic.com/en/docs/claude-code)** CLI — to use the MCP tools interactively

### Step 1: Clone the Repository

```bash
git clone https://github.com/samieh-abdeljabbar/blueprint-mcp.git
cd blueprint-mcp
```

### Step 2: Create a Virtual Environment & Install

```bash
python3 -m venv .venv
source .venv/bin/activate   # On macOS/Linux
# .venv\Scripts\activate    # On Windows

pip install -e ".[dev]"
```

This installs Blueprint MCP in editable mode along with all dependencies (FastMCP, aiosqlite, Pydantic, PyYAML, pathspec) and dev tools (pytest, pytest-asyncio).

### Step 3: Connect to Claude Code

> **Want Blueprint available in every project?** Skip to [Global Setup](#global-setup-recommended) below.

**Per-project** (recommended for trying it out):

```bash
claude mcp add blueprint -- python -m src.server
```

This only makes Blueprint available in this one project directory. For multi-project use, see Global Setup below.

**Global** (available in every project):

```bash
claude mcp add --scope global blueprint -- python -m src.server
```

**Or manually** — edit `~/.claude/settings.json`:

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

### Step 4: Verify Connection

Open Claude Code in any project directory and ask:

```
List the available blueprint templates
```

If Claude responds with template names (saas, api_service, fullstack, etc.), you're connected.

---

## Global Setup (Recommended)

The per-project setup above only makes Blueprint available in one project. To use Blueprint MCP across **all** your projects, set it up globally with a launcher script.

### Step 1: Create the Launcher Script

```bash
# From the blueprint-mcp directory:
echo '#!/bin/bash
cd '"$(pwd)"' && .venv/bin/python -m src.server' > ~/blueprint-mcp.sh
chmod +x ~/blueprint-mcp.sh
```

This creates a small script that starts the Blueprint server from the correct directory with the correct Python environment, no matter where you run Claude Code from.

### Step 2: Add to Each Project

Create a `.mcp.json` file in any project root:

```json
{
  "mcpServers": {
    "blueprint": {
      "command": "bash",
      "args": ["/path/to/your/home/blueprint-mcp.sh"],
      "env": {
        "BLUEPRINT_PROJECT_DIR": "/absolute/path/to/this/project"
      }
    }
  }
}
```

Replace `/path/to/your/home/` with your actual home directory path (e.g., `/Users/yourname/blueprint-mcp.sh`) and `/absolute/path/to/this/project` with the project's absolute path.

Or use this one-liner from any project directory:

```bash
echo '{"mcpServers":{"blueprint":{"command":"bash","args":["'$HOME'/blueprint-mcp.sh"],"env":{"BLUEPRINT_PROJECT_DIR":"'$(pwd)'"}}}}' > .mcp.json
```

### Step 3: Verify

Open Claude Code in any project with the `.mcp.json` file:

```bash
cd ~/your-project
claude
```

Run `/mcp` — Blueprint should show connected. Then:

```
List the available blueprint templates
```

If Claude responds with template names, you're set.

### Step 4: First-Time Setup Per Project

Each project gets its own `.blueprint.db` database. The first time you use Blueprint in a new project:

```
Scan this codebase and populate the blueprint
```

This creates the database and detects your project's architecture automatically.

> **Tip:** Add `.blueprint.db` to your global gitignore if you don't want blueprint databases committed:
> ```bash
> echo ".blueprint.db" >> ~/.gitignore_global
> git config --global core.excludesfile ~/.gitignore_global
> ```

### Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `/mcp` shows failed | Launcher script not found | Verify `~/blueprint-mcp.sh` exists and is executable: `ls -la ~/blueprint-mcp.sh` |
| `/mcp` shows failed | Wrong Python path | Run `bash ~/blueprint-mcp.sh` manually — if it shows the FastMCP banner, the script is fine |
| `/mcp` shows `Command: python` | Old config overriding `.mcp.json` | Check `~/.claude.json` for stale blueprint entries and remove them |
| Server starts but tools don't work | Missing dependencies | Run `cd /path/to/blueprint-mcp && pip install -e ".[dev]"` in the venv |
| "Failed to reconnect" on restart | Cached config | Fully quit terminal, reopen, and run `claude` fresh |

---

## Quick Start

After installing, try these commands inside Claude Code:

```
1. Apply the saas template for "My App"
2. Show me the blueprint summary
3. Find architectural issues in the blueprint
4. What connects to the database?
5. Trace the flow from the API gateway
6. What if we removed the cache?
7. Show me the project health score
8. Export the blueprint as a Mermaid diagram
```

---

## All 38 MCP Tools

### Node Management (4 tools)

| Tool | Description |
|------|-------------|
| `register_node` | Register a new component (service, database, route, etc.) |
| `update_node` | Update an existing node's properties. Metadata is merged, not replaced |
| `remove_node` | Delete a node and cascade to all children and connections |
| `get_node` | Retrieve a node with its children and edges |

**25 node types:** system, service, database, table, column, api, route, function, module, container, queue, cache, external, config, file, submodule, class_def, struct, protocol, view, test, script, middleware, migration, webhook, worker, model, schema, enum_def, util

**5 statuses:** planned, in_progress, built, broken, deprecated

### Connection Management (2 tools)

| Tool | Description |
|------|-------------|
| `register_connection` | Create a relationship between two nodes |
| `remove_connection` | Remove a connection |

**20 relationships:** connects_to, reads_from, writes_to, depends_on, authenticates, calls, inherits, contains, exposes, observes, creates, produces, consumes, delegates, controls, uses, updates, implements, emits

### Blueprint Queries (2 tools)

| Tool | Description |
|------|-------------|
| `get_blueprint` | Get the full graph — all nodes, edges, and summary stats |
| `get_blueprint_summary` | Quick overview: counts by type/status, recent changes |

### Templates (2 tools)

| Tool | Description |
|------|-------------|
| `list_templates` | List all 6 available starter templates |
| `apply_template` | Scaffold a full architecture from a template |

### Scanner (2 tools)

| Tool | Description |
|------|-------------|
| `scan_codebase` | Auto-detect architecture from existing code |
| `scan_file` | Scan a single file and update the blueprint |

### Analyzer (2 tools)

| Tool | Description |
|------|-------------|
| `find_issues` | Detect architectural problems (10 checks, 3 severity levels) |
| `get_changes` | Get changelog entries since a given timestamp |

### Intelligence (3 tools)

| Tool | Description |
|------|-------------|
| `get_project_questions` | Generate actionable questions about gaps, risks, improvements |
| `get_review_prompt` | Generate a structured architecture review document |
| `impact_analysis` | Trace impact of changing a node — upstream, downstream, or both |

### Flow Tracing (3 tools)

| Tool | Description |
|------|-------------|
| `list_entry_points` | Find all entry points (routes, APIs, webhooks) |
| `trace_flow` | Trace a request/data flow through the system, detecting gaps |
| `what_if` | Simulate scenarios: remove, break, disconnect, or overload a node |

### Visualization (1 tool)

| Tool | Description |
|------|-------------|
| `render_blueprint` | Generate a self-contained HTML visualization with D3.js |

### Snapshots (4 tools)

| Tool | Description |
|------|-------------|
| `snapshot_blueprint` | Save a snapshot of the current blueprint state |
| `list_snapshots` | List all saved snapshots |
| `compare_snapshots` | Diff a snapshot against another or the current state |
| `restore_snapshot` | Restore the blueprint to a previous snapshot (requires `confirm=True`) |

### Export (5 tools)

| Tool | Description |
|------|-------------|
| `export_mermaid` | Export as a Mermaid diagram |
| `export_markdown` | Export as structured Markdown documentation |
| `export_json` | Export as a portable JSON blob |
| `export_csv` | Export nodes as CSV |
| `export_dot` | Export as Graphviz DOT format |

### Health & Quality (3 tools)

| Tool | Description |
|------|-------------|
| `health_report` | Score blueprint health (0-100, grades A-F) for a node or project |
| `find_stale` | Detect stale source files, old planned nodes, missing files |
| `query_blueprint` | Ask natural language questions about the architecture |

### Multi-Project (2 tools)

| Tool | Description |
|------|-------------|
| `link_projects` | Create a cross-project link between nodes in different blueprints |
| `get_project_map` | Show all linked projects and their connections |

### Annotations (3 tools)

| Tool | Description |
|------|-------------|
| `annotate_node` | Add or update a key-value annotation (cost, provider, tier) on a node |
| `get_annotations` | Query annotations by node or key |
| `cost_report` | Summarize all cost-related annotations by provider and node type |

---

## Templates

Six starter templates cover common architectures. All nodes are created with `status: planned` so you can track progress as you build.

| Template | Description | Nodes | Edges |
|----------|-------------|-------|-------|
| `saas` | Auth, billing, API, database, cache, queue, frontend, email | 12 | 8 |
| `api_service` | Standalone API with database, auth, health check, config | 9 | 6 |
| `fullstack` | Frontend, backend API, database with 5 tables, cache, CDN | 13 | 9 |
| `data_pipeline` | ETL/ELT with ingestion, transformation, warehouse, monitoring | 9 | 7 |
| `desktop_app` | Tauri/Electron shell, UI, local database, IPC, auto-updater | 8 | 5 |
| `multi_entity_business` | Multi-location business with POS, payroll, compliance, BI | 20 | 17 |

### Example

Ask Claude Code:

```
Apply the api_service template for "User Service"
```

Creates 9 planned components (API server, health check, auth middleware, database, 3 tables, config) with 6 edges. As you build each part, Claude updates statuses to `built`.

---

## Scanner

The scanner auto-detects architecture from existing codebases. It's **non-destructive** (adds/updates only, never deletes) and **idempotent** (running twice doesn't create duplicates).

| Language | Method | Detects |
|----------|--------|---------|
| **Python** | AST parsing | FastAPI/Flask/Django apps, routes, SQLAlchemy/Django models, Pydantic models, Celery tasks, imports, classes, protocols |
| **JavaScript/TypeScript** | Regex | Express/Next.js/React routes & components, Prisma/Drizzle/TypeORM models, Vue SFCs, class inheritance, package.json |
| **SQL/Database** | Regex | CREATE TABLE with columns, foreign keys, views with source edges, indexes, triggers, functions, ALTER TABLE FK |
| **Prisma** | Regex | Datasource → database node, models → tables, fields → columns, `@relation` → edges |
| **ORM Migrations** | Regex | Django migrations (CreateModel, ForeignKey), Alembic (op.create_table, ForeignKeyConstraint) |
| **TypeORM** | Regex | @Entity → tables, @Column → columns, @ManyToOne/@OneToMany → edges |
| **Knex/Sequelize** | Regex | createTable → tables, .references().inTable() → FK edges |
| **Connection Strings** | Regex | DATABASE_URL → database, REDIS_URL → cache (credentials never stored) |
| **Docker** | YAML/text | Dockerfile images & ports, docker-compose services, depends_on edges |
| **Swift** | Regex | SwiftUI views, structs, ObservableObject classes, protocols, SPM targets |
| **Rust** | Regex | Structs, traits, enums, impl blocks, Actix/Axum routes, Cargo.toml deps |
| **Go** | Regex | Structs, interfaces, HTTP handlers, packages, go.mod deps |
| **Config/IaC** | YAML/HCL/text | Kubernetes manifests, Terraform resources, GraphQL schemas, GitHub Actions, .env files |

The scanner respects `.gitignore` and always skips `.git/`, `node_modules/`, `__pycache__/`, `.venv/`.

---

## Analyzer

10 architectural checks at three severity levels:

| Check | Severity | Detects |
|-------|----------|---------|
| Orphaned tables | Critical | Tables with no read/write connections |
| Broken references | Critical | Edges with status `broken` |
| Missing database | Critical | Services with routes but no database connection |
| Circular dependencies | Critical | Cycles in dependency graph (DFS 3-color algorithm) |
| Unimplemented planned | Warning | Nodes still in `planned` status |
| Missing authentication | Warning | API/route nodes with no `authenticates` edge |
| Single point of failure | Warning | Nodes whose removal disconnects the graph (Tarjan's algorithm) |
| Stale nodes | Warning | Nodes referencing missing source files |
| Unused modules | Info | Modules with no connections |
| Missing descriptions | Info | Nodes without descriptions |

---

## CLI

Blueprint MCP includes a CLI for use outside of Claude Code:

```bash
# Initialize a blueprint database in the current directory
blueprint-mcp init

# Install git hooks (post-commit sync, pre-push health check)
blueprint-mcp install-hooks

# Scan the codebase and update the blueprint
blueprint-mcp sync

# Print project health score (exit code 1 if below threshold)
blueprint-mcp health --fail-below 60

# Export to stdout
blueprint-mcp export --format mermaid
blueprint-mcp export --format json
blueprint-mcp export --format csv
blueprint-mcp export --format dot
blueprint-mcp export --format markdown
```

---

## Using Blueprint in Your Workflow

### New Project: Template -> Build -> Scan -> Verify

```
1. "Apply the fullstack template for 'Acme App'"
   -> Creates 13 planned components

2. Build your project, telling Claude Code as you go:
   "Register the users table as built"
   "Update the API Server status to in_progress"

3. "Scan this codebase to pick up anything we missed"
   -> Auto-detects routes, models, Docker services

4. "Find issues in the blueprint"
   -> Catches orphaned tables, missing auth, circular deps

5. "What's the project health score?"
   -> 0-100 score with letter grade
```

### Existing Project: Scan -> Review -> Fix

```
1. "Scan this codebase and populate the blueprint"
2. "Show me the blueprint summary"
3. "Find critical issues"
4. "Trace the flow from the API entry point"
5. "What if we removed the auth service?"
6. "Export the blueprint as Mermaid"
```

### Auto-Register Components

Add this to your project's `CLAUDE.md` to keep the blueprint updated automatically:

```markdown
## Blueprint

This project uses Blueprint MCP to track architecture.

When you create, modify, or delete any of the following, update the blueprint:
- Database tables or models -> register as `table` nodes
- API routes or endpoints -> register as `route` nodes
- Services or microservices -> register as `service` nodes
- Docker containers -> register as `container` nodes

After completing a feature, run `find_issues` to check for architectural problems.
```

---

## Development

### Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

**309 tests** across 17 test files:

| File | Tests | Coverage |
|------|-------|----------|
| `test_server.py` | 21 | Node/edge CRUD, blueprint queries, changelog, extended types |
| `test_templates.py` | 28 | Template loading, validation, application, multi-template |
| `test_scanner.py` | 120 | Python/JS/Docker/Swift/Rust/Go/Config/SQL scanners, idempotency, edge cases |
| `test_analyzer.py` | 20 | All 10 checks with positive and negative cases |
| `test_tracer.py` | 11 | Entry points, linear flow, branches, cycles, gaps |
| `test_impact.py` | 6 | Upstream/downstream/both cascade analysis |
| `test_whatif.py` | 5 | Remove, break, disconnect, overload scenarios |
| `test_questions.py` | 6 | Security, completeness, data flow gap detection |
| `test_review.py` | 3 | Review prompt generation |
| `test_xray.py` | 11 | HTML visualization, themes, D3 embedding, legend, onboarding |
| `test_snapshots.py` | 6 | Save, restore, compare, confirm safety |
| `test_export.py` | 5 | Mermaid, Markdown, JSON, CSV, DOT formats |
| `test_health.py` | 6 | Node scoring, project grades, edge cases |
| `test_stale.py` | 3 | Missing files, stale planned nodes |
| `test_query.py` | 5 | Natural language parsing, keyword matching |
| `test_cli.py` | 3 | CLI subcommand parsing and execution |
| `test_projects.py` | 3 | Cross-project linking |
| `test_annotations.py` | 4 | Annotations CRUD, cost reports |

### Adding a New MCP Tool

1. Add Pydantic model in `src/models.py` if needed
2. Add DB method in `src/db.py`
3. Add domain function in appropriate module
4. Add `@mcp.tool` function in `src/server.py`
5. Add tests in `tests/`

### Adding a New Scanner

1. Create `src/scanner/{name}_scanner.py` extending `BaseScanner`
2. Use `self._track_node()` / `self._track_edge()` for dedup
3. Register in `src/scanner/__init__.py`
4. Add fixtures in `tests/fixtures/` and tests in `tests/test_scanner.py`

### Adding a New Template

1. Create `src/templates/{name}.json` — auto-discovered, no registration needed
2. Use `ref` strings for internal references (converted to UUIDs on apply)
3. Parents must appear before children in the `nodes` array

---

## Architecture

```
blueprint-mcp/
├── src/
│   ├── server.py           # FastMCP server — 38 @mcp.tool definitions
│   ├── db.py               # Async SQLite layer (7 tables, full CRUD)
│   ├── models.py           # Pydantic v2 models for all data types
│   ├── analyzer.py          # 10 architectural checks
│   ├── tracer.py            # Flow tracing & entry point discovery
│   ├── impact.py            # Impact analysis (BFS cascade)
│   ├── whatif.py            # Scenario simulation
│   ├── questions.py         # Gap detection & fix prompts
│   ├── review.py            # Architecture review generation
│   ├── snapshots.py         # Snapshot save/restore/compare
│   ├── export.py            # 5 export formats
│   ├── health.py            # Health scoring (0-100, A-F grades)
│   ├── stale.py             # Stale detection
│   ├── query.py             # Natural language queries
│   ├── projects.py          # Cross-project linking
│   ├── annotations.py       # Key-value annotations & cost reports
│   ├── xray.py              # HTML visualization (D3.js)
│   ├── cli.py               # CLI entry point
│   ├── scanner/
│   │   ├── __init__.py      # Orchestrator — coordinates all scanners
│   │   ├── base.py          # Abstract base with dedup helpers
│   │   ├── python_scanner.py    # AST-based Python analysis
│   │   ├── javascript_scanner.py # Regex-based JS/TS analysis
│   │   ├── docker_scanner.py    # Dockerfile + compose parsing
│   │   ├── swift_scanner.py     # Swift/SwiftUI analysis
│   │   ├── rust_scanner.py      # Rust analysis
│   │   ├── go_scanner.py        # Go analysis
│   │   ├── config_scanner.py    # K8s, Terraform, GraphQL, GitHub Actions
│   │   ├── sql_scanner.py       # SQL, Prisma, ORM migrations, connection strings
│   │   └── file_scanner.py      # Project detection + gitignore
│   └── templates/
│       ├── registry.py      # Template loading & application
│       └── *.json           # 6 starter templates
├── tests/                   # 309 tests across 17 files
│   └── fixtures/            # Sample projects for scanner tests
├── viewer/                  # React + ReactFlow frontend (optional)
└── pyproject.toml           # Python 3.11+, all deps
```

Built with:

- **[FastMCP](https://github.com/jlowin/fastmcp)** — MCP server framework
- **[aiosqlite](https://github.com/omnilib/aiosqlite)** — Async SQLite (portable, no server)
- **[Pydantic v2](https://docs.pydantic.dev/)** — Strict input/output validation
- **AST parsing** — Accurate Python analysis
- **D3.js** — Embedded interactive visualization

---

## License

MIT
