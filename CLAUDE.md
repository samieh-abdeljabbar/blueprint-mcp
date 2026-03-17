# CLAUDE.md — Blueprint MCP

## What This Is

Blueprint MCP is a Model Context Protocol server that maintains a living architectural map of any software project. It tracks components (databases, services, APIs, tables, routes, functions), their connections, and their build status via a local SQLite database.

## Project Structure

- `src/server.py` — FastMCP server entry point with all tool definitions
- `src/db.py` — SQLite database layer (aiosqlite), all CRUD
- `src/models.py` — Pydantic v2 models for nodes, edges, changelog
- `src/scanner/` — Codebase analysis modules (Python, JS/TS, SQL, Docker, file tree)
- `src/templates/` — Starter project templates as JSON files
- `src/analyzer.py` — Graph analysis for detecting issues
- `viewer/` — React + ReactFlow frontend for visualization
- `tests/` — pytest test suite

## Key Commands

```bash
# Install dependencies
pip install -e ".[dev]"

# Run the MCP server (stdio mode for Claude Code)
python -m src.server

# Run tests
pytest tests/ -v

# Launch the viewer
cd viewer && pnpm install && pnpm dev
```

## Conventions

- All IDs are UUIDs generated server-side
- All timestamps are ISO 8601 UTC
- Node types: system, service, database, table, column, api, route, function, module, container, queue, cache, external, config, file
- Node statuses: planned, in_progress, built, broken, deprecated
- Edge relationships: connects_to, reads_from, writes_to, depends_on, authenticates, calls, inherits, contains, exposes
- The `.blueprint.db` SQLite file lives in the target project root, not in this repo
- Templates use `ref` strings internally, converted to UUIDs on apply
- Scanners should be non-destructive — they add/update but never delete existing nodes
- The changelog table logs every mutation for `get_changes` support

## Architecture Decisions

- FastMCP over raw MCP SDK for simpler Python tool definitions
- SQLite over PostgreSQL because the blueprint must be portable (travels with the project)
- Pydantic v2 for strict typing on all inputs/outputs
- AST parsing for Python scanner, regex for JS/TS scanner (v1 simplicity)
- ReactFlow for the viewer because it handles nested graph rendering well
- ELK.js for auto-layout so users don't have to manually arrange nodes

## Testing

- Every MCP tool needs a corresponding test
- Scanner tests use fixture project directories in `tests/fixtures/`
- Analyzer tests use pre-built SQLite databases with known issues
- Use `pytest-asyncio` for async test support

## Common Patterns

When adding a new MCP tool:
1. Add Pydantic model in `models.py` if needed
2. Add DB method in `db.py`
3. Add tool function in `server.py` with `@mcp.tool()` decorator
4. Add test in `tests/`

When adding a new scanner:
1. Create `src/scanner/{name}_scanner.py`
2. Implement `scan(path: str, db: Database) -> ScanResult`
3. Register in `src/scanner/__init__.py`
4. Add test fixtures in `tests/fixtures/`
