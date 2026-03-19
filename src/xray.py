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
  display: flex;
  align-items: center;
  gap: 4px;
}
.filter-btn:hover { border-color: var(--accent); color: var(--accent); }
.filter-btn.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.filter-dot {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.filter-btn.active .filter-dot { background: #fff !important; }

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
   MAIN LAYOUT -- left 65% canvas, right 35% panel
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
   DETAIL PANEL (right -- Details tab)
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
   LAYOUT TOGGLE
   ================================================================ */
.layout-toggle {
  position: absolute;
  top: 12px; left: 12px;
  display: flex; gap: 0;
  z-index: 10;
}
.layout-btn {
  padding: 6px 12px;
  font-size: 11px; font-weight: 600;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
  box-shadow: 0 1px 3px var(--shadow);
}
.layout-btn:first-child { border-radius: 6px 0 0 6px; }
.layout-btn:last-child  { border-radius: 0 6px 6px 0; border-left: none; }
.layout-btn.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.layout-btn:hover:not(.active) { border-color: var(--accent); color: var(--accent); }

/* ================================================================
   CONTEXT MENU
   ================================================================ */
.context-menu {
  position: fixed;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 4px 16px var(--shadow-lg);
  padding: 4px;
  z-index: 1000;
  min-width: 200px;
}
.context-menu-item {
  padding: 8px 12px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.1s;
}
.context-menu-item:hover { background: var(--bg-tertiary); }

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
.node-group { cursor: pointer; transition: opacity 0.3s; }
.node-rect { rx: 8; ry: 8; stroke-width: 1.5; }
.node-name { font-weight: 700; fill: var(--text); }
.node-type-label {
  font-size: 9px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.node-desc  { font-size: 11px; fill: var(--text-secondary); }
.node-source {
  font-size: 10px;
  font-family: 'SF Mono', Consolas, monospace;
  fill: var(--text-muted);
}

.edge-line { fill: none; stroke-width: 1.5; opacity: 0.15; }
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

.node-group.dimmed       { opacity: 0.15 !important; }
.node-group.highlighted  { opacity: 1 !important; }
.edge-group.dimmed       { opacity: 0.05; transition: opacity 0.3s; }
.edge-group.highlighted  { opacity: 1;    transition: opacity 0.3s; }
.edge-group.highlighted .edge-line { stroke-width: 2.5; opacity: 0.9; }
.edge-group.highlighted .edge-label { opacity: 1; }

/* ---- STATUS ENCODING ---- */
@keyframes pulse-bar {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
.status-bar-in_progress {
  animation: pulse-bar 2s ease-in-out infinite;
}

/* ---- GROUP / PARENT NODES ---- */
.group-bg {
  rx: 12; ry: 12;
  pointer-events: all;
  cursor: pointer;
}
.group-label {
  font-size: 11px; font-weight: 700;
  fill: var(--text-muted);
  text-transform: uppercase; letter-spacing: 0.5px;
  pointer-events: none;
}
.group-count {
  font-size: 10px;
  fill: var(--text-muted);
  pointer-events: none;
}
.collapsed-pill {
  cursor: pointer;
}
.collapsed-pill rect {
  rx: 12; ry: 12;
}
.collapsed-pill text {
  font-size: 11px; font-weight: 600;
  fill: var(--text-secondary);
  pointer-events: none;
}

/* ---- SCROLLBAR ---- */
.tab-content::-webkit-scrollbar       { width: 6px; }
.tab-content::-webkit-scrollbar-track  { background: transparent; }
.tab-content::-webkit-scrollbar-thumb  { background: var(--border); border-radius: 3px; }
.tab-content::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

/* Connection summary */
.conn-summary { display:flex; flex-wrap:wrap; gap:8px; margin:4px 0 8px; }
.conn-stat { font-size:12px; padding:2px 8px; border-radius:10px; background:var(--bg-tertiary); color:var(--text-secondary); }
.conn-stat.warn { color:#e53e3e; background:var(--issue-critical-bg); }
.conn-hint { font-size:11px; color:var(--text-muted); font-style:italic; margin-top:4px; }

/* Connection items */
.conn-item { cursor:pointer; padding:6px 4px; transition:background 0.1s; display:flex; flex-wrap:wrap; align-items:center; gap:4px; }
.conn-item:hover { background:var(--bg-tertiary); border-radius:4px; }
.conn-dot { width:6px; height:6px; border-radius:50%; flex-shrink:0; }
.conn-name { font-weight:600; color:var(--accent); font-size:12px; }
.conn-type-badge { font-size:9px; text-transform:uppercase; opacity:0.7; }
.conn-warn { color:#e53e3e; font-size:12px; }
.conn-edge-label { width:100%; font-size:10px; color:var(--text-secondary); font-style:italic; padding-left:10px; }
.conn-explanation { width:100%; font-size:10px; color:var(--text-muted); padding-left:10px; }

/* Back button */
.nav-back-btn { font-size:12px; padding:4px 10px; border:1px solid var(--border); border-radius:4px; background:var(--bg); color:var(--text-secondary); cursor:pointer; margin-bottom:8px; }
.nav-back-btn:hover { border-color:var(--accent); color:var(--accent); }

/* Edge hit zone */
.edge-hit-zone { pointer-events:stroke; }
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
  <!-- LEFT: D3 canvas (65%) -->
  <div id="canvas-panel">
    <svg id="graph-svg"></svg>
    <div class="layout-toggle">
      <button class="layout-btn active" data-layout="clustered">Clustered</button>
      <button class="layout-btn" data-layout="force">Force</button>
    </div>
    <div class="zoom-controls">
      <button class="zoom-btn" id="zoom-in"  title="Zoom in">+</button>
      <button class="zoom-btn" id="zoom-out" title="Zoom out">&minus;</button>
      <button class="zoom-btn" id="zoom-fit" title="Zoom to fit">&#8859;</button>
      <button class="zoom-btn" id="help-btn" title="Shortcuts">?</button>
    </div>
    <div id="help-panel" class="context-menu" style="display:none;bottom:48px;left:12px;position:absolute">
      <div style="padding:8px 12px;font-size:12px;line-height:1.8;color:var(--text-secondary)">
        <b>Dbl-click group</b> — collapse/expand<br>
        <b>Right-click node</b> — focus neighborhood<br>
        <b>Escape</b> — reset view<br>
        <b>Click pill</b> — expand hidden group
      </div>
    </div>
    <div id="minimap"><svg id="minimap-svg"></svg></div>
  </div>

  <!-- RIGHT: insight panel (35%) -->
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

<!-- Context menu (hidden by default) -->
<div id="context-menu" class="context-menu" style="display:none">
  <div class="context-menu-item" id="ctx-focus">Focus (2-hop neighborhood)</div>
  <div class="context-menu-item" id="ctx-show-all">Show all</div>
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
   Constants -- Type Colors (9 categories)
   ---------------------------------------------------------------- */
const TYPE_COLORS = {
  system: '#6366f1', container: '#6366f1',
  service: '#8b5cf6', worker: '#8b5cf6',
  api: '#10b981', route: '#10b981', webhook: '#10b981', middleware: '#10b981',
  database: '#f59e0b', table: '#f59e0b', column: '#f59e0b', cache: '#f59e0b', queue: '#f59e0b',
  function: '#3b82f6', class_def: '#3b82f6', module: '#3b82f6', struct: '#3b82f6', protocol: '#3b82f6',
  file: '#6b7280', script: '#6b7280', config: '#6b7280', migration: '#6b7280',
  model: '#ec4899', schema: '#ec4899', enum_def: '#ec4899', view: '#ec4899', util: '#ec4899',
  external: '#ef4444', submodule: '#ef4444',
  test: '#14b8a6'
};

const TYPE_CATEGORIES = {
  'Infrastructure': { types: ['system','container'], color: '#6366f1' },
  'Services':       { types: ['service','worker'], color: '#8b5cf6' },
  'API':            { types: ['api','route','webhook','middleware'], color: '#10b981' },
  'Data':           { types: ['database','table','column','cache','queue'], color: '#f59e0b' },
  'Code':           { types: ['function','class_def','module','struct','protocol'], color: '#3b82f6' },
  'Files':          { types: ['file','script','config','migration'], color: '#6b7280' },
  'Schema':         { types: ['model','schema','enum_def','view','util'], color: '#ec4899' },
  'External':       { types: ['external','submodule'], color: '#ef4444' },
  'Testing':        { types: ['test'], color: '#14b8a6' }
};

const NODE_SIZES = {
  system: [200,60], container: [200,60],
  service: [160,48], module: [160,48], database: [160,48], api: [160,48], worker: [160,48],
  function: [140,40], route: [140,40], table: [140,40], class_def: [140,40],
    middleware: [140,40], webhook: [140,40], struct: [140,40], protocol: [140,40], test: [140,40],
  column: [120,32], config: [120,32], file: [120,32], script: [120,32],
    migration: [120,32], cache: [120,32], queue: [120,32], external: [120,32],
    submodule: [120,32], model: [120,32], schema: [120,32], enum_def: [120,32],
    view: [120,32], util: [120,32]
};

const TIER_Y = {
  system: 0.1, container: 0.1,
  service: 0.3, worker: 0.3, module: 0.35, database: 0.3, api: 0.25,
  function: 0.55, route: 0.5, table: 0.6, class_def: 0.55,
    middleware: 0.5, webhook: 0.5, struct: 0.55, protocol: 0.55,
  column: 0.75, config: 0.75, file: 0.75, external: 0.7,
    script: 0.75, migration: 0.75, cache: 0.65, queue: 0.65,
    model: 0.6, schema: 0.6, enum_def: 0.65, view: 0.6, util: 0.65,
    submodule: 0.7, test: 0.8
};

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

const EDGE_DASH = {
  calls: null, delegates: null, uses: null,
  depends_on: '8 4', inherits: '8 4', implements: '8 4',
  contains: '3 3', creates: '3 3', produces: '3 3',
  reads_from: '12 4', writes_to: '12 4', updates: '12 4'
};

const RELATIONSHIP_HELP = {
  connects_to:   'General connection between components',
  reads_from:    'Reads data from this source (database, cache, file)',
  writes_to:     'Writes or persists data to this target',
  depends_on:    'Requires this to function \u2014 cannot work without it',
  authenticates: 'Handles auth verification through this service',
  calls:         'Directly invokes functions or methods on this target',
  inherits:      'Extends or subclasses this component',
  contains:      'Parent-child: this is nested inside or owned by',
  exposes:       'Makes functionality available externally (API, endpoint)',
  observes:      'Watches for changes or events from this source',
  creates:       'Instantiates or constructs instances of this target',
  produces:      'Generates output consumed by downstream components',
  consumes:      'Receives and processes input from this source',
  delegates:     'Forwards responsibility to this target to handle',
  controls:      'Manages lifecycle or behavior of this target',
  uses:          'Utilizes functionality from this target as a dependency',
  updates:       'Modifies state or data in this target',
  implements:    'Provides the concrete implementation of this interface',
  emits:         'Sends events or signals that others can listen to'
};

/* ----------------------------------------------------------------
   Mutable state
   ---------------------------------------------------------------- */
let selectedNodeId   = null;
let activeFilters    = new Set();
let simulation       = null;
let mainG            = null;
let zoom             = null;
let svgEl            = null;
let layoutMode       = 'clustered';
let collapsedGroups  = new Set();
let hiddenNodes      = new Set();
let contextMenuTarget = null;
let focusedMode      = false;
let tickCount        = 0;
let lastTickTime     = 0;
let navHistory       = [];
let zoomFitTimer     = null;

/* Global references for rebuilding */
let gNodeData    = [];
let gEdgeData    = [];
let gNodeMap     = {};
let gChildrenOf  = {};
let gParentIds   = new Set();
let gDepthMap    = {};
let gNodeGroups  = null;
let gEdgeGroups  = null;
let gGroupG      = null;
let gW = 0, gH = 0;

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
  initEscapeKey();
  initContextMenu();
  initLayoutToggle();
  renderHealth();
  renderQuestions();
  renderEmptyDetail();
  buildGraph();
});

/* ================================================================
   FILTERS (category-based)
   ================================================================ */
function initFilters() {
  const presentTypes = new Set(DATA.nodes.map(n => n.type));
  const group = document.getElementById('filter-group');
  Object.entries(TYPE_CATEGORIES).forEach(([cat, info]) => {
    if (!info.types.some(t => presentTypes.has(t))) return;
    const btn = document.createElement('button');
    btn.className = 'filter-btn';
    btn.dataset.category = cat;
    btn.innerHTML = '<span class="filter-dot" style="background:' + info.color + '"></span>' + cat;
    btn.addEventListener('click', () => {
      btn.classList.toggle('active');
      if (activeFilters.has(cat)) activeFilters.delete(cat);
      else activeFilters.add(cat);
      applyFilters();
    });
    group.appendChild(btn);
  });
}

function applyFilters() {
  const term = document.getElementById('search-input').value.toLowerCase();
  let visibleTypes = null;
  if (activeFilters.size > 0) {
    visibleTypes = new Set();
    activeFilters.forEach(cat => {
      TYPE_CATEGORIES[cat].types.forEach(t => visibleTypes.add(t));
    });
  }

  d3.selectAll('.node-group').each(function(d) {
    if (hiddenNodes.has(d.id)) { d3.select(this).style('display', 'none'); return; }
    const okType   = !visibleTypes || visibleTypes.has(d.type);
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
  if (hiddenNodes.has(nodeId)) return false;
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
   ESCAPE KEY
   ================================================================ */
function initEscapeKey() {
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      deselectAll();
      if (focusedMode) showAllNodes();
      hideContextMenu();
    }
  });
}

/* ================================================================
   CONTEXT MENU
   ================================================================ */
function initContextMenu() {
  document.getElementById('ctx-focus').addEventListener('click', () => {
    if (contextMenuTarget) focusOnNode(contextMenuTarget.id, 2);
    hideContextMenu();
  });
  document.getElementById('ctx-show-all').addEventListener('click', () => {
    showAllNodes();
    hideContextMenu();
  });
  document.addEventListener('click', e => {
    if (!e.target.closest('.context-menu')) hideContextMenu();
  });
}

function showContextMenu(event, d) {
  event.preventDefault();
  event.stopPropagation();
  contextMenuTarget = d;
  const menu = document.getElementById('context-menu');
  menu.style.left = event.pageX + 'px';
  menu.style.top  = event.pageY + 'px';
  menu.style.display = 'block';
}

function hideContextMenu() {
  document.getElementById('context-menu').style.display = 'none';
  contextMenuTarget = null;
}

function focusOnNode(nodeId, hops) {
  const visited = new Set([nodeId]);
  let frontier = [nodeId];
  for (let i = 0; i < hops; i++) {
    const next = [];
    frontier.forEach(nid => {
      DATA.edges.forEach(e => {
        if (e.source_id === nid && !visited.has(e.target_id)) {
          visited.add(e.target_id); next.push(e.target_id);
        }
        if (e.target_id === nid && !visited.has(e.source_id)) {
          visited.add(e.source_id); next.push(e.source_id);
        }
      });
    });
    frontier = next;
  }
  focusedMode = true;
  d3.selectAll('.node-group').style('display', d => visited.has(d.id) ? null : 'none');
  d3.selectAll('.edge-group').style('display', d => {
    const s = d.source.id || d.source, t = d.target.id || d.target;
    return (visited.has(s) && visited.has(t)) ? null : 'none';
  });
  d3.selectAll('.group-container').style('display', 'none');
  updateMinimap();
  scheduleZoomToFit(200);
}

function showAllNodes() {
  focusedMode = false;
  applyCollapse();
  applyFilters();
  updateMinimap();
  scheduleZoomToFit(200);
}

/* ================================================================
   LAYOUT TOGGLE
   ================================================================ */
function initLayoutToggle() {
  document.querySelectorAll('.layout-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const mode = btn.dataset.layout;
      if (mode === layoutMode) return;
      layoutMode = mode;
      document.querySelectorAll('.layout-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      rebuildSimulation();
    });
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

function navigateToNode(nodeId) {
  const nd = DATA.nodes.find(n => n.id === nodeId);
  if (!nd) return;
  if (selectedNodeId) {
    navHistory.push(selectedNodeId);
    if (navHistory.length > 5) navHistory.shift();
  }
  selectNode(gNodeMap[nodeId] || nd);
}

function navigateBack() {
  if (navHistory.length === 0) return;
  const prevId = navHistory.pop();
  selectNode(gNodeMap[prevId] || DATA.nodes.find(n => n.id === prevId));
}

function renderNodeDetail(nd) {
  const nodeMap = {};
  DATA.nodes.forEach(n => nodeMap[n.id] = n);

  const conns       = DATA.edges.filter(e => e.source_id === nd.id || e.target_id === nd.id);
  const statusColor = STATUS_COLORS[nd.status] || '#a0aec0';
  const typeColor   = TYPE_COLORS[nd.type] || '#6b7280';

  let h = '<div class="node-detail">';

  /* Back button */
  if (navHistory.length > 0) {
    h += '<button class="nav-back-btn" id="nav-back-btn">\u2190 Back</button>';
  }

  h += '<h2><span class="status-indicator" style="background:' + statusColor + '"></span>'
     + esc(nd.name) + '</h2>';
  h += '<span class="node-type-badge" style="background:' + typeColor + '20;color:' + typeColor + '">'
     + esc(nd.type) + '</span>';

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

  /* ---- Connection health summary ---- */
  if (conns.length > 0) {
    const outgoing = conns.filter(e => e.source_id === nd.id);
    const incoming = conns.filter(e => e.target_id === nd.id);
    const brokenConns = conns.filter(e => {
      const oid = e.source_id === nd.id ? e.target_id : e.source_id;
      const o = nodeMap[oid];
      return o && (o.status === 'broken' || o.status === 'deprecated');
    });
    const plannedConns = conns.filter(e => e.status === 'planned');
    const depsCount = conns.filter(e => e.relationship === 'depends_on').length;

    h += '<div class="field-label">Connections (' + conns.length + ')</div>';
    h += '<div class="conn-summary">';
    h += '<span class="conn-stat">\u2192 ' + outgoing.length + ' out</span>';
    h += '<span class="conn-stat">\u2190 ' + incoming.length + ' in</span>';
    if (brokenConns.length > 0) h += '<span class="conn-stat warn">\u26A0 ' + brokenConns.length + ' unhealthy</span>';
    if (plannedConns.length > 0) h += '<span class="conn-stat">\u2022 ' + plannedConns.length + ' planned</span>';
    h += '</div>';

    /* Hint */
    let hint = '';
    if (conns.length === 0) hint = 'Isolated';
    else if (outgoing.length > incoming.length * 3 && incoming.length > 0) hint = 'High fan-out \u2014 this node does a lot';
    else if (incoming.length > outgoing.length * 3 && outgoing.length > 0) hint = 'High fan-in \u2014 many things depend on this';
    else if (brokenConns.length > 0) hint = 'Connected to ' + brokenConns.length + ' broken component(s)';
    else if (depsCount >= 5) hint = 'Heavy dependencies';
    if (hint) h += '<div class="conn-hint">' + hint + '</div>';

    /* Detect bidirectional edges */
    const edgePairs = {};
    conns.forEach(e => {
      const key = [e.source_id, e.target_id].sort().join('|');
      if (!edgePairs[key]) edgePairs[key] = [];
      edgePairs[key].push(e);
    });
    const biKeys = new Set();
    Object.entries(edgePairs).forEach(([key, edges]) => {
      const hasSrc = edges.some(e => e.source_id === nd.id);
      const hasTgt = edges.some(e => e.target_id === nd.id);
      if (hasSrc && hasTgt) biKeys.add(key);
    });

    const biEdges = [], outEdges = [], inEdges = [];
    conns.forEach(e => {
      const key = [e.source_id, e.target_id].sort().join('|');
      if (biKeys.has(key)) { biEdges.push(e); }
      else if (e.source_id === nd.id) { outEdges.push(e); }
      else { inEdges.push(e); }
    });

    function renderConnItem(e) {
      const isSrc = e.source_id === nd.id;
      const otherId = isSrc ? e.target_id : e.source_id;
      const other = nodeMap[otherId];
      const otherName = other ? other.name : otherId.slice(0, 8);
      const otherType = other ? other.type : '';
      const edgeColor = EDGE_COLORS[e.relationship] || '#a0aec0';
      const otherTypeColor = TYPE_COLORS[otherType] || '#6b7280';
      const isUnhealthy = other && (other.status === 'broken' || other.status === 'deprecated');

      let item = '<div class="conn-item" data-node-id="' + otherId + '">';
      item += '<span class="conn-dot" style="background:' + edgeColor + '"></span>';
      item += '<span class="rel-badge" style="background:' + edgeColor + '20;color:' + edgeColor + '">' + esc(e.relationship) + '</span>';
      item += '<span class="conn-name">' + esc(otherName) + '</span>';
      if (otherType) item += '<span class="conn-type-badge" style="color:' + otherTypeColor + '">' + esc(otherType) + '</span>';
      if (isUnhealthy) item += '<span class="conn-warn">\u26A0</span>';
      if (e.status === 'planned') item += '<span style="font-size:10px;color:var(--text-muted)">(planned)</span>';
      if (e.label) item += '<div class="conn-edge-label">\u201C' + esc(e.label) + '\u201D</div>';
      if (RELATIONSHIP_HELP[e.relationship]) item += '<div class="conn-explanation">' + RELATIONSHIP_HELP[e.relationship] + '</div>';
      item += '</div>';
      return item;
    }

    if (outEdges.length > 0) {
      h += '<div class="field-label">\u2192 Outgoing (' + outEdges.length + ')</div>';
      outEdges.forEach(e => { h += renderConnItem(e); });
    }
    if (inEdges.length > 0) {
      h += '<div class="field-label">\u2190 Incoming (' + inEdges.length + ')</div>';
      inEdges.forEach(e => { h += renderConnItem(e); });
    }
    if (biEdges.length > 0) {
      h += '<div class="field-label">\u2194 Bidirectional (' + biEdges.length + ')</div>';
      biEdges.forEach(e => { h += renderConnItem(e); });
    }
  }

  h += '<div class="field-label">ID</div>';
  h += '<div class="field-value" style="font-family:monospace;font-size:11px;' +
       'color:var(--text-muted)">' + esc(nd.id) + '</div>';
  h += '</div>';

  document.getElementById('tab-details').innerHTML = h;

  /* Attach click handlers */
  document.querySelectorAll('.conn-item[data-node-id]').forEach(el => {
    el.addEventListener('click', () => { navigateToNode(el.dataset.nodeId); });
  });
  const backBtn = document.getElementById('nav-back-btn');
  if (backBtn) backBtn.addEventListener('click', () => navigateBack());

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

  document.querySelectorAll('.question-card').forEach(card => {
    card.addEventListener('click', () => {
      const ids = JSON.parse(card.dataset.highlight || '[]');
      if (ids.length > 0) highlightNodes(ids);
    });
  });
}

/* ================================================================
   HELPER: compute node size with degree bonus
   ================================================================ */
function getNodeSize(node, degree) {
  const base = NODE_SIZES[node.type] || [140, 40];
  const bonus = 1 + Math.min(degree / 20, 0.2);
  return [Math.round(base[0] * bonus), Math.round(base[1] * bonus)];
}

/* ================================================================
   HELPER: compute depth map for parent-child hierarchy
   ================================================================ */
function computeDepths(nodeData, childrenOf) {
  const depth = {};
  nodeData.forEach(n => { if (!n.parent_id) depth[n.id] = 0; });
  let changed = true;
  while (changed) {
    changed = false;
    nodeData.forEach(n => {
      if (n.parent_id && depth[n.parent_id] !== undefined && depth[n.id] === undefined) {
        depth[n.id] = depth[n.parent_id] + 1;
        changed = true;
      }
    });
  }
  nodeData.forEach(n => { if (depth[n.id] === undefined) depth[n.id] = 0; });
  return depth;
}

/* ================================================================
   HELPER: get all descendants of a node
   ================================================================ */
function getAllDescendants(parentId) {
  const result = [];
  const stack = [...(gChildrenOf[parentId] || [])];
  while (stack.length) {
    const id = stack.pop();
    result.push(id);
    if (gChildrenOf[id]) stack.push(...gChildrenOf[id]);
  }
  return result;
}

/* ================================================================
   D3 FORCE-DIRECTED GRAPH
   ================================================================ */
function buildGraph() {
  svgEl = d3.select('#graph-svg');
  const container = document.getElementById('canvas-panel');
  gW = container.clientWidth;
  gH = container.clientHeight;

  /* ---- Compute degree per node ---- */
  const degreeMap = {};
  DATA.nodes.forEach(n => degreeMap[n.id] = 0);
  DATA.edges.forEach(e => {
    if (degreeMap[e.source_id] !== undefined) degreeMap[e.source_id]++;
    if (degreeMap[e.target_id] !== undefined) degreeMap[e.target_id]++;
  });

  /* ---- Prepare node data ---- */
  gNodeData = DATA.nodes.map(n => {
    const [w, h] = getNodeSize(n, degreeMap[n.id] || 0);
    return {
      ...n,
      x: gW / 2 + (Math.random() - 0.5) * gW * 0.6,
      y: gH / 2 + (Math.random() - 0.5) * gH * 0.6,
      w: w, h: h
    };
  });
  gNodeMap = {};
  gNodeData.forEach(n => gNodeMap[n.id] = n);

  /* ---- Prepare edge data ---- */
  gEdgeData = DATA.edges
    .filter(e => gNodeMap[e.source_id] && gNodeMap[e.target_id])
    .map(e => ({ ...e, source: e.source_id, target: e.target_id }));

  const edgePairCount = {};
  gEdgeData.forEach(e => {
    const key = [e.source_id, e.target_id].sort().join('|');
    if (!edgePairCount[key]) edgePairCount[key] = 0;
    e._pairIndex = edgePairCount[key]++;
  });
  gEdgeData.forEach(e => {
    const key = [e.source_id, e.target_id].sort().join('|');
    e._pairTotal = edgePairCount[key];
  });

  /* ---- Identify parent/child grouping ---- */
  gParentIds  = new Set(gNodeData.filter(n => n.parent_id).map(n => n.parent_id));
  gChildrenOf = {};
  gNodeData.forEach(n => {
    if (n.parent_id) {
      if (!gChildrenOf[n.parent_id]) gChildrenOf[n.parent_id] = [];
      gChildrenOf[n.parent_id].push(n.id);
    }
  });

  /* ---- Compute depths & auto-collapse depth > 2 ---- */
  gDepthMap = computeDepths(gNodeData, gChildrenOf);
  Object.keys(gChildrenOf).forEach(pid => {
    if ((gDepthMap[pid] || 0) >= 2) collapsedGroups.add(pid);
  });

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
        .attr('fill', color).attr('opacity', 0.4);
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
    .attr('width', gW).attr('height', gH)
    .attr('fill', 'transparent');

  mainG = svgEl.append('g').attr('class', 'main-group');

  /* ---- Layers (draw order: groups, edges, nodes) ---- */
  gGroupG = mainG.append('g').attr('class', 'groups-layer');
  const edgeG  = mainG.append('g').attr('class', 'edges-layer');
  const nodeG  = mainG.append('g').attr('class', 'nodes-layer');

  /* ---- Draw edges ---- */
  gEdgeGroups = edgeG.selectAll('.edge-group')
    .data(gEdgeData).join('g')
    .attr('class', d => 'edge-group' + (d.status === 'planned' ? ' planned' : ''));

  gEdgeGroups.append('path')
    .attr('class', d => 'edge-line' + (d.status === 'planned' ? ' planned' : ''))
    .attr('stroke', d => EDGE_COLORS[d.relationship] || '#a0aec0')
    .attr('stroke-dasharray', d => d.status === 'planned' ? '6 4' : (EDGE_DASH[d.relationship] || null))
    .attr('marker-end', d => 'url(#arrow-' + d.relationship + ')');

  gEdgeGroups.append('path')
    .attr('class', 'edge-hit-zone')
    .attr('stroke', 'transparent').attr('stroke-width', 12)
    .attr('fill', 'none').style('pointer-events', 'stroke');

  gEdgeGroups.append('text')
    .attr('class', 'edge-label')
    .attr('text-anchor', 'middle').attr('dy', -6)
    .text(d => d.label || d.relationship);

  /* ---- Draw nodes ---- */
  gNodeGroups = nodeG.selectAll('.node-group')
    .data(gNodeData).join('g')
    .attr('class', d => 'node-group')
    .attr('id', d => 'node-' + d.id)
    .on('click', (event, d) => { event.stopPropagation(); selectNode(d); })
    .on('contextmenu', (event, d) => showContextMenu(event, d))
    .on('mouseenter', (event, d) => {
      gEdgeGroups.select('.edge-label').style('opacity', e => {
        const s = e.source.id || e.source, t = e.target.id || e.target;
        return (s === d.id || t === d.id) ? 1 : null;
      });
    })
    .on('mouseleave', () => {
      if (!selectedNodeId) gEdgeGroups.select('.edge-label').style('opacity', null);
    })
    .on('dblclick', (event, d) => {
      event.stopPropagation();
      if (gChildrenOf[d.id]) toggleCollapse(d.id);
    })
    .call(d3.drag()
      .on('start', dragStarted)
      .on('drag',  dragged)
      .on('end',   dragEnded));

  /* Background rect */
  gNodeGroups.append('rect')
    .attr('class', 'node-rect')
    .attr('width', d => d.w).attr('height', d => d.h)
    .attr('fill', 'var(--node-bg)')
    .attr('stroke', d => d.status === 'broken' ? '#e53e3e' : 'var(--node-border)')
    .attr('stroke-width', d => d.status === 'broken' ? 2 : 1.5)
    .attr('stroke-dasharray', d => d.status === 'planned' ? '6 3' : null);

  /* Type color tint overlay */
  gNodeGroups.append('rect')
    .attr('width', d => d.w).attr('height', d => d.h)
    .attr('rx', 8).attr('ry', 8)
    .attr('fill', d => d.status === 'deprecated' ? '#9ca3af' : (TYPE_COLORS[d.type] || '#6b7280'))
    .attr('fill-opacity', d => d.status === 'planned' ? 0.04 : 0.08)
    .attr('pointer-events', 'none');

  /* Left color bar */
  gNodeGroups.append('rect')
    .attr('class', d => 'node-status-bar' + (d.status === 'in_progress' ? ' status-bar-in_progress' : ''))
    .attr('width', 4).attr('height', d => d.h)
    .attr('rx', 2)
    .attr('fill', d => TYPE_COLORS[d.type] || '#6b7280');

  /* Type badge pill */
  gNodeGroups.filter(d => d.w > 120).append('rect')
    .attr('x', d => d.w - (d.type.length * 5.5 + 10))
    .attr('y', 6)
    .attr('width', d => d.type.length * 5.5 + 10)
    .attr('height', 16).attr('rx', 8)
    .attr('fill', d => TYPE_COLORS[d.type] || '#6b7280')
    .attr('fill-opacity', 0.15);

  gNodeGroups.filter(d => d.w > 120).append('text')
    .attr('class', 'node-type-label')
    .attr('x', d => d.w - 8).attr('y', 18)
    .attr('text-anchor', 'end')
    .attr('fill', d => TYPE_COLORS[d.type] || '#6b7280')
    .text(d => d.type);

  /* Name */
  gNodeGroups.append('text')
    .attr('class', 'node-name')
    .attr('x', 12).attr('y', d => d.h <= 36 ? d.h / 2 + 4 : 24)
    .attr('font-size', d => d.h <= 36 ? '12px' : '14px')
    .text(d => trunc(d.name, Math.floor((d.w - 40) / 7)));

  /* SVG title tooltip */
  gNodeGroups.append('title')
    .text(d => d.name + ' (' + d.type + ', ' + d.status + ')'
      + (d.description ? '\n' + d.description : ''));

  /* Description (only for h >= 48) */
  gNodeGroups.filter(d => d.h >= 48).append('text')
    .attr('class', 'node-desc')
    .attr('x', 12).attr('y', 42)
    .text(d => d.description ? trunc(d.description, Math.floor((d.w - 20) / 7)) : '');

  /* Source file (only for h >= 56) */
  gNodeGroups.filter(d => d.h >= 56).append('text')
    .attr('class', 'node-source')
    .attr('x', 12).attr('y', d => d.h - 8)
    .text(d => d.source_file ? trunc(d.source_file, Math.floor((d.w - 20) / 6)) : '');

  /* Apply status opacity */
  gNodeGroups
    .style('opacity', d => {
      if (d.status === 'planned') return 0.45;
      if (d.status === 'deprecated') return 0.5;
      return null;
    })
    .style('filter', d => d.status === 'deprecated' ? 'grayscale(0.8)' : null);

  /* ---- Build simulation ---- */
  rebuildSimulation();

  /* ---- Apply auto-collapse ---- */
  applyCollapse();

  /* Initial fit */
  setTimeout(() => { zoomToFit(); updateMinimap(); }, 300);
  initMinimap(gW, gH);

  /* Zoom buttons */
  document.getElementById('zoom-in').addEventListener('click',  () => svgEl.transition().duration(300).call(zoom.scaleBy, 1.3));
  document.getElementById('zoom-out').addEventListener('click', () => svgEl.transition().duration(300).call(zoom.scaleBy, 0.7));
  document.getElementById('zoom-fit').addEventListener('click', () => zoomToFit());
  document.getElementById('help-btn').addEventListener('click', () => {
    const p = document.getElementById('help-panel');
    p.style.display = p.style.display === 'none' ? 'block' : 'none';
  });
}

/* ================================================================
   SIMULATION BUILDER
   ================================================================ */
function clusterForce() {
  let nodes;
  function force(alpha) {
    nodes.forEach(d => {
      if (d.parent_id && gNodeMap[d.parent_id]) {
        const parent = gNodeMap[d.parent_id];
        d.vx += (parent.x - d.x) * 0.15;
        d.vy += (parent.y - d.y) * alpha * 0.5;
      }
    });
  }
  force.initialize = function(_) { nodes = _; };
  return force;
}

function groupRepulsionForce() {
  let nodes;
  function force(alpha) {
    const boxes = {};
    nodes.forEach(d => {
      const pid = d.parent_id;
      if (!pid || !gParentIds.has(pid)) return;
      if (!boxes[pid]) boxes[pid] = { x1:Infinity, y1:Infinity, x2:-Infinity, y2:-Infinity, nodes:[] };
      const b = boxes[pid];
      b.x1 = Math.min(b.x1, d.x - d.w/2); b.y1 = Math.min(b.y1, d.y - d.h/2);
      b.x2 = Math.max(b.x2, d.x + d.w/2); b.y2 = Math.max(b.y2, d.y + d.h/2);
      b.nodes.push(d);
    });
    const pids = Object.keys(boxes);
    for (let i = 0; i < pids.length; i++) {
      for (let j = i+1; j < pids.length; j++) {
        const da = gDepthMap[pids[i]] || 0, db = gDepthMap[pids[j]] || 0;
        if (da !== db) continue;
        const a = boxes[pids[i]], b = boxes[pids[j]];
        const pad = 50;
        const ox = Math.min(a.x2+pad, b.x2+pad) - Math.max(a.x1-pad, b.x1-pad);
        const oy = Math.min(a.y2+pad, b.y2+pad) - Math.max(a.y1-pad, b.y1-pad);
        if (ox > 0 && oy > 0) {
          const dx = ((a.x1+a.x2)/2) - ((b.x1+b.x2)/2);
          const sep = (dx >= 0 ? 1 : -1) * alpha * 0.8;
          a.nodes.forEach(n => { n.vx += sep; });
          b.nodes.forEach(n => { n.vx -= sep; });
        }
      }
    }
  }
  force.initialize = function(_) { nodes = _; };
  return force;
}

function rebuildSimulation() {
  if (simulation) simulation.stop();
  tickCount = 0;

  simulation = d3.forceSimulation(gNodeData)
    .force('link', d3.forceLink(gEdgeData).id(d => d.id)
      .distance(d => {
        const s = gNodeMap[d.source.id || d.source];
        const t = gNodeMap[d.target.id || d.target];
        return (s && t && s.parent_id && s.parent_id === t.parent_id) ? 220 : 180;
      }).strength(0.4))
    .force('collision', d3.forceCollide().radius(d => Math.max(d.w, d.h) / 2 + 20).strength(0.8))
    .force('x', d3.forceX(gW / 2).strength(0.04))
    .alphaDecay(0.02)
    .alphaMin(0.01);

  if (layoutMode === 'clustered') {
    simulation
      .force('charge', d3.forceManyBody().strength(-400).distanceMax(600))
      .force('center', d3.forceCenter(gW / 2, gH / 2).strength(0.03))
      .force('tierY', d3.forceY(d => {
        const tier = TIER_Y[d.type];
        return (tier !== undefined ? tier : 0.5) * gH;
      }).strength(0.3))
      .force('cluster', clusterForce())
      .force('groupRepulsion', groupRepulsionForce());
  } else {
    simulation
      .force('charge', d3.forceManyBody().strength(-800).distanceMax(600))
      .force('center', d3.forceCenter(gW / 2, gH / 2).strength(0.05))
      .force('tierY', d3.forceY(gH / 2).strength(0.02));
  }

  simulation
    .on('tick', () => {
      tickCount++;
      if (tickCount > 500) { simulation.stop(); return; }
      const now = performance.now();
      if (now - lastTickTime < 16) return;
      lastTickTime = now;
      onTick();
    })
    .on('end', () => { zoomToFit(); updateMinimap(); });

  simulation.alpha(1).restart();
}

function onTick() {
  gNodeGroups.attr('transform', d =>
    'translate(' + (d.x - d.w / 2) + ',' + (d.y - d.h / 2) + ')');

  gEdgeGroups.select('.edge-line').attr('d', d => {
    const sx = d.source.x, sy = d.source.y;
    const tx = d.target.x, ty = d.target.y;
    const dx = tx - sx, dy = ty - sy;
    const dist = Math.sqrt(dx * dx + dy * dy);
    const offset = (d._pairTotal > 1) ? (d._pairIndex - (d._pairTotal-1)/2) * 0.3 : 0;
    const dr = dist * (0.7 + offset);
    const sweep = d._pairIndex % 2 === 0 ? 1 : 0;
    return 'M'+sx+','+sy+'A'+Math.abs(dr)+','+Math.abs(dr)+' 0 0,'+sweep+' '+tx+','+ty;
  });

  gEdgeGroups.select('.edge-hit-zone').attr('d', d => {
    const sx = d.source.x, sy = d.source.y;
    const tx = d.target.x, ty = d.target.y;
    const dx = tx - sx, dy = ty - sy;
    const dist = Math.sqrt(dx * dx + dy * dy);
    const offset = (d._pairTotal > 1) ? (d._pairIndex - (d._pairTotal-1)/2) * 0.3 : 0;
    const dr = dist * (0.7 + offset);
    const sweep = d._pairIndex % 2 === 0 ? 1 : 0;
    return 'M'+sx+','+sy+'A'+Math.abs(dr)+','+Math.abs(dr)+' 0 0,'+sweep+' '+tx+','+ty;
  });

  gEdgeGroups.select('text')
    .attr('x', d => (d.source.x + d.target.x) / 2)
    .attr('y', d => (d.source.y + d.target.y) / 2);

  updateGroupBGs();
}

/* ================================================================
   GROUP BACKGROUNDS (parent nodes)
   ================================================================ */
function updateGroupBGs() {
  const groups = [];
  gParentIds.forEach(pid => {
    if (collapsedGroups.has(pid)) return;
    const parent = gNodeData.find(n => n.id === pid);
    if (!parent) return;
    const children = (gChildrenOf[pid] || [])
      .map(cid => gNodeData.find(n => n.id === cid)).filter(Boolean)
      .filter(n => !hiddenNodes.has(n.id));
    if (children.length === 0) return;
    const all = [parent, ...children];
    const pad = 50;
    const x1  = d3.min(all, n => n.x - n.w / 2)  - pad;
    const y1  = d3.min(all, n => n.y - n.h / 2) - pad - 18;
    const x2  = d3.max(all, n => n.x + n.w / 2)  + pad;
    const y2  = d3.max(all, n => n.y + n.h / 2) + pad;
    const typeColor = TYPE_COLORS[parent.type] || '#6b7280';
    groups.push({ id: pid, name: parent.name, x: x1, y: y1,
                  w: x2 - x1, h: y2 - y1, count: children.length,
                  typeColor: typeColor });
  });

  /* Also add collapsed group pills */
  const pills = [];
  collapsedGroups.forEach(pid => {
    const parent = gNodeData.find(n => n.id === pid);
    if (!parent) return;
    const childCount = getAllDescendants(pid).length;
    if (childCount === 0) return;
    const typeColor = TYPE_COLORS[parent.type] || '#6b7280';
    pills.push({ id: pid + '-pill', parentId: pid, name: parent.name,
                 x: parent.x, y: parent.y + parent.h / 2 + 16,
                 count: childCount, typeColor: typeColor });
  });

  /* Render expanded group boxes */
  const sel = gGroupG.selectAll('.group-container').data(groups, d => d.id);
  const entered = sel.enter().append('g').attr('class', 'group-container');
  entered.append('rect').attr('class', 'group-bg');
  entered.append('text').attr('class', 'group-label');
  entered.select('.group-bg').on('dblclick', (event, d) => {
    event.stopPropagation();
    toggleCollapse(d.id);
  });
  const merged = entered.merge(sel);
  merged.select('.group-bg')
    .attr('x', d => d.x).attr('y', d => d.y)
    .attr('width', d => d.w).attr('height', d => d.h)
    .attr('fill', d => d.typeColor)
    .attr('fill-opacity', 0.04)
    .attr('stroke', d => d.typeColor)
    .attr('stroke-opacity', 0.15)
    .attr('stroke-width', 1.5);
  merged.select('.group-label')
    .attr('x', d => d.x + 12).attr('y', d => d.y + 14)
    .text(d => d.name + ' (' + d.count + ')');
  sel.exit().remove();

  /* Render collapsed pills */
  const pillSel = gGroupG.selectAll('.collapsed-pill').data(pills, d => d.id);
  const pillEntered = pillSel.enter().append('g').attr('class', 'collapsed-pill')
    .on('click', (event, d) => { event.stopPropagation(); toggleCollapse(d.parentId); });
  pillEntered.append('rect');
  pillEntered.append('text');
  const pillMerged = pillEntered.merge(pillSel);
  pillMerged.select('rect')
    .attr('x', d => { const pillW = Math.max(100, d.name.length * 7 + 40); return d.x - pillW/2; })
    .attr('y', d => d.y - 10)
    .attr('width', d => Math.max(100, d.name.length * 7 + 40)).attr('height', 20)
    .attr('fill', d => d.typeColor).attr('fill-opacity', 0.15)
    .attr('stroke', d => d.typeColor).attr('stroke-opacity', 0.3);
  pillMerged.select('text')
    .attr('x', d => d.x).attr('y', d => d.y + 4)
    .attr('text-anchor', 'middle')
    .attr('font-size', '10px')
    .attr('fill', d => d.typeColor)
    .text(d => '\u25B6 ' + d.name + ' (' + d.count + ')');
  pillSel.exit().remove();
}

/* ================================================================
   COLLAPSE / EXPAND
   ================================================================ */
function toggleCollapse(parentId) {
  if (collapsedGroups.has(parentId)) collapsedGroups.delete(parentId);
  else collapsedGroups.add(parentId);
  applyCollapse();
}

function applyCollapse() {
  hiddenNodes = new Set();
  collapsedGroups.forEach(pid => {
    getAllDescendants(pid).forEach(cid => hiddenNodes.add(cid));
  });

  d3.selectAll('.node-group').each(function(d) {
    d3.select(this).style('display', hiddenNodes.has(d.id) ? 'none' : null);
  });
  d3.selectAll('.edge-group').each(function(d) {
    const s = d.source.id || d.source;
    const t = d.target.id || d.target;
    d3.select(this).style('display', (hiddenNodes.has(s) || hiddenNodes.has(t)) ? 'none' : null);
  });
  updateMinimap();
  scheduleZoomToFit(200);
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
  const nodes = d3.selectAll('.node-group').data().filter(n => !hiddenNodes.has(n.id));
  if (nodes.length === 0) return;

  const pad = 50;
  const x1 = d3.min(nodes, d => d.x - d.w / 2) - pad;
  const y1 = d3.min(nodes, d => d.y - d.h / 2) - pad;
  const x2 = d3.max(nodes, d => d.x + d.w / 2) + pad;
  const y2 = d3.max(nodes, d => d.y + d.h / 2) + pad;
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
    .attr('stroke', '#a0aec0').attr('stroke-width', 1).attr('opacity', 0.2);

  /* minimap nodes -- colored by type */
  g.selectAll('.mm-node')
    .data(nodes).join('rect').attr('class', 'mm-node')
    .attr('x', d => d.x - d.w / 2).attr('y', d => d.y - d.h / 2)
    .attr('width', d => d.w).attr('height', d => d.h)
    .attr('rx', 3)
    .attr('fill', d => TYPE_COLORS[d.type] || '#6b7280')
    .attr('opacity', 0.7);

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
function scheduleZoomToFit(delay) {
  if (zoomFitTimer) clearTimeout(zoomFitTimer);
  zoomFitTimer = setTimeout(() => { zoomToFit(); updateMinimap(); }, delay || 200);
}

function zoomToFit() {
  const ctr   = document.getElementById('canvas-panel');
  const W     = ctr.clientWidth;
  const H     = ctr.clientHeight;
  const nodes = d3.selectAll('.node-group')
    .filter(function(d) {
      return !hiddenNodes.has(d.id) && d3.select(this).style('display') !== 'none';
    }).data();
  if (nodes.length === 0) return;

  const pad = 60;
  const x1 = d3.min(nodes, d => d.x - d.w / 2) - pad;
  const y1 = d3.min(nodes, d => d.y - d.h / 2) - pad;
  const x2 = d3.max(nodes, d => d.x + d.w / 2) + pad;
  const y2 = d3.max(nodes, d => d.y + d.h / 2) + pad;
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
  const x1  = d3.min(nodes, d => d.x - d.w / 2) - pad;
  const y1  = d3.min(nodes, d => d.y - d.h / 2) - pad;
  const x2  = d3.max(nodes, d => d.x + d.w / 2) + pad;
  const y2  = d3.max(nodes, d => d.y + d.h / 2) + pad;
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
