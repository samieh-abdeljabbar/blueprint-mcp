import ELK, { type ElkNode, type ElkExtendedEdge } from 'elkjs/lib/elk.bundled.js';
import type { Node as RFNode, Edge as RFEdge } from 'reactflow';
import type { BlueprintNode, BlueprintEdge } from '../types';

const elk = new ELK();

const NODE_WIDTH = 220;
const NODE_HEIGHT = 60;

export async function computeLayout(
  nodes: BlueprintNode[],
  edges: BlueprintEdge[]
): Promise<{ rfNodes: RFNode[]; rfEdges: RFEdge[] }> {
  // Build parent-child map
  const childMap = new Map<string, BlueprintNode[]>();
  const rootNodes: BlueprintNode[] = [];
  const nodeMap = new Map(nodes.map(n => [n.id, n]));

  for (const n of nodes) {
    if (n.parent_id && nodeMap.has(n.parent_id)) {
      const siblings = childMap.get(n.parent_id) || [];
      siblings.push(n);
      childMap.set(n.parent_id, siblings);
    } else {
      rootNodes.push(n);
    }
  }

  // Recursively build ELK graph
  function toElkNode(n: BlueprintNode): ElkNode {
    const children = childMap.get(n.id) || [];
    return {
      id: n.id,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      ...(children.length > 0
        ? {
            children: children.map(toElkNode),
            layoutOptions: {
              'elk.algorithm': 'layered',
              'elk.direction': 'DOWN',
              'elk.spacing.nodeNode': '30',
              'elk.padding': '[top=40,left=20,bottom=20,right=20]',
            },
          }
        : {}),
    };
  }

  const elkEdges: ElkExtendedEdge[] = edges.map(e => ({
    id: e.id,
    sources: [e.source_id],
    targets: [e.target_id],
  }));

  const graph: ElkNode = {
    id: 'root',
    children: rootNodes.map(toElkNode),
    edges: elkEdges,
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': 'DOWN',
      'elk.spacing.nodeNode': '50',
      'elk.layered.spacing.nodeNodeBetweenLayers': '80',
    },
  };

  const laid = await elk.layout(graph);

  // Flatten ELK tree to ReactFlow nodes with absolute positions
  const rfNodes: RFNode[] = [];

  function flatten(elkNode: ElkNode, parentId?: string) {
    const bpNode = nodeMap.get(elkNode.id);
    if (!bpNode) return;
    const hasChildren = (elkNode.children || []).length > 0;
    rfNodes.push({
      id: elkNode.id,
      type: 'custom',
      position: { x: elkNode.x || 0, y: elkNode.y || 0 },
      data: bpNode,
      ...(parentId ? { parentNode: parentId, extent: 'parent' as const } : {}),
      style: hasChildren
        ? {
            width: elkNode.width,
            height: elkNode.height,
          }
        : undefined,
    });
    for (const child of elkNode.children || []) {
      flatten(child, elkNode.id);
    }
  }

  for (const child of laid.children || []) {
    flatten(child);
  }

  // Build ReactFlow edges
  const rfEdges: RFEdge[] = edges.map(e => ({
    id: e.id,
    source: e.source_id,
    target: e.target_id,
    label: e.label || e.relationship,
    animated: e.status === 'active',
    style: {
      stroke: e.status === 'broken' ? '#ef4444' : '#64748b',
      strokeWidth: e.status === 'broken' ? 3 : 1.5,
      ...(e.status === 'planned' ? { strokeDasharray: '5 5' } : {}),
    },
  }));

  return { rfNodes, rfEdges };
}
