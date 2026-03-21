# Fix Layout: Wider Graph + Real Hierarchy

Use ultrathink to plan before writing any code.

Read `src/xray.py` and `src/scanner/javascript_scanner.py` before making changes.

## Problem 1: Vertical Strip Layout

The graph renders as a narrow vertical column instead of using the full canvas width. This is a force configuration issue.

### Fix in `src/xray.py` — `rebuildSimulation()` function:

**A. Kill the global X centering force** — it's pulling everything into one column:

```javascript
// REMOVE or drastically weaken:
.force('x', d3.forceX(gW / 2).strength(0.02))
// REPLACE WITH:
.force('x', d3.forceX(gW / 2).strength(0.003))  // nearly zero — just prevents drift off-screen
```

**B. Weaken the center force:**
```javascript
// Change from:
.force('center', d3.forceCenter(gW / 2, gH / 2).strength(0.03))
// To:
.force('center', d3.forceCenter(gW / 2, gH / 2).strength(0.005))
```

**C. Increase charge repulsion** so nodes push apart horizontally:
```javascript
// Change from:
.force('charge', d3.forceManyBody().strength(-400).distanceMax(600))
// To (clustered mode):
.force('charge', d3.forceManyBody().strength(-600).distanceMax(800))
```

**D. Widen initial node positions:**
```javascript
// Change from something like:
x: gW / 2 + (Math.random() - 0.5) * gW * 0.6
// To:
x: gW * 0.1 + Math.random() * gW * 0.8
```

**E. Add a spread force** that pushes nodes in the same tier band apart horizontally:
```javascript
// Add this new force in clustered mode:
.force('spreadX', d3.forceX(d => {
  // Use a hash of the node name to spread nodes left/right within their tier
  const hash = d.name.split('').reduce((acc, ch) => ((acc << 5) - acc) + ch.charCodeAt(0), 0);
  const norm = ((hash % 1000) + 1000) % 1000 / 1000; // 0 to 1
  return gW * 0.15 + norm * gW * 0.7; // spread across 70% of canvas width
}).strength(0.03))
```

---

## Problem 2: Flat Hierarchy — Everything Has parent=levantservices

The JS scanner currently sets `parent_id=self.root_id` for every node. This means every component, page, hook, and utility all sit at the same level under the project root. There's no intermediate grouping.

### Fix in `src/scanner/javascript_scanner.py`:

**Create directory-based parent nodes** so the hierarchy reflects the file structure:

```
levantservices (system)
├── components (module)         ← NEW parent node
│   ├── ui (module)             ← NEW parent node  
│   │   ├── button (module)
│   │   ├── dialog (module)
│   │   └── card (module)
│   ├── layout (module)         ← NEW parent node
│   │   ├── Navbar (module)
│   │   └── Footer (module)
│   └── shared (module)         ← NEW parent node
│       └── Logo (module)
├── app (module)                ← NEW parent node
│   ├── admin (module)          ← NEW parent node
│   │   ├── blog (module)
│   │   └── team (module)
│   └── (app) (module)          ← pages group
│       ├── apps (route)
│       └── downloads (route)
├── lib (module)                ← NEW parent node
│   └── utils (module)
├── hooks (module)              ← NEW parent node
│   └── useAuth (function)
└── [database tables]           ← from SQL scanner
```

**Implementation approach:**

Add a method that creates parent nodes for significant directories. A "significant directory" is one that contains 2+ scanned files.

```python
async def _create_directory_parents(self, project_root: str):
    """Create parent module nodes for directories that contain multiple components."""
    # Count files per directory from self._module_node_ids
    dir_counts = {}  # rel_dir -> count of files
    dir_files = {}   # rel_dir -> list of (rel_path, node_id)
    
    for rel_path, node_id in self._module_node_ids.items():
        rel_dir = os.path.dirname(rel_path)
        if not rel_dir or rel_dir == '.':
            continue
        if rel_dir not in dir_counts:
            dir_counts[rel_dir] = 0
            dir_files[rel_dir] = []
        dir_counts[rel_dir] += 1
        dir_files[rel_dir].append((rel_path, node_id))
    
    # Create parent nodes for directories with 2+ files
    # Process from deepest to shallowest so children get correct parents
    sorted_dirs = sorted(dir_counts.keys(), key=lambda d: d.count(os.sep), reverse=True)
    dir_node_ids = {}  # rel_dir -> node_id
    
    for rel_dir in sorted_dirs:
        if dir_counts[rel_dir] < 2:
            continue
        
        dir_name = os.path.basename(rel_dir)
        # Skip generic names that don't add value
        if dir_name in ('src', '.'):
            continue
        
        # Find this directory's parent directory node (if it exists)
        parent_dir = os.path.dirname(rel_dir)
        parent_id = dir_node_ids.get(parent_dir, self.root_id)
        
        # Create the directory node
        node_id, _ = await self._track_node(NodeCreateInput(
            name=dir_name,
            type=NodeType.module,
            status=NodeStatus.built,
            parent_id=parent_id,
            description=f"Directory: {rel_dir}",
            metadata={"directory": True, "path": rel_dir},
        ))
        dir_node_ids[rel_dir] = node_id
    
    # Re-parent existing nodes to their directory parent
    for rel_dir, files in dir_files.items():
        parent_node_id = dir_node_ids.get(rel_dir)
        if not parent_node_id:
            continue
        for rel_path, node_id in files:
            # Update the node's parent_id to the directory node
            await self.db.update_node_parent(node_id, parent_node_id)
```

