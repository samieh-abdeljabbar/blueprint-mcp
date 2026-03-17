import type { BlueprintNode } from '../types';

interface Props {
  nodes: BlueprintNode[];
  value: string | null;
  onChange: (v: string | null) => void;
}

export function TemplateSelector({ nodes, value, onChange }: Props) {
  const origins = [...new Set(nodes.map(n => n.template_origin).filter(Boolean))] as string[];
  if (origins.length === 0) return null;

  return (
    <div
      style={{
        position: 'absolute',
        top: 16,
        right: 16,
        zIndex: 10,
      }}
    >
      <select
        value={value || ''}
        onChange={e => onChange(e.target.value || null)}
        style={{
          padding: '6px 12px',
          borderRadius: 6,
          border: '1px solid #d1d5db',
          background: '#fff',
          fontSize: 13,
          cursor: 'pointer',
        }}
      >
        <option value="">All templates</option>
        {origins.map(o => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </div>
  );
}
