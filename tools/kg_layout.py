"""Pre-compute force-directed layout for knowledge graph nodes."""
import json
import argparse
from pathlib import Path

import networkx as nx


def main():
    parser = argparse.ArgumentParser(description="Pre-compute KG layout positions")
    parser.add_argument("--input", default="data/knowledge_graph/database_kg.json")
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--scale", type=float, default=2000.0)
    args = parser.parse_args()

    path = Path(args.input)
    data = json.loads(path.read_text(encoding="utf-8"))

    nodes = data["nodes"]
    edges = data["edges"]

    G = nx.Graph()
    for n in nodes:
        G.add_node(n["id"])
    for e in edges:
        if G.has_node(e["source"]) and G.has_node(e["target"]):
            G.add_edge(e["source"], e["target"])

    print(f"Computing layout: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    pos = nx.spring_layout(G, k=None, iterations=args.iterations, scale=args.scale)

    pos_map = {nid: {"x": round(xy[0], 2), "y": round(xy[1], 2)} for nid, xy in pos.items()}

    for n in nodes:
        if n["id"] in pos_map:
            n["x"] = pos_map[n["id"]]["x"]
            n["y"] = pos_map[n["id"]]["y"]

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Done. Positions written to {path}")


if __name__ == "__main__":
    main()
