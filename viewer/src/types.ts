export type NodeType =
  | 'system' | 'service' | 'database' | 'table' | 'column'
  | 'api' | 'route' | 'function' | 'module' | 'container'
  | 'queue' | 'cache' | 'external' | 'config' | 'file';

export type NodeStatus = 'planned' | 'in_progress' | 'built' | 'broken' | 'deprecated';

export type EdgeRelationship =
  | 'connects_to' | 'reads_from' | 'writes_to' | 'depends_on'
  | 'authenticates' | 'calls' | 'inherits' | 'contains' | 'exposes';

export type EdgeStatus = 'active' | 'broken' | 'planned';

export interface BlueprintNode {
  id: string;
  name: string;
  type: NodeType;
  status: NodeStatus;
  parent_id: string | null;
  description: string | null;
  metadata: Record<string, unknown> | null;
  source_file: string | null;
  source_line: number | null;
  template_origin: string | null;
  created_at: string;
  updated_at: string;
  children?: BlueprintNode[] | null;
  edges?: BlueprintEdge[] | null;
}

export interface BlueprintEdge {
  id: string;
  source_id: string;
  target_id: string;
  relationship: EdgeRelationship;
  label: string | null;
  metadata: Record<string, unknown> | null;
  status: EdgeStatus;
  created_at: string;
}

export interface BlueprintData {
  nodes: BlueprintNode[];
  edges: BlueprintEdge[];
  summary: {
    total_nodes: number;
    total_edges: number;
  };
}

export interface BlueprintSummary {
  counts_by_type: Record<string, number>;
  counts_by_status: Record<string, number>;
  total_nodes: number;
  total_edges: number;
  recent_changes: unknown[];
}

export interface Issue {
  severity: 'critical' | 'warning' | 'info';
  type: string;
  message: string;
  node_ids: string[];
  suggestion: string;
}
