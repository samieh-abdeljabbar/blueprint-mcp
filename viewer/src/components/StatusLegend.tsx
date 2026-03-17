import type { BlueprintSummary, NodeStatus } from '../types';
import { STATUS_COLORS } from '../utils/colors';

interface Props {
  summary: BlueprintSummary | null;
}

const STATUSES: NodeStatus[] = ['planned', 'in_progress', 'built', 'broken', 'deprecated'];

export function StatusLegend({ summary }: Props) {
  return (
    <div
      style={{
        position: 'absolute',
        bottom: 16,
        left: 16,
        background: '#fff',
        borderRadius: 8,
        boxShadow: '0 2px 8px rgba(0,0,0,0.12)',
        padding: '12px 16px',
        fontSize: 12,
        zIndex: 10,
      }}
    >
      {STATUSES.map(status => {
        const colors = STATUS_COLORS[status];
        const count = summary?.counts_by_status?.[status] ?? 0;
        return (
          <div key={status} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <div
              style={{
                width: 14,
                height: 14,
                borderRadius: 3,
                background: colors.bg,
                border: `2px solid ${colors.border}`,
              }}
            />
            <span style={{ color: '#475569' }}>{status.replace('_', ' ')}</span>
            <span style={{ color: '#94a3b8', marginLeft: 'auto' }}>{count}</span>
          </div>
        );
      })}
    </div>
  );
}
