#!/usr/bin/env python
"""
E2E Smoke Test：真实 PDF 入库 + Hybrid 检索 + Rerank 验证

完整端到端流程：
  1. 将指定 PDF 复制到 data/stored_files/ 并入库
  2. 用 MinerU 解析 PDF 提取锚点文本
  3. 对每个锚点执行 hybrid_search 断言命中
  4. 可选：若配置了 reranker_path，验证 rerank 后 top1 更准确

使用独立临时 collection，不污染 database collection。

用法:
    python scripts/smoke_e2e_pdf_hybrid_rerank.py <pdf1> <pdf2> ...
"""
import os
import sys
import time
import re
import shutil
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.load_files import load_multiple_files
from tools.mineru_toolkit import MineruComponent
from tools.qdrant import QdrantDB, QdrantDB_Init
from backend.app.core.model_runtime import backend_reranker_model


def must(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


def norm_text(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def first_n_chars(s: str, n: int = 40) -> str:
    return (s or "").strip()[:n]


def extract_anchors(mineru_data: List[dict], max_items: int = 3) -> List[str]:
    keys_priority = ["text", "title", "equation", "table_caption",
                     "image_caption", "table_body", "content"]
    anchors: List[str] = []
    seen = set()
    for item in mineru_data:
        if not isinstance(item, dict):
            continue
        for k in keys_priority:
            v = item.get(k)
            if v is None:
                continue
            s = " ".join(str(x) for x in v) if isinstance(v, list) else str(v)
            s = " ".join(s.split()).strip()
            if len(s) < 15:
                continue
            s = s[:80]
            if s not in seen:
                seen.add(s)
                anchors.append(s)
                break
        if len(anchors) >= max_items:
            break
    return anchors


def copy_to_stored_files(pdf_paths: List[str]) -> List[str]:
    stored_dir = PROJECT_ROOT / "data" / "stored_files"
    stored_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for p in pdf_paths:
        src = Path(p).resolve()
        must(src.exists(), f"PDF 不存在: {src}")
        dst = stored_dir / src.name
        if src != dst:
            shutil.copy2(src, dst)
        saved.append(str(dst))
    return saved


def run_hybrid_assert(qdb: QdrantDB, query: str, expect_any: List[str], top_k: int = 5):
    hits = qdb.hybrid_search(
        query=query, top_k=top_k, alpha=0.75,
        dynamic_topk=True, score_threshold=0.30, max_results=20,
    )
    must(len(hits) >= top_k, f"hybrid_search 应返回 >= top_k 条，实际 {len(hits)}")

    big = "\n".join(str((h.get("payload") or {}).get("Content", "")) for h in hits)
    big_n = norm_text(big)

    ok = any(norm_text(x) in big_n for x in expect_any if x)
    if not ok:
        print(f"\nFAIL query={query!r}")
        print(f"  expect_any (前3): {expect_any[:3]}")
        print(f"  retrieved head: {big[:600]}")
        raise AssertionError("hybrid 检索断言失败")
    print(f"  hybrid PASS: {query!r}")


def run_rerank_assert(qdb: QdrantDB, query: str, top1_should_contain: str):
    reranker_path = os.getenv("reranker_path")
    if not reranker_path:
        return

    reranker = backend_reranker_model()
    must(reranker is not None, "reranker_path 已设置但模型加载失败")

    base_hits = qdb.hybrid_search(query=query, top_k=10, alpha=0.75, dynamic_topk=False)
    pairs, valid_hits = [], []
    for h in base_hits:
        content = ((h.get("payload") or {}).get("Content") or "").strip()
        if content:
            pairs.append((query, content))
            valid_hits.append(h)

    must(len(pairs) > 0, "无有效 pair 可供 rerank")
    scores = [float(s) for s in reranker.predict(pairs)]
    vmin, vmax = min(scores), max(scores)
    norm_scores = [(s - vmin) / (vmax - vmin + 1e-9) for s in scores] if vmax > vmin else [1.0] * len(scores)

    for h, s in zip(valid_hits, norm_scores):
        h["score"] = s
    valid_hits.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)

    top1 = (valid_hits[0].get("payload") or {}).get("Content", "")
    must(
        norm_text(top1_should_contain) in norm_text(top1),
        f"rerank top1 应包含: {top1_should_contain}\n实际 top1 head: {top1[:200]}"
    )
    print(f"  rerank PASS: {query!r}")


def main():
    pdf_paths = sys.argv[1:]
    if not pdf_paths:
        print("用法: python scripts/smoke_e2e_pdf_hybrid_rerank.py <pdf1> <pdf2> ...")
        sys.exit(2)

    print("\n" + "=" * 60)
    print("E2E SMOKE: 真实 PDF 入库 + hybrid + rerank")
    print("=" * 60)

    stored_pdf_paths = copy_to_stored_files(pdf_paths)
    print(f"==> PDF 已复制到 data/stored_files/")

    collection = f"e2e_real_{int(time.time())}"
    print(f"==> collection: {collection}")

    ingest_res = load_multiple_files(
        file_paths=stored_pdf_paths, collection_name=collection, dpi=200,
    )
    print(f"==> 入库结果: {ingest_res}")
    must(len(ingest_res.get("success", [])) > 0, "没有 PDF 入库成功")

    mineru = MineruComponent()
    qdb = QdrantDB(QdrantDB_Init(collection_name=collection))

    try:
        for p in stored_pdf_paths:
            name = Path(p).name
            print(f"\n--- {name} ---")

            out = mineru.run(pdf_file_path=str(Path(p).resolve()))
            if getattr(out, "status", None) != "success" or not getattr(out, "data", None):
                print(f"  MinerU 失败，跳过: {getattr(out, 'error', None)}")
                continue

            anchors = extract_anchors(out.data, max_items=3)
            print(f"  锚点: {anchors}")

            for a in anchors:
                q = first_n_chars(a, 40)
                run_hybrid_assert(qdb, q, expect_any=[a], top_k=5)
                run_rerank_assert(qdb, q, top1_should_contain=a[:20])

        print("\nALL DONE: E2E smoke 全部通过")
    finally:
        try:
            qdb.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
