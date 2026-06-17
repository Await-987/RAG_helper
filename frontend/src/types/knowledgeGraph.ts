export interface KGNodeSource {
  file: string;
  content: string;
}

export interface KGNode {
  id: string;
  type: string;
  freq: number;
  x?: number;
  y?: number;
  sources?: KGNodeSource[];
}

export interface KGEdge {
  source: string;
  target: string;
  relation: string;
  weight: number;
}

export interface KGMeta {
  collection: string;
  extracted_at: string;
  total_chunks_processed: number;
  total_nodes: number;
  total_edges: number;
}

export interface KGGraphData {
  meta: KGMeta;
  nodes: KGNode[];
  edges: KGEdge[];
}

export interface KGStats {
  total_nodes: number;
  total_edges: number;
  node_types: Record<string, number>;
  relation_types: Record<string, number>;
  meta: KGMeta;
}