**Call this at the end of the scan, after all nodes are created but before edges:**

In the `scan()` method, add after node scanning and before `_create_deferred_edges()`:

```python
# Phase 2.5: Create directory hierarchy
await self._create_directory_parents(path)
```

**You'll need to add `update_node_parent` to db.py** if it doesn't exist:

```python
async def update_node_parent(self, node_id: str, parent_id: str):
    """Update a node's parent_id."""
    await self.execute(
        "UPDATE nodes SET parent_id = ?, updated_at = ? WHERE id = ?",
        (parent_id, datetime.utcnow().isoformat(), node_id)
    )
```

### How this improves the X-Ray viewer:

With directory parents, the viewer's group boxes become meaningful:
- "COMPONENTS (15)" groups all UI components
- "UI (8)" groups shared UI primitives inside components
- "APP (12)" groups all pages/routes
- "LIB (3)" groups utilities

The hierarchical layout forces push children near their parents, creating visual clusters that match the actual file structure. Instead of 100 nodes floating independently, you get 5-8 groups with nodes nested inside them.

### Important: Skip `src/` as a parent

Most Next.js/React projects have everything under `src/`. Creating a `src` parent node that contains everything defeats the purpose. Skip it:

```python
SKIP_DIRS = {'src', 'app', 'pages'}  # too broad to be useful parents
# Only skip 'src' and 'app' at the TOP level (1 segment deep)
# app/admin should still create a parent, but top-level app/ is too broad
if dir_name in SKIP_DIRS and rel_dir.count(os.sep) == 0:
    continue
```

Actually — `app` IS useful because Next.js `app/` has sub-routes. Only skip `src/`:

```python
if dir_name == 'src' and rel_dir == 'src':
    continue
```

---

## Problem 3: Tier Y values need wider gaps

The current tier bands are too close together (0.05 to 0.90). Spread them out and use the hierarchy:

```javascript
const TIER_Y = {
  // System — very top
  system: 0.03, container: 0.03,
  service: 0.08, worker: 0.08,
  
  // Code Layer — top third
  module: 0.30, function: 0.35, class_def: 0.32,
  struct: 0.33, protocol: 0.33,
  
  // API Layer — middle (clear gap above and below)
  api: 0.50, route: 0.52, webhook: 0.50, middleware: 0.48,
  
  // Data Layer — bottom third (well separated from code)
  database: 0.72, table: 0.75,
  cache: 0.70, queue: 0.70,
  
  // Config/Files — very bottom
  file: 0.92, script: 0.92, config: 0.90, migration: 0.90,
  external: 0.88, submodule: 0.88,
  model: 0.55, schema: 0.55, enum_def: 0.55,
  view: 0.75, util: 0.38, test: 0.95,
};
```

And strengthen the tier force for data nodes so they stay in their band:

```javascript
.force('tierY', d3.forceY(d => {
  const tier = TIER_Y[d.type];
  return (tier !== undefined ? tier : 0.5) * gH;
}).strength(d => {
  // Data layer gets stronger pull to stay separated from UI
  if (['database', 'table', 'cache', 'queue', 'view'].includes(d.type)) return 0.6;
  if (['route', 'api', 'middleware', 'webhook'].includes(d.type)) return 0.5;
  if (['file', 'config', 'script', 'migration'].includes(d.type)) return 0.4;
  return 0.2;  // UI/code layer — looser, lets hierarchy clustering dominate
}))
```

---

## After Implementation

```bash
pytest tests/test_scanner.py -v    # scanner tests pass  
pytest tests/ -v                    # all tests pass
```

Then delete levantservices .blueprint.db and re-scan fresh:
```
# In Claude Code inside levantservices:
Remove all existing nodes, re-scan this project, and render the visualization
```

Verify:
1. Graph uses full canvas width, not a narrow vertical strip
2. Components are grouped by directory (components/, app/, lib/, hooks/)
3. Database tables are clearly below the UI components  
4. Group boxes show directory names (COMPONENTS, UI, APP, LIB)
5. Clicking a group box shows its children nested inside
6. The layout reads top-to-bottom: System → UI Components → API Routes → Database → Config
