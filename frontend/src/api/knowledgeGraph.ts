import api from './client';
import type { KGGraphData, KGStats } from '@/types';

export const knowledgeGraphApi = {
  getGraph: async (): Promise<KGGraphData> => {
    const response = await api.get<KGGraphData>('/knowledge-graph');
    return response.data;
  },

  getStats: async (): Promise<KGStats> => {
    const response = await api.get<KGStats>('/knowledge-graph/stats');
    return response.data;
  },

  getSubgraph: async (node: string, depth: number = 2): Promise<{ nodes: KGGraphData['nodes']; edges: KGGraphData['edges'] }> => {
    const params = new URLSearchParams({ node, depth: String(depth) });
    const response = await api.get(`/knowledge-graph/subgraph?${params}`);
    return response.data;
  },
};
