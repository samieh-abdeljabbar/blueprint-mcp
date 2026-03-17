import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import type { BlueprintNode, NodeStatus } from '../types';
import { STATUS_COLORS, TYPE_ICONS } from '../utils/colors';

function CustomNodeInner({ data }: NodeProps<BlueprintNode>) {
  const colors = STATUS_COLORS[data.status as NodeStatus] || STATUS_COLORS.built;
  const icon = TYPE_ICONS[data.type] || '';

  return (
    <div
      style={{
        background: colors.bg,
        border: `2px solid ${colors.border}`,
        borderRadius: 8,
        padding: '8px 12px',
        minWidth: 180,
        fontSize: 13,
        color: colors.text,
        fontFamily: '-apple-system, BlinkMacSystemFont, sans-serif',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: colors.border }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 16 }}>{icon}</span>
        <strong style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {data.name}
        </strong>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 11, opacity: 0.8 }}>
        <span>{data.type}</span>
        <span
          style={{
            background: colors.border,
            color: '#fff',
            borderRadius: 4,
            padding: '1px 6px',
            fontSize: 10,
          }}
        >
          {data.status}
        </span>
      </div>
      <Handle type="source" position={Position.Bottom} style={{ background: colors.border }} />
    </div>
  );
}

export const CustomNode = memo(CustomNodeInner);
