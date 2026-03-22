# X-Ray Polish: Colors, Readability, Questions, Architecture Breakdown

Use ultrathink to plan before writing any code.

Read `src/xray.py` fully before making changes.

## Fix 1: Group Card Colors by Content Type (Light + Dark Mode)

**Problem:** All group cards in Level 1 are the same blue. You can't tell at a glance which groups contain UI components vs database tables vs utilities.

**Fix:** Color each group card based on the dominant node type of its children. Use the existing TYPE_COLORS categories but at a softer tint for the card background.

### Determine dominant type per group:

When building the overview data, compute what's inside each group:

```javascript
function getGroupColor(group) {
  // Count child types
  const typeCounts = {};
  group.descendants.forEach(n => {
    const category = getTypeCategory(n.type);
    typeCounts[category] = (typeCounts[category] || 0) + 1;
  });
  
  // Find dominant category
  let dominant = 'Code'; // default
  let maxCount = 0;
  Object.entries(typeCounts).forEach(([cat, count]) => {
    if (count > maxCount) { maxCount = count; dominant = cat; }
  });
  
  return TYPE_CATEGORIES[dominant]?.color || '#3b82f6';
}

function getTypeCategory(type) {
  for (const [cat, info] of Object.entries(TYPE_CATEGORIES)) {
    if (info.types.includes(type)) return cat;
  }
  return 'Code';
}
```

### Color mapping for group cards:

| Group Contains Mostly | Card Color | Example Groups |
|---|---|---|
| modules (components) | Blue `#3b82f6` | components, layout, shared, home |
| routes/api | Green `#10b981` | app (pages), api |
| tables/database | Amber `#f59e0b` | database tables group |
| config/files | Gray `#6b7280` | config, types |
| utilities/lib | Purple `#8b5cf6` | lib, supabase |
| external | Red `#ef4444` | external services |

### Apply to card rendering:

```javascript
// In renderOverview(), when drawing group cards:
const groupColor = getGroupColor(group);

// Card background — very subtle tint
cardG.append('rect')
  .attr('width', cardW).attr('height', cardH)
  .attr('rx', 12).attr('ry', 12)
  .attr('fill', groupColor)
  .attr('fill-opacity', theme === 'dark' ? 0.12 : 0.06)
  .attr('stroke', groupColor)
  .attr('stroke-opacity', theme === 'dark' ? 0.3 : 0.2)
  .attr('stroke-width', 1.5);

// Left color bar (like node cards)
cardG.append('rect')
  .attr('width', 4).attr('height', cardH)
  .attr('rx', 2)
  .attr('fill', groupColor)
  .attr('fill-opacity', 0.6);
```

### Theme-aware CSS variables:

Add to the existing CSS variable system:

```css
[data-theme="dark"] {
  --card-tint-opacity: 0.12;
  --card-border-opacity: 0.3;
  --card-text: #e2e8f0;
  --card-subtitle: #94a3b8;
  --card-stats: #64748b;
}
[data-theme="light"] {
  --card-tint-opacity: 0.06;
  --card-border-opacity: 0.2;
  --card-text: #1e293b;
  --card-subtitle: #475569;
  --card-stats: #64748b;
}
```

### Add a small type composition bar on each card:

Below the card title, show a thin horizontal bar that's segmented by type category:

```javascript
// Type composition bar (like a mini stacked bar chart)
const barY = cardH - 14;
const barW = cardW - 16;
let barX = 8;
const total = group.descendants.length;

Object.entries(typeCounts).forEach(([cat, count]) => {
  const w = (count / total) * barW;
  cardG.append('rect')
    .attr('x', barX).attr('y', barY)
    .attr('width', w).attr('height', 6)
    .attr('rx', 3)
    .attr('fill', TYPE_CATEGORIES[cat]?.color || '#6b7280')
    .attr('fill-opacity', 0.5);
  barX += w;
});
```

---

## Fix 2: Level 2 Edge Readability

**Problem:** When drilled into a group, edges to external reference (ghost) nodes curve wildly across the canvas and are hard to follow.

### Fix A: Position ghost nodes closer to the boundary

Ghost nodes (external references) should be positioned at the edge of the visible group, not scattered far away:

