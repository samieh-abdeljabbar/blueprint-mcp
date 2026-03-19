# Blueprint MCP — Master Build Plan

## What This Project Is

Blueprint MCP is a codebase awareness tool. You point it at any codebase and it shows you:
- Every component and how they're connected
- What's missing (no auth? no tests? no error handling?)
- What's dead (built but connected to nothing)
- What happens when data flows through the system (like pressing play on an n8n workflow)
- What breaks if you change or remove something (cascade impact)
- WHY each gap matters, teaching architecture fundamentals over time

The audience is developers using Claude Code AND non-technical people learning to understand and prompt about software. Everything must be visually clear, clickable, and explained in plain English.

## Current State (DO NOT REBUILD)

These are done, tested, and working. Do not modify unless a phase specifically says to:

- `src/models.py` — 31 node types, 19 relationship types, 5 statuses, full Pydantic models (214 lines)
- `src/db.py` — SQLite CRUD, cascade deletes, metadata merge, changelog (576 lines)
- `src/server.py` — 15 MCP tools registered (291 lines)
- `src/analyzer.py` — find_issues with critical/warning/info detection (320 lines)
- `src/scanner/` — Python, JavaScript, Docker, file scanners (955 lines total)
- `src/templates/` — 6 templates, registry, apply logic (689 lines total)
- `tests/` — 117 tests, ALL PASSING in 0.43s
- `src/models.py` enums already include extended types (submodule, struct, protocol, view, etc.) and extended relationships (observes, creates, uses, delegates, etc.)

## Phase A — Cleanup (Do First)

**Delete these:**
- `viewer/` directory (entire React app — all .tsx, package.json, package-lock.json, vite.config, tsconfig)
- `src/viewer/` directory (`__init__.py`, `__main__.py`, `serve.py`)
- The `open_viewer` tool from `src/server.py`
- Remove `uvicorn` and `starlette` from `pyproject.toml` dependencies

**After cleanup:**
- Run all tests. Expect 117 passing (or 117 minus any viewer-specific tests — remove those tests too).
- Verify all 14 remaining MCP tools still register: `python -c "from src.server import mcp; import asyncio; tools = asyncio.run(mcp.list_tools()); [print(t.name) for t in tools]"`
- Commit: "Remove React viewer, preparing for D3 X-Ray replacement"

---

## Phase B — Intelligence Tools

Build these three tools. Each one is a separate file in `src/`. Register each as an MCP tool in `src/server.py`.

### B1: `get_project_questions` 

**File:** `src/questions.py`  
**MCP tool name:** `get_project_questions`

**Parameters:**
```json
{
    "category": "string (optional, default: 'all') — Filter: 'all', 'security', 'scaling', 'completeness', 'data', 'operations', 'architecture'",
    "node_id": "string (optional) — Scope to a subtree"
}
```

**What it does:** Runs rule-based checks against the blueprint graph. Each check looks for the PRESENCE or ABSENCE of patterns and generates a question with four parts:
1. **question** — plain English, conversational ("There's no authentication. Who will use this app?")
2. **context** — what was actually found ("Found 0 auth-related nodes. 12 routes have no auth connection.")
3. **fix_prompt** — a ready-made prompt the user can paste into Claude Code to fix the gap
4. **learn_more** — 2-3 sentences explaining WHY this matters in plain English, teaching architecture fundamentals

**Checks to implement (minimum 10):**

CHECK 1 — Authentication:
- Search for nodes with "auth", "login", "jwt", "session", "oauth" in name, or type "middleware"
- If none found → severity: critical, "No authentication found. Who will use this app and how will they log in?"
- If found but routes exist without auth connection → severity: warning, "Auth exists but X routes aren't protected"
- learn_more: "Authentication verifies who is using your app. Without it, anyone who finds your URL can access and modify all data."

CHECK 2 — Database & Storage:
- Search for nodes with type "database", "table", "cache"
- If none → severity: critical, "No database found. Where will this app keep its data?"
- If table exists but nothing writes_to it → severity: warning, "The '{name}' table exists but nothing writes to it. How does data get in?"
- If table exists but nothing reads_from it → severity: info, "The '{name}' table exists but nothing reads from it. Is it still needed?"
- learn_more: "Every app that remembers anything needs a database. Without one, everything resets when the app restarts."

