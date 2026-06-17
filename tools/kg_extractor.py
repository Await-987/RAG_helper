"""
Knowledge Graph triple extraction script.

Reads chunks from Qdrant local storage, sends batches to LLM for
entity-relation extraction, deduplicates and normalizes results,
and outputs a JSON file for visualization.

Usage (run locally on host, containers stopped):
    python tools/kg_extractor.py --collection database --batch-size 5 --max-chunks 500
"""
import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv()

from loguru import logger


EXTRACTION_PROMPT = """你是一个电力工程知识图谱构建专家。请从以下电网设计规范文本中抽取实体和关系三元组。

实体类型：设备、规范标准、参数指标、设计要求、工程场景、材料
关系类型：适用于、要求满足、参数值为、引用规范、包含、连接、属于

请严格按以下 JSON 格式输出，不要输出任何其他内容：
{
  "triples": [
    {"head": "实体1", "head_type": "类型", "relation": "关系", "tail": "实体2", "tail_type": "类型"}
  ]
}

文本内容：
"""


def scroll_chunks_local(collection_name: str, qdrant_url: str, limit: int) -> List[Dict[str, Any]]:
    """
    Read payloads from Qdrant via HTTP API (containers must be running).
    """
    from qdrant_client import QdrantClient

    client = QdrantClient(url=qdrant_url)
    results: List[Dict[str, Any]] = []
    offset = None

    while True:
        points, next_offset = client.scroll(
            collection_name=collection_name,
            with_payload=True,
            with_vectors=False,
            limit=256,
            offset=offset,
        )
        for p in points or []:
            payload = getattr(p, "payload", {}) or {}
            results.append(payload)

        if not next_offset or (limit and len(results) >= limit):
            break
        offset = next_offset

    client.close()
    return results[:limit] if limit else results


def normalize_entity(name: str) -> str:
    """Normalize entity name for deduplication."""
    text = unicodedata.normalize("NFKC", (name or "").strip())
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"设备$", "", text)
    text = re.sub(r"装置$", "", text) if len(text) > 4 else text
    return text


def extract_triples_from_response(response_text: str) -> List[Dict[str, str]]:
    """Parse LLM response to extract triples."""
    json_match = re.search(r"\{[\s\S]*\}", response_text)
    if not json_match:
        return []
    try:
        data = json.loads(json_match.group())
        triples = data.get("triples", [])
        valid = []
        for t in triples:
            if all(k in t for k in ("head", "head_type", "relation", "tail", "tail_type")):
                if t["head"].strip() and t["tail"].strip():
                    valid.append(t)
        return valid
    except (json.JSONDecodeError, TypeError):
        return []


