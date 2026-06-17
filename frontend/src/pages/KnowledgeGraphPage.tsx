import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { knowledgeGraphApi } from '@/api/knowledgeGraph';
import type { KGGraphData, KGNode, KGEdge } from '@/types';
import type { EdgeData, Graph as G6Graph, IElementEvent, NodeData } from '@antv/g6';
import { Check, FileText, Filter, Loader2, Network, RotateCcw, Search, X } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';

const NODE_TYPE_COLORS: Record<string, string> = {
  '设备': '#3b82f6',
  '规范标准': '#22c55e',
  '参数指标': '#f97316',
  '设计要求': '#a855f7',
  '工程场景': '#06b6d4',
  '材料': '#ef4444',
};

const DEFAULT_NODE_COLOR = '#6b7280';
const RELATION_ORDER = ['适用于', '要求满足', '参数值为', '引用规范', '包含', '连接', '属于'];

function getNodeColor(type: string): string {
  return NODE_TYPE_COLORS[type] || DEFAULT_NODE_COLOR;
}

function getNodeSize(freq: number, maxFreq: number): number {
  const minSize = 16;
  const maxSize = 48;
  if (maxFreq <= 1) return minSize;
  return minSize + ((freq - 1) / (maxFreq - 1)) * (maxSize - minSize);
}

function countBy<T extends string>(values: T[]): Record<T, number> {
  return values.reduce((acc, value) => {
    acc[value] = (acc[value] || 0) + 1;
    return acc;
  }, {} as Record<T, number>);
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: unknown } } }).response;
    if (typeof response?.data?.detail === 'string') return response.data.detail;
  }
  return fallback;
}