CHECK 3 — Testing:
- Search for nodes with "test", "spec" in name or type "test", or source_file containing "test_", "_test.", ".spec."
- If none → severity: warning, "No tests found. Do you want test coverage?"
- learn_more: "Tests are like spell-check for your code. They catch mistakes before they reach real users."

CHECK 4 — Error Handling:
- Search for "error", "exception", "handler", "fallback", "retry" in names, or type "middleware" with error-related descriptions
- If none → severity: warning, "No error handling found. What happens when something goes wrong?"
- learn_more: "Every app will eventually hit an error. Without error handling, the app crashes and the user sees a scary technical message."

CHECK 5 — Scaling / Multi-tenancy:
- Search for "user", "team", "organization", "tenant", "role", "permission" in names
- If none → severity: info, "No user or team concepts found. Is this single-user or multi-user?"
- If database exists but no cache → severity: info, "Database found but no caching layer. Will this handle heavy traffic?"
- learn_more: "A database handles ~1000 requests/sec. A cache handles 100,000+. For many users, caching prevents bottlenecks."

CHECK 6 — Orphaned / Dead Components:
- Find nodes with zero edges (not system, config, or file types)
- For each → severity: warning, "'{name}' exists but isn't connected to anything. Is it dead code?"
- learn_more: "Dead code is like a room with no doors. It takes up space but nobody can reach it. Removing it makes the project cleaner."

CHECK 7 — External Dependencies Without Fallbacks:
- Find nodes with type "external" that have 3+ other nodes depending on them
- severity: warning, "'{name}' is an external service that X components depend on. What if it goes down?"
- learn_more: "External services will go down eventually. Good architecture has fallback plans — retry, queue for later, or degrade gracefully."

CHECK 8 — Planned But Stale:
- Find nodes with status "planned" where created_at is older than 14 days
- severity: info, "'{name}' has been planned for X days but not built. Still needed?"
- learn_more: "Planned components sitting unbuilt for weeks are often features that seemed important but turned out unnecessary."

CHECK 9 — Data Flow Integrity:
- Find routes that have writes_to edges to tables but no validation/middleware node in between (check the path)
- severity: warning, "Route '{name}' writes directly to '{table}' with no validation layer."
- learn_more: "When data goes straight from user input into your database without validation, bad things happen — wrong data types, empty fields, or even malicious code."

CHECK 10 — Logging & Monitoring:
- Search for "log", "monitor", "metrics", "observability" in names
- If none → severity: info, "No logging found. How will you know when something goes wrong in production?"
- learn_more: "Logging is like a security camera for your app. When something breaks at 3 AM, logs tell you what happened."

CHECK 11 — Configuration Management:
- Search for "config", "env", "secret", "settings" in names or type "config"
- If none → severity: info, "No configuration management found. Where are API keys and settings stored?"
- learn_more: "Hardcoding API keys in your code is dangerous. If your code is ever shared or leaked, all your secrets are exposed."

**Return format:**
```json
{
    "project_name": "string",
    "total_questions": 12,
    "by_severity": {"critical": 2, "warning": 6, "info": 4},
    "by_category": {"security": 3, "data": 2, "completeness": 3, "scaling": 2, "operations": 1, "architecture": 1},
    "questions": [
        {
            "id": "q-001",
            "category": "security",
            "severity": "critical",
            "question": "There's no authentication. Who will use this app?",
            "context": "Found 0 auth-related components.",
            "fix_prompt": "Add JWT authentication...",
            "learn_more": "Authentication verifies who is using your app...",
            "related_nodes": [],
            "highlight_nodes": ["node-id-1", "node-id-2"]
        }
    ]
}
```

**Tests (in `tests/test_questions.py`):**
All tests use real in-memory SQLite databases. No mocking.
- Create blueprint with NO auth nodes → returns auth critical question
- Create blueprint WITH auth but 3 routes not connected to it → returns warning naming those routes
- Create blueprint with no database → returns data critical question
- Create blueprint with table + no writers → returns question naming that specific table
- Create blueprint with no test nodes → returns testing question
- Create blueprint with 2 orphaned nodes → returns dead code warning for EACH one by name
- Create blueprint with external service + 4 dependents → returns fallback question
- Create blueprint with planned node, manually set created_at to 30 days ago → returns stale question with "30 days"
- Create blueprint with everything (auth connected to all routes, database, tests, error handling, logging, config) → returns ZERO critical questions
- Category filter: category="security" returns ONLY security-related questions
- Every question has non-empty fix_prompt and learn_more
- highlight_nodes contains actual node IDs that exist in the database

