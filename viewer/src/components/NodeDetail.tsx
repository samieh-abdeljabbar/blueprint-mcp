import type { BlueprintNode, BlueprintEdge } from '../types';
import { STATUS_COLORS } from '../utils/colors';

interface Props {
  node: BlueprintNode;
  allNodes: BlueprintNode[];
  allEdges: BlueprintEdge[];
  onClose: () => void;
}

export function NodeDetail({ node, allNodes, allEdges, onClose }: Props) {
  const nodeMap = new Map(allNodes.map(n => [n.id, n]));
  const colors = STATUS_COLORS[node.status] || STATUS_COLORS.built;

  const connections = allEdges.filter(
    e => e.source_id === node.id || e.target_id === node.id
  );

  const children = allNodes.filter(n => n.parent_id === node.id);

  return (
    <div
      style={{
        width: 350,
        height: '100vh',
        borderLeft: `3px solid ${colors.border}`,
        background: '#fff',
        padding: 20,
        overflowY: 'auto',
        fontSize: 13,
        fontFamily: '-apple-system, BlinkMacSystemFont, sans-serif',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ fontSize: 18, color: colors.text }}>{node.name}</h2>
        <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer' }}>
          &times;
        </button>
      </div>

      <div style={{ marginTop: 12 }}>
        <Label>Type</Label>
        <Value>{node.type}</Value>
      </div>
      <div style={{ marginTop: 8 }}>
        <Label>Status</Label>
        <span
          style={{
            background: colors.bg,
            border: `1px solid ${colors.border}`,
            color: colors.text,
            padding: '2px 8px',
            borderRadius: 4,
            fontSize: 12,
          }}
        >
          {node.status}
        </span>
      </div>

      {node.description && (
        <div style={{ marginTop: 12 }}>
          <Label>Description</Label>
          <p style={{ color: '#475569' }}>{node.description}</p>
        </div>
      )}

      {node.source_file && (
        <div style={{ marginTop: 12 }}>
          <Label>Source</Label>
          <code style={{ fontSize: 12, color: '#64748b' }}>
            {node.source_file}
            {node.source_line ? `:${node.source_line}` : ''}
          </code>
        </div>
      )}

      {node.metadata && Object.keys(node.metadata).length > 0 && (
        <div style={{ marginTop: 12 }}>
          <Label>Metadata</Label>
          <pre
            style={{
              background: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: 4,
              padding: 8,
              fontSize: 11,
              overflow: 'auto',
              maxHeight: 200,
            }}
          >
            {JSON.stringify(node.metadata, null, 2)}
          </pre>
        </div>
      )}

      {children.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <Label>Children ({children.length})</Label>
          {children.map(c => (
            <div key={c.id} style={{ padding: '4px 0', color: '#475569' }}>
              {c.name} <span style={{ fontSize: 11, color: '#94a3b8' }}>({c.type})</span>
            </div>
          ))}
        </div>
      )}

      {connections.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <Label>Connections ({connections.length})</Label>
          {connections.map(e => {
            const other = e.source_id === node.id
              ? nodeMap.get(e.target_id)
              : nodeMap.get(e.source_id);
            const direction = e.source_id === node.id ? '\u2192' : '\u2190';
            return (
              <div key={e.id} style={{ padding: '4px 0', color: '#475569' }}>
                {direction} {other?.name || 'unknown'}
                <span style={{ fontSize: 11, color: '#94a3b8', marginLeft: 4 }}>
                  ({e.relationship})
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 11, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', marginBottom: 4 }}>
      {children}
    </div>
  );
}

function Value({ children }: { children: React.ReactNode }) {
  return <div style={{ color: '#334155' }}>{children}</div>;
}
