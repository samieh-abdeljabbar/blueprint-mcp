# X-Ray Viewer Round 3: Declutter, Separate Layers, Fix Column Rendering

Use ultrathink to plan before writing any code.

Read `src/xray.py` fully, then `src/models.py` for NodeType enum.

The viewer currently shows 164 nodes and 240 edges for a Next.js project. It's a tall vertical sausage with column nodes (id, name, slug) scattered everywhere, overlapping groups, and unreadable edges. Here are the 4 fixes, in priority order.

---

## Fix 1: Render Columns INSIDE Table Nodes (BIGGEST IMPACT)

**Problem:** Column nodes (id, name, slug, email, created_at, etc.) render as individual floating boxes. A table with 10 columns creates 10 separate nodes cluttering the graph. This accounts for ~40% of all visible nodes.

**Fix:** Column nodes should NOT be part of the force simulation. Instead, render them as rows inside their parent table node — like every database tool does (pgAdmin, DBeaver, dbdiagram.io).

### Step 1: Remove columns from the simulation

In the `buildGraph()` function, after preparing `gNodeData`, separate column nodes from the simulation:

```javascript
// Collect columns grouped by parent table
const columnsByParent = {};
gNodeData.forEach(n => {
  if (n.type === 'column' && n.parent_id) {
    if (!columnsByParent[n.parent_id]) columnsByParent[n.parent_id] = [];
    columnsByParent[n.parent_id].push(n);
  }
});

// Attach columns to their parent table, remove from simulation
gNodeData = gNodeData.filter(n => n.type !== 'column');
gNodeData.forEach(n => {
  if (columnsByParent[n.id]) {
    n._columns = columnsByParent[n.id];
    // Resize table node to fit columns
    n.h = 34 + (n._columns.length * 18) + 6;
    n.w = Math.max(n.w, 200);
  }
});

// Track column IDs so they're excluded from filters/minimap/collapse
const columnNodeIds = new Set();
Object.values(columnsByParent).flat().forEach(c => columnNodeIds.add(c.id));
```

Also update `hiddenNodes`, `applyFilters`, `updateMinimap`, and `isNodeVisible` to ignore column nodes.

### Step 2: Render table nodes as database-style cards

After the normal node rendering section, add special rendering for table nodes with columns:

```javascript
gNodeGroups.filter(d => d._columns && d._columns.length > 0).each(function(d) {
  const g = d3.select(this);
  const headerH = 30;
  
  // Separator line below header
  g.append('line')
    .attr('x1', 4).attr('y1', headerH)
    .attr('x2', d.w).attr('y2', headerH)
    .attr('stroke', 'var(--node-border)').attr('stroke-opacity', 0.4);
  
  d._columns.forEach((col, i) => {
    const y = headerH + 2 + (i * 18);
    const isPK = col.metadata && col.metadata.primary_key;
    const isFK = col.metadata && col.metadata.fk;
    const colType = (col.metadata && col.metadata.data_type) || '';
    
    // Row background (alternating for readability)
    if (i % 2 === 0) {
      g.append('rect')
        .attr('x', 4).attr('y', y)
        .attr('width', d.w - 4).attr('height', 18)
        .attr('fill', 'var(--bg-tertiary)').attr('fill-opacity', 0.3)
        .attr('pointer-events', 'none');
    }
    
    // Key indicator
    let prefix = '  ';
    if (isPK) prefix = '🔑';
    else if (isFK) prefix = '→ ';
    
    g.append('text')
      .attr('x', 10).attr('y', y + 13)
      .attr('font-size', '11px')
      .attr('fill', isPK ? '#f59e0b' : isFK ? '#3b82f6' : 'var(--text-secondary)')
      .text(prefix + ' ' + col.name);
    
    // Column type (right-aligned, muted)
    if (colType) {
      g.append('text')
        .attr('x', d.w - 8).attr('y', y + 13)
        .attr('text-anchor', 'end')
        .attr('font-size', '9px')
        .attr('fill', 'var(--text-muted)')
        .text(colType.toLowerCase());
    }
  });
});
```

### Step 3: Update edges that reference column nodes

Some edges may point to column node IDs. Reroute them to the parent table:

```javascript
// Before creating the edge data, remap column source/target to parent table
gEdgeData.forEach(e => {
  if (columnNodeIds.has(e.source)) {
    // Find parent table
    const col = Object.values(columnsByParent).flat().find(c => c.id === e.source);
    if (col) e.source = col.parent_id;
  }
  if (columnNodeIds.has(e.target)) {
    const col = Object.values(columnsByParent).flat().find(c => c.id === e.target);
    if (col) e.target = col.parent_id;
  }
});
```

### Step 4: Update the detail panel