---

### B2: `get_review_prompt`

**File:** `src/review.py`  
**MCP tool name:** `get_review_prompt`

**Parameters:**
```json
{
    "focus": "string (optional, default: 'all') — 'architecture', 'security', 'performance', 'completeness', 'connections', 'all'",
    "node_id": "string (optional) — Scope to subtree"
}
```

**What it does:** Generates a structured text document (NOT JSON) that is optimized for Claude or any LLM to read and give architectural advice. This tool does NOT call an LLM — it prepares the data.

**Output structure:**
```
=== ARCHITECTURE REVIEW REQUEST ===
PROJECT: [name]
GENERATED: [timestamp]

--- SYSTEM OVERVIEW ---
Total nodes: X (Y built, Z planned, W broken)
Total connections: X
Issues found: X critical, Y warning, Z info

--- ARCHITECTURE LAYERS ---
[Hierarchical tree view of all nodes grouped by parent, with connections listed for each]

--- CONNECTIONS MAP ---
[Every edge listed as: Source → Target (relationship, "label")]

--- CURRENT ISSUES ---
[Output from find_issues]

--- GAPS DETECTED ---
[Summary from get_project_questions — just the questions, not the full objects]

--- REVIEW QUESTIONS ---
[Targeted questions based on focus parameter]
```

**Tests:**
- Generate for SaaS template → contains all 12 node names
- Generate with focus="security" → only security review questions
- Generate scoped to subtree → only that subtree's nodes
- Empty blueprint → valid output with "no components found"

---

### B3: `impact_analysis`

**File:** `src/impact.py`  
**MCP tool name:** `impact_analysis`

**Parameters:**
```json
{
    "node_id": "string (required) — Node to analyze",
    "depth": "integer (optional, default: -1) — Hops to trace. -1 = unlimited",
    "direction": "string (optional, default: 'downstream') — 'downstream', 'upstream', 'both'"
}
```

**What it does:** BFS graph traversal from the target node. Follows edges in the specified direction. Tracks visited nodes to avoid cycles. Returns every affected node organized by depth level.

**Returns:**
```json
{
    "source_node": {"id": "...", "name": "users table", "type": "table"},
    "direction": "downstream",
    "impact_chain": [
        {"depth": 1, "nodes": [{"id": "...", "name": "Auth", "relationship": "reads_from"}]},
        {"depth": 2, "nodes": [{"id": "...", "name": "POST /login", "relationship": "calls"}]}
    ],
    "total_affected": 5,
    "critical_paths": ["users → Auth → POST /login"],
    "summary": "Changing 'users table' affects 5 components across 2 levels."
}
```

**Tests:**
- Linear chain A→B→C: returns B at depth 1, C at depth 2
- Fan-out A→B, A→C, A→D: returns all three at depth 1
- Circular A→B→A: doesn't infinite loop, returns both
- Upstream from leaf: traces back to root
- Isolated node: returns empty impact
- Depth limit respected: depth=1 only returns immediate connections
- Direction="both": returns upstream AND downstream

---

## Phase C — Flow Tools

### C1: `list_entry_points`

**File:** `src/tracer.py` (same file as trace_flow)  
**MCP tool name:** `list_entry_points`

**What it does:** Finds all "front doors" — nodes that receive input from outside the system. These are the things you can press play on.

Entry points are:
- Nodes with type: route, api, webhook, view
- Nodes with only outgoing edges (nothing calls them from inside the system)
- Root-level nodes with no parent

**Returns:**
```json
{
    "entry_points": [
        {
            "node": {"id": "...", "name": "POST /api/orders", "type": "route"},
            "description": "Handles new order submissions",
            "connections_out": 4,
            "suggested_trigger": "User submits a new order"
        }
    ],
    "total": 3
}
```

---

### C2: `trace_flow`

**File:** `src/tracer.py`  
**MCP tool name:** `trace_flow`

**Parameters:**
```json
{
    "start_node_id": "string (required)",
    "trigger": "string (optional) — Plain English description like 'user submits order'",
    "max_depth": "integer (optional, default: 20)",
    "include_error_paths": "boolean (optional, default: true)"
}
```

