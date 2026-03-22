"""X-Ray Viewer -- generates a self-contained HTML blueprint visualization with D3.js."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from src.db import Database
from src.models import (
    EDGE_RELATIONSHIP_DESCRIPTIONS,
    NODE_STATUS_DESCRIPTIONS,
    NODE_TYPE_DESCRIPTIONS,
)


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
        "node_type_descriptions": NODE_TYPE_DESCRIPTIONS,
        "node_status_descriptions": NODE_STATUS_DESCRIPTIONS,
        "edge_relationship_descriptions": EDGE_RELATIONSHIP_DESCRIPTIONS,
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
    # Escape </script> to prevent XSS if any node data contains it (OWASP recommendation)
    safe_json = data_json.replace("</", "<\\/")
    return _HTML_TEMPLATE.replace("__BLUEPRINT_DATA__", safe_json).replace(
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
  --card-tint-opacity: 0.06;
  --card-border-opacity: 0.2;
  --card-text: #1e293b;
  --card-subtitle: #475569;
  --card-stats: #64748b;
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
  --card-tint-opacity: 0.12;
  --card-border-opacity: 0.3;
  --card-text: #e2e8f0;
  --card-subtitle: #94a3b8;
  --card-stats: #64748b;
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
   BREADCRUMB BAR (32px)
   ================================================================ */
#breadcrumb-bar { height: 32px; display: flex; align-items: center; gap: 4px; padding: 0 16px; background: var(--bg); border-bottom: 1px solid var(--border-light, var(--border)); font-size: 12px; }
.breadcrumb-item { cursor: pointer; padding: 2px 6px; border-radius: 4px; transition: all 0.15s; white-space: nowrap; color: var(--text-secondary); }
.breadcrumb-item:hover { background: var(--bg-tertiary); color: var(--accent); }
.breadcrumb-item.active { font-weight: 700; color: var(--text); cursor: default; }
.breadcrumb-sep { color: var(--text-muted); font-size: 10px; }

/* Overview cards */
.overview-card { cursor: pointer; }
.overview-card:hover .card-bg { stroke-width: 2.5; filter: brightness(1.1); }
.agg-edge-label { font-size: 11px; font-weight: 600; fill: var(--text-secondary); }
.level-subtitle { pointer-events: none; }

/* Ghost nodes (Level 2) */
.ghost-node .node-rect { stroke-dasharray: 6 3; opacity: 0.55; }
.ghost-node .node-name { opacity: 0.8; font-style: italic; }
.ghost-label { font-size: 9px; fill: var(--text-muted); opacity: 0.7; }
.ghost-edge .edge-line { stroke-dasharray: 8 4; opacity: 0.15; }
.ghost-edge:hover .edge-line { opacity: 0.6; }

/* Focus center (Level 3) */
.focus-center .node-rect { stroke-width: 3; filter: drop-shadow(0 0 8px var(--accent)); }

/* Drill-in button */
.drill-in-btn { display: block; width: 100%; padding: 10px; margin-top: 12px; border: 1px solid var(--accent); border-radius: 6px; background: transparent; color: var(--accent); font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
.drill-in-btn:hover { background: var(--accent); color: #fff; }

/* ================================================================
   MAIN LAYOUT -- left 65% canvas, right 35% panel
   ================================================================ */
#main {
  display: flex;
  height: calc(100% - 82px);
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
.explain-section { margin: 8px 0 12px; }
.explain-toggle {
  font-size: 12px; font-weight: 600;
  color: var(--accent); background: none; border: none;
  cursor: pointer; padding: 4px 0; display: block;
}
.explain-toggle:hover { text-decoration: underline; }
.explain-body {
  font-size: 12px; color: var(--text-secondary);
  line-height: 1.6; padding: 8px 0 4px;
}
.explain-text { margin-bottom: 4px; }
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
  cursor: pointer;
  transition: background 0.15s;
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
.issue-explanation {
  font-size: 11px; color: var(--text-muted);
  margin-top: 6px; padding-top: 6px;
  border-top: 1px solid var(--border-light); line-height: 1.5;
}

/* ================================================================
   QUESTIONS TAB
   ================================================================ */
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

/* ================================================================
   LAYERS TAB
   ================================================================ */
.layers-container { padding: 16px; }
.layers-title { font-size: 16px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
.layers-subtitle { font-size: 12px; color: var(--text-muted); margin-bottom: 16px; }
.layer-card {
  padding: 12px 14px; margin-bottom: 4px; border-radius: 8px;
  background: var(--bg-secondary); border-left: 4px solid;
  transition: background 0.15s;
}
.layer-card:hover { background: var(--bg-tertiary); }
.layer-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.layer-icon { font-size: 16px; }
.layer-name { font-size: 14px; font-weight: 700; color: var(--text); flex: 1; }
.layer-count {
  font-size: 11px; color: var(--text-muted);
  background: var(--bg-tertiary); padding: 2px 8px; border-radius: 10px;
}
.layer-description { font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; font-style: italic; }
.layer-groups { display: flex; flex-wrap: wrap; gap: 4px; }
.layer-group-pill {
  font-size: 11px; padding: 2px 8px; border-radius: 4px;
  background: var(--bg-tertiary); color: var(--text-secondary);
  cursor: pointer; transition: all 0.15s;
}
.layer-group-pill:hover { background: var(--accent); color: #fff; }
.layer-arrow { text-align: center; color: var(--text-muted); font-size: 14px; padding: 2px 0; opacity: 0.4; }
.layers-flow-summary { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border); }
.flow-title { font-size: 13px; font-weight: 700; color: var(--text); margin-bottom: 8px; }
.flow-item { padding: 6px 0; border-bottom: 1px solid var(--border); }
.flow-item:last-child { border-bottom: none; }
.flow-path { font-size: 12px; font-weight: 600; color: var(--text); display: block; }
.flow-desc { font-size: 11px; color: var(--text-muted); }

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

.edge-line { fill: none; stroke-width: 1.5; opacity: 0.08; }
.edge-calls .edge-line { stroke-dasharray: none; }
.edge-depends .edge-line { stroke-dasharray: 8 4; }
.edge-data .edge-line { stroke-dasharray: 3 3; }
.edge-structural .edge-line { stroke-dasharray: 12 4 2 4; }
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
.edge-group.highlighted .edge-line { stroke-width: 3; opacity: 1; }
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
.conn-context { width:100%; font-size:11px; color:var(--text-secondary); padding-left:10px; margin-top:2px; line-height:1.4; }
.conn-explanation { width:100%; font-size:10px; color:var(--text-muted); padding-left:10px; }

/* Back button */
.nav-back-btn { font-size:12px; padding:4px 10px; border:1px solid var(--border); border-radius:4px; background:var(--bg); color:var(--text-secondary); cursor:pointer; margin-bottom:8px; }
.nav-back-btn:hover { border-color:var(--accent); color:var(--accent); }

/* Edge hit zone */
.edge-hit-zone { pointer-events:stroke; }

/* ================================================================
   HELP PANEL (Legend + Shortcuts)
   ================================================================ */
#help-panel {
  width: 320px; max-height: 420px;
  display: none; flex-direction: column;
  position: absolute; bottom: 48px; left: 12px;
  background: var(--bg); border: 1px solid var(--border);
  border-radius: 8px; box-shadow: 0 4px 16px var(--shadow-lg);
  z-index: 100; overflow: hidden;
}
.help-tabs {
  display: flex; border-bottom: 1px solid var(--border);
  background: var(--bg-secondary); flex-shrink: 0;
}
.help-tab-btn {
  flex: 1; padding: 8px 0; font-size: 12px; font-weight: 600;
  border: none; background: transparent; color: var(--text-secondary);
  cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.15s;
}
.help-tab-btn:hover { color: var(--text); }
.help-tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); background: var(--tab-active-bg); }
.help-tab-content { flex: 1; overflow-y: auto; }
.help-tab-pane { display: none; padding: 10px 12px; }
.help-tab-pane.active { display: block; }
.legend-section {
  font-size: 9px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.5px; color: var(--text-muted); margin: 10px 0 6px; padding-top: 6px;
  border-top: 1px solid var(--border-light);
}
.legend-section:first-child { border-top: none; margin-top: 0; padding-top: 0; }
.legend-row {
  display: flex; align-items: center; gap: 8px;
  padding: 3px 0; font-size: 12px; color: var(--text-secondary);
}
.legend-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.legend-name { font-weight: 600; color: var(--text); }
.legend-types { font-size: 10px; color: var(--text-muted); }
.legend-status-dot {
  width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
}
.legend-status-dot.dashed {
  background: transparent !important;
  border: 2px dashed currentColor;
  width: 8px; height: 8px;
}
.legend-status-dot.pulsing { animation: pulse-bar 2s ease-in-out infinite; }
.legend-status-dot.grayscale { filter: grayscale(0.8); opacity: 0.5; }
.legend-edge-row {
  display: flex; align-items: center; gap: 8px;
  padding: 3px 0; font-size: 12px; color: var(--text-secondary);
}
.legend-edge-line {
  width: 30px; height: 2px; flex-shrink: 0;
}

/* ================================================================
   STATUS SUMMARY BAR
   ================================================================ */
.status-summary {
  display: flex; gap: 10px; align-items: center;
  font-size: 11px; margin-left: 8px;
  padding-left: 8px; border-left: 1px solid var(--border);
}
.status-item {
  display: flex; align-items: center; gap: 4px;
  white-space: nowrap; color: var(--text-secondary);
}
.status-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
}

/* ================================================================
   ONBOARDING OVERLAY
   ================================================================ */
#onboarding-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.45); z-index: 2000;
  display: flex; align-items: center; justify-content: center;
}
.onboarding-card {
  background: var(--bg); border-radius: 12px;
  box-shadow: 0 8px 32px var(--shadow-lg);
  padding: 28px 32px; max-width: 420px; width: 90%;
}
.onboarding-card h3 {
  font-size: 18px; margin-bottom: 16px; color: var(--text);
}
.onboarding-hints { list-style: none; margin: 0 0 20px; }
.onboarding-hint {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 8px 0; font-size: 13px; color: var(--text-secondary);
  line-height: 1.5;
}
.onboarding-hint .hint-icon {
  flex-shrink: 0; width: 22px; text-align: center; font-size: 15px;
}
.onboarding-dismiss {
  display: block; width: 100%;
  padding: 10px; border: none; border-radius: 8px;
  background: var(--accent); color: #fff;
  font-size: 14px; font-weight: 600; cursor: pointer;
  transition: background 0.15s;
}
.onboarding-dismiss:hover { background: var(--accent-hover); }
.onboarding-progress { display: flex; gap: 6px; margin-bottom: 16px; justify-content: center; }
.onboarding-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--border); transition: all 0.2s;
}
.onboarding-dot.active { background: var(--accent); transform: scale(1.3); }
.onboarding-dot.done { background: var(--accent); opacity: 0.5; }
.onboarding-back {
  flex: 0 0 auto; padding: 10px 16px;
  border: 1px solid var(--border); border-radius: 8px;
  background: var(--bg); color: var(--text-secondary);
  font-size: 14px; font-weight: 600; cursor: pointer;
  transition: all 0.15s;
}
.onboarding-back:hover { border-color: var(--accent); color: var(--accent); }
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
  <div class="status-summary" id="status-summary"></div>
  <div class="filter-group" id="filter-group"></div>
  <button id="theme-toggle" title="Toggle theme">&#9681;</button>
</div>

<div id="breadcrumb-bar">
  <span class="breadcrumb-item active" data-level="1">Overview</span>
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
    <div id="help-panel">
      <div class="help-tabs">
        <button class="help-tab-btn active" data-help-tab="legend">Legend</button>
        <button class="help-tab-btn" data-help-tab="shortcuts">Shortcuts</button>
      </div>
      <div class="help-tab-content">
        <div id="help-legend" class="help-tab-pane active"></div>
        <div id="help-shortcuts" class="help-tab-pane">
          <div style="font-size:12px;line-height:1.8;color:var(--text-secondary)">
            <b>Dbl-click group</b> — drill into group<br>
            <b>Dbl-click node</b> — focus on connections<br>
            <b>Dbl-click ghost</b> — go to ghost's group<br>
            <b>Escape / Backspace</b> — go back one level<br>
            <b>Right-click node</b> — focus neighborhood<br>
            <b>Click node</b> — view details in panel
          </div>
        </div>
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
      <button class="tab-btn" data-tab="layers">Layers</button>
    </div>
    <div class="tab-content">
      <div id="tab-details"   class="tab-pane active"></div>
      <div id="tab-health"    class="tab-pane"></div>
      <div id="tab-questions" class="tab-pane"></div>
      <div id="tab-layers"    class="tab-pane"></div>
    </div>
  </div>
</div>

<!-- Context menu (hidden by default) -->
<div id="context-menu" class="context-menu" style="display:none">
  <div class="context-menu-item" id="ctx-focus">Focus (2-hop neighborhood)</div>
  <div class="context-menu-item" id="ctx-show-all">Show all</div>
</div>

<!-- Edge tooltip (hidden by default) -->
<div id="edge-tooltip" style="display:none;position:fixed;background:var(--tooltip-bg);color:var(--tooltip-text);border-radius:8px;padding:10px 14px;font-size:12px;max-width:320px;z-index:1001;box-shadow:0 4px 16px var(--shadow-lg);pointer-events:none;line-height:1.6"></div>

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

function getTypeCategory(type) {
  for (var cat in TYPE_CATEGORIES) {
    if (TYPE_CATEGORIES[cat].types.indexOf(type) !== -1) return cat;
  }
  return 'Code';
}

function getGroupColor(group) {
  var descendants = group._descendants || [];
  var typeCounts = {};
  descendants.forEach(function(n) {
    var cat = getTypeCategory(n.type);
    typeCounts[cat] = (typeCounts[cat] || 0) + 1;
  });
  var dominant = 'Code';
  var maxCount = 0;
  Object.entries(typeCounts).forEach(function(entry) {
    if (entry[1] > maxCount) { maxCount = entry[1]; dominant = entry[0]; }
  });
  return TYPE_CATEGORIES[dominant] ? TYPE_CATEGORIES[dominant].color : '#3b82f6';
}

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
  // System — very top
  system: 0.03, container: 0.03,
  service: 0.08, worker: 0.08,
  // Code Layer — top third
  module: 0.30, function: 0.35, class_def: 0.32,
  struct: 0.33, protocol: 0.33,
  // API Layer — middle
  api: 0.50, route: 0.52, webhook: 0.50, middleware: 0.48,
  // Data Layer — bottom third
  database: 0.72, table: 0.75,
  cache: 0.70, queue: 0.70,
  // Config/Files — very bottom
  file: 0.92, script: 0.92, config: 0.90, migration: 0.90,
  external: 0.88, submodule: 0.88,
  model: 0.55, schema: 0.55, enum_def: 0.55,
  view: 0.75, util: 0.38, test: 0.95,
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

const RELATIONSHIP_HELP = DATA.edge_relationship_descriptions || {};
const NODE_TYPE_HELP = DATA.node_type_descriptions || {};
const NODE_STATUS_HELP = DATA.node_status_descriptions || {};

const ISSUE_TYPE_HELP = {
  'orphaned_table': 'This database table exists but nothing reads from or writes to it. It may be leftover from a removed feature, or a new table not yet wired up.',
  'broken_reference': 'A connection between two components is marked as broken. The link exists in the blueprint but is not functioning correctly.',
  'missing_database': 'This service has URL routes but no database connection. Most services with routes need to store or retrieve data.',
  'circular_dependency': 'Components depend on each other in a loop (A needs B, B needs C, C needs A). This makes them fragile and hard to change independently.',
  'unimplemented_planned': 'This component was designed but never built. It is still marked as planned and may need implementation or removal.',
  'missing_auth': 'This API endpoint or route has no authentication. Anyone who knows the URL could access it without restriction.',
  'single_point_of_failure': 'If this component goes down, parts of the system become disconnected. It is a bottleneck with no backup path.',
  'stale_node': 'This component references a source file that no longer exists on disk. The code may have been moved or deleted.',
  'unused_module': 'This module is not connected to any other component. It may be dead code or a utility that was never integrated.',
  'missing_description': 'This component has no description, making it harder for others to understand its purpose at a glance.'
};

const GROUP_DESCRIPTIONS = {
  'src': 'Core application source code \u2014 the main logic lives here.',
  'lib': 'Shared library code reused across the project.',
  'ui': 'Reusable interface building blocks \u2014 buttons, inputs, cards, dialogs.',
  'components': 'UI components that make up the visible interface.',
  'pages': 'Top-level views that users navigate between.',
  'views': 'Screen templates that define what the user sees.',
  'api': 'Backend endpoints that handle requests and return data.',
  'routes': 'URL paths mapped to handlers \u2014 the API surface area.',
  'controllers': 'Request handlers that coordinate business logic.',
  'models': 'Data structures representing domain entities.',
  'schemas': 'Validation rules defining expected data shapes.',
  'services': 'Business logic modules that orchestrate operations.',
  'utils': 'Shared helper functions used throughout the codebase.',
  'helpers': 'Utility code that simplifies common tasks.',
  'config': 'Configuration files controlling app behavior and settings.',
  'tests': 'Automated tests verifying the code works correctly.',
  'test': 'Automated tests verifying the code works correctly.',
  'middleware': 'Request processing layers that run before handlers.',
  'hooks': 'Reusable lifecycle callbacks (React hooks, Git hooks, etc.).',
  'store': 'State management \u2014 where app data is held in memory.',
  'styles': 'CSS and styling definitions for the interface.',
  'assets': 'Static files like images, fonts, and icons.',
  'public': 'Publicly served static files.',
  'scripts': 'Standalone executable scripts for tasks and automation.',
  'migrations': 'Database schema changes applied in sequence.',
  'types': 'TypeScript type definitions and interfaces.',
  'db': 'Database access layer and query logic.',
  'data': 'Data access, seeding, or fixture files.',
  'shared': 'Components and utilities shared across features.',
  'layout': 'Page structure \u2014 navigation bar, footer, and page skeleton.',
  'home': 'Components that build the homepage.',
  'about': 'The about page \u2014 company story and values.',
  'contact': 'Contact page with form and contact info.',
  'blog': 'Blog listing, cards, and category filtering.',
  'admin': 'Admin dashboard for managing content.',
  'app': 'The pages and routes users visit in their browser.',
  'supabase': 'Connection to your Supabase database \u2014 reads and writes data.',
  'content': 'Static content files \u2014 text, bios, testimonials.',
  'infra': 'Infrastructure-as-code definitions.',
  'deploy': 'Deployment configuration and scripts.',
};

function getGroupDescription(name) {
  var lower = (name || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  for (var key in GROUP_DESCRIPTIONS) {
    if (lower === key || lower.endsWith(key) || lower.startsWith(key)) {
      return GROUP_DESCRIPTIONS[key];
    }
  }
  return null;
}

function getContextualEdgeExplanation(rel, srcName, tgtName, isSrc) {
  var templates = {
    'depends_on':    ['{s} requires {t} to work. If {t} breaks, {s} will fail.', '{t} is a dependency of {s}.'],
    'calls':         ['{s} directly calls code in {t}.', '{t} is called by {s} at runtime.'],
    'reads_from':    ['{s} reads data from {t}.', '{t} provides data to {s}.'],
    'writes_to':     ['{s} sends data to {t} for storage.', '{t} receives data from {s}.'],
    'uses':          ['{s} imports and uses code from {t}. If {t} is deleted, {s} will break.', '{t} provides functionality used by {s}.'],
    'contains':      ['{t} lives inside {s}.', '{s} is contained within {t}.'],
    'inherits':      ['{s} extends {t} and inherits its behavior.', '{t} is the base for {s}.'],
    'implements':    ['{s} provides the concrete implementation of {t}.', '{t} is implemented by {s}.'],
    'authenticates': ['{s} verifies identity through {t}.', '{t} handles auth for {s}.'],
    'exposes':       ['{s} makes {t} available externally.', '{t} is exposed by {s}.'],
    'creates':       ['{s} creates instances of {t}.', '{t} is created by {s}.'],
    'produces':      ['{s} generates output consumed by {t}.', '{t} consumes what {s} produces.'],
    'consumes':      ['{s} processes input from {t}.', '{t} feeds data into {s}.'],
    'delegates':     ['{s} forwards work to {t} to handle.', '{t} handles work delegated by {s}.'],
    'observes':      ['{s} watches for changes in {t} and reacts automatically.', '{t} is observed by {s}.'],
    'connects_to':   ['{s} is connected to {t}.', '{t} is connected to {s}.'],
    'controls':      ['{s} manages the lifecycle of {t}.', '{t} is controlled by {s}.'],
    'updates':       ['{s} modifies state in {t}.', '{t} is updated by {s}.'],
    'emits':         ['{s} sends events that {t} can listen for.', '{t} receives events from {s}.'],
  };
  var tpl = templates[rel];
  if (!tpl) return null;
  var text = isSrc ? tpl[0] : tpl[1];
  return text.replace(/\{s\}/g, srcName).replace(/\{t\}/g, tgtName);
}

const NODE_EXPLAIN = {
  'module': 'A module is a file that groups related code. Think of it like a chapter in a book \u2014 it contains functions, classes, or variables that work together for one purpose.',
  'table': 'A database table is like a spreadsheet. Each row is a record, each column is a field. Other parts of your app read from and write to this table.',
  'column': 'A column is a field in a database table \u2014 one piece of data stored for each record. Like a column header in a spreadsheet.',
  'route': 'A route is a URL endpoint \u2014 when someone visits this path or an API call hits it, this code runs. It is the front door to a specific feature.',
  'service': 'A service is a running program that handles business logic. It processes requests, talks to databases, and coordinates between other parts of your app.',
  'database': 'A database stores all persistent data. When the app restarts, data in the database survives. Services read from and write to it.',
  'function': 'A function is a reusable block of code that does one specific task. Other code calls it by name and gets a result back.',
  'api': 'An API (Application Programming Interface) is a set of endpoints other programs can call. It defines what requests your app accepts and what responses it returns.',
  'class_def': 'A class is a blueprint for creating objects. It bundles data (properties) and behavior (methods) together. Other code creates instances of it.',
  'container': 'A container is a packaged, runnable unit (like Docker). It bundles code and dependencies so it runs the same everywhere.',
  'queue': 'A queue holds messages waiting to be processed. Producers add messages, consumers pick them up later. This decouples fast writers from slow readers.',
  'cache': 'A cache stores frequently-accessed data in fast memory so the app does not have to fetch it from the database every time.',
  'external': 'An external service is something outside your codebase \u2014 a third-party API, SaaS product, or partner system you depend on but do not control.',
  'config': 'A configuration file controls how the app behaves without changing code. Environment variables, feature flags, and settings live here.',
  'test': 'A test automatically verifies that code works correctly. If someone breaks something, the test should catch it before it reaches users.',
  'middleware': 'Middleware sits between incoming requests and your handlers. It can check authentication, log requests, or transform data before your code sees it.',
  'webhook': 'A webhook is a URL that another service calls when something happens. Instead of polling, your app gets notified automatically.',
  'worker': 'A worker is a background process that picks up tasks from a queue and processes them. It handles work too slow for a direct request.',
  'view': 'A view is a UI component or template that renders what the user sees on screen.',
  'model': 'A model represents a real-world concept in code \u2014 like a User, Order, or Product. It defines what data the concept has.',
  'schema': 'A schema defines the expected shape of data. It validates that incoming data matches what the code expects.',
  'migration': 'A migration is a versioned change to the database structure. Migrations run in order to evolve the database as the app grows.',
  'file': 'A general source or data file in the project.',
  'script': 'A standalone script that runs on its own for tasks like database seeding, deployment, or one-off data fixes.',
  'struct': 'A struct is a lightweight data container grouping related fields. Unlike a class, it typically has no behavior.',
  'protocol': 'A protocol (or interface/trait) defines a contract. Any type that conforms to it must implement the required methods.',
  'enum_def': 'An enum is a fixed set of named values. Instead of magic strings or numbers, code uses the enum for type safety.',
  'util': 'A utility module provides shared helper functions \u2014 small reusable pieces of code that many parts of the app need.',
  'system': 'The top-level container representing your entire project. Everything else lives inside it.',
  'submodule': 'A Git submodule or nested dependency \u2014 a separate repository included within this project.',
};

var detailClickCount = 0;
try { detailClickCount = parseInt(localStorage.getItem('blueprint-xray-detail-clicks') || '0', 10); } catch(e) {}

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

/* Drill-down state */
let currentLevel    = 1;       // 1=Overview, 2=Group, 3=Focus
let currentGroupId  = null;    // Active group ID for Level 2
let currentFocusId  = null;    // Active focus node ID for Level 3
let levelHistory    = [];      // Stack of {level, groupId, focusId}
let overviewNodes   = [];      // Cached overview-level node data
let overviewEdges   = [];      // Cached aggregated edges
let activeGhosts    = [];      // Ghost nodes in current Level 2

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
let columnNodeIds = new Set();

function edgeDashClass(rel) {
  if (['calls', 'delegates', 'uses'].includes(rel)) return 'edge-calls';
  if (['depends_on', 'inherits', 'implements'].includes(rel)) return 'edge-depends';
  if (['reads_from', 'writes_to', 'updates', 'produces', 'consumes'].includes(rel)) return 'edge-data';
  if (['contains', 'creates', 'controls'].includes(rel)) return 'edge-structural';
  return 'edge-calls';
}

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
  buildStatusSummary();

  initFilters();
  initTabs();
  initSearch();
  initThemeToggle();
  initEscapeKey();
  initContextMenu();
  initLayoutToggle();
  initHelpPanel();
  renderHealth();
  renderQuestions();
  renderEmptyDetail();
  buildGraph();
});

/* ================================================================
   STATUS SUMMARY BAR
   ================================================================ */
function buildStatusSummary() {
  const counts = {};
  DATA.nodes.forEach(n => { counts[n.status] = (counts[n.status] || 0) + 1; });
  const bar = document.getElementById('status-summary');
  let h = '';
  const order = ['built','in_progress','planned','broken','deprecated'];
  order.forEach(s => {
    if (!counts[s]) return;
    h += '<span class="status-item">';
    h += '<span class="status-dot" style="background:' + (STATUS_COLORS[s] || '#a0aec0') + '"></span>';
    h += counts[s] + ' ' + s.replace('_', ' ');
    h += '</span>';
  });
  bar.innerHTML = h;
}

/* ================================================================
   ONBOARDING OVERLAY
   ================================================================ */
function initOnboarding() {
  var shouldShow = false;
  try { shouldShow = !localStorage.getItem('blueprint-xray-onboarded'); } catch(e) { shouldShow = true; }
  if (DATA.nodes.length === 0) shouldShow = true;
  if (!shouldShow) return;

  var currentStep = 0;
  try { currentStep = parseInt(localStorage.getItem('blueprint-xray-onboard-step') || '0', 10); } catch(e) {}
  if (currentStep >= 3) { dismissOnboarding(); return; }

  var steps = [
    {
      title: 'What am I looking at?',
      hints: [
        { icon: '&#127968;', text: 'This is a living map of your project\u2019s architecture.' },
        { icon: '&#128230;', text: 'Each card represents a directory or group of related files.' },
        { icon: '&#128268;', text: 'Lines between cards show which groups depend on each other.' }
      ],
      button: 'Next \u2192'
    },
    {
      title: 'How do I explore?',
      hints: [
        { icon: '&#128070;', text: 'Double-click any card to see what\u2019s inside.' },
        { icon: '&#128269;', text: 'Click any component to see its details on the right.' },
        { icon: '&#11013;', text: 'Use the breadcrumb bar or press Escape to go back.' }
      ],
      button: 'Next \u2192'
    },
    {
      title: 'What should I look for?',
      hints: [
        { icon: '&#9888;', text: 'Check the Health tab for broken links or missing connections.' },
        { icon: '&#128161;', text: 'Look for isolated components \u2014 they might be dead code.' },
        { icon: '&#128200;', text: 'Thick lines between groups mean heavy coupling worth investigating.' }
      ],
      button: 'Got it'
    }
  ];

  var overlay = document.createElement('div');
  overlay.id = 'onboarding-overlay';
  document.body.appendChild(overlay);

  function renderStep(idx) {
    var step = steps[idx];
    var html = '<div class="onboarding-card">';
    html += '<div class="onboarding-progress">';
    for (var i = 0; i < steps.length; i++) {
      html += '<span class="onboarding-dot' + (i === idx ? ' active' : '') + (i < idx ? ' done' : '') + '"></span>';
    }
    html += '</div>';
    html += '<h3>' + step.title + '</h3>';
    html += '<div class="onboarding-hints">';
    step.hints.forEach(function(hint) {
      html += '<div class="onboarding-hint"><span class="hint-icon">' + hint.icon + '</span><span>' + hint.text + '</span></div>';
    });
    html += '</div>';
    if (idx > 0) {
      html += '<div style="display:flex;gap:8px">';
      html += '<button class="onboarding-back" id="onboarding-back">\u2190 Back</button>';
      html += '<button class="onboarding-dismiss" id="onboarding-next">' + step.button + '</button>';
      html += '</div>';
    } else {
      html += '<button class="onboarding-dismiss" id="onboarding-next">' + step.button + '</button>';
    }
    html += '</div>';
    overlay.innerHTML = html;

    overlay.querySelector('#onboarding-next').addEventListener('click', function() {
      if (idx < steps.length - 1) {
        currentStep = idx + 1;
        try { localStorage.setItem('blueprint-xray-onboard-step', String(currentStep)); } catch(e) {}
        renderStep(currentStep);
      } else {
        dismissOnboarding();
      }
    });
    var backBtn = overlay.querySelector('#onboarding-back');
    if (backBtn) {
      backBtn.addEventListener('click', function() {
        currentStep = idx - 1;
        try { localStorage.setItem('blueprint-xray-onboard-step', String(currentStep)); } catch(e) {}
        renderStep(currentStep);
      });
    }
  }

  renderStep(currentStep);

  overlay.addEventListener('click', function(e) { if (e.target === overlay) dismissOnboarding(); });
  document.addEventListener('keydown', function onEsc(e) {
    if (e.key === 'Escape') { dismissOnboarding(); document.removeEventListener('keydown', onEsc); }
  });
}

function dismissOnboarding() {
  var overlay = document.getElementById('onboarding-overlay');
  if (overlay) overlay.remove();
  try {
    localStorage.setItem('blueprint-xray-onboarded', '1');
    localStorage.setItem('blueprint-xray-onboard-step', '3');
  } catch(e) {}
}

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
    if (columnNodeIds.has(d.id) || hiddenNodes.has(d.id)) { d3.select(this).style('display', 'none'); return; }
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
  if (columnNodeIds.has(nodeId) || hiddenNodes.has(nodeId)) return false;
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
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'Escape' || e.key === 'Backspace') {
      if (currentLevel > 1) { navigateLevelBack(); return; }
      deselectAll();
      if (focusedMode) showAllNodes();
      hideContextMenu();
      document.getElementById('help-panel').style.display = 'none';
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

function showEdgeTooltip(event, d) {
  var tip = document.getElementById('edge-tooltip');
  var srcNode = overviewNodes.find(function(n) { return n.id === (d.source.id || d.source); });
  var tgtNode = overviewNodes.find(function(n) { return n.id === (d.target.id || d.target); });
  var srcName = srcNode ? srcNode.name : '?';
  var tgtName = tgtNode ? tgtNode.name : '?';

  var html = '<strong>' + esc(srcName) + ' \u2194 ' + esc(tgtName) + '</strong><br>';
  html += '<span style="opacity:0.8">' + d.count + ' connection' + (d.count !== 1 ? 's' : '') + ' between these groups</span>';
  if (d.rels && d.rels.length > 0) {
    html += '<div style="margin-top:6px;border-top:1px solid rgba(255,255,255,0.15);padding-top:6px">';
    d.rels.forEach(function(rel) {
      var desc = RELATIONSHIP_HELP[rel] || '';
      html += '<div><strong>' + esc(rel.replace(/_/g, ' ')) + '</strong>';
      if (desc) html += ' \u2014 ' + esc(desc);
      html += '</div>';
    });
    html += '</div>';
  }
  tip.innerHTML = html;
  tip.style.left = Math.min(event.pageX + 12, window.innerWidth - 340) + 'px';
  tip.style.top = (event.pageY - 10) + 'px';
  tip.style.display = 'block';
}

function hideEdgeTooltip() {
  document.getElementById('edge-tooltip').style.display = 'none';
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
   HELP PANEL (Legend + Shortcuts)
   ================================================================ */
function initHelpPanel() {
  /* Tab switching */
  document.querySelectorAll('.help-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.help-tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.help-tab-pane').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('help-' + btn.dataset.helpTab).classList.add('active');
    });
  });

  /* Click outside to close */
  document.addEventListener('click', (e) => {
    const panel = document.getElementById('help-panel');
    if (panel.style.display === 'flex' && !panel.contains(e.target) && e.target.id !== 'help-btn') {
      panel.style.display = 'none';
    }
  });

  /* Build legend content */
  let h = '';

  /* Node Colors section */
  h += '<div class="legend-section">Node Colors</div>';
  Object.entries(TYPE_CATEGORIES).forEach(([cat, info]) => {
    h += '<div class="legend-row">';
    h += '<span class="legend-dot" style="background:' + info.color + '"></span>';
    h += '<span class="legend-name">' + cat + '</span>';
    h += '<span class="legend-types">' + info.types.join(', ') + '</span>';
    h += '</div>';
  });

  /* Status section */
  h += '<div class="legend-section">Status</div>';
  const statusEntries = [
    { key: 'built',       label: 'Built',       cls: '' },
    { key: 'planned',     label: 'Planned',     cls: ' dashed' },
    { key: 'in_progress', label: 'In Progress', cls: ' pulsing' },
    { key: 'broken',      label: 'Broken',      cls: '' },
    { key: 'deprecated',  label: 'Deprecated',  cls: ' grayscale' }
  ];
  statusEntries.forEach(s => {
    h += '<div class="legend-row">';
    h += '<span class="legend-status-dot' + s.cls + '" style="background:' + (STATUS_COLORS[s.key] || '#a0aec0') + ';color:' + (STATUS_COLORS[s.key] || '#a0aec0') + '"></span>';
    h += '<span class="legend-name">' + s.label + '</span>';
    if (NODE_STATUS_HELP[s.key]) h += '<span class="legend-types">' + NODE_STATUS_HELP[s.key] + '</span>';
    h += '</div>';
  });

  /* Edge Patterns section */
  h += '<div class="legend-section">Edge Patterns</div>';
  const edgePatterns = [
    { label: 'Solid',       dash: '', desc: 'calls, delegates, uses' },
    { label: 'Long dash',   dash: '12 4', desc: 'reads_from, writes_to, updates' },
    { label: 'Short dash',  dash: '3 3', desc: 'contains, creates, produces' },
    { label: 'Medium dash', dash: '8 4', desc: 'depends_on, inherits, implements' }
  ];
  edgePatterns.forEach(p => {
    h += '<div class="legend-edge-row">';
    h += '<svg width="30" height="4" style="flex-shrink:0"><line x1="0" y1="2" x2="30" y2="2" stroke="var(--text-secondary)" stroke-width="2"' + (p.dash ? ' stroke-dasharray="' + p.dash + '"' : '') + '/></svg>';
    h += '<span class="legend-name">' + p.label + '</span>';
    h += '<span class="legend-types">' + p.desc + '</span>';
    h += '</div>';
  });

  document.getElementById('help-legend').innerHTML = h;
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
  h += '<span class="node-type-badge" style="background:' + typeColor + '20;color:' + typeColor + '"'
     + (NODE_TYPE_HELP[nd.type] ? ' title="' + esc(NODE_TYPE_HELP[nd.type]) + '"' : '')
     + '>' + esc(nd.type) + '</span>';
  if (NODE_TYPE_HELP[nd.type]) {
    h += '<div class="field-value" style="font-size:12px;margin-bottom:8px;color:var(--text-secondary)">' + esc(NODE_TYPE_HELP[nd.type]) + '</div>';
  }

  if (nd.description) {
    h += '<div class="field-label">Description</div>';
    h += '<div class="field-value">' + esc(nd.description) + '</div>';
  }

  /* "What does this mean?" explainer */
  var explainText = NODE_EXPLAIN[nd.type] || '';
  var connSignificance = '';
  if (conns.length === 0) connSignificance = 'This component is isolated \u2014 nothing connects to it. It may be new, unused, or missing connections.';
  else if (conns.length > 10) connSignificance = 'Highly connected (' + conns.length + ' connections). Changes here could have wide impact across your app.';
  else if (conns.filter(function(e) { return e.target_id === nd.id; }).length > 5) connSignificance = 'Many components depend on this. Treat it as critical infrastructure \u2014 be careful when changing it.';

  if (explainText || connSignificance) {
    var shouldExpand = detailClickCount < 3;
    h += '<div class="explain-section">';
    h += '<button class="explain-toggle" id="explain-toggle">';
    h += (shouldExpand ? '\u25BC' : '\u25B6') + ' What does this mean?</button>';
    h += '<div class="explain-body" id="explain-body" style="display:' + (shouldExpand ? 'block' : 'none') + '">';
    if (explainText) h += '<div class="explain-text">' + esc(explainText) + '</div>';
    if (connSignificance) h += '<div class="explain-text" style="font-weight:600">' + esc(connSignificance) + '</div>';
    h += '</div></div>';
  }

  h += '<div class="field-label">Status</div>';
  h += '<div class="field-value" style="text-transform:capitalize">'
     + esc(nd.status.replace('_', ' ')) + '</div>';
  if (NODE_STATUS_HELP[nd.status]) {
    h += '<div class="field-value" style="font-size:11px;color:var(--text-muted)">' + esc(NODE_STATUS_HELP[nd.status]) + '</div>';
  }

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

  /* ---- Drill In button for groups/directories ---- */
  if (gParentIds.has(nd.id) || (nd.metadata && nd.metadata.directory)) {
    h += '<button class="drill-in-btn" id="drill-in-btn">Explore inside \u2192</button>';
  }

  /* ---- Columns (for table nodes with embedded columns) ---- */
  const simNode = gNodeMap[nd.id];
  if (simNode && simNode._columns && simNode._columns.length > 0) {
    h += '<div class="field-label">Columns (' + simNode._columns.length + ')</div>';
    h += '<div class="conn-summary" style="flex-direction:column;gap:0">';
    simNode._columns.forEach(col => {
      const isPK = col.metadata && col.metadata.primary_key;
      const isFK = col.metadata && col.metadata.fk;
      const icon = isPK ? '\uD83D\uDD11 ' : isFK ? '\u2192 ' : '';
      const colType = (col.metadata && col.metadata.data_type) || '';
      h += '<div style="font-size:12px;padding:2px 0;font-family:monospace">';
      h += icon + esc(col.name);
      if (colType) h += ' <span style="color:var(--text-muted)">' + esc(colType) + '</span>';
      if (isFK) h += ' <span style="color:#3b82f6;font-size:10px">FK\u2192' + esc(col.metadata.fk) + '</span>';
      h += '</div>';
    });
    h += '</div>';
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
      var ctxExpl = getContextualEdgeExplanation(e.relationship, nd.name, otherName, isSrc);
      if (ctxExpl) item += '<div class="conn-context">' + esc(ctxExpl) + '</div>';
      if (RELATIONSHIP_HELP[e.relationship]) item += '<div class="conn-explanation">' + esc(RELATIONSHIP_HELP[e.relationship]) + '</div>';
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
  const drillBtn = document.getElementById('drill-in-btn');
  if (drillBtn) drillBtn.addEventListener('click', () => navigateToLevel(2, nd.id));

  /* Explanation toggle */
  var explainBtn = document.getElementById('explain-toggle');
  if (explainBtn) {
    explainBtn.addEventListener('click', function() {
      var body = document.getElementById('explain-body');
      var isOpen = body.style.display !== 'none';
      body.style.display = isOpen ? 'none' : 'block';
      explainBtn.textContent = (isOpen ? '\u25B6' : '\u25BC') + ' What does this mean?';
    });
  }
  detailClickCount++;
  try { localStorage.setItem('blueprint-xray-detail-clicks', String(detailClickCount)); } catch(e) {}

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
    h += '<div class="issue-card ' + issue.severity + '" data-highlight=\'' + JSON.stringify(issue.node_ids || []) + '\'>';
    h += '<div class="issue-type">' + esc(issue.type) + '</div>';
    h += '<div class="issue-msg">'  + esc(issue.message) + '</div>';
    if (issue.suggestion)
      h += '<div class="issue-suggestion">' + esc(issue.suggestion) + '</div>';
    if (ISSUE_TYPE_HELP[issue.type])
      h += '<div class="issue-explanation">' + esc(ISSUE_TYPE_HELP[issue.type]) + '</div>';
    h += '</div>';
  });

  document.getElementById('tab-health').innerHTML = h;

  /* Click issue to highlight affected nodes on the graph */
  document.querySelectorAll('.issue-card[data-highlight]').forEach(function(card) {
    card.addEventListener('click', function() {
      var ids = JSON.parse(card.dataset.highlight || '[]');
      if (ids.length > 0) highlightNodes(ids);
    });
  });
}

/* ================================================================
   QUESTIONS TAB
   ================================================================ */
function renderQuestions() {
  var qs = DATA.questions || [];

  if (qs.length === 0) {
    document.getElementById('tab-questions').innerHTML =
      '<div class="detail-empty" style="height:auto;padding:32px 0">' +
      '<div style="font-size:24px;opacity:0.3">&#10003;</div>' +
      '<div>No questions detected \u2014 your architecture looks clean!</div></div>';
    return;
  }

  var h = '<div class="questions-header">';
  h += '<div class="questions-count">' + qs.length + ' questions to investigate</div>';
  h += '</div>';

  /* Group by category */
  var grouped = {};
  qs.forEach(function(q) {
    var cat = q.category || 'general';
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(q);
  });

  var catIcons = {
    security: '\uD83D\uDD12',
    completeness: '\uD83D\uDCCB',
    data_flow: '\uD83D\uDD04',
    reliability: '\u26A1',
    testing: '\uD83E\uDDEA',
    general: '\uD83D\uDCA1'
  };
  var catLabels = {
    security: 'Security',
    completeness: 'Missing Pieces',
    data_flow: 'Data Flow',
    reliability: 'Reliability',
    testing: 'Testing',
    general: 'General'
  };

  Object.entries(grouped).forEach(function(entry) {
    var cat = entry[0], questions = entry[1];
    var icon = catIcons[cat] || '\uD83D\uDCA1';
    var label = catLabels[cat] || cat;

    h += '<div class="question-category">';
    h += '<div class="question-category-header">' + icon + ' ' + label + ' (' + questions.length + ')</div>';

    questions.forEach(function(q) {
      h += '<div class="question-card" data-highlight=\'' + JSON.stringify(q.highlight_nodes || []) + '\'>';
      h += '<div class="question-text">' + esc(q.question) + '</div>';
      if (q.context) {
        h += '<div class="question-context">' + esc(q.context) + '</div>';
      }
      if (q.fix_prompt) {
        h += '<div class="question-fix">\uD83D\uDCA1 Fix: ' + esc(q.fix_prompt) + '</div>';
      }
      if (q.learn_more) {
        h += '<div class="question-learn">\uD83D\uDCD6 ' + esc(q.learn_more) + '</div>';
      }
      h += '</div>';
    });

    h += '</div>';
  });

  document.getElementById('tab-questions').innerHTML = h;

  document.querySelectorAll('.question-card').forEach(function(card) {
    card.addEventListener('click', function() {
      var ids = JSON.parse(card.dataset.highlight || '[]');
      if (ids.length > 0) highlightNodes(ids);
    });
  });
}

/* ================================================================
   LAYERS TAB
   ================================================================ */
function renderLayers() {
  var layers = [
    { icon: '\uD83D\uDDA5\uFE0F', name: 'User Interface', description: 'What the user sees and interacts with',
      color: '#3b82f6', groups: [], nodeTypes: ['view', 'route'],
      dirPatterns: ['view', 'views', 'ui', 'toolbar', 'inspector', 'screen', 'pages', 'layout', 'home', 'components', 'shared'] },
    { icon: '\uD83E\uDDE9', name: 'App Structure', description: 'App entry point, navigation, and top-level wiring',
      color: '#8b5cf6', groups: [], nodeTypes: ['system'],
      dirPatterns: ['app', 'navigation'] },
    { icon: '\u2699\uFE0F', name: 'Core Logic', description: 'Data models, state management, and business rules',
      color: '#10b981', groups: [], nodeTypes: ['function'],
      dirPatterns: ['model', 'models', 'sketch', 'solver', 'constraint', 'operation', 'lib', 'utils', 'hooks', 'content'] },
    { icon: '\uD83D\uDCD0', name: 'Geometry & Math', description: 'Mathematical foundations \u2014 points, vectors, transforms',
      color: '#f59e0b', groups: [], nodeTypes: ['struct'],
      dirPatterns: ['geometry', 'math', 'primitives', 'vector'] },
    { icon: '\uD83D\uDD37', name: 'Topology & Mesh', description: 'How shapes are built \u2014 faces, edges, vertices, bodies',
      color: '#ec4899', groups: [], nodeTypes: [],
      dirPatterns: ['topology', 'mesh', 'brep', 'viewport'] },
    { icon: '\uD83D\uDCE4', name: 'Import & Export', description: 'Getting data in and out \u2014 file formats, exporters',
      color: '#ef4444', groups: [], nodeTypes: [],
      dirPatterns: ['export', 'import', 'io'] },
    { icon: '\uD83D\uDD0C', name: 'API & Services', description: 'How your app talks to servers and external services',
      color: '#06b6d4', groups: [], nodeTypes: ['middleware', 'service'],
      dirPatterns: ['supabase', 'api', 'server'] },
    { icon: '\uD83D\uDDC4\uFE0F', name: 'Data Layer', description: 'Where data is stored permanently',
      color: '#64748b', groups: [], nodeTypes: ['table', 'database', 'column'],
      dirPatterns: ['db', 'data', 'migration'] }
  ];

  var ovCards = overviewNodes.filter(function(n) { return n._isOverviewCard; });

  ovCards.forEach(function(group) {
    var nameLower = (group.name || '').toLowerCase();
    var dominantTypes = Object.entries(group._typeBreakdown || {}).sort(function(a, b) { return b[1] - a[1]; });
    var topType = dominantTypes.length > 0 ? dominantTypes[0][0] : '';
    var assigned = false;

    /* Try node type match first */
    for (var i = 0; i < layers.length; i++) {
      if (layers[i].nodeTypes.indexOf(topType) !== -1) {
        layers[i].groups.push({ name: group.name, childCount: group._childCount, id: group.id });
        assigned = true; break;
      }
    }

    /* Then directory name pattern match */
    if (!assigned) {
      for (var j = 0; j < layers.length; j++) {
        for (var k = 0; k < layers[j].dirPatterns.length; k++) {
          if (nameLower.indexOf(layers[j].dirPatterns[k]) !== -1) {
            layers[j].groups.push({ name: group.name, childCount: group._childCount, id: group.id });
            assigned = true; break;
          }
        }
        if (assigned) break;
      }
    }

    /* Default to Business Logic */
    if (!assigned) {
      layers[2].groups.push({ name: group.name, childCount: group._childCount, id: group.id });
    }
  });

  layers.forEach(function(layer) {
    layer.totalNodes = layer.groups.reduce(function(sum, g) { return sum + g.childCount; }, 0);
    layer.groupNames = layer.groups.map(function(g) { return g; });
  });

  var h = '<div class="layers-container">';
  h += '<div class="layers-title">How Your App Is Organized</div>';
  h += '<div class="layers-subtitle">Data flows from top to bottom</div>';

  var rendered = 0;
  layers.forEach(function(layer, i) {
    if (layer.totalNodes === 0 && layer.groups.length === 0) return;
    if (rendered > 0) {
      h += '<div class="layer-arrow">\u25BC</div>';
    }
    rendered++;

    h += '<div class="layer-card" style="border-left-color:' + layer.color + '">';
    h += '<div class="layer-header">';
    h += '<span class="layer-icon">' + layer.icon + '</span>';
    h += '<span class="layer-name">' + layer.name + '</span>';
    h += '<span class="layer-count">' + layer.totalNodes + ' components</span>';
    h += '</div>';
    h += '<div class="layer-description">' + layer.description + '</div>';

    if (layer.groupNames.length > 0) {
      h += '<div class="layer-groups">';
      layer.groupNames.forEach(function(g) {
        h += '<span class="layer-group-pill" data-group-id="' + g.id + '">' + esc(g.name) + '</span>';
      });
      h += '</div>';
    }
    h += '</div>';
  });

  /* Data flow summary */
  h += '<div class="layers-flow-summary">';
  h += '<div class="flow-title">Key Data Flows</div>';
  var flows = computeTopFlows();
  flows.forEach(function(flow) {
    h += '<div class="flow-item">';
    h += '<span class="flow-path">' + flow.path.join(' \u2192 ') + '</span>';
    h += '<span class="flow-desc">' + flow.description + '</span>';
    h += '</div>';
  });
  h += '</div>';
  h += '</div>';

  document.getElementById('tab-layers').innerHTML = h;

  /* Click handlers for group pills */
  document.querySelectorAll('.layer-group-pill[data-group-id]').forEach(function(pill) {
    pill.addEventListener('click', function() {
      navigateToGroup(pill.dataset.groupId);
    });
  });
}

function computeTopFlows() {
  var flows = [];
  var outDegree = {};
  DATA.edges.forEach(function(e) {
    var sid = e.source_id || e.source;
    outDegree[sid] = (outDegree[sid] || 0) + 1;
  });

  var topNodes = Object.entries(outDegree)
    .sort(function(a, b) { return b[1] - a[1]; })
    .slice(0, 3)
    .map(function(entry) {
      var node = DATA.nodes.find(function(n) { return n.id === entry[0]; });
      return node ? { name: node.name, count: entry[1] } : null;
    })
    .filter(Boolean);

  topNodes.forEach(function(n) {
    flows.push({
      path: [n.name, '...', 'data layer'],
      description: n.count + ' outgoing connections \u2014 a key hub in your app'
    });
  });

  return flows;
}

function navigateToGroup(groupId) {
  var targetGroup = overviewNodes.find(function(n) { return n.id === groupId && n._isOverviewCard; });
  if (targetGroup && targetGroup._childCount > 0) {
    navigateToLevel(2, targetGroup.id);
  }
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
      x: gW * 0.1 + Math.random() * gW * 0.8,
      y: gH / 2 + (Math.random() - 0.5) * gH * 0.6,
      w: w, h: h
    };
  });
  gNodeMap = {};
  gNodeData.forEach(n => gNodeMap[n.id] = n);

  /* ---- Separate column nodes from simulation (render inside tables) ---- */
  const columnsByParent = {};
  gNodeData.forEach(n => {
    if (n.type === 'column' && n.parent_id) {
      if (!columnsByParent[n.parent_id]) columnsByParent[n.parent_id] = [];
      columnsByParent[n.parent_id].push(n);
    }
  });
  gNodeData = gNodeData.filter(n => n.type !== 'column');
  gNodeData.forEach(n => {
    if (columnsByParent[n.id]) {
      n._columns = columnsByParent[n.id];
      n.h = 34 + (n._columns.length * 18) + 6;
      n.w = Math.max(n.w, 200);
    }
  });
  columnNodeIds = new Set();
  Object.values(columnsByParent).flat().forEach(c => columnNodeIds.add(c.id));
  /* Rebuild gNodeMap without columns */
  gNodeMap = {};
  gNodeData.forEach(n => gNodeMap[n.id] = n);

  /* ---- Prepare edge data (remap column references to parent table) ---- */
  gEdgeData = DATA.edges.map(e => {
    let src = e.source_id, tgt = e.target_id;
    if (columnNodeIds.has(src)) {
      const col = Object.values(columnsByParent).flat().find(c => c.id === src);
      if (col) src = col.parent_id;
    }
    if (columnNodeIds.has(tgt)) {
      const col = Object.values(columnsByParent).flat().find(c => c.id === tgt);
      if (col) tgt = col.parent_id;
    }
    return { ...e, source_id: src, target_id: tgt, source: src, target: tgt };
  }).filter(e => gNodeMap[e.source_id] && gNodeMap[e.target_id]);

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

  initMinimap(gW, gH);

  /* Zoom buttons */
  document.getElementById('zoom-in').addEventListener('click',  () => svgEl.transition().duration(300).call(zoom.scaleBy, 1.3));
  document.getElementById('zoom-out').addEventListener('click', () => svgEl.transition().duration(300).call(zoom.scaleBy, 0.7));
  document.getElementById('zoom-fit').addEventListener('click', () => zoomToFit());
  document.getElementById('help-btn').addEventListener('click', (evt) => {
    evt.stopPropagation();
    const p = document.getElementById('help-panel');
    p.style.display = p.style.display === 'flex' ? 'none' : 'flex';
  });

  /* Compute overview data and start at Level 1 */
  computeOverviewData();
  renderLayers();
  currentLevel = 0;
  navigateToLevel(1);
  initOnboarding();
}

/* ================================================================
   SHARED RENDERING HELPERS
   ================================================================ */
function drawEdges(edgeG, edges) {
  var groups = edgeG.selectAll('.edge-group')
    .data(edges, function(d) { return d.id; }).join('g')
    .attr('class', function(d) { return 'edge-group ' + edgeDashClass(d.relationship) + (d.status === 'planned' ? ' planned' : '') + (d._isGhostEdge ? ' ghost-edge' : ''); });

  groups.append('path')
    .attr('class', function(d) { return 'edge-line' + (d.status === 'planned' ? ' planned' : ''); })
    .attr('stroke', function(d) { return EDGE_COLORS[d.relationship] || '#a0aec0'; })
    .attr('stroke-dasharray', function(d) { return d.status === 'planned' ? '6 4' : (EDGE_DASH[d.relationship] || null); })
    .attr('marker-end', function(d) { return 'url(#arrow-' + d.relationship + ')'; });

  groups.append('path')
    .attr('class', 'edge-hit-zone')
    .attr('stroke', 'transparent').attr('stroke-width', 12)
    .attr('fill', 'none').style('pointer-events', 'stroke');

  groups.append('text')
    .attr('class', 'edge-label')
    .attr('text-anchor', 'middle').attr('dy', -6)
    .text(function(d) { return d.label || d.relationship; });

  return groups;
}

function drawNodes(nodeG, nodes, opts) {
  opts = opts || {};
  var groups = nodeG.selectAll('.node-group')
    .data(nodes, function(d) { return d.id; }).join('g')
    .attr('class', function(d) { return 'node-group' + (d._isGhost ? ' ghost-node' : '') + (d._isFocusCenter ? ' focus-center' : ''); })
    .attr('id', function(d) { return 'node-' + d.id; })
    .on('click', function(event, d) { event.stopPropagation(); selectNode(d); })
    .on('contextmenu', function(event, d) { showContextMenu(event, d); })
    .on('mouseenter', function(event, d) {
      if (gEdgeGroups) gEdgeGroups.select('.edge-label').style('opacity', function(e) {
        var s = e.source.id || e.source, t = e.target.id || e.target;
        return (s === d.id || t === d.id) ? 1 : null;
      });
    })
    .on('mouseleave', function() {
      if (!selectedNodeId && gEdgeGroups) gEdgeGroups.select('.edge-label').style('opacity', null);
    });

  if (opts.dblclickHandler) {
    groups.on('dblclick', opts.dblclickHandler);
  }

  if (!opts.noDrag) {
    groups.call(d3.drag()
      .on('start', dragStarted)
      .on('drag',  dragged)
      .on('end',   dragEnded));
  }

  /* Background rect */
  groups.append('rect')
    .attr('class', 'node-rect')
    .attr('width', function(d) { return d.w; }).attr('height', function(d) { return d.h; })
    .attr('fill', 'var(--node-bg)')
    .attr('stroke', function(d) { return d.status === 'broken' ? '#e53e3e' : 'var(--node-border)'; })
    .attr('stroke-width', function(d) { return d.status === 'broken' ? 2 : 1.5; })
    .attr('stroke-dasharray', function(d) { return d.status === 'planned' ? '6 3' : null; });

  /* Type color tint overlay */
  groups.append('rect')
    .attr('width', function(d) { return d.w; }).attr('height', function(d) { return d.h; })
    .attr('rx', 8).attr('ry', 8)
    .attr('fill', function(d) { return d.status === 'deprecated' ? '#9ca3af' : (TYPE_COLORS[d.type] || '#6b7280'); })
    .attr('fill-opacity', function(d) { return d.status === 'planned' ? 0.04 : 0.08; })
    .attr('pointer-events', 'none');

  /* Left color bar */
  groups.append('rect')
    .attr('class', function(d) { return 'node-status-bar' + (d.status === 'in_progress' ? ' status-bar-in_progress' : ''); })
    .attr('width', 4).attr('height', function(d) { return d.h; })
    .attr('rx', 2)
    .attr('fill', function(d) { return TYPE_COLORS[d.type] || '#6b7280'; });

  /* Type badge pill */
  groups.filter(function(d) { return d.w > 120; }).append('rect')
    .attr('x', function(d) { return d.w - (d.type.length * 5.5 + 10); })
    .attr('y', 6)
    .attr('width', function(d) { return d.type.length * 5.5 + 10; })
    .attr('height', 16).attr('rx', 8)
    .attr('fill', function(d) { return TYPE_COLORS[d.type] || '#6b7280'; })
    .attr('fill-opacity', 0.15);

  groups.filter(function(d) { return d.w > 120; }).append('text')
    .attr('class', 'node-type-label')
    .attr('x', function(d) { return d.w - 8; }).attr('y', 18)
    .attr('text-anchor', 'end')
    .attr('fill', function(d) { return TYPE_COLORS[d.type] || '#6b7280'; })
    .text(function(d) { return d.type; });

  /* Name */
  groups.append('text')
    .attr('class', 'node-name')
    .attr('x', 12).attr('y', function(d) { return d.h <= 36 ? d.h / 2 + 4 : 24; })
    .attr('font-size', function(d) { return d.h <= 36 ? '12px' : '14px'; })
    .text(function(d) { return trunc(d.name, Math.floor((d.w - 40) / 7)); });

  /* SVG title tooltip */
  groups.append('title')
    .text(function(d) { return d.name + ' (' + d.type + ', ' + d.status + ')'
      + (NODE_TYPE_HELP[d.type] ? '\n' + NODE_TYPE_HELP[d.type] : '')
      + (d.description ? '\n' + d.description : ''); });

  /* Description (only for h >= 48) */
  groups.filter(function(d) { return d.h >= 48; }).append('text')
    .attr('class', 'node-desc')
    .attr('x', 12).attr('y', 42)
    .text(function(d) { return d.description ? trunc(d.description, Math.floor((d.w - 20) / 7)) : ''; });

  /* Source file (only for h >= 56) */
  groups.filter(function(d) { return d.h >= 56; }).append('text')
    .attr('class', 'node-source')
    .attr('x', 12).attr('y', function(d) { return d.h - 8; })
    .text(function(d) { return d.source_file ? trunc(d.source_file, Math.floor((d.w - 20) / 6)) : ''; });

  /* ---- Render columns inside table nodes (database-style cards) ---- */
  groups.filter(function(d) { return d._columns && d._columns.length > 0; }).each(function(d) {
    var g = d3.select(this);
    var headerH = 30;

    g.append('line')
      .attr('x1', 4).attr('y1', headerH)
      .attr('x2', d.w).attr('y2', headerH)
      .attr('stroke', 'var(--node-border)').attr('stroke-opacity', 0.4);

    d._columns.forEach(function(col, i) {
      var y = headerH + 2 + (i * 18);
      var isPK = col.metadata && col.metadata.primary_key;
      var isFK = col.metadata && col.metadata.fk;
      var colType = (col.metadata && col.metadata.data_type) || '';

      if (i % 2 === 0) {
        g.append('rect')
          .attr('x', 4).attr('y', y)
          .attr('width', d.w - 4).attr('height', 18)
          .attr('fill', 'var(--bg-tertiary)').attr('fill-opacity', 0.3)
          .attr('pointer-events', 'none');
      }

      var prefix = '  ';
      if (isPK) prefix = '\uD83D\uDD11';
      else if (isFK) prefix = '\u2192 ';

      g.append('text')
        .attr('x', 10).attr('y', y + 13)
        .attr('font-size', '11px')
        .attr('fill', isPK ? '#f59e0b' : isFK ? '#3b82f6' : 'var(--text-secondary)')
        .text(prefix + ' ' + col.name);

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

  /* Ghost label */
  groups.filter(function(d) { return d._isGhost && d._ghostLabel; }).append('text')
    .attr('class', 'ghost-label')
    .attr('x', function(d) { return d.w / 2; }).attr('y', function(d) { return d.h + 12; })
    .attr('text-anchor', 'middle')
    .text(function(d) { return d._ghostLabel; });

  /* Apply status opacity */
  groups
    .style('opacity', function(d) {
      if (d._isGhost) return 0.6;
      if (d.status === 'planned') return 0.45;
      if (d.status === 'deprecated') return 0.5;
      return null;
    })
    .style('filter', function(d) { return d.status === 'deprecated' ? 'grayscale(0.8)' : null; });

  return groups;
}

function drawLayerLabels(parentG) {
  var layers = [
    { label: 'UI LAYER', y: 0.10 },
    { label: 'CODE', y: 0.30 },
    { label: 'API', y: 0.48 },
    { label: 'DATA', y: 0.68 },
    { label: 'CONFIG', y: 0.88 }
  ];
  var labelG = parentG.append('g').attr('class', 'layer-labels');
  layers.forEach(function(l) {
    labelG.append('text')
      .attr('x', 20)
      .attr('y', l.y * gH)
      .attr('font-size', '10px')
      .attr('font-weight', '700')
      .attr('fill', 'var(--text-muted)')
      .attr('opacity', 0.3)
      .style('text-transform', 'uppercase')
      .style('letter-spacing', '2px')
      .text(l.label);
  });
}

/* ================================================================
   OVERVIEW DATA COMPUTATION
   ================================================================ */
function isOverviewGroup(node) {
  var isMdDir = node.metadata && node.metadata.directory === true;
  var isTopParent = gParentIds.has(node.id) && (gDepthMap[node.id] || 0) === 0;
  return isMdDir || isTopParent;
}

function findParentGroupName(nodeId) {
  var current = gNodeMap[nodeId];
  while (current && current.parent_id && gNodeMap[current.parent_id]) {
    current = gNodeMap[current.parent_id];
    if (isOverviewGroup(current)) return current.name;
  }
  return current ? current.name : null;
}

function computeOverviewData() {
  overviewNodes = [];
  var groupNodeIds = new Set();
  var nodeToGroup = {};

  gNodeData.forEach(function(n) {
    if (isOverviewGroup(n)) {
      var descIds = getAllDescendants(n.id);
      var descSet = new Set([n.id].concat(descIds));

      descSet.forEach(function(id) { nodeToGroup[id] = n.id; });

      var internalCount = 0, externalCount = 0;
      gEdgeData.forEach(function(e) {
        var sIn = descSet.has(e.source_id);
        var tIn = descSet.has(e.target_id);
        if (sIn && tIn) internalCount++;
        else if (sIn || tIn) externalCount++;
      });

      var typeBreakdown = {};
      [n].concat(descIds.map(function(id) { return gNodeMap[id]; }).filter(Boolean)).forEach(function(child) {
        if (child.type !== 'column') typeBreakdown[child.type] = (typeBreakdown[child.type] || 0) + 1;
      });

      var descNodeObjs = [n].concat(descIds.map(function(id) { return gNodeMap[id]; }).filter(Boolean));
      var ovNode = {
        ...n, _isOverviewCard: true,
        _childCount: descIds.length,
        _internalEdgeCount: internalCount,
        _externalEdgeCount: externalCount,
        _typeBreakdown: typeBreakdown,
        _descendants: descNodeObjs,
        w: 220, h: 120,
        x: gW * 0.1 + Math.random() * gW * 0.8,
        y: gH * 0.2 + Math.random() * gH * 0.6
      };
      ovNode._groupColor = getGroupColor(ovNode);
      overviewNodes.push(ovNode);
      groupNodeIds.add(n.id);
    }
  });

  /* Orphan top-level nodes */
  gNodeData.forEach(function(n) {
    if (!n.parent_id && !groupNodeIds.has(n.id) && !columnNodeIds.has(n.id)) {
      nodeToGroup[n.id] = n.id;
      overviewNodes.push({
        ...n, _isOverviewCard: false,
        w: 160, h: 48,
        x: gW * 0.1 + Math.random() * gW * 0.8,
        y: gH * 0.2 + Math.random() * gH * 0.6
      });
    }
  });

  /* Aggregate edges between groups */
  var aggMap = {};
  gEdgeData.forEach(function(e) {
    var sg = nodeToGroup[e.source_id], tg = nodeToGroup[e.target_id];
    if (!sg || !tg || sg === tg) return;
    var key = [sg, tg].sort().join('|');
    if (!aggMap[key]) aggMap[key] = { source: sg, target: tg, count: 0, rels: new Set() };
    aggMap[key].count++;
    aggMap[key].rels.add(e.relationship);
  });
  overviewEdges = Object.values(aggMap).map(function(e) {
    return { ...e, id: e.source + '|' + e.target, rels: Array.from(e.rels) };
  });
}

/* ================================================================
   LEVEL NAVIGATION
   ================================================================ */
function navigateToLevel(level, targetId) {
  if (currentLevel !== 0) {
    levelHistory.push({ level: currentLevel, groupId: currentGroupId, focusId: currentFocusId });
    if (levelHistory.length > 20) levelHistory.shift();
  }
  currentLevel = level;
  currentGroupId = level === 2 ? targetId : null;
  currentFocusId = level === 3 ? targetId : null;

  updateBreadcrumb();
  updateUIForLevel();
  transitionToLevel();
}

function navigateLevelBack() {
  if (levelHistory.length === 0) return;
  var prev = levelHistory.pop();
  currentLevel = prev.level;
  currentGroupId = prev.groupId;
  currentFocusId = prev.focusId;
  updateBreadcrumb();
  updateUIForLevel();
  transitionToLevel();
}

function transitionToLevel() {
  if (simulation) simulation.stop();
  mainG.transition().duration(200).style('opacity', 0)
    .on('end', function() {
      mainG.selectAll('*').remove();
      mainG.style('opacity', 0);
      if (currentLevel === 1) renderOverview();
      else if (currentLevel === 2) renderGroup(currentGroupId);
      else if (currentLevel === 3) renderFocus(currentFocusId);
      mainG.transition().duration(300).style('opacity', 1);
    });
}

function updateBreadcrumb() {
  var bar = document.getElementById('breadcrumb-bar');
  var html = '<span class="breadcrumb-item' + (currentLevel === 1 ? ' active' : '') + '" onclick="navigateToLevel(1)">' + esc(DATA.project_name || 'Overview') + '</span>';
  if (currentLevel >= 2 && currentGroupId) {
    var gNode = gNodeMap[currentGroupId];
    html += '<span class="breadcrumb-sep">\u203A</span>';
    html += '<span class="breadcrumb-item' + (currentLevel === 2 ? ' active' : '') + '" onclick="navigateToLevel(2,\'' + currentGroupId + '\')">' + esc(gNode ? gNode.name : 'Group') + '</span>';
  }
  if (currentLevel === 3 && currentFocusId) {
    var fNode = gNodeMap[currentFocusId];
    html += '<span class="breadcrumb-sep">\u203A</span>';
    html += '<span class="breadcrumb-item active">' + esc(fNode ? fNode.name : 'Node') + '</span>';
  }
  bar.innerHTML = html;
}

function updateUIForLevel() {
  /* Layout toggle: only show in Level 2 */
  var lt = document.querySelector('.layout-toggle');
  if (lt) lt.style.display = currentLevel === 2 ? 'flex' : 'none';

  /* Stats bar update */
  var statsBar = document.getElementById('stats-bar');
  if (currentLevel === 1) {
    var groups = overviewNodes.filter(function(n) { return n._isOverviewCard; }).length;
    var orphans = overviewNodes.filter(function(n) { return !n._isOverviewCard; }).length;
    var totalConns = overviewEdges.reduce(function(a, e) { return a + e.count; }, 0);
    statsBar.innerHTML = '<span>' + groups + ' groups</span><span>' + orphans + ' top-level</span><span>' + totalConns + ' connections</span>';
  } else if (currentLevel === 2) {
    var children = getAllDescendants(currentGroupId).length;
    statsBar.innerHTML = '<span>' + children + ' nodes</span><span>' + activeGhosts.length + ' external refs</span>';
  } else if (currentLevel === 3) {
    var fNode = gNodeMap[currentFocusId];
    var conns = gEdgeData.filter(function(e) { return e.source_id === currentFocusId || e.target_id === currentFocusId; }).length;
    statsBar.innerHTML = '<span>' + esc(fNode ? fNode.name : '') + '</span><span>' + conns + ' connections</span>';
  }

  deselectAll();
}

/* ================================================================
   LEVEL 1: OVERVIEW (group cards + orphans)
   ================================================================ */
function renderOverview() {
  gGroupG = mainG.append('g').attr('class', 'groups-layer');
  var edgeG = mainG.append('g').attr('class', 'edges-layer');
  var nodeG = mainG.append('g').attr('class', 'nodes-layer');

  /* Level 1 subtitle */
  mainG.append('text')
    .attr('class', 'level-subtitle')
    .attr('x', 20).attr('y', 20)
    .attr('font-size', '13px')
    .attr('fill', 'var(--text-muted)')
    .text('Each card is a section of your code. Double-click to explore inside.');

  /* Draw aggregated edges */
  var aggEdgeGroups = edgeG.selectAll('.agg-edge')
    .data(overviewEdges, function(d) { return d.id; }).join('g')
    .attr('class', 'agg-edge')
    .style('cursor', 'help')
    .on('mouseenter', function(event, d) { showEdgeTooltip(event, d); })
    .on('mousemove', function(event) {
      var tip = document.getElementById('edge-tooltip');
      tip.style.left = Math.min(event.pageX + 12, window.innerWidth - 340) + 'px';
      tip.style.top = (event.pageY - 10) + 'px';
    })
    .on('mouseleave', function() { hideEdgeTooltip(); });

  /* Invisible wider hit zone for easier hover */
  aggEdgeGroups.append('line')
    .attr('stroke', 'transparent')
    .attr('stroke-width', 14)
    .style('pointer-events', 'stroke');

  aggEdgeGroups.append('line')
    .attr('class', 'edge-line')
    .attr('stroke', '#a0aec0')
    .attr('stroke-width', function(d) { return Math.min(1 + d.count * 0.5, 5); })
    .attr('stroke-opacity', 0.3);

  aggEdgeGroups.append('text')
    .attr('class', 'agg-edge-label')
    .attr('text-anchor', 'middle').attr('dy', -6)
    .text(function(d) { return d.count + ' conn'; });

  /* Separate overview cards from orphan nodes */
  var overviewCards = overviewNodes.filter(function(n) { return n._isOverviewCard; });
  var orphanNodes = overviewNodes.filter(function(n) { return !n._isOverviewCard; });

  /* Draw overview cards */
  var cardGroups = nodeG.selectAll('.overview-card')
    .data(overviewCards, function(d) { return d.id; }).join('g')
    .attr('class', 'overview-card node-group')
    .attr('id', function(d) { return 'node-' + d.id; })
    .on('click', function(event, d) { event.stopPropagation(); selectNode(d); })
    .on('dblclick', function(event, d) {
      event.stopPropagation();
      if (d._childCount > 0) navigateToLevel(2, d.id);
    })
    .call(d3.drag()
      .on('start', dragStarted)
      .on('drag', dragged)
      .on('end', dragEnded));

  /* Card background — colored by dominant child type */
  cardGroups.append('rect')
    .attr('class', 'card-bg node-rect')
    .attr('width', function(d) { return d.w; }).attr('height', function(d) { return d.h; })
    .attr('rx', 12).attr('ry', 12)
    .attr('fill', function(d) { return d._groupColor || '#3b82f6'; })
    .attr('fill-opacity', 'var(--card-tint-opacity)')
    .attr('stroke', function(d) { return d._groupColor || '#3b82f6'; })
    .attr('stroke-opacity', 'var(--card-border-opacity)')
    .attr('stroke-width', 1.5);

  /* Left color bar */
  cardGroups.append('rect')
    .attr('width', 4).attr('height', function(d) { return d.h; })
    .attr('rx', 2)
    .attr('fill', function(d) { return d._groupColor || '#3b82f6'; })
    .attr('fill-opacity', 0.6);

  /* Group name */
  cardGroups.append('text')
    .attr('x', 14).attr('y', 24)
    .attr('font-size', '15px').attr('font-weight', '700')
    .attr('fill', 'var(--text)')
    .text(function(d) { return trunc(d.name, 25); });

  /* Stats line */
  cardGroups.append('text')
    .attr('x', 14).attr('y', 44)
    .attr('font-size', '11px')
    .attr('fill', 'var(--text-secondary)')
    .text(function(d) { return d._childCount + ' nodes | ' + d._internalEdgeCount + ' internal | ' + d._externalEdgeCount + ' external'; });

  /* Group description */
  cardGroups.append('text')
    .attr('x', 14).attr('y', 60)
    .attr('font-size', '10px')
    .attr('fill', 'var(--card-subtitle)')
    .attr('font-style', 'italic')
    .text(function(d) {
      var desc = getGroupDescription(d.name);
      return desc ? trunc(desc, 45) : '';
    });

  /* Type composition bar (category-level colors) */
  cardGroups.each(function(d) {
    var g = d3.select(this);
    var barY = d.h - 14, barH = 6, barW = d.w - 16;
    var catCounts = {};
    Object.entries(d._typeBreakdown).forEach(function(entry) {
      var cat = getTypeCategory(entry[0]);
      catCounts[cat] = (catCounts[cat] || 0) + entry[1];
    });
    var total = Object.values(catCounts).reduce(function(a, b) { return a + b; }, 0);
    if (total === 0) return;
    var xOff = 8;
    Object.entries(catCounts).forEach(function(entry) {
      var cat = entry[0], count = entry[1];
      var w = (count / total) * barW;
      g.append('rect')
        .attr('x', xOff).attr('y', barY)
        .attr('width', Math.max(w, 2)).attr('height', barH)
        .attr('rx', 3)
        .attr('fill', TYPE_CATEGORIES[cat] ? TYPE_CATEGORIES[cat].color : '#6b7280')
        .attr('fill-opacity', 0.5);
      xOff += w;
    });
  });

  /* Type breakdown legend text */
  cardGroups.append('text')
    .attr('x', 14).attr('y', 80)
    .attr('font-size', '9px')
    .attr('fill', 'var(--card-stats)')
    .text(function(d) {
      return Object.entries(d._typeBreakdown)
        .sort(function(a, b) { return b[1] - a[1]; })
        .slice(0, 4)
        .map(function(e) { return e[1] + ' ' + e[0]; })
        .join(', ');
    });

  /* SVG title tooltip */
  cardGroups.append('title')
    .text(function(d) { return d.name + ' (' + d._childCount + ' nodes)'; });

  /* Draw orphan nodes using shared helper */
  if (orphanNodes.length > 0) {
    var orphanG = nodeG.append('g').attr('class', 'orphan-nodes');
    gNodeGroups = drawNodes(orphanG, orphanNodes, {
      dblclickHandler: function(event, d) {
        event.stopPropagation();
        navigateToLevel(3, d.id);
      }
    });
  }

  /* Combine for gNodeGroups reference used by onTick */
  gNodeGroups = nodeG.selectAll('.node-group');
  gEdgeGroups = edgeG.selectAll('.agg-edge');

  /* Force simulation for overview */
  if (simulation) simulation.stop();
  tickCount = 0;

  var allOvNodes = overviewNodes;
  var ovNodeMap = {};
  allOvNodes.forEach(function(n) { ovNodeMap[n.id] = n; });
  simulation = d3.forceSimulation(allOvNodes)
    .force('charge', d3.forceManyBody().strength(-600).distanceMax(800))
    .force('center', d3.forceCenter(gW / 2, gH / 2).strength(0.05))
    .force('collision', d3.forceCollide().radius(function(d) { return Math.max(d.w, d.h) / 2 + 30; }).strength(0.8))
    .force('link', d3.forceLink(overviewEdges).id(function(d) { return d.id; }).distance(300).strength(0.3))
    .alphaDecay(0.03)
    .alphaMin(0.01);

  simulation
    .on('tick', function() {
      tickCount++;
      if (tickCount > 500) { simulation.stop(); return; }
      var now = performance.now();
      if (now - lastTickTime < 16) return;
      lastTickTime = now;

      /* Position cards and orphan nodes */
      gNodeGroups.attr('transform', function(d) {
        return 'translate(' + (d.x - d.w / 2) + ',' + (d.y - d.h / 2) + ')';
      });

      /* Position aggregated edges (both hit-zone and visible lines) */
      aggEdgeGroups.selectAll('line')
        .attr('x1', function(d) { var n = ovNodeMap[d.source.id || d.source]; return n ? n.x : 0; })
        .attr('y1', function(d) { var n = ovNodeMap[d.source.id || d.source]; return n ? n.y : 0; })
        .attr('x2', function(d) { var n = ovNodeMap[d.target.id || d.target]; return n ? n.x : 0; })
        .attr('y2', function(d) { var n = ovNodeMap[d.target.id || d.target]; return n ? n.y : 0; });

      aggEdgeGroups.select('text')
        .attr('x', function(d) {
          var s = ovNodeMap[d.source.id || d.source];
          var t = ovNodeMap[d.target.id || d.target];
          return s && t ? (s.x + t.x) / 2 : 0;
        })
        .attr('y', function(d) {
          var s = ovNodeMap[d.source.id || d.source];
          var t = ovNodeMap[d.target.id || d.target];
          return s && t ? (s.y + t.y) / 2 : 0;
        });

      updateMinimap();
    })
    .on('end', function() { zoomToFit(); updateMinimap(); });

  simulation.alpha(1).restart();
}

/* ================================================================
   LEVEL 2: GROUP (children + ghost external refs)
   ================================================================ */
function renderGroup(groupId) {
  gGroupG = mainG.append('g').attr('class', 'groups-layer');
  var edgeG = mainG.append('g').attr('class', 'edges-layer');
  var nodeG = mainG.append('g').attr('class', 'nodes-layer');

  /* Collect all descendants */
  var descIds = getAllDescendants(groupId);
  var memberSet = new Set([groupId].concat(descIds));
  var memberNodes = gNodeData.filter(function(n) { return memberSet.has(n.id); });

  /* Reset positions for clean layout */
  memberNodes.forEach(function(n) {
    n.x = gW * 0.1 + Math.random() * gW * 0.8;
    n.y = gH * 0.2 + Math.random() * gH * 0.6;
    n.fx = null; n.fy = null;
  });

  /* Find edges that touch these nodes */
  var internalEdges = [];
  var crossingEdges = [];
  var ghostNodeIds = new Set();

  gEdgeData.forEach(function(e) {
    var sIn = memberSet.has(e.source_id);
    var tIn = memberSet.has(e.target_id);
    if (sIn && tIn) {
      internalEdges.push({ ...e, source: e.source_id, target: e.target_id });
    } else if (sIn || tIn) {
      crossingEdges.push(e);
      var extId = sIn ? e.target_id : e.source_id;
      ghostNodeIds.add(extId);
    }
  });

  /* Create ghost nodes — positioned in a row at the top boundary */
  activeGhosts = [];
  var ghostArr = Array.from(ghostNodeIds);
  ghostArr.forEach(function(gid, gi) {
    var orig = gNodeMap[gid];
    if (!orig) return;
    var parentGroupName = findParentGroupName(gid);
    var ghostCount = ghostArr.length;
    activeGhosts.push({
      ...orig,
      _isGhost: true,
      _ghostLabel: parentGroupName ? 'from ' + parentGroupName : '',
      _ghostOrigGroup: parentGroupName,
      w: 100, h: 32,
      x: gW * 0.1 + (ghostCount > 1 ? (gi / (ghostCount - 1)) * gW * 0.8 : gW * 0.4),
      y: 40
    });
  });

  /* Combine edges for ghost connections */
  var allLevelEdges = internalEdges.slice();
  crossingEdges.forEach(function(e) {
    allLevelEdges.push({ ...e, source: e.source_id, target: e.target_id, _isGhostEdge: true });
  });

  /* Recompute pair counts for this level */
  var lvlPairCount = {};
  allLevelEdges.forEach(function(e) {
    var key = [e.source_id, e.target_id].sort().join('|');
    if (!lvlPairCount[key]) lvlPairCount[key] = 0;
    e._pairIndex = lvlPairCount[key]++;
  });
  allLevelEdges.forEach(function(e) {
    var key = [e.source_id, e.target_id].sort().join('|');
    e._pairTotal = lvlPairCount[key];
  });

  var allLevelNodes = memberNodes.concat(activeGhosts);

  /* Draw edges */
  gEdgeGroups = drawEdges(edgeG, allLevelEdges);

  /* Draw nodes */
  gNodeGroups = drawNodes(nodeG, allLevelNodes, {
    dblclickHandler: function(event, d) {
      event.stopPropagation();
      if (d._isGhost) {
        /* Navigate to ghost's parent group */
        var ghostGroupName = d._ghostOrigGroup;
        var targetGroup = overviewNodes.find(function(n) { return n._isOverviewCard && n.name === ghostGroupName; });
        if (targetGroup) navigateToLevel(2, targetGroup.id);
        else navigateToLevel(3, d.id);
      } else if (gChildrenOf[d.id] && memberSet.has(d.id) && d.id !== groupId) {
        toggleCollapse(d.id);
      } else {
        navigateToLevel(3, d.id);
      }
    }
  });

  /* Auto-collapse sub-groups deeper than 1 within this group */
  collapsedGroups = new Set();
  descIds.forEach(function(cid) {
    if (gChildrenOf[cid] && (gDepthMap[cid] || 0) >= 2) {
      collapsedGroups.add(cid);
    }
  });

  /* Force simulation */
  if (simulation) simulation.stop();
  tickCount = 0;

  simulation = d3.forceSimulation(allLevelNodes)
    .force('link', d3.forceLink(allLevelEdges).id(function(d) { return d.id; })
      .distance(function(d) {
        var s = gNodeMap[d.source.id || d.source];
        var t = gNodeMap[d.target.id || d.target];
        return (s && t && s.parent_id && s.parent_id === t.parent_id) ? 220 : 180;
      }).strength(0.4))
    .force('collision', d3.forceCollide().radius(function(d) { return Math.max(d.w, d.h) / 2 + 20; }).strength(0.8))
    .force('x', d3.forceX(gW / 2).strength(0.02))
    .alphaDecay(0.03)
    .alphaMin(0.01);

  if (layoutMode === 'clustered') {
    simulation
      .force('charge', d3.forceManyBody().strength(-400).distanceMax(600))
      .force('center', d3.forceCenter(gW / 2, gH / 2).strength(0.03))
      .force('tierY', d3.forceY(function(d) {
        var tier = TIER_Y[d.type];
        return (tier !== undefined ? tier : 0.5) * gH;
      }).strength(0.3))
      .force('cluster', clusterForce());
  } else {
    simulation
      .force('charge', d3.forceManyBody().strength(-800).distanceMax(600))
      .force('center', d3.forceCenter(gW / 2, gH / 2).strength(0.05))
      .force('tierY', d3.forceY(gH / 2).strength(0.02));
  }

  simulation
    .on('tick', function() {
      tickCount++;
      if (tickCount > 500) { simulation.stop(); return; }
      var now = performance.now();
      if (now - lastTickTime < 16) return;
      lastTickTime = now;
      onTick();
    })
    .on('end', function() { zoomToFit(); updateMinimap(); });

  simulation.alpha(1).restart();
  applyCollapse();
}

/* ================================================================
   LEVEL 3: FOCUS (center node + 1-hop radial)
   ================================================================ */
function renderFocus(nodeId) {
  var edgeG = mainG.append('g').attr('class', 'edges-layer');
  var nodeG = mainG.append('g').attr('class', 'nodes-layer');

  var centerNode = gNodeMap[nodeId];
  if (!centerNode) return;

  /* Find 1-hop neighbors */
  var neighborIds = new Set();
  var focusEdges = [];
  gEdgeData.forEach(function(e) {
    if (e.source_id === nodeId) { neighborIds.add(e.target_id); focusEdges.push({ ...e, source: e.source_id, target: e.target_id }); }
    if (e.target_id === nodeId) { neighborIds.add(e.source_id); focusEdges.push({ ...e, source: e.source_id, target: e.target_id }); }
  });

  var neighborNodes = [];
  var radius = Math.min(gW, gH) * 0.3;
  var angleStep = neighborIds.size > 0 ? (2 * Math.PI) / neighborIds.size : 0;
  var i = 0;
  neighborIds.forEach(function(nid) {
    var orig = gNodeMap[nid];
    if (!orig) return;
    var angle = angleStep * i;
    neighborNodes.push({
      ...orig,
      x: gW / 2 + radius * Math.cos(angle),
      y: gH / 2 + radius * Math.sin(angle)
    });
    i++;
  });

  /* Position center node */
  var focusCenterNode = {
    ...centerNode,
    _isFocusCenter: true,
    x: gW / 2,
    y: gH / 2,
    fx: gW / 2,
    fy: gH / 2
  };

  var allFocusNodes = [focusCenterNode].concat(neighborNodes);

  /* Recompute pair counts */
  var fPairCount = {};
  focusEdges.forEach(function(e) {
    var key = [e.source_id, e.target_id].sort().join('|');
    if (!fPairCount[key]) fPairCount[key] = 0;
    e._pairIndex = fPairCount[key]++;
  });
  focusEdges.forEach(function(e) {
    var key = [e.source_id, e.target_id].sort().join('|');
    e._pairTotal = fPairCount[key];
  });

  /* Draw edges */
  gEdgeGroups = drawEdges(edgeG, focusEdges);

  /* Make edge labels always visible in focus mode */
  gEdgeGroups.select('.edge-label').style('opacity', 1);

  /* Draw nodes */
  gNodeGroups = drawNodes(nodeG, allFocusNodes, {
    dblclickHandler: function(event, d) {
      event.stopPropagation();
      if (!d._isFocusCenter) navigateToLevel(3, d.id);
    }
  });

  /* Force simulation: radial layout */
  if (simulation) simulation.stop();
  tickCount = 0;

  simulation = d3.forceSimulation(allFocusNodes)
    .force('link', d3.forceLink(focusEdges).id(function(d) { return d.id; }).distance(radius * 0.8).strength(0.5))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('radial', d3.forceRadial(function(d) { return d._isFocusCenter ? 0 : radius; }, gW / 2, gH / 2).strength(0.8))
    .force('collision', d3.forceCollide().radius(function(d) { return Math.max(d.w, d.h) / 2 + 15; }).strength(0.9))
    .alphaDecay(0.05)
    .alphaMin(0.01);

  simulation
    .on('tick', function() {
      tickCount++;
      if (tickCount > 300) { simulation.stop(); return; }
      var now = performance.now();
      if (now - lastTickTime < 16) return;
      lastTickTime = now;
      onTick();
    })
    .on('end', function() { zoomToFit(); updateMinimap(); });

  simulation.alpha(1).restart();
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
        y2: d3.max(all, n => n.y + n.h/2) + 50
      });
    });
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
    .force('x', d3.forceX(gW / 2).strength(0.02))
    .alphaDecay(0.03)
    .alphaMin(0.01);

  if (layoutMode === 'clustered') {
    simulation
      .force('charge', d3.forceManyBody().strength(-400).distanceMax(600))
      .force('center', d3.forceCenter(gW / 2, gH / 2).strength(0.03))
      .force('tierY', d3.forceY(d => {
        const tier = TIER_Y[d.type];
        return (tier !== undefined ? tier : 0.5) * gH;
      }).strength(0.3))
      .force('cluster', clusterForce());
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
  const nodes = d3.selectAll('.node-group').data().filter(n => !hiddenNodes.has(n.id) && !columnNodeIds.has(n.id));
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