When a table node with `_columns` is selected, show the columns in the detail panel as a formatted list instead of showing "0 children":

```javascript
// In selectNode(), if nd._columns exists:
if (nd._columns && nd._columns.length > 0) {
  h += '<div class="field-label">Columns (' + nd._columns.length + ')</div>';
  h += '<div class="conn-summary">';
  nd._columns.forEach(col => {
    const isPK = col.metadata && col.metadata.primary_key;
    const isFK = col.metadata && col.metadata.fk;
    const icon = isPK ? '🔑 ' : isFK ? '→ ' : '';
    const colType = (col.metadata && col.metadata.data_type) || '';
    h += '<div style="font-size:12px;padding:2px 0;font-family:monospace">';
    h += icon + esc(col.name);
    if (colType) h += ' <span style="color:var(--text-muted)">' + esc(colType) + '</span>';
    if (isFK) h += ' <span style="color:#3b82f6;font-size:10px">FK→' + esc(col.metadata.fk) + '</span>';
    h += '</div>';
  });
  h += '</div>';
}
```

---

## Fix 2: Separate UI Components from Database Layer

**Problem:** React components (modules), database tables, API routes, and config files are all mixed together in one vertical column. You can't see the layers of your application.

**Fix:** Use horizontal bands — UI at top, API in middle, Data at bottom — with more separation force.

### Update TIER_Y to create distinct horizontal bands with gaps:

```javascript
const TIER_Y = {
  // UI Layer — top 20%
  system: 0.05, container: 0.05,
  service: 0.10, worker: 0.10,
  
  // Code Layer — 20-45%  
  module: 0.30, function: 0.35, class_def: 0.35,
  struct: 0.35, protocol: 0.35,
  
  // API Layer — 45-55% (narrow band in the middle)
  api: 0.48, route: 0.50, webhook: 0.50, middleware: 0.48,
  
  // Data Layer — 60-85% (clearly separated below API)
  database: 0.65, table: 0.70, column: 0.75,
  cache: 0.65, queue: 0.65,
  
  // Files/Config — bottom
  file: 0.88, script: 0.88, config: 0.88, migration: 0.88,
  external: 0.85, submodule: 0.85,
  model: 0.55, schema: 0.55, enum_def: 0.55,
  view: 0.70, util: 0.40, test: 0.90,
};
```

### Increase forceY strength for database nodes:

```javascript
// In rebuildSimulation(), when setting up the clustered layout:
.force('tierY', d3.forceY(d => {
  const tier = TIER_Y[d.type];
  return (tier !== undefined ? tier : 0.5) * gH;
}).strength(d => {
  // Stronger tier force for data layer — keep tables separate from UI
  if (['database', 'table', 'cache', 'queue'].includes(d.type)) return 0.5;
  if (['route', 'api', 'middleware', 'webhook'].includes(d.type)) return 0.4;
  return 0.25;
}))
```

### Add horizontal spread force:

The graph is too narrow vertically. Weaken the global X centering and widen the spread:

```javascript
// Change from:
.force('x', d3.forceX(gW / 2).strength(0.02))
// To:
.force('x', d3.forceX(gW / 2).strength(0.008))  // weaker — let nodes spread wider
```

Also add a layer-aware X spread — nodes in the same tier band should spread horizontally:

```javascript
// Add after the tierY force:
.force('spreadX', d3.forceX(d => {
  // Nudge nodes left or right based on a hash of their name
  // This prevents all nodes in the same tier from stacking vertically
  const hash = d.name.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  const offset = ((hash % 100) / 100 - 0.5) * gW * 0.6;
  return gW / 2 + offset;
}).strength(0.02))
```

---

## Fix 3: Group Overlap Prevention

**Problem:** Group boxes like "BLOG_POSTS (13)" and "SERVICES (11)" overlap each other when they contain many nodes.

**Fix:** Add inter-group repulsion.

After `updateGroupBGs()` computes group bounding boxes, add a force that pushes overlapping groups apart:

```javascript
function groupRepulsionForce() {
  let nodes;
  function force(alpha) {
    // Get current group bounding boxes
    const groups = [];
    gParentIds.forEach(pid => {
      if (collapsedGroups.has(pid)) return;
      const parent = gNodeMap[pid];
      if (!parent) return;
      const children = (gChildrenOf[pid] || [])
        .map(cid => gNodeMap[cid])
        .filter(Boolean)
        .filter(n => !hiddenNodes.has(n.id));
      if (children.length === 0) return;
      const all = [parent, ...children];
      groups.push({
        pid,
        cx: d3.mean(all, n => n.x),
        cy: d3.mean(all, n => n.y),
        children: all,
        x1: d3.min(all, n => n.x - n.w/2) - 50,
        y1: d3.min(all, n => n.y - n.h/2) - 50,
        x2: d3.max(all, n => n.x + n.w/2) + 50,
        y2: d3.max(all, n => n.y + n.h/2) + 50,
      });
    });
    
    // Push overlapping groups apart
    for (let i = 0; i < groups.length; i++) {
      for (let j = i + 1; j < groups.length; j++) {
        const a = groups[i], b = groups[j];
        const overlapX = Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1);
        const overlapY = Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1);
        if (overlapX > 0 && overlapY > 0) {
          const dx = a.cx - b.cx || 1;
          const dy = a.cy - b.cy || 1;
          const pushX = (overlapX * 0.3) * Math.sign(dx) * alpha;
          const pushY = (overlapY * 0.3) * Math.sign(dy) * alpha;
          a.children.forEach(n => { n.vx += pushX; n.vy += pushY; });
          b.children.forEach(n => { n.vx -= pushX; n.vy -= pushY; });
        }
      }
    }
  }
  force.initialize = function(_) { nodes = _; };
  return force;
}
```

Register it in `rebuildSimulation()`:
```javascript
.force('groupRepulsion', groupRepulsionForce())
```

---

## Fix 4: Edge Readability

**Problem:** 240 edges create unreadable spaghetti. All edges look the same.

### 4a: Reduce default edge opacity further

```javascript
// Change from 0.15 to 0.08
.edge-line { fill: none; stroke-width: 1.5; opacity: 0.08; }
```

Edges become near-invisible by default — they only appear when you hover or click a node. This is how large graph tools (Gephi, Neo4j Bloom) handle edge density.

### 4b: Thicken and brighten on hover

```javascript
// On node hover: show connected edges at full opacity with thicker stroke
.edge-group.highlighted .edge-line { stroke-width: 3; opacity: 1; }
```

### 4c: Vary edge dash pattern by relationship category

```css
/* In the CSS section */
.edge-calls { stroke-dasharray: none; }          /* solid — direct calls */
.edge-depends { stroke-dasharray: 8 4; }         /* dashed — dependencies */
.edge-data { stroke-dasharray: 3 3; }            /* dotted — data flow */
.edge-structural { stroke-dasharray: 12 4 2 4; } /* dash-dot — structural */
```

Map relationships to categories when creating edge elements:
```javascript
function edgeDashClass(rel) {
  if (['calls', 'delegates', 'uses'].includes(rel)) return 'edge-calls';
  if (['depends_on', 'inherits', 'implements'].includes(rel)) return 'edge-depends';
  if (['reads_from', 'writes_to', 'updates', 'produces', 'consumes'].includes(rel)) return 'edge-data';
  if (['contains', 'creates', 'controls'].includes(rel)) return 'edge-structural';
  return 'edge-calls';
}
```

### 4d: Layer labels

Add subtle horizontal labels on the left edge of the canvas showing the layer bands:

```javascript
// After building the graph, add layer labels
const layers = [
  { label: 'UI LAYER', y: 0.10 },
  { label: 'CODE', y: 0.30 },
  { label: 'API', y: 0.48 },
  { label: 'DATA', y: 0.68 },
  { label: 'CONFIG', y: 0.88 },
];
const labelG = mainG.append('g').attr('class', 'layer-labels');
layers.forEach(l => {
  labelG.append('text')
    .attr('x', 20)
    .attr('y', l.y * gH)
    .attr('font-size', '10px')
    .attr('font-weight', '700')
    .attr('fill', 'var(--text-muted)')
    .attr('opacity', 0.3)
    .attr('text-transform', 'uppercase')
    .attr('letter-spacing', '2px')
    .text(l.label);
});
```

---

## Fix 5: Increase Canvas Width Usage

**Problem:** The graph renders as a narrow vertical strip, wasting horizontal space.

In `buildGraph()`, when initializing node positions:
```javascript
// Instead of centering everything:
// x: gW / 2 + (Math.random() - 0.5) * gW * 0.6
// Spread wider initially:
x: gW * 0.1 + Math.random() * gW * 0.8
```

And reduce the center force:
```javascript
.force('center', d3.forceCenter(gW / 2, gH / 2).strength(0.01))  // was 0.03
```

---

## After Implementation

```bash
pytest tests/test_xray.py -v    # xray tests pass
pytest tests/ -v                # all tests pass
wc -c src/xray.py               # under 120KB
```

Then re-render levantservices and verify:
1. Column nodes render INSIDE table cards, not as separate floating boxes
2. UI components are clearly separated from database tables
3. Group boxes don't overlap
4. Edges are nearly invisible by default, appear on hover/click
5. The graph uses the full canvas width, not a narrow vertical strip
6. Layer labels (UI / CODE / API / DATA / CONFIG) are visible on the left
7. You can look at the graph and immediately understand the app's architecture