**What it does:** Starting from a node, follows all outgoing edges step by step (BFS). At each step, records:
- Step number and node details
- How we got here (which edge/relationship)
- Whether the path branches
- Gap detection at every step:
  - DEAD END: node has no outgoing edges (flow stops)
  - NO ERROR HANDLING: no error/fallback node connected
  - UNPROTECTED WRITE: writes to database with no auth in the path
  - NO VALIDATION: writes to database with no validation in between
  - NO FALLBACK: calls external service with nothing catching failures

**Returns:**
```json
{
    "flow_name": "User submits order",
    "start_node": {"id": "...", "name": "POST /api/orders"},
    "total_steps": 7,
    "total_branches": 1,
    "gaps_found": 2,
    "steps": [
        {
            "step": 1,
            "node": {"id": "...", "name": "POST /api/orders", "type": "route"},
            "action": "Receives incoming request",
            "via": null,
            "status": "ok",
            "branches_to": null,
            "gaps": []
        },
        {
            "step": 6,
            "node": {"id": "...", "name": "Notification Service", "type": "service"},
            "action": "Sends confirmation email",
            "via": {"relationship": "calls"},
            "status": "warning",
            "branches_to": null,
            "gaps": [
                {
                    "type": "no_error_handling",
                    "severity": "warning",
                    "message": "If email fails, nothing catches the error.",
                    "fix_prompt": "Add error handling around notification service...",
                    "learn_more": "External services fail sometimes. Always wrap them in try/catch..."
                }
            ]
        }
    ],
    "dead_ends": [],
    "flow_summary": "Request → Auth → Validation → Handler → [orders + Notification] → Response. 1 warning."
}
```

**Tests:**
- Linear A→B→C→D: 4 steps in order
- Branch A→B, A→C: branch detected at A
- Dead end A→B→nothing: B marked as dead end
- Circular A→B→A: detects cycle, stops
- Route→table with no auth in path: unprotected write detected
- Route→auth→table: NO unprotected write gap
- Route→external with no error handler: no_fallback gap
- max_depth=2 stops at 2 steps

---

### C3: `what_if`

**File:** `src/whatif.py`  
**MCP tool name:** `what_if`

**Parameters:**
```json
{
    "node_id": "string (required)",
    "scenario": "string (required) — 'remove', 'break', 'disconnect', 'overload'"
}
```

**Scenarios:**
- `remove`: What if this didn't exist? Find everything that would lose a connection, become orphaned, or have broken flows.
- `break`: What if this stops working? Same analysis but check for error handling and fallbacks.
- `disconnect`: What if all connections to/from this are cut? What becomes unreachable?
- `overload`: What if this gets 100x traffic? Check for caches, queues, load balancing.

**Returns:**
```json
{
    "scenario": "break",
    "target_node": {"name": "Primary Database"},
    "directly_affected": [{"name": "API Service", "has_fallback": false}],
    "indirectly_affected": [{"name": "Frontend", "cascade_path": "DB → API → Frontend"}],
    "broken_flows": ["User login breaks at step 3", "Order submission breaks at step 5"],
    "resilience_score": "2/10",
    "recommendations": [
        {
            "priority": "critical",
            "suggestion": "Add Redis cache for read-heavy queries",
            "fix_prompt": "Add a Redis cache layer...",
            "learn_more": "A cache keeps copies of frequently accessed data..."
        }
    ],
    "summary": "If database breaks, 8/12 components fail. No fallbacks. Score: 2/10."
}
```

**Tests:**
- Remove node with 3 dependents: all 3 listed as directly affected
- Break node with error handler: has_fallback=true
- Break node without error handler: has_fallback=false
- Disconnect: orphaned nodes correctly found
- Overload node with cache: better resilience score than without
- Unaffected nodes listed correctly
- Broken flows include the step where they break

---

## Phase D — Codebase X-Ray Viewer

**THIS IS THE MOST IMPORTANT PHASE. THE VISUAL MUST BE CLEAN, SPACED, AND USABLE.**

**File:** `src/xray.py` — Python generates a single self-contained HTML file  
**MCP tool name:** `render_blueprint`

**Parameters:**
```json
{
    "output_path": "string (optional, default: '.blueprint.html')",
    "theme": "string (optional, default: 'light') — 'light' or 'dark'"
}
```