def call_llm(text: str, model_name: Optional[str] = None) -> str:
    """Call LLM to extract triples from text chunk using OpenAI client directly."""
    from backend.app.config import settings
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_API_URL,
    )
    prompt = EXTRACTION_PROMPT + text
    response = client.chat.completions.create(
        model=model_name or settings.MODEL_NAME,
        messages=[
            {"role": "system", "content": "你是知识图谱抽取专家。只输出JSON，不要输出其他内容。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=32768,
    )
    content = response.choices[0].message.content or ""
    logger.debug(f"LLM response (len={len(content)}): {content[:200]}")
    return content


def build_graph(
    all_triples: List[Dict[str, str]],
    collection_name: str,
    total_chunks: int,
) -> Dict[str, Any]:
    """Build the final graph JSON from collected triples."""
    edge_counter: Dict[Tuple[str, str, str], int] = {}
    node_info: Dict[str, Dict[str, Any]] = {}

    for t in all_triples:
        head = normalize_entity(t["head"])
        tail = normalize_entity(t["tail"])
        relation = t["relation"].strip()
        head_type = t["head_type"].strip()
        tail_type = t["tail_type"].strip()
        source_file = t.get("source_file", "")
        source_content = t.get("source_content", "")

        if not head or not tail or not relation:
            continue

        edge_key = (head, relation, tail)
        edge_counter[edge_key] = edge_counter.get(edge_key, 0) + 1

        for entity, etype in [(head, head_type), (tail, tail_type)]:
            if entity not in node_info:
                node_info[entity] = {"type": etype, "freq": 0, "sources": []}
            node_info[entity]["freq"] += 1
            if source_file and len(node_info[entity]["sources"]) < 15:
                src = {"file": source_file, "content": source_content[:200]}
                if src not in node_info[entity]["sources"]:
                    node_info[entity]["sources"].append(src)

    nodes = [
        {"id": nid, "type": info["type"], "freq": info["freq"], "sources": info["sources"]}
        for nid, info in sorted(node_info.items(), key=lambda x: -x[1]["freq"])
    ]
    edges = [
        {"source": src, "target": tgt, "relation": rel, "weight": cnt}
        for (src, rel, tgt), cnt in sorted(edge_counter.items(), key=lambda x: -x[1])
    ]

    return {
        "meta": {
            "collection": collection_name,
            "extracted_at": datetime.now().isoformat(),
            "total_chunks_processed": total_chunks,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
        },
        "nodes": nodes,
        "edges": edges,
    }


def main():
    parser = argparse.ArgumentParser(description="Extract knowledge graph triples from Qdrant chunks")
    parser.add_argument("--collection", default="database", help="Qdrant collection name")
    parser.add_argument("--batch-size", type=int, default=5, help="Chunks per LLM call")
    parser.add_argument("--max-chunks", type=int, default=500, help="Max chunks to process")
    parser.add_argument("--qdrant-url", default="http://localhost:6333", help="Qdrant HTTP URL")
    parser.add_argument("--output", default="data/knowledge_graph/", help="Output directory")
    parser.add_argument("--model", default=None, help="LLM model name override")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{args.collection}_kg.json"

    logger.info(f"Connecting to Qdrant at {args.qdrant_url}, collection: {args.collection}")
    chunks = scroll_chunks_local(args.collection, args.qdrant_url, args.max_chunks)
    logger.info(f"Retrieved {len(chunks)} chunks")

    if not chunks:
        logger.warning("No chunks found. Exiting.")
        return

    seen_files: set = set()
    diverse_chunks: List[Dict[str, Any]] = []
    remaining: List[Dict[str, Any]] = []
    for payload in chunks:
        source = str(payload.get("Original_file", "")).strip()
        if source and source not in seen_files:
            seen_files.add(source)
            diverse_chunks.append(payload)
        else:
            remaining.append(payload)
    ordered_chunks = diverse_chunks + remaining
    ordered_chunks = ordered_chunks[:args.max_chunks]

    all_triples: List[Dict[str, str]] = []
    total_batches = (len(ordered_chunks) + args.batch_size - 1) // args.batch_size

    for batch_idx in range(total_batches):
        start = batch_idx * args.batch_size
        end = start + args.batch_size
        batch = ordered_chunks[start:end]

        batch_text_parts = []
        batch_sources = []
        for payload in batch:
            content = payload.get("Content", "") or payload.get("content", "")
            source = payload.get("Original_file", "")
            if content:
                batch_text_parts.append(f"[来源: {source}]\n{content}")
                batch_sources.append({"file": source, "content": content})

        if not batch_text_parts:
            continue

        batch_text = "\n\n---\n\n".join(batch_text_parts)
        if len(batch_text) > 8000:
            batch_text = batch_text[:8000]

        logger.info(f"Processing batch {batch_idx + 1}/{total_batches}...")
        try:
            response = call_llm(batch_text, model_name=args.model)
            triples = extract_triples_from_response(response)
            for t in triples:
                t["source_file"] = batch_sources[0]["file"] if batch_sources else ""
                t["source_content"] = batch_sources[0]["content"] if batch_sources else ""
            all_triples.extend(triples)
            logger.info(f"  Extracted {len(triples)} triples (total: {len(all_triples)})")
        except Exception as exc:
            logger.warning(f"  Batch {batch_idx + 1} failed: {exc}")
            continue

        if all_triples:
            graph = build_graph(all_triples, args.collection, end)
            output_file.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"  Saved: {graph['meta']['total_nodes']} nodes, {graph['meta']['total_edges']} edges")

    logger.info(f"Total raw triples: {len(all_triples)}")
    graph = build_graph(all_triples, args.collection, len(ordered_chunks))
    logger.info(f"Final graph: {graph['meta']['total_nodes']} nodes, {graph['meta']['total_edges']} edges")

    output_file.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Output saved to: {output_file}")


if __name__ == "__main__":
    main()