```javascript
// When creating ghost nodes in renderGroup():
// Position them in a row at the top or bottom of the canvas
const ghostNodes = externalRefs.map((ref, i) => ({
  ...ref,
  x: gW * 0.1 + (i / externalRefs.length) * gW * 0.8,
  y: 40,  // top row for incoming external refs
  // or gH - 40 for outgoing
  _isGhost: true,
  fx: null, fy: null  // let simulation position, but with strong Y pull
}));
```

### Fix B: Style ghost edges differently

```css
.ghost-edge {
  stroke-dasharray: 8 4;
  opacity: 0.2;
}
.ghost-edge:hover {
  opacity: 0.6;
}
```

### Fix C: Label ghost nodes with their source group

Instead of just showing the node name, show "NodeName (from groupName)":

```javascript
// Ghost node label
ghostG.append('text')
  .attr('class', 'ghost-origin')
  .attr('x', 0).attr('y', h + 14)
  .attr('text-anchor', 'middle')
  .attr('font-size', '9px')
  .attr('fill', 'var(--text-muted)')
  .attr('opacity', 0.5)
  .text('from ' + ref.sourceGroup);
```

---

## Fix 3: Enhanced Questions Tab

**Problem:** The Questions tab exists but could be more useful for beginners. It should feel like a checklist of things to investigate, not a wall of text.

### Add priority icons and categories:

```javascript
function renderQuestions() {
  if (!DATA.questions || DATA.questions.length === 0) {
    document.getElementById('tab-questions').innerHTML = 
      '<div class="detail-empty"><p>No questions detected — your architecture looks clean!</p></div>';
    return;
  }

  let h = '<div class="questions-header">';
  h += '<div class="questions-count">' + DATA.questions.length + ' questions to investigate</div>';
  h += '</div>';

  // Group questions by category
  const grouped = {};
  DATA.questions.forEach(q => {
    const cat = q.category || 'general';
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(q);
  });

  // Category icons and labels
  const catIcons = {
    security: '🔒',
    completeness: '📋',
    data_flow: '🔄',
    reliability: '⚡',
    testing: '🧪',
    general: '💡'
  };

  const catLabels = {
    security: 'Security',
    completeness: 'Missing Pieces',
    data_flow: 'Data Flow',
    reliability: 'Reliability',
    testing: 'Testing',
    general: 'General'
  };

  Object.entries(grouped).forEach(([cat, questions]) => {
    const icon = catIcons[cat] || '💡';
    const label = catLabels[cat] || cat;
    
    h += '<div class="question-category">';
    h += '<div class="question-category-header">' + icon + ' ' + label + ' (' + questions.length + ')</div>';
    
    questions.forEach(q => {
      h += '<div class="question-card" data-highlight=\'' + JSON.stringify(q.highlight_nodes || []) + '\'>';
      h += '<div class="question-text">' + esc(q.question) + '</div>';
      if (q.context) {
        h += '<div class="question-context">' + esc(q.context) + '</div>';
      }
      if (q.fix_prompt) {
        h += '<div class="question-fix">💡 Fix: ' + esc(q.fix_prompt) + '</div>';
      }
      if (q.learn_more) {
        h += '<div class="question-learn">📖 ' + esc(q.learn_more) + '</div>';
      }
      h += '</div>';
    });
    
    h += '</div>';
  });

  document.getElementById('tab-questions').innerHTML = h;

  // Click a question to highlight nodes
  document.querySelectorAll('.question-card').forEach(card => {
    card.addEventListener('click', () => {
      const ids = JSON.parse(card.dataset.highlight || '[]');
      highlightNodes(ids);
    });
  });
}
```

### CSS for questions:

```css
.questions-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.questions-count {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.question-category {
  padding: 8px 0;
}
.question-category-header {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  padding: 8px 16px 4px;
}
.question-card {
  padding: 10px 16px;
  margin: 4px 8px;
  border-radius: 8px;
  border-left: 3px solid var(--accent);
  cursor: pointer;
  transition: background 0.15s;
}
.question-card:hover {
  background: var(--bg-tertiary);
}
.question-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 4px;
}
.question-context {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}
.question-fix {
  font-size: 11px;
  color: var(--accent);
  margin-top: 4px;
}
.question-learn {
  font-size: 11px;
  color: var(--text-muted);
  font-style: italic;
  margin-top: 2px;
}
```