**What it does:**
1. Reads all nodes and edges from .blueprint.db
2. Calls find_issues for health data
3. Calls get_project_questions for questions data
4. Embeds everything as a JSON blob inside a `<script>` tag
5. Generates a single .html file with D3.js loaded from CDN
6. Opens in default browser

**The HTML file must be completely self-contained. No npm. No build step. No server. Just one .html file that works when double-clicked.**

---

### VISUAL DESIGN REQUIREMENTS (NON-NEGOTIABLE)

**SPACING:**
- Minimum 80px between nodes horizontally
- Minimum 60px between nodes vertically
- Minimum 40px padding inside group containers
- Group container titles get 50px top padding so children don't overlap the title
- Minimum node width: 250px
- Minimum node height: 80px (taller if description is shown)
- The map should feel SPACIOUS, not cramped. When in doubt, add more space.
- On first load, the graph should be centered and zoomed to fit all nodes with comfortable padding

**NODES:**
- Rounded rectangles with subtle shadow
- Name in bold, 14px font
- Type shown as a small colored badge pill (e.g., "module" in blue, "function" in purple, "route" in orange, "database" in green, "table" in teal)
- Description below the name in 11px gray text, truncated to 60 chars, full text on hover tooltip
- Source file path at bottom in 10px monospace gray
- Left border colored by status: green=built, blue=planned, yellow=in_progress, red=broken, gray=deprecated
- Nodes must be DRAGGABLE — user can rearrange and they stay where put

**GROUP CONTAINERS (parent nodes):**
- Larger rounded rectangle with very subtle background tint (e.g., light blue at 5% opacity)
- Title at top-left in bold 16px with the child count: "Kernel (4 components)"
- Clear visual separation from children — the group is a CONTAINER, not just another node
- Children arranged inside with the spacing rules above
- Collapsible — click the group title to collapse/expand children
- When collapsed, shows just the title and a summary: "Kernel — 4 components, 3 built, 1 planned"

