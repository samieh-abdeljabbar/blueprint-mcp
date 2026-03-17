import { useState, useMemo } from 'react';
import { useBlueprintData } from './hooks/useBlueprintData';
import { BlueprintCanvas } from './components/BlueprintCanvas';
import { NodeDetail } from './components/NodeDetail';
import { StatusLegend } from './components/StatusLegend';
import { TemplateSelector } from './components/TemplateSelector';
import { IssuePanel } from './components/IssuePanel';
import type { BlueprintNode } from './types';

export default function App() {
  const { data, summary, loading, error } = useBlueprintData();
  const [selectedNode, setSelectedNode] = useState<BlueprintNode | null>(null);
  const [templateFilter, setTemplateFilter] = useState<string | null>(null);

  const filteredNodes = useMemo(() => {
    if (!data) return [];
    if (!templateFilter) return data.nodes;
    return data.nodes.filter(n => n.template_origin === templateFilter);
  }, [data, templateFilter]);

  const filteredNodeIds = useMemo(() => new Set(filteredNodes.map(n => n.id)), [filteredNodes]);

  const filteredEdges = useMemo(() => {
    if (!data) return [];
    return data.edges.filter(
      e => filteredNodeIds.has(e.source_id) && filteredNodeIds.has(e.target_id)
    );
  }, [data, filteredNodeIds]);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: '#64748b' }}>
        Loading blueprint...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: '#ef4444' }}>
        Error: {error}
      </div>
    );
  }

  if (!data || data.nodes.length === 0) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: '#94a3b8' }}>
        No nodes in blueprint. Scan a project or apply a template first.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', width: '100%', height: '100vh' }}>
      <div style={{ flex: 1, position: 'relative' }}>
        <BlueprintCanvas
          nodes={filteredNodes}
          edges={filteredEdges}
          onNodeClick={setSelectedNode}
        />
        <StatusLegend summary={summary} />
        <TemplateSelector
          nodes={data.nodes}
          value={templateFilter}
          onChange={setTemplateFilter}
        />
        <IssuePanel />
      </div>
      {selectedNode && (
        <NodeDetail
          node={selectedNode}
          allNodes={data.nodes}
          allEdges={data.edges}
          onClose={() => setSelectedNode(null)}
        />
      )}
    </div>
  );
}