export function KnowledgeGraphPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<G6Graph | null>(null);
  const nodesRef = useRef<KGNode[]>([]);
  const fullGraphDataRef = useRef<KGGraphData | null>(null);
  const highlightedNodeIdRef = useRef<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [subgraphLoadingNode, setSubgraphLoadingNode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [graphData, setGraphData] = useState<KGGraphData | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedNodeTypes, setSelectedNodeTypes] = useState<Set<string>>(new Set());
  const [selectedRelTypes, setSelectedRelTypes] = useState<Set<string>>(new Set());
  const [showFilters, setShowFilters] = useState(false);
  const [subgraphCenter, setSubgraphCenter] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<KGNode | null>(null);

  const clearGraphHighlight = useCallback(() => {
    const graph = graphRef.current;
    highlightedNodeIdRef.current = null;
    if (!graph) return;

    const state: Record<string, string[]> = {};
    graph.getNodeData()?.forEach((node: NodeData) => {
      state[node.id] = [];
    });
    graph.getEdgeData()?.forEach((edge: EdgeData) => {
      if (edge.id) state[edge.id] = [];
    });
    void graph.setElementState(state, false);
  }, []);

  const applyNodeHighlight = useCallback((nodeId: string) => {
    const graph = graphRef.current;
    if (!graph) return;

    const nodeData = graph.getNodeData?.() || [];
    const edgeData = graph.getEdgeData?.() || [];
    const relatedNodeIds = new Set<string>([nodeId]);
    const relatedEdgeIds = new Set<string>();

    edgeData.forEach((edge: EdgeData) => {
      if (edge.source === nodeId || edge.target === nodeId) {
        if (edge.id) relatedEdgeIds.add(edge.id);
        relatedNodeIds.add(edge.source);
        relatedNodeIds.add(edge.target);
      }
    });

    const state: Record<string, string[]> = {};
    nodeData.forEach((node: NodeData) => {
      state[node.id] = relatedNodeIds.has(node.id)
        ? node.id === nodeId ? ['selected'] : ['active']
        : ['inactive'];
    });
    edgeData.forEach((edge: EdgeData) => {
      if (edge.id) state[edge.id] = relatedEdgeIds.has(edge.id) ? ['active'] : ['inactive'];
    });

    highlightedNodeIdRef.current = nodeId;
    void graph.setElementState(state, false);
    void graph.frontElement([...relatedNodeIds]);
  }, []);

  const loadGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await knowledgeGraphApi.getGraph();
      fullGraphDataRef.current = data;
      setGraphData(data);
      nodesRef.current = data.nodes;
      setSubgraphCenter(null);
      clearGraphHighlight();
    } catch (err: unknown) {
      setError(getErrorMessage(err, '加载知识图谱失败'));
    } finally {
      setLoading(false);
    }
  }, [clearGraphHighlight]);

  useEffect(() => { loadGraph(); }, [loadGraph]);

  const filteredData = useMemo(() => {
    if (!graphData) return { nodes: [] as KGNode[], edges: [] as KGEdge[] };
    let nodes = graphData.nodes;
    let edges = graphData.edges;

    if (selectedNodeTypes.size > 0) {
      const allowedIds = new Set(
        nodes.filter((n) => selectedNodeTypes.has(n.type)).map((n) => n.id)
      );
      nodes = nodes.filter((n) => allowedIds.has(n.id));
      edges = edges.filter((e) => allowedIds.has(e.source) && allowedIds.has(e.target));
    }

    if (selectedRelTypes.size > 0) {
      edges = edges.filter((e) => selectedRelTypes.has(e.relation));
      const edgeNodeIds = new Set(edges.flatMap((e) => [e.source, e.target]));
      nodes = nodes.filter((n) => edgeNodeIds.has(n.id));
    }

    // Remove isolated nodes (no edges)
    const connectedIds = new Set(edges.flatMap((e) => [e.source, e.target]));
    nodes = nodes.filter((n) => connectedIds.has(n.id));

    return { nodes, edges };
  }, [graphData, selectedNodeTypes, selectedRelTypes]);

  const stats = useMemo(() => {
    const nodeTypes = new Set(filteredData.nodes.map((n) => n.type));
    return {
      nodes: filteredData.nodes.length,
      edges: filteredData.edges.length,
      types: nodeTypes.size,
    };
  }, [filteredData]);

  const nodeTypeCounts = useMemo(
    () => countBy((graphData?.nodes || []).map((n) => n.type)),
    [graphData],
  );

  const relationTypeCounts = useMemo(
    () => countBy((graphData?.edges || []).map((e) => e.relation)),
    [graphData],
  );

  const handleExpandSubgraph = useCallback(async (nodeId: string) => {
    const baseGraph = fullGraphDataRef.current || graphData;
    if (!baseGraph) return;

    setSubgraphLoadingNode(nodeId);
    try {
      const subgraph = await knowledgeGraphApi.getSubgraph(nodeId, 2);
      const nextData: KGGraphData = {
        meta: baseGraph.meta,
        nodes: subgraph.nodes,
        edges: subgraph.edges,
      };
      setSelectedNodeTypes(new Set());
      setSelectedRelTypes(new Set());
      setGraphData(nextData);
      nodesRef.current = nextData.nodes;
      highlightedNodeIdRef.current = nodeId;
      setSelectedNode(nextData.nodes.find((node) => node.id === nodeId) || null);
      setSubgraphCenter(nodeId);
      toast.success(`已展开 ${nodeId} 的 2 跳子图`);
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, '展开子图失败'));
    } finally {
      setSubgraphLoadingNode(null);
    }
  }, [graphData]);

  useEffect(() => {
    if (!graphData || !containerRef.current) return;

    let destroyed = false;

    const initGraph = async () => {
      const G6 = await import('@antv/g6');
      if (destroyed) return;

      if (graphRef.current) {
        graphRef.current.destroy();
        graphRef.current = null;
      }

      const { nodes, edges } = filteredData;
      nodesRef.current = nodes;
      if (!nodes.length) return;

      const maxFreq = Math.max(...nodes.map((n) => n.freq), 1);

      const g6Data = {
        nodes: nodes.map((n) => ({
          id: n.id,
          data: { ...n, cluster: n.type },
          style: {
            x: n.x ?? 0,
            y: n.y ?? 0,
            size: getNodeSize(n.freq, maxFreq),
            fill: getNodeColor(n.type),
            stroke: getNodeColor(n.type),
            lineWidth: 1,
            labelText: n.id,
            labelFontSize: 10,
            labelFill: '#e4e4e7',
            labelPlacement: 'bottom' as const,
          },
        })),
        edges: edges.map((e, i) => ({
          id: `edge-${i}`,
          source: e.source,
          target: e.target,
          data: { ...e },
          style: {
            stroke: '#525252',
            lineWidth: Math.min(e.weight, 3),
            endArrow: true,
            labelText: e.relation,
            labelFontSize: 9,
            labelFill: '#a1a1aa',
          },
        })),
      };

      const container = containerRef.current!;
      const width = container.clientWidth || 800;
      const height = container.clientHeight || 600;

      const graph = new G6.Graph({
        container,
        width,
        height,
        autoResize: true,
        autoFit: 'view',
        data: g6Data,
        behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element'],
        node: {
          style: { labelMaxWidth: 80, cursor: 'pointer' },
          state: {
            selected: {
              stroke: '#f8fafc',
              lineWidth: 3,
              halo: true,
              haloStroke: '#f8fafc',
              haloLineWidth: 10,
              haloOpacity: 0.18,
              labelFontWeight: 600,
              opacity: 1,
              labelOpacity: 1,
            },
            active: {
              stroke: '#facc15',
              lineWidth: 2,
              opacity: 1,
              labelOpacity: 1,
            },
            inactive: {
              opacity: 0.18,
              labelOpacity: 0.24,
            },
          },
        },
        edge: {
          state: {
            active: {
              stroke: '#facc15',
              lineWidth: 3,
              labelFill: '#fde68a',
              opacity: 1,
              labelOpacity: 1,
            },
            inactive: {
              opacity: 0.1,
              labelOpacity: 0.08,
            },
          },
        },
      });

      await graph.render();
      if (destroyed) {
        graph.destroy();
        return;
      }
      graphRef.current = graph;

      graph.on('node:click', (evt: IElementEvent) => {
        const nodeId = evt?.target?.id;
        if (!nodeId) return;
        const found = nodes.find((n) => n.id === nodeId);
        if (found) setSelectedNode(found);
        applyNodeHighlight(nodeId);
      });

      graph.on('node:dblclick', (evt: IElementEvent) => {
        const nodeId = evt?.target?.id;
        if (!nodeId) return;
        void handleExpandSubgraph(nodeId);
      });

      graph.on('canvas:click', () => {
        setSelectedNode(null);
        clearGraphHighlight();
      });

      const highlightedNodeId = highlightedNodeIdRef.current;
      if (highlightedNodeId && nodes.some((node) => node.id === highlightedNodeId)) {
        applyNodeHighlight(highlightedNodeId);
      } else if (highlightedNodeId) {
        highlightedNodeIdRef.current = null;
        setSelectedNode(null);
      }
    };

    initGraph();

    return () => {
      destroyed = true;
      if (graphRef.current) {
        graphRef.current.destroy();
        graphRef.current = null;
      }
    };
  }, [graphData, filteredData, applyNodeHighlight, clearGraphHighlight, handleExpandSubgraph]);

  const handleSearch = useCallback(() => {
    if (!graphRef.current || !searchQuery.trim()) return;
    const graph = graphRef.current;
    const nodeData = graph.getNodeData();
    const match = nodeData?.find((n) => n.id.includes(searchQuery.trim()));
    if (match) {
      void graph.focusElement(match.id, { duration: 300 });
      const found = nodesRef.current.find((n) => n.id === match.id);
      if (found) setSelectedNode(found);
      applyNodeHighlight(match.id);
      toast.success(`已定位到: ${match.id}`);
    } else {
      toast.error('未找到匹配的实体');
    }
  }, [applyNodeHighlight, searchQuery]);

  const handleReset = useCallback(() => {
    const fullGraphData = fullGraphDataRef.current;
    if (fullGraphData) {
      setGraphData(fullGraphData);
      nodesRef.current = fullGraphData.nodes;
    }
    setSelectedNodeTypes(new Set());
    setSelectedRelTypes(new Set());
    setSearchQuery('');
    setSelectedNode(null);
    setSubgraphCenter(null);
    clearGraphHighlight();
    if (graphRef.current) {
      void graphRef.current.fitView(undefined, { duration: 300 });
    }
  }, [clearGraphHighlight]);

  const toggleNodeType = (type: string) => {
    setSelectedNodeTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const toggleRelType = (type: string) => {
    setSelectedRelTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const allNodeTypes = graphData
    ? [...new Set(graphData.nodes.map((n) => n.type))]
    : [];
  const allRelTypes = graphData
    ? [...new Set(graphData.edges.map((e) => e.relation))]
      .sort((a, b) => {
        const ai = RELATION_ORDER.indexOf(a);
        const bi = RELATION_ORDER.indexOf(b);
        if (ai === -1 && bi === -1) return a.localeCompare(b, 'zh-CN');
        if (ai === -1) return 1;
        if (bi === -1) return -1;
        return ai - bi;
      })
    : [];
  const activeFilterCount = selectedNodeTypes.size + selectedRelTypes.size;

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="animate-spin text-zinc-400" size={32} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-4 text-zinc-400">
        <p>{error}</p>
        <Button variant="outline" size="sm" onClick={loadGraph}>重试</Button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="shrink-0 px-4 py-3 border-b border-white/[0.06] flex items-center gap-3">
        <div className="flex items-center gap-2 text-sm text-zinc-400">
          <span className="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300">{stats.nodes} 节点</span>
          <span className="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300">{stats.edges} 关系</span>
          <span className="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300">{stats.types} 类型</span>
          {subgraphCenter && (
            <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20">
              子图: {subgraphCenter}
            </span>
          )}
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
            <Input
              type="text"
              placeholder="搜索实体..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              className="pl-9 h-8 w-48 text-sm"
            />
          </div>
          <Button variant="outline" size="sm" onClick={() => setShowFilters(!showFilters)}>
            <Filter size={14} />
            {activeFilterCount > 0 && <span>{activeFilterCount}</span>}
          </Button>
          <Button variant="outline" size="sm" onClick={handleReset}>
            <RotateCcw size={14} />
          </Button>
        </div>
      </div>

      {showFilters && (
        <div className="shrink-0 border-b border-white/[0.06] bg-zinc-950/70 px-4 py-3">
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <div className="mb-2 text-xs font-medium text-zinc-500">实体类型筛选</div>
              <div className="flex flex-wrap gap-2">
                {allNodeTypes.map((type) => {
                  const selected = selectedNodeTypes.has(type);
                  return (
                    <button
                      key={type}
                      type="button"
                      onClick={() => toggleNodeType(type)}
                      className={`inline-flex h-8 items-center gap-2 rounded-lg border px-2.5 text-xs transition-colors ${
                        selected
                          ? 'border-white/[0.18] bg-zinc-800 text-zinc-100'
                          : 'border-white/[0.08] bg-zinc-900/70 text-zinc-400 hover:bg-zinc-800/70 hover:text-zinc-200'
                      }`}
                    >
                      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: getNodeColor(type) }} />
                      <span>{type}</span>
                      <span className="text-zinc-500">{nodeTypeCounts[type] || 0}</span>
                      {selected && <Check size={12} className="text-emerald-400" />}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <div className="mb-2 text-xs font-medium text-zinc-500">关系类型筛选</div>
              <div className="flex flex-wrap gap-2">
                {allRelTypes.map((type) => {
                  const selected = selectedRelTypes.has(type);
                  return (
                    <button
                      key={type}
                      type="button"
                      onClick={() => toggleRelType(type)}
                      className={`inline-flex h-8 items-center gap-2 rounded-lg border px-2.5 text-xs transition-colors ${
                        selected
                          ? 'border-amber-400/40 bg-amber-400/10 text-amber-200'
                          : 'border-white/[0.08] bg-zinc-900/70 text-zinc-400 hover:bg-zinc-800/70 hover:text-zinc-200'
                      }`}
                    >
                      <span>{type}</span>
                      <span className="text-zinc-500">{relationTypeCounts[type] || 0}</span>
                      {selected && <Check size={12} className="text-amber-300" />}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Graph + Detail panel */}
      <div className="flex-1 relative overflow-hidden">
        <div ref={containerRef} className="w-full h-full" />

        {filteredData.nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="rounded-lg border border-white/[0.08] bg-zinc-900/90 px-4 py-3 text-sm text-zinc-400">
              当前筛选条件下没有可展示的关系
            </div>
          </div>
        )}

        {/* Node detail panel — absolute overlay */}
        {selectedNode && (
          <div className="absolute top-0 right-0 h-full w-80 z-50 border-l border-white/[0.06] bg-zinc-900/95 overflow-y-auto shadow-xl">
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06]">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: getNodeColor(selectedNode.type) }} />
                <span className="text-sm font-medium text-zinc-200 truncate max-w-[200px]">{selectedNode.id}</span>
              </div>
              <button onClick={() => setSelectedNode(null)} className="text-zinc-500 hover:text-zinc-300">
                <X size={16} />
              </button>
            </div>
            <div className="px-4 py-3 space-y-3">
              <div className="flex gap-4 text-xs text-zinc-400">
                <span>类型: <span className="text-zinc-200">{selectedNode.type}</span></span>
                <span>频次: <span className="text-zinc-200">{selectedNode.freq}</span></span>
              </div>
              <Button
                variant="secondary"
                size="sm"
                className="w-full"
                onClick={() => handleExpandSubgraph(selectedNode.id)}
                disabled={subgraphLoadingNode === selectedNode.id}
              >
                {subgraphLoadingNode === selectedNode.id ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Network size={14} />
                )}
                展开 2 跳子图
              </Button>
              {selectedNode.sources && selectedNode.sources.length > 0 ? (
                <div className="space-y-2">
                  <div className="text-xs text-zinc-500 font-medium">来源文档</div>
                  {selectedNode.sources.map((src, i) => (
                    <div key={i} className="rounded border border-white/[0.06] bg-zinc-800/50 p-3">
                      <div className="flex items-center gap-1.5 mb-2">
                        <FileText size={12} className="text-zinc-500" />
                        <span className="text-xs text-zinc-300 truncate">{src.file}</span>
                      </div>
                      <p className="text-xs text-zinc-400 leading-relaxed line-clamp-6">{src.content}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-zinc-500">暂无来源信息</p>
              )}
            </div>
          </div>
        )}

        {/* Legend */}
        <div className="absolute bottom-4 left-4 bg-zinc-900/90 border border-white/[0.08] rounded-lg p-3 text-xs">
          <div className="text-zinc-400 mb-2 font-medium">图例</div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            {Object.entries(NODE_TYPE_COLORS).map(([type, color]) => (
              <div key={type} className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                <span className="text-zinc-300">{type}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