**EDGES (connections):**
- Smooth bezier curves, NOT straight lines
- 1.5px stroke width for normal edges, 2.5px for highlighted
- Color by relationship type:
  - calls, connects_to → blue (#3B82F6)
  - reads_from → green (#10B981)
  - writes_to → orange (#F59E0B)
  - depends_on → purple (#8B5CF6)
  - authenticates → red (#EF4444)
  - all others → gray (#9CA3AF)
- Labels HIDDEN by default — shown only on hover over the edge
- Animated dashed pattern for planned-status edges
- When a node is selected, its edges become full opacity and everything else dims to 20%

**CLICK INTERACTIONS:**
- Click a node → it highlights, connected nodes highlight at 60% opacity, everything else dims to 20%, edges to/from selected node animate, right panel shows node details
- Click empty space → deselect, everything returns to normal
- Double-click a group → zoom into that group (progressive disclosure)
- Breadcrumb navigation at top: "Project > Kernel > Topology" — click any level to zoom back out
- All nodes are draggable

**MINIMAP:**
- Bottom-right corner, 200x150px
- Shows the full graph in miniature with a viewport rectangle
- Click/drag the viewport rectangle to pan the main view

---

### THE THREE-PANEL LAYOUT

**TOP BAR (full width, 50px height):**
- Search box on the left: type to filter, matching nodes highlight on map
- Filter toggle buttons: [Built ✓] [Planned ✓] [Broken ✓] [Orphaned ✓] — click to toggle visibility
- "Last scanned: March 16, 2026 8:41 PM" on the right
- Project name centered

**LEFT PANEL — THE MAP (65% width):**
- D3.js force-directed graph with the visual rules above
- Play ▶ button appears on hover over any node (for trace_flow)
- What-if ⚡ button appears on hover (for what_if simulations)
- Zoom controls: + and - buttons in bottom-left corner, plus scroll to zoom

**RIGHT PANEL — INSIGHT PANEL (35% width, 3 tabs):**

**Tab 1: DETAILS (shown when a node is selected)**
```
╔═══════════════════════════════════╗
║ 🔧 Auth Middleware                ║
║ Type: middleware          [built] ║
╠═══════════════════════════════════╣
║                                   ║
║ JWT authentication and session    ║
║ management for all API routes.    ║
║                                   ║
║ 📁 src/middleware/auth.py         ║
║                                   ║
║ ── Sends data to ──               ║
║ → users table (reads_from)        ║
║ → sessions table (writes_to)      ║
║                                   ║
║ ── Receives data from ──          ║
║ ← POST /api/login (calls)        ║
║ ← POST /api/register (calls)     ║
║                                   ║
║ ── Impact ──                      ║
║ If this changes, 6 components     ║
║ are affected.                     ║
║                                   ║
║ [▶ Trace flow] [⚡ What if?]      ║
╚═══════════════════════════════════╝
```
Every node name in the connections list is CLICKABLE — clicking it selects that node on the map and scrolls to it.

**Tab 2: HEALTH (always available, no selection needed)**
```
╔═══════════════════════════════════╗
║ PROJECT HEALTH          Score: B  ║
║                         73/100    ║
╠═══════════════════════════════════╣
║                                   ║
║ ✅ Authentication     Found       ║
║    Auth Module → 4 routes         ║
║                                   ║
║ ❌ Error Handling     Not found   ║
║    No error handlers detected     ║
║                                   ║
║ ✅ Database           Found       ║
║    PostgreSQL, 7 tables           ║
║                                   ║
║ ❌ Tests              Not found   ║
║    0 test files detected          ║
║                                   ║
║ ⚠️ Caching           Planned     ║
║    Redis planned, not built       ║
║                                   ║
║ ❌ Logging            Not found   ║
║                                   ║
║ ⚠️ Dead Code         3 found     ║
║    3 orphaned components          ║
║                                   ║
║ ❌ Input Validation   Not found   ║
║    Routes write directly to DB    ║
║                                   ║
╚═══════════════════════════════════╝
```
Each row is CLICKABLE — clicking "Authentication: Found" highlights all auth-related nodes on the map. Clicking "Dead Code: 3 found" highlights all orphaned nodes.

**Tab 3: QUESTIONS (from get_project_questions)**
```
╔═══════════════════════════════════╗
║ QUESTIONS          12 found       ║
║ 🔴 2 critical  🟡 6 warning      ║
╠═══════════════════════════════════╣
║                                   ║
║ ┌───────────────────────────────┐ ║
║ │ 🔴 CRITICAL — Security       │ ║
║ │                               │ ║
║ │ "There's no authentication.   │ ║
║ │  Who will use this app?"      │ ║
║ │                               │ ║
║ │ Found 0 auth components.      │ ║
║ │                               │ ║
║ │ [Show on map] [Copy fix]      │ ║
║ │                               │ ║
║ │ ▶ Why this matters            │ ║
║ │ Authentication verifies who   │ ║
║ │ is using your app. Without    │ ║
║ │ it, anyone can access and     │ ║
║ │ modify all your data...       │ ║
║ └───────────────────────────────┘ ║
║                                   ║
║ ┌───────────────────────────────┐ ║
║ │ 🟡 WARNING — Data            │ ║
║ │                               │ ║
║ │ "The 'orders' table exists    │ ║
║ │  but nothing writes to it."   │ ║
║ │                               │ ║
║ │ [Show on map] [Copy fix]      │ ║
║ │ [▶ Why this matters]          │ ║
║ └───────────────────────────────┘ ║
╚═══════════════════════════════════╝
```
- [Show on map] highlights the related nodes on the map
- [Copy fix] copies the fix_prompt to clipboard with a "Copied!" toast notification
- [▶ Why this matters] expands the learn_more text inline

---

### FLOW TRACE ANIMATION (when user clicks ▶ on a node)

1. All nodes dim to 20% opacity
2. Starting node glows with a pulsing blue border
3. After 0.8 seconds, an animated dot (10px circle, bright blue) travels along the edge to the next node
4. Next node lights up — GREEN border if status=ok, YELLOW if warning, RED if error
5. Dot continues to each subsequent step with 0.8 second delay
6. At branches: dot splits into multiple dots going different directions simultaneously
7. At gaps: node flashes yellow/red, a tooltip appears with the gap message
8. At dead ends: dot hits a visible wall (red X icon) and stops

**Flow control bar appears at bottom of map during playback:**
```
[⏮] [◀ Back] [⏸ Pause] [▶ Next] [⏭]   Speed: [0.5x] [1x] [2x]   Step 4 of 7: "Order Handler"
```

After animation completes:
- All flow nodes stay highlighted
- Gaps marked with warning/error icons that persist
- Right panel switches to a FLOW RESULTS view showing all steps and gaps
- User can click any step to jump to that node

---

### WHAT-IF SIMULATION (when user clicks ⚡ on a node)

Dropdown appears: "What if this..." → [Is removed] [Breaks] [Is disconnected] [Gets overloaded]

User selects "Breaks":

1. Target node turns RED and pulses
2. Red ripple wave animates outward along edges (0.5 second per hop)
3. Directly affected nodes turn ORANGE
4. Second ripple: indirectly affected turn YELLOW
5. Unaffected nodes turn GREEN (immediately visible — "these are safe")
6. Broken flow paths turn into red dashed lines

Right panel shows impact results:
- Resilience score with visual meter (colored bar: red=0-3, yellow=4-6, green=7-10)
- Directly affected list
- Indirectly affected list with cascade paths
- Broken flows
- Recommendations with [Copy fix] buttons and [Why this matters] expandables

---

## Phase E — Snapshots & Export

### E1: `snapshot_blueprint` and `compare_snapshots`

**File:** `src/snapshots.py`

**New SQLite table:**
```sql
CREATE TABLE snapshots (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    node_data TEXT NOT NULL,
    edge_data TEXT NOT NULL,
    node_count INTEGER NOT NULL,
    edge_count INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**Tools:**
- `snapshot_blueprint(name, description?)` → saves current state
- `list_snapshots()` → returns all snapshots
- `compare_snapshots(snapshot_id, compare_to?)` → diffs two states, returns nodes added/removed/changed, edges added/removed

**Tests:**
- Create → snapshot → add nodes → compare → diff shows exactly what was added
- Create → snapshot → delete nodes → compare → diff shows what was removed
- Create → snapshot → change status → compare → shows field change with old/new values
- list_snapshots returns correct count

### E2: `export_mermaid` and `export_markdown`

**File:** `src/export.py`

**Tools:**
- `export_mermaid(scope?)` → returns raw Mermaid syntax string. Use `graph TD`, subgraphs for parent groups, style nodes by status color.
- `export_markdown(scope?)` → returns human-readable markdown architecture doc with sections per layer, connections listed, health summary.

**Tests:**
- Export mermaid → contains all node names, valid syntax
- Export markdown → contains all node names and connections
- Scoped export → only subtree nodes appear

---

## Implementation Order

```
Phase A  →  cleanup (30 min)
Phase B1 →  get_project_questions (1-2 hours)
Phase B2 →  get_review_prompt (30 min)
Phase B3 →  impact_analysis (1 hour)
Phase C1 →  list_entry_points (30 min)
Phase C2 →  trace_flow (1-2 hours)
Phase C3 →  what_if (1-2 hours)
Phase D  →  render_blueprint X-Ray viewer (this is the big one — 3-4 hours)
Phase E1 →  snapshots (1 hour)
Phase E2 →  exports (30 min)
```

Build each phase completely with tests before moving to the next. Run ALL tests after each phase to make sure nothing broke.

---

## Testing Rules (ALL PHASES)

1. Real integration tests against in-memory SQLite — NO mocking
2. Every assertion checks SPECIFIC VALUES, not just "result is not None"
3. Graph traversals: create known structures, assert exact paths and depth levels
4. Questions: create blueprints with specific gaps, assert exact question text and severity
5. Flow traces: create known chains, assert exact step order and gap detection
6. What-if: create known dependency graphs, assert exact affected nodes
7. Viewer: assert generated HTML contains expected node names, D3 script tag, and embedded JSON with correct counts
8. Every fix_prompt and learn_more field is non-empty and specific
9. Run FULL test suite after every phase — all previous tests must still pass

---

## Success Criteria

When everything is built, a user should be able to:

1. `cd` into ANY project with Python, JavaScript, or Docker files
2. Tell Claude Code: "Scan this codebase and show me the blueprint"
3. Claude calls `scan_codebase` → `render_blueprint`
4. Browser opens with a clean, spacious, clickable map of the entire project
5. User clicks around — sees what connects to what, zooms into modules
6. User checks the Health tab — sees green/yellow/red checklist
7. User reads the Questions tab — learns what's missing and WHY
8. User clicks ▶ on an API route — watches data flow through the system
9. User clicks ⚡ on the database — sees what breaks if it goes down
10. User copies a fix prompt — pastes it into Claude Code — gap gets fixed
11. User does this across 5-10 projects and starts intuitively understanding architecture
