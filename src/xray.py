"""X-Ray Viewer -- generates a self-contained HTML blueprint visualization with D3.js."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from src.db import Database


async def render_blueprint(
    db: Database,
    output_path: str = ".blueprint.html",
    theme: str = "light",
) -> dict:
    """Render the full blueprint as a single self-contained HTML file with D3.js."""
    data_json, counts = await _build_data_json(db)
    html = _generate_html(data_json, theme)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return {
        "path": output_path,
        "node_count": counts["nodes"],
        "edge_count": counts["edges"],
        "issue_count": counts["issues"],
        "question_count": counts["questions"],
        "theme": theme,
    }


async def _build_data_json(db: Database) -> tuple[str, dict]:
    """Gather all blueprint data and serialize to a JSON string."""
    from src.analyzer import analyze
    from src.questions import get_project_questions

    nodes = await db.get_all_nodes()
    edges = await db.get_all_edges()
    issues = await analyze(db)
    questions_result = await get_project_questions(db)

    # Find project name from first system node, or default
    project_name = "Blueprint"
    for n in nodes:
        if n.type.value == "system":
            project_name = n.name
            break

    now = datetime.now(timezone.utc).isoformat()

    data = {
        "project_name": project_name,
        "generated_at": now,
        "nodes": [n.model_dump() for n in nodes],
        "edges": [e.model_dump() for e in edges],
        "issues": [i.model_dump() for i in issues],
        "questions": questions_result["questions"],
        "questions_summary": questions_result["summary"],
    }

    counts = {
        "nodes": len(nodes),
        "edges": len(edges),
        "issues": len(issues),
        "questions": questions_result["total"],
    }

    return json.dumps(data, default=str), counts


def _generate_html(data_json: str, theme: str) -> str:
    """Assemble the complete HTML string with embedded data and D3.js visualization."""
    return _HTML_TEMPLATE.replace("__BLUEPRINT_DATA__", data_json).replace(
        "__THEME__", theme
    )


# ---------------------------------------------------------------------------
# Self-contained HTML template
# ---------------------------------------------------------------------------
_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en" data-theme="__THEME__">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Blueprint X-Ray</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
/* ---- RESET ---- */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}

/* ---- THEME VARIABLES ---- */
:root {
  --bg: #ffffff;
  --bg-secondary: #f8f9fa;
  --bg-tertiary: #e9ecef;
  --text: #212529;
  --text-secondary: #6c757d;
  --text-muted: #adb5bd;
  --border: #dee2e6;
  --border-light: #e9ecef;
  --accent: #4361ee;
  --accent-hover: #3a56d4;
  --shadow: rgba(0,0,0,0.08);
  --shadow-lg: rgba(0,0,0,0.12);
  --node-bg: #ffffff;
  --node-border: #dee2e6;
  --canvas-bg: #f0f2f5;
  --minimap-bg: rgba(255,255,255,0.92);
  --badge-bg: #e9ecef;
  --badge-text: #495057;
  --tab-active-bg: #ffffff;
  --tab-inactive-bg: #f8f9fa;
  --issue-critical-bg: #fff5f5;
  --issue-critical-border: #fc8181;
  --issue-warning-bg: #fffff0;
  --issue-warning-border: #f6e05e;
  --issue-info-bg: #ebf8ff;
  --issue-info-border: #63b3ed;
  --search-bg: #ffffff;
  --tooltip-bg: #1a202c;
  --tooltip-text: #ffffff;
}

[data-theme="dark"] {
  --bg: #1a1b26;
  --bg-secondary: #24253a;
  --bg-tertiary: #2f3146;
  --text: #c0caf5;
  --text-secondary: #9aa5ce;
  --text-muted: #565f89;
  --border: #3b3d57;
  --border-light: #2f3146;
  --accent: #7aa2f7;
  --accent-hover: #89b4fa;
  --shadow: rgba(0,0,0,0.3);
  --shadow-lg: rgba(0,0,0,0.4);
  --node-bg: #24253a;
  --node-border: #3b3d57;
  --canvas-bg: #16161e;
  --minimap-bg: rgba(26,27,38,0.92);
  --badge-bg: #2f3146;
  --badge-text: #9aa5ce;
  --tab-active-bg: #24253a;
  --tab-inactive-bg: #1a1b26;
  --issue-critical-bg: #2d1b1b;
  --issue-critical-border: #f7768e;
  --issue-warning-bg: #2d2b1b;
  --issue-warning-border: #e0af68;
  --issue-info-bg: #1b2d2d;
  --issue-info-border: #7dcfff;
  --search-bg: #24253a;
  --tooltip-bg: #c0caf5;
  --tooltip-text: #1a1b26;
}

html, body {
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  overflow: hidden;
}

/* ================================================================
   TOP BAR (50px)
   ================================================================ */
#topbar {
  height: 50px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  z-index: 100;
}
#topbar .project-name {
  font-weight: 700;
  font-size: 15px;
  white-space: nowrap;
  color: var(--text);
}
#topbar .timestamp {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}
#search-input {
  flex: 0 1 260px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0 10px;
  font-size: 13px;
  background: var(--search-bg);
  color: var(--text);
  outline: none;
  transition: border-color 0.15s;
}
#search-input:focus { border-color: var(--accent); }
#search-input::placeholder { color: var(--text-muted); }

.filter-group {
  display: flex;
  gap: 4px;
  margin-left: auto;
  flex-wrap: wrap;
}
.filter-btn {
  font-size: 11px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.filter-btn:hover { border-color: var(--accent); color: var(--accent); }
.filter-btn.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
#theme-toggle {
  width: 32px; height: 32px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 14px;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
  flex-shrink: 0;
}
#theme-toggle:hover { border-color: var(--accent); color: var(--accent); }

/* ================================================================
   MAIN LAYOUT — left 65 % canvas, right 35 % panel
   ================================================================ */
#main {
  display: flex;
  height: calc(100% - 50px);
}
#canvas-panel {
  flex: 0 0 65%;
  position: relative;
  background: var(--canvas-bg);
  overflow: hidden;
}
#canvas-panel svg { width: 100%; height: 100%; }

#right-panel {
  flex: 0 0 35%;
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  background: var(--bg);
  overflow: hidden;
}

/* ================================================================
   TABS
   ================================================================ */
.tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
}
.tab-btn {
  flex: 1;
  padding: 10px 0;
  font-size: 13px;
  font-weight: 600;
  border: none;
  background: var(--tab-inactive-bg);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
  border-bottom: 2px solid transparent;
}
.tab-btn:hover { color: var(--text); }
.tab-btn.active {
  background: var(--tab-active-bg);
  color: var(--accent);
  border-bottom-color: var(--accent);
}
.tab-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
.tab-pane { display: none; }
.tab-pane.active { display: block; }

/* ================================================================
   DETAIL PANEL (right — Details tab)
   ================================================================ */
.detail-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  font-size: 14px;
  text-align: center;
  gap: 8px;
}
.detail-empty .icon { font-size: 40px; opacity: 0.3; }

.node-detail { animation: fadeIn 0.2s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

.node-detail h2 {
  font-size: 18px;
  margin-bottom: 4px;
  color: var(--text);
}
.node-detail .node-type-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--badge-bg);
  color: var(--badge-text);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
}
.node-detail .status-indicator {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}
.node-detail .field-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-top: 14px;
  margin-bottom: 4px;
}
.node-detail .field-value {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}
.node-detail .source-file {
  font-family: 'SF Mono', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12px;
  color: var(--accent);
  background: var(--bg-tertiary);
  padding: 4px 8px;
  border-radius: 4px;
  display: inline-block;
}
.connection-list { list-style: none; margin-top: 4px; }
.connection-list li {
  font-size: 12px;
  padding: 4px 0;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-light);
}
.connection-list li:last-child { border-bottom: none; }
.connection-list .rel-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--bg-tertiary);
  color: var(--text-muted);
  margin-right: 4px;
}

/* ================================================================
   HEALTH TAB
   ================================================================ */
.health-summary {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.health-stat {
  flex: 1;
  text-align: center;
  padding: 12px 8px;
  border-radius: 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
}
.health-stat .stat-number {
  font-size: 24px;
  font-weight: 700;
  line-height: 1;
}
.health-stat .stat-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  margin-top: 4px;
}
.health-stat.critical .stat-number { color: #e53e3e; }
.health-stat.warning .stat-number  { color: #d69e2e; }
.health-stat.info .stat-number     { color: #3182ce; }

.issue-card {
  padding: 10px 12px;
  border-radius: 6px;
  margin-bottom: 8px;
  border-left: 3px solid;
  font-size: 13px;
  line-height: 1.5;
}
.issue-card.critical { background: var(--issue-critical-bg); border-color: var(--issue-critical-border); }
.issue-card.warning  { background: var(--issue-warning-bg);  border-color: var(--issue-warning-border);  }
.issue-card.info     { background: var(--issue-info-bg);     border-color: var(--issue-info-border);     }
.issue-card .issue-type {
  font-size: 10px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.5px;
  margin-bottom: 2px;
}
.issue-card.critical .issue-type { color: #e53e3e; }
.issue-card.warning  .issue-type { color: #d69e2e; }
.issue-card.info     .issue-type { color: #3182ce; }
.issue-card .issue-msg { color: var(--text); }
.issue-card .issue-suggestion {
  font-size: 12px; color: var(--text-secondary);
  margin-top: 4px; font-style: italic;
}

/* ================================================================
   QUESTIONS TAB
   ================================================================ */
.question-card {
  padding: 12px;
  border-radius: 6px;
  margin-bottom: 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  cursor: pointer;
  transition: border-color 0.15s;
}
.question-card:hover { border-color: var(--accent); }
.question-card .q-severity {
  font-size: 10px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.5px;
  margin-bottom: 4px;
}
.question-card .q-severity.critical { color: #e53e3e; }
.question-card .q-severity.warning  { color: #d69e2e; }
.question-card .q-severity.info     { color: #3182ce; }
.question-card .q-text {
  font-size: 14px; font-weight: 600;
  color: var(--text); margin-bottom: 4px;
}
.question-card .q-context {
  font-size: 12px; color: var(--text-secondary); line-height: 1.5;
}
.question-card .q-category {
  display: inline-block; font-size: 10px;
  padding: 1px 6px; border-radius: 8px;
  background: var(--bg-tertiary); color: var(--text-muted);
  margin-top: 6px;
}

/* ================================================================
   MINIMAP (200x150 bottom-right)
   ================================================================ */
#minimap {
  position: absolute;
  bottom: 12px; right: 12px;
  width: 200px; height: 150px;
  background: var(--minimap-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 8px var(--shadow);
  z-index: 10;
}
#minimap svg { width: 100%; height: 100%; }
#minimap .viewport-rect {
  fill: var(--accent); fill-opacity: 0.1;
  stroke: var(--accent); stroke-width: 1.5;
}

/* ================================================================
   ZOOM CONTROLS
   ================================================================ */
.zoom-controls {
  position: absolute;
  top: 12px; right: 12px;
  display: flex; flex-direction: column; gap: 4px;
  z-index: 10;
}
.zoom-btn {
  width: 32px; height: 32px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 16px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
  box-shadow: 0 1px 3px var(--shadow);
}
.zoom-btn:hover { border-color: var(--accent); color: var(--accent); }

/* ================================================================
   STATS BAR
   ================================================================ */
.stats-bar {
  display: flex; gap: 12px;
  font-size: 11px; color: var(--text-muted);
}
.stats-bar span { white-space: nowrap; }

/* ================================================================
   D3 GRAPH ELEMENTS
   ================================================================ */
.node-group { cursor: pointer; }
.node-rect { rx: 8; ry: 8; stroke-width: 1.5; }
.node-status-bar { rx: 8; ry: 8; }
.node-name { font-size: 14px; font-weight: 700; fill: var(--text); }
.node-type-label {
  font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.node-desc  { font-size: 11px; fill: var(--text-secondary); }
.node-source {
  font-size: 10px;
  font-family: 'SF Mono', Consolas, monospace;
  fill: var(--text-muted);
}

.edge-line { fill: none; stroke-width: 1.5; opacity: 0.6; }
.edge-label {
  font-size: 10px; fill: var(--text-muted);
  opacity: 0; pointer-events: none;
}
.edge-group:hover .edge-label { opacity: 1; }
.edge-group:hover .edge-line  { opacity: 1; stroke-width: 2.5; }

.edge-line.planned {
  stroke-dasharray: 6 4;
  animation: dashflow 1s linear infinite;
}
@keyframes dashflow { to { stroke-dashoffset: -10; } }

.node-group.dimmed       { opacity: 0.2; transition: opacity 0.3s; }
.node-group.highlighted  { opacity: 1;   transition: opacity 0.3s; }
.edge-group.dimmed       { opacity: 0.05; transition: opacity 0.3s; }
.edge-group.highlighted  { opacity: 1;    transition: opacity 0.3s; }
.edge-group.highlighted .edge-line { stroke-width: 2.5; opacity: 0.9; }

/* ---- GROUP / PARENT NODES ---- */
.group-bg {
  rx: 12; ry: 12;
  stroke-dasharray: 4 2;
  opacity: 0.15;
}
.group-label {
  font-size: 12px; font-weight: 700;
  fill: var(--text-muted);
  text-transform: uppercase; letter-spacing: 0.5px;
}

/* ---- SCROLLBAR ---- */
.tab-content::-webkit-scrollbar       { width: 6px; }
.tab-content::-webkit-scrollbar-track  { background: transparent; }
.tab-content::-webkit-scrollbar-thumb  { background: var(--border); border-radius: 3px; }
.tab-content::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }
</style>
</head>
<body>

<!-- ============================================================
     TOP BAR
     ============================================================ -->
<div id="topbar">
  <span class="project-name" id="project-name"></span>
  <span class="timestamp" id="timestamp"></span>
  <input type="text" id="search-input" placeholder="Search nodes...">
  <div class="stats-bar" id="stats-bar"></div>
  <div class="filter-group" id="filter-group"></div>
  <button id="theme-toggle" title="Toggle theme">&#9681;</button>
</div>

<!-- ============================================================
     MAIN LAYOUT
     ============================================================ -->
<div id="main">
  <!-- LEFT: D3 canvas (65 %) -->
  <div id="canvas-panel">
    <svg id="graph-svg"></svg>
    <div class="zoom-controls">
      <button class="zoom-btn" id="zoom-in"  title="Zoom in">+</button>
      <button class="zoom-btn" id="zoom-out" title="Zoom out">&minus;</button>
      <button class="zoom-btn" id="zoom-fit" title="Zoom to fit">&#8859;</button>
    </div>
    <div id="minimap"><svg id="minimap-svg"></svg></div>
  </div>

  <!-- RIGHT: insight panel (35 %) -->
  <div id="right-panel">
    <div class="tabs">
      <button class="tab-btn active" data-tab="details">Details</button>
      <button class="tab-btn" data-tab="health">Health</button>
      <button class="tab-btn" data-tab="questions">Questions</button>
    </div>
    <div class="tab-content">
      <div id="tab-details"   class="tab-pane active"></div>
      <div id="tab-health"    class="tab-pane"></div>
      <div id="tab-questions" class="tab-pane"></div>
    </div>
  </div>
</div>

<!-- ============================================================
     JAVASCRIPT
     ============================================================ -->
<script>
/* ----------------------------------------------------------------
   Embedded data blob (replaced at generation time)
   ---------------------------------------------------------------- */
const DATA = __BLUEPRINT_DATA__;

/* ----------------------------------------------------------------
   Constants
   ---------------------------------------------------------------- */
const STATUS_COLORS = {
  built:       '#38a169',
  planned:     '#4299e1',
  in_progress: '#d69e2e',
  broken:      '#e53e3e',
  deprecated:  '#a0aec0'
};

const EDGE_COLORS = {
  connects_to:   '#a0aec0',
  reads_from:    '#4299e1',
  writes_to:     '#e53e3e',
  depends_on:    '#805ad5',
  authenticates: '#d69e2e',
  calls:         '#38a169',
  inherits:      '#dd6b20',
  contains:      '#a0aec0',
  exposes:       '#319795',
  observes:      '#9f7aea',
  creates:       '#e53e3e',
  produces:      '#38a169',
  consumes:      '#4299e1',
  delegates:     '#ed8936',
  controls:      '#e53e3e',
  uses:          '#718096',
  updates:       '#d69e2e',
  implements:    '#805ad5',
  emits:         '#38a169'
};

const NODE_WIDTH  = 260;
const NODE_HEIGHT = 88;

/* ----------------------------------------------------------------
   Mutable state
   ---------------------------------------------------------------- */
let selectedNodeId = null;
let activeFilters  = new Set();
let simulation     = null;
let mainG          = null;
let zoom           = null;
let svgEl          = null;

/* ================================================================
   BOOTSTRAP
   ================================================================ */
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('project-name').textContent = DATA.project_name;
  document.getElementById('timestamp').textContent =
    'Generated: ' + new Date(DATA.generated_at).toLocaleString();
  document.getElementById('stats-bar').innerHTML =
    '<span>' + DATA.nodes.length   + ' nodes</span>' +
    '<span>' + DATA.edges.length   + ' edges</span>' +
    '<span>' + DATA.issues.length  + ' issues</span>' +
    '<span>' + DATA.questions.length + ' questions</span>';

  initFilters();
  initTabs();
  initSearch();
  initThemeToggle();
  renderHealth();
  renderQuestions();
  renderEmptyDetail();
  buildGraph();
});

/* ================================================================
   FILTERS
   ================================================================ */
function initFilters() {
  const types = [...new Set(DATA.nodes.map(n => n.type))].sort();
  const group = document.getElementById('filter-group');
  types.forEach(t => {
    const btn = document.createElement('button');
    btn.className = 'filter-btn';
    btn.textContent = t;
    btn.addEventListener('click', () => {
      btn.classList.toggle('active');
      if (activeFilters.has(t)) activeFilters.delete(t);
      else activeFilters.add(t);
      applyFilters();
    });
    group.appendChild(btn);
  });
}

function applyFilters() {
  const term = document.getElementById('search-input').value.toLowerCase();
  d3.selectAll('.node-group').each(function(d) {
    const okType   = activeFilters.size === 0 || activeFilters.has(d.type);
    const okSearch = !term ||
      d.name.toLowerCase().includes(term) ||
      (d.description && d.description.toLowerCase().includes(term)) ||
      d.type.toLowerCase().includes(term);
    d3.select(this).style('display', (okType && okSearch) ? null : 'none');
  });
  d3.selectAll('.edge-group').each(function(d) {
    const sVis = isNodeVisible(d.source.id || d.source);
    const tVis = isNodeVisible(d.target.id || d.target);
    d3.select(this).style('display', (sVis && tVis) ? null : 'none');
  });
}

function isNodeVisible(nodeId) {
  const el = d3.select('#node-' + CSS.escape(nodeId));
  return !el.empty() && el.style('display') !== 'none';
}

/* ================================================================
   SEARCH
   ================================================================ */
function initSearch() {
  document.getElementById('search-input').addEventListener('input', () => applyFilters());
}

/* ================================================================
   TABS
   ================================================================ */
function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b  => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    });
  });
}

/* ================================================================
   THEME TOGGLE
   ================================================================ */
function initThemeToggle() {
  document.getElementById('theme-toggle').addEventListener('click', () => {
    const html = document.documentElement;
    const cur  = html.getAttribute('data-theme');
    html.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
  });
}

/* ================================================================
   DETAIL PANEL (Details tab)
   ================================================================ */
function renderEmptyDetail() {
  document.getElementById('tab-details').innerHTML =
    '<div class="detail-empty">' +
      '<div class="icon">&#9737;</div>' +
      '<div>Click a node to view details</div>' +
    '</div>';
}

function renderNodeDetail(nd) {
  const nodeMap = {};
  DATA.nodes.forEach(n => nodeMap[n.id] = n);

  const conns       = DATA.edges.filter(e => e.source_id === nd.id || e.target_id === nd.id);
  const statusColor = STATUS_COLORS[nd.status] || '#a0aec0';

  let h = '<div class="node-detail">';
  h += '<h2><span class="status-indicator" style="background:' + statusColor + '"></span>'
     + esc(nd.name) + '</h2>';
  h += '<span class="node-type-badge">' + esc(nd.type) + '</span>';

  if (nd.description) {
    h += '<div class="field-label">Description</div>';
    h += '<div class="field-value">' + esc(nd.description) + '</div>';
  }

  h += '<div class="field-label">Status</div>';
  h += '<div class="field-value" style="text-transform:capitalize">'
     + esc(nd.status.replace('_', ' ')) + '</div>';

  if (nd.source_file) {
    h += '<div class="field-label">Source</div>';
    h += '<div class="source-file">' + esc(nd.source_file);
    if (nd.source_line) h += ':' + nd.source_line;
    h += '</div>';
  }

  if (nd.parent_id && nodeMap[nd.parent_id]) {
    h += '<div class="field-label">Parent</div>';
    h += '<div class="field-value">' + esc(nodeMap[nd.parent_id].name) + '</div>';
  }

  if (nd.metadata && Object.keys(nd.metadata).length > 0) {
    h += '<div class="field-label">Metadata</div>';
    h += '<div class="field-value" style="font-family:monospace;font-size:11px;' +
         'white-space:pre-wrap;background:var(--bg-tertiary);padding:8px;border-radius:4px">'
       + esc(JSON.stringify(nd.metadata, null, 2)) + '</div>';
  }

  if (conns.length > 0) {
    h += '<div class="field-label">Connections (' + conns.length + ')</div>';
    h += '<ul class="connection-list">';
    conns.forEach(e => {
      const isSrc    = e.source_id === nd.id;
      const otherId  = isSrc ? e.target_id : e.source_id;
      const other    = nodeMap[otherId];
      const otherNm  = other ? other.name : otherId.slice(0, 8);
      const arrow    = isSrc ? '\u2192' : '\u2190';
      h += '<li><span class="rel-badge">' + esc(e.relationship) + '</span>'
         + arrow + ' ' + esc(otherNm);
      if (e.label) h += ' <span style="color:var(--text-muted);font-size:10px">(' + esc(e.label) + ')</span>';
      h += '</li>';
    });
    h += '</ul>';
  }

  h += '<div class="field-label">ID</div>';
  h += '<div class="field-value" style="font-family:monospace;font-size:11px;' +
       'color:var(--text-muted)">' + esc(nd.id) + '</div>';
  h += '</div>';

  document.getElementById('tab-details').innerHTML = h;

  // Switch to Details tab automatically
  document.querySelectorAll('.tab-btn').forEach(b  => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelector('.tab-btn[data-tab="details"]').classList.add('active');
  document.getElementById('tab-details').classList.add('active');
}

/* ================================================================
   HEALTH TAB
   ================================================================ */
function renderHealth() {
  const critCnt = DATA.issues.filter(i => i.severity === 'critical').length;
  const warnCnt = DATA.issues.filter(i => i.severity === 'warning').length;
  const infoCnt = DATA.issues.filter(i => i.severity === 'info').length;

  let h = '<div class="health-summary">';
  h += '<div class="health-stat critical"><div class="stat-number">' + critCnt + '</div><div class="stat-label">Critical</div></div>';
  h += '<div class="health-stat warning"><div class="stat-number">'  + warnCnt + '</div><div class="stat-label">Warnings</div></div>';
  h += '<div class="health-stat info"><div class="stat-number">'     + infoCnt + '</div><div class="stat-label">Info</div></div>';
  h += '</div>';

  const sorted = [...DATA.issues].sort((a, b) => {
    const ord = { critical: 0, warning: 1, info: 2 };
    return (ord[a.severity] ?? 3) - (ord[b.severity] ?? 3);
  });

  if (sorted.length === 0) {
    h += '<div class="detail-empty" style="height:auto;padding:32px 0">' +
         '<div style="font-size:24px;opacity:0.3">&#10003;</div>' +
         '<div>No issues detected</div></div>';
  }

  sorted.forEach(issue => {
    h += '<div class="issue-card ' + issue.severity + '">';
    h += '<div class="issue-type">' + esc(issue.type) + '</div>';
    h += '<div class="issue-msg">'  + esc(issue.message) + '</div>';
    if (issue.suggestion)
      h += '<div class="issue-suggestion">' + esc(issue.suggestion) + '</div>';
    h += '</div>';
  });

  document.getElementById('tab-health').innerHTML = h;
}

/* ================================================================
   QUESTIONS TAB
   ================================================================ */
function renderQuestions() {
  const qs = DATA.questions || [];
  let h = '';

  if (qs.length === 0) {
    h += '<div class="detail-empty" style="height:auto;padding:32px 0">' +
         '<div style="font-size:24px;opacity:0.3">&#10003;</div>' +
         '<div>No questions detected</div></div>';
  }

  qs.forEach(q => {
    h += '<div class="question-card" data-highlight=\'' +
         JSON.stringify(q.highlight_nodes || []) + '\'>';
    h += '<div class="q-severity ' + (q.severity || 'info') + '">' +
         (q.severity || 'info').toUpperCase() + '</div>';
    h += '<div class="q-text">'    + esc(q.question) + '</div>';
    h += '<div class="q-context">' + esc(q.context)  + '</div>';
    h += '<span class="q-category">' + esc(q.category) + '</span>';
    h += '</div>';
  });

  document.getElementById('tab-questions').innerHTML = h;

  // Click a question card to highlight its nodes on the graph
  document.querySelectorAll('.question-card').forEach(card => {
    card.addEventListener('click', () => {
      const ids = JSON.parse(card.dataset.highlight || '[]');
      if (ids.length > 0) highlightNodes(ids);
    });
  });
}

/* ================================================================
   D3 FORCE-DIRECTED GRAPH
   ================================================================ */
function buildGraph() {
  svgEl = d3.select('#graph-svg');
  const container = document.getElementById('canvas-panel');
  const W = container.clientWidth;
  const H = container.clientHeight;

  /* ---- Arrow markers ---- */
  const defs = svgEl.append('defs');
  Object.entries(EDGE_COLORS).forEach(([rel, color]) => {
    defs.append('marker')
      .attr('id', 'arrow-' + rel)
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 20).attr('refY', 0)
      .attr('markerWidth', 6).attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
        .attr('d', 'M0,-4L8,0L0,4')
        .attr('fill', color).attr('opacity', 0.6);
  });

  /* ---- Zoom ---- */
  zoom = d3.zoom()
    .scaleExtent([0.1, 4])
    .on('zoom', event => {
      mainG.attr('transform', event.transform);
      updateMinimap();
    });
  svgEl.call(zoom);

  /* Click on background to deselect */
  svgEl.on('click', event => {
    if (event.target === svgEl.node() ||
        (event.target.tagName === 'rect' && event.target.classList.contains('bg-rect')))
      deselectAll();
  });

  /* Transparent background rect for click target */
  svgEl.append('rect')
    .attr('class', 'bg-rect')
    .attr('width', W).attr('height', H)
    .attr('fill', 'transparent');

  mainG = svgEl.append('g').attr('class', 'main-group');

  /* ---- Prepare node data ---- */
  const nodeData = DATA.nodes.map((n, i) => ({
    ...n,
    x: W / 2 + (Math.random() - 0.5) * W * 0.6,
    y: H / 2 + (Math.random() - 0.5) * H * 0.6,
    w: NODE_WIDTH,
    h: NODE_HEIGHT
  }));
  const nodeMap = {};
  nodeData.forEach(n => nodeMap[n.id] = n);

  /* ---- Prepare edge data ---- */
  const edgeData = DATA.edges
    .filter(e => nodeMap[e.source_id] && nodeMap[e.target_id])
    .map(e => ({ ...e, source: e.source_id, target: e.target_id }));

  /* ---- Identify parent/child grouping ---- */
  const parentIds  = new Set(nodeData.filter(n => n.parent_id).map(n => n.parent_id));
  const childrenOf = {};
  nodeData.forEach(n => {
    if (n.parent_id) {
      if (!childrenOf[n.parent_id]) childrenOf[n.parent_id] = [];
      childrenOf[n.parent_id].push(n.id);
    }
  });

  /* ---- Layers (draw order: groups, edges, nodes) ---- */
  const groupG = mainG.append('g').attr('class', 'groups-layer');
  const edgeG  = mainG.append('g').attr('class', 'edges-layer');
  const nodeG  = mainG.append('g').attr('class', 'nodes-layer');

  /* ---- Draw edges ---- */
  const edgeGroups = edgeG.selectAll('.edge-group')
    .data(edgeData).join('g')
    .attr('class', d => 'edge-group' + (d.status === 'planned' ? ' planned' : ''));

  edgeGroups.append('path')
    .attr('class', d => 'edge-line' + (d.status === 'planned' ? ' planned' : ''))
    .attr('stroke', d => EDGE_COLORS[d.relationship] || '#a0aec0')
    .attr('marker-end', d => 'url(#arrow-' + d.relationship + ')');

  edgeGroups.append('text')
    .attr('class', 'edge-label')
    .attr('text-anchor', 'middle').attr('dy', -6)
    .text(d => d.label || d.relationship);

  /* ---- Draw nodes ---- */
  const nodeGroups = nodeG.selectAll('.node-group')
    .data(nodeData).join('g')
    .attr('class', 'node-group')
    .attr('id', d => 'node-' + d.id)
    .on('click', (event, d) => { event.stopPropagation(); selectNode(d); })
    .call(d3.drag()
      .on('start', dragStarted)
      .on('drag',  dragged)
      .on('end',   dragEnded));

  /* background rect */
  nodeGroups.append('rect')
    .attr('class', 'node-rect')
    .attr('width', NODE_WIDTH).attr('height', NODE_HEIGHT)
    .attr('fill', 'var(--node-bg)')
    .attr('stroke', 'var(--node-border)');

  /* status left bar */
  nodeGroups.append('rect')
    .attr('class', 'node-status-bar')
    .attr('width', 4).attr('height', NODE_HEIGHT)
    .attr('fill', d => STATUS_COLORS[d.status] || '#a0aec0');

  /* type badge pill */
  nodeGroups.append('rect')
    .attr('x', d => NODE_WIDTH - (d.type.length * 7 + 20))
    .attr('y', 8)
    .attr('width', d => d.type.length * 7 + 12)
    .attr('height', 18).attr('rx', 9)
    .attr('fill', 'var(--badge-bg)');

  nodeGroups.append('text')
    .attr('class', 'node-type-label')
    .attr('x', NODE_WIDTH - 14).attr('y', 21)
    .attr('text-anchor', 'end')
    .attr('fill', 'var(--badge-text)')
    .text(d => d.type);

  /* name */
  nodeGroups.append('text')
    .attr('class', 'node-name')
    .attr('x', 14).attr('y', 28)
    .text(d => trunc(d.name, 28));

  /* description */
  nodeGroups.append('text')
    .attr('class', 'node-desc')
    .attr('x', 14).attr('y', 48)
    .text(d => d.description ? trunc(d.description, 38) : '');

  /* source file */
  nodeGroups.append('text')
    .attr('class', 'node-source')
    .attr('x', 14).attr('y', 68)
    .text(d => d.source_file ? trunc(d.source_file, 36) : '');

  /* ---- Force simulation ---- */
  simulation = d3.forceSimulation(nodeData)
    .force('link',      d3.forceLink(edgeData).id(d => d.id).distance(220).strength(0.4))
    .force('charge',    d3.forceManyBody().strength(-800).distanceMax(600))
    .force('center',    d3.forceCenter(W / 2, H / 2).strength(0.05))
    .force('collision', d3.forceCollide().radius(Math.max(NODE_WIDTH, NODE_HEIGHT) / 2 + 30).strength(0.8))
    .force('x',         d3.forceX(W / 2).strength(0.02))
    .force('y',         d3.forceY(H / 2).strength(0.02))
    .alphaDecay(0.02)
    .on('tick', () => {
      nodeGroups.attr('transform', d =>
        'translate(' + (d.x - NODE_WIDTH / 2) + ',' + (d.y - NODE_HEIGHT / 2) + ')');

      edgeGroups.select('path').attr('d', d => {
        const sx = d.source.x, sy = d.source.y;
        const tx = d.target.x, ty = d.target.y;
        const dx = tx - sx, dy = ty - sy;
        const dr = Math.sqrt(dx * dx + dy * dy) * 0.7;
        return 'M' + sx + ',' + sy + 'A' + dr + ',' + dr + ' 0 0,1 ' + tx + ',' + ty;
      });

      edgeGroups.select('text')
        .attr('x', d => (d.source.x + d.target.x) / 2)
        .attr('y', d => (d.source.y + d.target.y) / 2);

      updateGroupBGs(groupG, nodeData, childrenOf, parentIds);
    })
    .on('end', () => { zoomToFit(); updateMinimap(); });

  /* Initial fit */
  setTimeout(() => { zoomToFit(); updateMinimap(); }, 300);
  initMinimap(W, H);

  /* Zoom buttons */
  document.getElementById('zoom-in').addEventListener('click',  () => svgEl.transition().duration(300).call(zoom.scaleBy, 1.3));
  document.getElementById('zoom-out').addEventListener('click', () => svgEl.transition().duration(300).call(zoom.scaleBy, 0.7));
  document.getElementById('zoom-fit').addEventListener('click', () => zoomToFit());
}

/* ================================================================
   GROUP BACKGROUNDS (parent nodes)
   ================================================================ */
function updateGroupBGs(groupG, nodeData, childrenOf, parentIds) {
  const groups = [];
  parentIds.forEach(pid => {
    const parent   = nodeData.find(n => n.id === pid);
    if (!parent) return;
    const children = (childrenOf[pid] || [])
      .map(cid => nodeData.find(n => n.id === cid)).filter(Boolean);
    if (children.length === 0) return;
    const all = [parent, ...children];
    const pad = 30;
    const x1  = d3.min(all, n => n.x - NODE_WIDTH / 2)  - pad;
    const y1  = d3.min(all, n => n.y - NODE_HEIGHT / 2) - pad - 20;
    const x2  = d3.max(all, n => n.x + NODE_WIDTH / 2)  + pad;
    const y2  = d3.max(all, n => n.y + NODE_HEIGHT / 2) + pad;
    groups.push({ id: pid, name: parent.name, x: x1, y: y1,
                  w: x2 - x1, h: y2 - y1, count: children.length, status: parent.status });
  });

  const sel     = groupG.selectAll('.group-container').data(groups, d => d.id);
  const entered = sel.enter().append('g').attr('class', 'group-container');
  entered.append('rect').attr('class', 'group-bg');
  entered.append('text').attr('class', 'group-label');
  const merged = entered.merge(sel);
  merged.select('.group-bg')
    .attr('x', d => d.x).attr('y', d => d.y)
    .attr('width', d => d.w).attr('height', d => d.h)
    .attr('fill',   d => STATUS_COLORS[d.status] || '#a0aec0')
    .attr('stroke', d => STATUS_COLORS[d.status] || '#a0aec0')
    .attr('stroke-width', 1);
  merged.select('.group-label')
    .attr('x', d => d.x + 12).attr('y', d => d.y + 16)
    .text(d => d.name + ' (' + d.count + ')');
  sel.exit().remove();
}

/* ================================================================
   MINIMAP
   ================================================================ */
function initMinimap(W, H) {
  const mm = d3.select('#minimap-svg');
  mm.append('g').attr('class', 'mm-content');
  mm.append('rect').attr('class', 'viewport-rect');
  updateMinimap();
}

function updateMinimap() {
  if (!mainG) return;
  const mm  = d3.select('#minimap-svg');
  const mmW = 200, mmH = 150;
  const nodes = d3.selectAll('.node-group').data();
  if (nodes.length === 0) return;

  const pad = 50;
  const x1 = d3.min(nodes, d => d.x - NODE_WIDTH / 2) - pad;
  const y1 = d3.min(nodes, d => d.y - NODE_HEIGHT / 2) - pad;
  const x2 = d3.max(nodes, d => d.x + NODE_WIDTH / 2) + pad;
  const y2 = d3.max(nodes, d => d.y + NODE_HEIGHT / 2) + pad;
  const bw = x2 - x1, bh = y2 - y1;
  const sc = Math.min(mmW / bw, mmH / bh);

  const g = mm.select('.mm-content');
  g.selectAll('*').remove();
  g.attr('transform',
    'translate(' + ((mmW - bw * sc) / 2) + ',' + ((mmH - bh * sc) / 2) + ')' +
    ' scale(' + sc + ')' +
    ' translate(' + (-x1) + ',' + (-y1) + ')');

  /* minimap edges */
  g.selectAll('.mm-edge')
    .data(DATA.edges.filter(e => {
      return nodes.find(n => n.id === e.source_id) && nodes.find(n => n.id === e.target_id);
    }))
    .join('line').attr('class', 'mm-edge')
    .attr('x1', d => { const n = nodes.find(n => n.id === d.source_id); return n ? n.x : 0; })
    .attr('y1', d => { const n = nodes.find(n => n.id === d.source_id); return n ? n.y : 0; })
    .attr('x2', d => { const n = nodes.find(n => n.id === d.target_id); return n ? n.x : 0; })
    .attr('y2', d => { const n = nodes.find(n => n.id === d.target_id); return n ? n.y : 0; })
    .attr('stroke', '#a0aec0').attr('stroke-width', 1).attr('opacity', 0.3);

  /* minimap nodes */
  g.selectAll('.mm-node')
    .data(nodes).join('rect').attr('class', 'mm-node')
    .attr('x', d => d.x - NODE_WIDTH / 2).attr('y', d => d.y - NODE_HEIGHT / 2)
    .attr('width', NODE_WIDTH).attr('height', NODE_HEIGHT)
    .attr('rx', 4)
    .attr('fill', d => STATUS_COLORS[d.status] || '#a0aec0')
    .attr('opacity', 0.6);

  /* viewport rect */
  const ctr       = document.getElementById('canvas-panel');
  const transform = d3.zoomTransform(svgEl.node());
  const vx = -transform.x / transform.k;
  const vy = -transform.y / transform.k;
  const vw = ctr.clientWidth  / transform.k;
  const vh = ctr.clientHeight / transform.k;

  mm.select('.viewport-rect')
    .attr('transform',
      'translate(' + ((mmW - bw * sc) / 2) + ',' + ((mmH - bh * sc) / 2) + ')' +
      ' scale(' + sc + ')' +
      ' translate(' + (-x1) + ',' + (-y1) + ')')
    .attr('x', vx).attr('y', vy)
    .attr('width', vw).attr('height', vh);
}

/* ================================================================
   ZOOM TO FIT
   ================================================================ */
function zoomToFit() {
  const ctr   = document.getElementById('canvas-panel');
  const W     = ctr.clientWidth;
  const H     = ctr.clientHeight;
  const nodes = d3.selectAll('.node-group').data();
  if (nodes.length === 0) return;

  const pad = 60;
  const x1 = d3.min(nodes, d => d.x - NODE_WIDTH / 2) - pad;
  const y1 = d3.min(nodes, d => d.y - NODE_HEIGHT / 2) - pad;
  const x2 = d3.max(nodes, d => d.x + NODE_WIDTH / 2) + pad;
  const y2 = d3.max(nodes, d => d.y + NODE_HEIGHT / 2) + pad;
  const bw = x2 - x1, bh = y2 - y1;
  const sc = Math.min(W / bw, H / bh, 1.5);
  const tx = (W - bw * sc) / 2 - x1 * sc;
  const ty = (H - bh * sc) / 2 - y1 * sc;

  svgEl.transition().duration(600)
    .call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(sc));
}

/* ================================================================
   SELECTION & HIGHLIGHTING
   ================================================================ */
function selectNode(d) {
  selectedNodeId = d.id;
  const nd = DATA.nodes.find(n => n.id === d.id);
  if (nd) renderNodeDetail(nd);

  const connected = new Set([d.id]);
  DATA.edges.forEach(e => {
    if (e.source_id === d.id) connected.add(e.target_id);
    if (e.target_id === d.id) connected.add(e.source_id);
  });

  d3.selectAll('.node-group')
    .classed('dimmed',      n => !connected.has(n.id))
    .classed('highlighted', n =>  connected.has(n.id));
  d3.selectAll('.edge-group')
    .classed('dimmed', e => {
      const s = e.source.id || e.source, t = e.target.id || e.target;
      return s !== d.id && t !== d.id;
    })
    .classed('highlighted', e => {
      const s = e.source.id || e.source, t = e.target.id || e.target;
      return s === d.id || t === d.id;
    });
}

function highlightNodes(nodeIds) {
  const ids = new Set(nodeIds);
  d3.selectAll('.node-group')
    .classed('dimmed',      n => !ids.has(n.id))
    .classed('highlighted', n =>  ids.has(n.id));
  d3.selectAll('.edge-group')
    .classed('dimmed', true).classed('highlighted', false);

  /* Zoom to the highlighted cluster */
  const nodes = d3.selectAll('.node-group').data().filter(n => ids.has(n.id));
  if (nodes.length === 0) return;
  const ctr = document.getElementById('canvas-panel');
  const W   = ctr.clientWidth, H = ctr.clientHeight, pad = 100;
  const x1  = d3.min(nodes, d => d.x - NODE_WIDTH / 2) - pad;
  const y1  = d3.min(nodes, d => d.y - NODE_HEIGHT / 2) - pad;
  const x2  = d3.max(nodes, d => d.x + NODE_WIDTH / 2) + pad;
  const y2  = d3.max(nodes, d => d.y + NODE_HEIGHT / 2) + pad;
  const bw  = x2 - x1, bh = y2 - y1;
  const sc  = Math.min(W / bw, H / bh, 1.5);
  const tx  = (W - bw * sc) / 2 - x1 * sc;
  const ty  = (H - bh * sc) / 2 - y1 * sc;
  svgEl.transition().duration(500)
    .call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(sc));
}

function deselectAll() {
  selectedNodeId = null;
  renderEmptyDetail();
  d3.selectAll('.node-group').classed('dimmed', false).classed('highlighted', false);
  d3.selectAll('.edge-group').classed('dimmed', false).classed('highlighted', false);
}

/* ================================================================
   DRAG HANDLERS
   ================================================================ */
function dragStarted(event, d) {
  if (!event.active) simulation.alphaTarget(0.1).restart();
  d.fx = d.x; d.fy = d.y;
}
function dragged(event, d) {
  d.fx = event.x; d.fy = event.y;
}
function dragEnded(event, d) {
  if (!event.active) simulation.alphaTarget(0);
  d.fx = null; d.fy = null;
}

/* ================================================================
   HELPERS
   ================================================================ */
function trunc(s, max) {
  if (!s) return '';
  return s.length > max ? s.slice(0, max - 1) + '\u2026' : s;
}
function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
</script>
</body>
</html>
"""
