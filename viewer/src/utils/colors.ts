import type { NodeStatus, NodeType } from '../types';

export const STATUS_COLORS: Record<NodeStatus, { bg: string; border: string; text: string }> = {
  planned:    { bg: '#dbeafe', border: '#3b82f6', text: '#1e40af' },
  in_progress:{ bg: '#fef3c7', border: '#f59e0b', text: '#92400e' },
  built:      { bg: '#d1fae5', border: '#10b981', text: '#065f46' },
  broken:     { bg: '#fee2e2', border: '#ef4444', text: '#991b1b' },
  deprecated: { bg: '#f3f4f6', border: '#9ca3af', text: '#6b7280' },
};

export const TYPE_ICONS: Record<NodeType, string> = {
  system:    '\u{1F3D7}',
  service:   '\u{2699}',
  database:  '\u{1F5C4}',
  table:     '\u{1F4CB}',
  column:    '\u{1F4CF}',
  api:       '\u{1F310}',
  route:     '\u{27A1}',
  function:  '\u{1F527}',
  module:    '\u{1F4E6}',
  container: '\u{1F4E6}',
  queue:     '\u{23F3}',
  cache:     '\u{26A1}',
  external:  '\u{1F517}',
  config:    '\u{2699}',
  file:      '\u{1F4C4}',
};