---

## Fix 4: Architecture Breakdown Panel (NEW — "Layers" tab)

**Problem:** The viewer shows nodes and connections but doesn't explain the overall structure in plain English. A beginner needs a text-based overview that says "your app has these layers, and here's how data flows through them."

### Add a 4th tab: "Layers"

Add a new tab next to Details / Health / Questions:

```html
<button class="tab-btn" data-tab="layers">Layers</button>
```

```html
<div class="tab-pane" id="tab-layers">
  <!-- filled by renderLayers() -->
</div>
```

### What the Layers tab shows:

A vertical flow diagram in HTML (not D3 — just styled divs) showing the application's architecture layers from top to bottom:

```
┌─────────────────────────────────────────┐
│  🖥️  PRESENTATION LAYER                │
│  Navbar, Footer, Pages, Layouts         │
│  17 components                          │
│  "What the user sees and interacts with"│
└────────────────┬────────────────────────┘
                 │ imports
┌────────────────▼────────────────────────┐
│  🧩  UI PRIMITIVES                      │
│  button, card, input, dialog...         │
│  17 components                          │
│  "Reusable building blocks"             │
└────────────────┬────────────────────────┘
                 │ uses
┌────────────────▼────────────────────────┐
│  📚  BUSINESS LOGIC                     │
│  data, validations, mdx, email          │
│  8 utilities                            │
│  "Where the app's rules and logic live" │
└────────────────┬────────────────────────┘
                 │ reads/writes
┌────────────────▼────────────────────────┐
│  🔌  API & AUTH                         │
│  Supabase client/server, middleware     │
│  4 modules                              │
│  "How your app talks to the server"     │
└────────────────┬────────────────────────┘
                 │ queries
┌────────────────▼────────────────────────┐
│  🗄️  DATA LAYER                        │
│  services, apps, team_members...        │
│  5 tables, 25 columns                   │
│  "Where your data is stored"            │
└─────────────────────────────────────────┘
```

### Implementation:

```javascript
function renderLayers() {
  // Categorize all groups into layers
  const layers = [
    {
      icon: '🖥️',
      name: 'Presentation',
      description: 'What the user sees and interacts with',
      color: '#3b82f6',
      groups: [], // filled below
      nodeTypes: ['route'],
      dirPatterns: ['layout', 'home', 'about', 'contact', 'blog', 'services', 'apps', 'admin']
    },
    {
      icon: '🧩',
      name: 'UI Primitives',
      description: 'Reusable building blocks shared across pages',
      color: '#8b5cf6',
      groups: [],
      nodeTypes: [],
      dirPatterns: ['ui', 'shared']
    },
    {
      icon: '📚',
      name: 'Business Logic',
      description: 'Where the app\'s rules, data fetching, and utilities live',
      color: '#10b981',
      groups: [],
      nodeTypes: ['function'],
      dirPatterns: ['lib', 'utils', 'hooks', 'config', 'types', 'content']
    },
    {
      icon: '🔌',
      name: 'API & Services',
      description: 'How your app talks to servers and external services',
      color: '#f59e0b',
      groups: [],
      nodeTypes: ['middleware', 'service'],
      dirPatterns: ['supabase', 'api', 'server']
    },
    {
      icon: '🗄️',
      name: 'Data Layer',
      description: 'Where your data is stored permanently',
      color: '#ef4444',
      groups: [],
      nodeTypes: ['table', 'database', 'column'],
      dirPatterns: []
    }
  ];

  // Assign each group/node to a layer
  // ... (match by directory name patterns and node types)

  // Count components per layer
  layers.forEach(layer => {
    layer.totalNodes = layer.groups.reduce((sum, g) => sum + g.childCount, 0);
    layer.groupNames = layer.groups.map(g => g.name);
  });

  // Render
  let h = '<div class="layers-container">';
  h += '<div class="layers-title">How Your App Is Organized</div>';
  h += '<div class="layers-subtitle">Data flows from top to bottom</div>';

  layers.forEach((layer, i) => {
    if (layer.totalNodes === 0 && layer.groups.length === 0) return;

    h += '<div class="layer-card" style="border-left-color:' + layer.color + '">';
    h += '<div class="layer-header">';
    h += '<span class="layer-icon">' + layer.icon + '</span>';
    h += '<span class="layer-name">' + layer.name + '</span>';
    h += '<span class="layer-count">' + layer.totalNodes + ' components</span>';
    h += '</div>';
    h += '<div class="layer-description">' + layer.description + '</div>';
    
    if (layer.groupNames.length > 0) {
      h += '<div class="layer-groups">';
      layer.groupNames.forEach(name => {
        h += '<span class="layer-group-pill" onclick="navigateToGroup(\'' + name + '\')">' + name + '</span>';
      });
      h += '</div>';
    }
    h += '</div>';

    // Arrow between layers
    if (i < layers.length - 1) {
      h += '<div class="layer-arrow">▼</div>';
    }
  });

  // Data flow summary
  h += '<div class="layers-flow-summary">';
  h += '<div class="flow-title">Key Data Flows</div>';
  
  // Compute top data flows from edges
  const flows = computeTopFlows();
  flows.forEach(flow => {
    h += '<div class="flow-item">';
    h += '<span class="flow-path">' + flow.path.join(' → ') + '</span>';
    h += '<span class="flow-desc">' + flow.description + '</span>';
    h += '</div>';
  });
  
  h += '</div>';
  h += '</div>';

  document.getElementById('tab-layers').innerHTML = h;
}

function computeTopFlows() {
  // Find the most important data flows:
  // 1. Page → component → data → DB (user-facing read flow)
  // 2. Form → validation → API → DB (user-facing write flow)
  // 3. Most-connected nodes (hub nodes)
  
  const flows = [];
  
  // Find nodes with highest outgoing connections (entry points)
  const outDegree = {};
  DATA.edges.forEach(e => {
    const sid = e.source_id || e.source;
    outDegree[sid] = (outDegree[sid] || 0) + 1;
  });
  
  // Sort by degree, take top 3
  const topNodes = Object.entries(outDegree)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([id, count]) => {
      const node = DATA.nodes.find(n => n.id === id);
      return node ? { name: node.name, count } : null;
    })
    .filter(Boolean);
  
  topNodes.forEach(n => {
    flows.push({
      path: [n.name, '...', 'data layer'],
      description: n.count + ' outgoing connections — a key hub in your app'
    });
  });
  
  return flows;
}
```

### CSS for Layers tab:

```css
.layers-container {
  padding: 16px;
}
.layers-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 4px;
}
.layers-subtitle {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 16px;
}
.layer-card {
  padding: 12px 14px;
  margin-bottom: 4px;
  border-radius: 8px;
  background: var(--bg-secondary);
  border-left: 4px solid;
  transition: background 0.15s;
}
.layer-card:hover {
  background: var(--bg-tertiary);
}
.layer-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.layer-icon {
  font-size: 16px;
}
.layer-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  flex: 1;
}
.layer-count {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: 10px;
}
.layer-description {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 8px;
  font-style: italic;
}
.layer-groups {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.layer-group-pill {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}
.layer-group-pill:hover {
  background: var(--accent);
  color: #fff;
}
.layer-arrow {
  text-align: center;
  color: var(--text-muted);
  font-size: 14px;
  padding: 2px 0;
  opacity: 0.4;
}
.layers-flow-summary {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}
.flow-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 8px;
}
.flow-item {
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
}
.flow-item:last-child {
  border-bottom: none;
}
.flow-path {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  display: block;
}
.flow-desc {
  font-size: 11px;
  color: var(--text-muted);
}
```

---

## After Implementation

```bash
pytest tests/test_xray.py -v    # xray tests pass
pytest tests/ -v                # all tests pass
```

Re-render levantservices and verify:
1. Level 1 group cards have different colors based on content (blue for components, amber for DB, purple for lib)
2. Colors look good in BOTH dark and light themes (toggle to check)
3. Level 2 ghost nodes are positioned at the top, not scattered
4. Questions tab groups by category with icons
5. New "Layers" tab shows the 5-layer architecture breakdown
6. Clicking a group pill in the Layers tab navigates to that group
7. Key Data Flows section shows the most connected components

The Layers tab should make a beginner say: "Oh, my app goes: Pages → UI Components → Business Logic → API → Database. Got it."
