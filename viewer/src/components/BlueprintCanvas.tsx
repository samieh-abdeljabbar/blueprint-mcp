import { useCallback, useEffect, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node as RFNode,
  type Edge as RFEdge,
  type OnNodesChange,
  type OnEdgesChange,
  applyNodeChanges,
  applyEdgeChanges,
} from 'reactflow';
import 'reactflow/dist/style.css';
import type { BlueprintNode, BlueprintEdge } from '../types';
import { computeLayout } from '../utils/layout';
import { CustomNode } from './CustomNode';
import { STATUS_COLORS } from '../utils/colors';

const nodeTypes = { custom: CustomNode };

interface Props {
  nodes: BlueprintNode[];
  edges: BlueprintEdge[];
  onNodeClick: (node: BlueprintNode) => void;
}

export function BlueprintCanvas({ nodes, edges, onNodeClick }: Props) {
  const [rfNodes, setRfNodes] = useState<RFNode[]>([]);
  const [rfEdges, setRfEdges] = useState<RFEdge[]>([]);

  useEffect(() => {
    computeLayout(nodes, edges).then(({ rfNodes, rfEdges }) => {
      setRfNodes(rfNodes);
      setRfEdges(rfEdges);
    });
  }, [nodes, edges]);

  const onNodesChange: OnNodesChange = useCallback(
    changes => setRfNodes(nds => applyNodeChanges(changes, nds)),
    []
  );
  const onEdgesChange: OnEdgesChange = useCallback(
    changes => setRfEdges(eds => applyEdgeChanges(changes, eds)),
    []
  );

  return (
    <ReactFlow
      nodes={rfNodes}
      edges={rfEdges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={(_, node) => onNodeClick(node.data)}
      fitView
      minZoom={0.1}
      maxZoom={2}
    >
      <Background />
      <Controls />
      <MiniMap
        nodeColor={node => {
          const status = node.data?.status;
          return STATUS_COLORS[status as keyof typeof STATUS_COLORS]?.border || '#94a3b8';
        }}
        style={{ borderRadius: 8 }}
      />
    </ReactFlow>
  );
}
