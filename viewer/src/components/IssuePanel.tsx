import { useState, useEffect } from 'react';
import type { Issue } from '../types';

const SEVERITY_COLORS = {
  critical: { bg: '#fee2e2', text: '#991b1b' },
  warning: { bg: '#fef3c7', text: '#92400e' },
  info: { bg: '#dbeafe', text: '#1e40af' },
};

export function IssuePanel() {
  const [issues, setIssues] = useState<Issue[]>([]);
  const [unavailable, setUnavailable] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    fetch('/api/issues')
      .then(r => {
        if (!r.ok) throw new Error('unavailable');
        return r.json();
      })
      .then(data => {
        if (data.unavailable) {
          setUnavailable(true);
        } else {
          setIssues(data.issues || []);
        }
      })
      .catch(() => setUnavailable(true));
  }, []);

  if (unavailable) return null;
  if (issues.length === 0) return null;

  return (
    <div
      style={{
        position: 'absolute',
        top: 16,
        left: 16,
        zIndex: 10,
      }}
    >
      <button
        onClick={() => setOpen(!open)}
        style={{
          padding: '6px 14px',
          borderRadius: 6,
          border: '1px solid #d1d5db',
          background: issues.some(i => i.severity === 'critical') ? '#fee2e2' : '#fff',
          fontSize: 13,
          cursor: 'pointer',
        }}
      >
        Issues ({issues.length})
      </button>

      {open && (
        <div
          style={{
            marginTop: 8,
            background: '#fff',
            borderRadius: 8,
            boxShadow: '0 2px 8px rgba(0,0,0,0.12)',
            padding: 12,
            maxHeight: 400,
            overflowY: 'auto',
            width: 340,
          }}
        >
          {issues.map((issue, i) => {
            const colors = SEVERITY_COLORS[issue.severity];
            return (
              <div
                key={i}
                style={{
                  padding: '8px 10px',
                  marginBottom: 6,
                  borderRadius: 6,
                  background: colors.bg,
                  color: colors.text,
                  fontSize: 12,
                }}
              >
                <strong>{issue.type}</strong>
                <p style={{ marginTop: 4 }}>{issue.message}</p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
