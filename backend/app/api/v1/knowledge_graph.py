"""
Knowledge Graph API routes.
Serves pre-extracted entity-relation triples for visualization.
"""
import json
import os
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.dependencies import get_current_user
from app.config import settings

router = APIRouter(prefix="/knowledge-graph", tags=["Knowledge Graph"])

_kg_cache: Dict[str, Any] = {"data": None, "mtime": 0.0}

KG_DATA_DIR = Path(settings.SHARED_STORAGE_ROOT) / "knowledge_graph"


def _get_kg_path() -> Path:
    main_path = KG_DATA_DIR / f"{settings.COLLECTION_NAME}_kg_main.json"
    if main_path.exists():
        return main_path
    return KG_DATA_DIR / f"{settings.COLLECTION_NAME}_kg.json"


def _load_graph() -> Dict[str, Any]:
    kg_path = _get_kg_path()
    if not kg_path.exists():
        return {"meta": {}, "nodes": [], "edges": []}

    mtime = os.path.getmtime(kg_path)
    if _kg_cache["data"] is not None and _kg_cache["mtime"] == mtime:
        return _kg_cache["data"]

    data = json.loads(kg_path.read_text(encoding="utf-8"))
    _kg_cache["data"] = data
    _kg_cache["mtime"] = mtime
    return data


def _bfs_subgraph(graph: Dict[str, Any], start_node: str, depth: int) -> Dict[str, Any]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    node_map = {n["id"]: n for n in nodes}
    if start_node not in node_map:
        return {"nodes": [], "edges": []}

    adj: Dict[str, List[Dict[str, Any]]] = {}
    for edge in edges:
        adj.setdefault(edge["source"], []).append(edge)
        adj.setdefault(edge["target"], []).append(edge)

    visited: set = set()
    queue = deque([(start_node, 0)])
    visited.add(start_node)

    while queue:
        current, d = queue.popleft()
        if d >= depth:
            continue
        for edge in adj.get(current, []):
            neighbor = edge["target"] if edge["source"] == current else edge["source"]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, d + 1))

    sub_nodes = [node_map[nid] for nid in visited if nid in node_map]
    sub_edges = [
        e for e in edges
        if e["source"] in visited and e["target"] in visited
    ]
    return {"nodes": sub_nodes, "edges": sub_edges}


@router.get("")
async def get_knowledge_graph(
    current_user: dict = Depends(get_current_user),
):
    """Return the full knowledge graph JSON."""
    graph = _load_graph()
    if not graph.get("nodes"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge graph data not found. Run the extraction script first.",
        )
    return graph


@router.get("/stats")
async def get_knowledge_graph_stats(
    current_user: dict = Depends(get_current_user),
):
    """Return node/edge statistics."""
    graph = _load_graph()
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    node_types: Dict[str, int] = {}
    for n in nodes:
        t = n.get("type", "unknown")
        node_types[t] = node_types.get(t, 0) + 1

    relation_types: Dict[str, int] = {}
    for e in edges:
        r = e.get("relation", "unknown")
        relation_types[r] = relation_types.get(r, 0) + 1

    return {
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "node_types": node_types,
        "relation_types": relation_types,
        "meta": graph.get("meta", {}),
    }


@router.get("/preview")
async def get_knowledge_graph_preview(
    current_user: dict = Depends(get_current_user),
):
    """Return the pre-rendered knowledge graph image."""
    img_path = KG_DATA_DIR / "kg_preview.png"
    if not img_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preview image not found. Run kg_layout.py first.",
        )
    return FileResponse(img_path, media_type="image/png")


@router.get("/subgraph")
async def get_subgraph(
    node: str = Query(..., description="Center node ID"),
    depth: int = Query(2, ge=1, le=5, description="BFS depth"),
    current_user: dict = Depends(get_current_user),
):
    """Return a subgraph centered on the given node within N hops."""
    graph = _load_graph()
    if not graph.get("nodes"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge graph data not found.",
        )
    subgraph = _bfs_subgraph(graph, node, depth)
    if not subgraph["nodes"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node}' not found in graph.",
        )
    return subgraph
