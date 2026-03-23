# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Blueprint MCP is a Model Context Protocol server that maintains a living architectural map of any software project. It tracks components (services, databases, APIs, routes, functions, etc.), their connections, and build status via a local SQLite database. Currently exposes **39 MCP tools** with **347 tests**.

## Key Commands

```bash
# Install dependencies (use the project venv)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run the MCP server (stdio mode for Claude Code)
python -m src.server

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_server.py -v

# Run a specific test
pytest tests/test_health.py::test_project_health_score -v

# CLI commands
blueprint-mcp init                         # Create .blueprint.db
blueprint-mcp sync                         # Scan codebase
blueprint-mcp health --fail-below 60       # Health check (CI gate)
blueprint-mcp export --format mermaid      # Export to stdout
```

## Architecture

The server follows a layered pattern: **MCP tools** (server.py) -> **domain logic** (individual modules) -> **database** (db.py) -> **SQLite**.

- `src/server.py` — FastMCP entry point. All 38 `@mcp.tool` functions live here. Each tool validates input with Pydantic, gets the DB from `ctx.lifespan_context["db"]`, delegates to a domain module, and returns a dict.
- `src/db.py` — Async SQLite layer (aiosqlite). Schema has 7 tables: `nodes`, `edges`, `changelog`, `project_meta`, `snapshots`, `annotations`. All CRUD methods, dedup helpers (`find_or_create_node/edge`), and bulk queries.
- `src/models.py` — Pydantic v2 models. `NodeType` (25 values), `NodeStatus` (5), `EdgeRelationship` (20), `EdgeStatus` (3). Input models, output models, template models, scanner models, analyzer models, flow models.

### Domain Modules

| Module | Purpose |
|---|---|
| `src/scanner/` | Codebase analysis. `BaseScanner` ABC with dedup tracking. Python (AST), JS/TS (regex), Docker (YAML), SQL/Prisma/ORM (regex), Swift, Rust, Go, Config/IaC, file (project detection). Orchestrated by `scan_project()` in `__init__.py`. |
| `src/templates/registry.py` | Template loading/validation/application. Auto-discovers `*.json` from `src/templates/`. Ref strings -> UUIDs on apply. |
| `src/analyzer.py` | 10 graph checks (orphaned tables, circular deps via DFS, SPOF via Tarjan's, missing auth, stale nodes, etc.) |
| `src/tracer.py` | Flow tracing from entry points. BFS with gap detection (dead ends, unprotected writes). |
| `src/impact.py` | Impact analysis. BFS cascade upstream/downstream/both with depth levels. |
| `src/whatif.py` | Scenario simulation (remove, break, disconnect, overload). |
| `src/questions.py` | Rule-based gap detection across 6 categories. Returns fix prompts. |
| `src/review.py` | Generates LLM-optimized markdown review documents. |
| `src/snapshots.py` | Save/restore/compare blueprint states. Restore replaces all nodes/edges from snapshot data. |
| `src/export.py` | 5 formats: Mermaid, Markdown, JSON, CSV, Graphviz DOT. |
| `src/health.py` | Node scoring (0-100) and project-level health grades (A-F). |
| `src/stale.py` | Detects missing source files, old planned nodes, stale file modifications. |
| `src/query.py` | Natural language query parser. Keyword -> node type/status/edge lookups. |
| `src/projects.py` | Cross-project linking via separate `~/.blueprint/meta.db`. |
| `src/annotations.py` | Key-value annotations on nodes (cost, provider, tier). Cost reports. |
| `src/xray.py` | Self-contained HTML visualization with embedded D3.js. |
| `src/cli.py` | CLI: init, install-hooks, sync, health, export. Entry point in pyproject.toml. |

## Conventions

- All IDs are UUIDs generated server-side
- All timestamps are ISO 8601 UTC
- `.blueprint.db` lives in the target project root, not in this repo
- Scanners are non-destructive: add/update only, never delete
- The changelog table logs every mutation
- Templates use `ref` strings internally, converted to UUIDs on apply; parents must precede children in the array
- Tests use in-memory SQLite (`:memory:`) — no test database files
- `pytest-asyncio` with `asyncio_mode = "auto"` — all async tests run without explicit markers

## Common Patterns

**Adding a new MCP tool:**
1. Add Pydantic model in `models.py` if needed
2. Add DB method in `db.py`
3. Add domain function in appropriate module
4. Add `@mcp.tool` function in `server.py` (imports at section top, tool at section bottom)
5. Add test in `tests/`

**Adding a new scanner:**
1. Create `src/scanner/{name}_scanner.py` extending `BaseScanner`
2. Use `self._track_node()` / `self._track_edge()` for dedup
3. Register in `src/scanner/__init__.py` `SCANNER_MAP`
4. Add fixtures in `tests/fixtures/` and tests in `tests/test_scanner.py`

**Test fixture pattern** (used across all test files):
```python
@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()
```
