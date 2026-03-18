#!/usr/bin/env python
"""
Hybrid 检索接口 Smoke Test

使用可控文本（不依赖 PDF / MinerU）验证以下接口的正确性：
  - keyword_search：关键词检索
  - hybrid_search：混合检索，验证 score/vector_score/keyword_score 字段
  - dynamic_topk：动态阈值兜底
  - rerank（可选）：配置 reranker_path 后自动启用

写入临时 collection，测试结束后自动清理，不污染 database collection。

用法:
    python scripts/smoke_hybrid_retrieval.py
"""
import os
import sys
import time
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.qdrant import QdrantDB, QdrantDB_Init, save2Qdrant_Input
from backend.app.core.model_runtime import backend_reranker_model


def must(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


def minmax_norm(vals):
    if not vals:
        return []
    vmin, vmax = min(vals), max(vals)
    if vmax <= vmin:
        return [1.0] * len(vals)
    return [(v - vmin) / (vmax - vmin + 1e-9) for v in vals]


def main():
    print("\n" + "=" * 60)
    print("SMOKE: keyword / hybrid / dynamic topk / rerank")
    print("=" * 60 + "\n")

    collection = f"smoke_hybrid_{int(time.time())}"
    print(f"==> collection: {collection}")

    q = QdrantDB(QdrantDB_Init(collection_name=collection))

    try:
        # 写入可控文本
        docs = [
            "国网经济技术研究院（经研院）主要从事电力系统规划、技术研究与咨询等工作。",
            "变压器能效限定值及能效等级相关要求：本文件给出效率指标与测试方法。",
            "标准编号 SGCC-STD-001 给出了接口规范与字段说明，适用于系统对接。",
            "220kV 与 500kV 是常见电压等级，电压等级的选取与工程规模有关。",
            "这是一个无关文本，用于测试低相关召回时的阈值行为。",
        ]
        q.save2Qdrant(save2Qdrant_Input(text=docs, origin_file="smoke_doc", meta_data={"tag": "smoke"}))
        print(f"==> 写入文档: {len(docs)} 条")

        # keyword_search 验证
        for kw, expect in [
            ("经济技术研究院", ["经济技术研究院", "经研院"]),
            ("SGCC-STD-001", ["SGCC-STD-001"]),
        ]:
            hits = q.keyword_search(kw, top_k=5)
            print(f"\n[keyword_search] query={kw!r} hits={len(hits)}")
            must(len(hits) > 0, f"keyword_search 应有结果: {kw}")
            top_content = (hits[0].get("payload", {}) or {}).get("Content", "")
            must(any(e in top_content for e in expect), f"top hit 应包含 {expect}")
            print(f"  top hit (前80字符): {top_content[:80]}")
        print("\n[keyword_search] PASS")

        # hybrid_search 结构验证
        hy_query = "电压等级 怎么选"
        hy_hits = q.hybrid_search(query=hy_query, top_k=3, alpha=0.75, dynamic_topk=False)
        print(f"\n[hybrid_search] query={hy_query!r} hits={len(hy_hits)}")
        must(len(hy_hits) == 3, "dynamic_topk=False 应精确返回 top_k 条")
        for i, h in enumerate(hy_hits, 1):
            must("score" in h, f"hit#{i} 缺少 score")
            must("vector_score" in h, f"hit#{i} 缺少 vector_score")
            must("keyword_score" in h, f"hit#{i} 缺少 keyword_score")
            must(0.0 <= float(h["score"]) <= 1.0, f"hit#{i} score 应归一化到 0~1")
        print("[hybrid_search] PASS")

        # dynamic_topk 验证：高阈值下应有 min_results 兜底
        dyn_hits = q.hybrid_search(
            query=hy_query, top_k=3, alpha=0.75,
            dynamic_topk=True, score_threshold=0.95, max_results=20,
        )
        print(f"\n[dynamic_topk] threshold=0.95 hits={len(dyn_hits)}")
        must(len(dyn_hits) >= 3, "dynamic_topk 应保证至少 top_k 条")
        must(len(dyn_hits) <= 20, "dynamic_topk 不应超过 max_results")
        print("[dynamic_topk] PASS")

        # rerank（可选）
        reranker_path = os.getenv("reranker_path")
        print(f"\n[rerank] reranker_path={reranker_path}")
        if reranker_path:
            reranker = backend_reranker_model()
            must(reranker is not None, "reranker_path 已设置但模型加载失败")

            base_hits = q.hybrid_search(query="SGCC-STD-001", top_k=5, dynamic_topk=False)
            pairs, valid_idx = [], []
            for idx, h in enumerate(base_hits):
                content = ((h.get("payload") or {}).get("Content") or "").strip()
                if content:
                    pairs.append(("SGCC-STD-001", content))
                    valid_idx.append(idx)

            must(len(pairs) > 0, "无有效 (query, passage) 对可供 rerank")
            scores = [float(s) for s in reranker.predict(pairs)]
            norm_scores = minmax_norm(scores)
            for hit_idx, s_norm in zip(valid_idx, norm_scores):
                base_hits[hit_idx]["score"] = s_norm

            sorted_hits = sorted(base_hits, key=lambda x: float(x.get("score", 0.0)), reverse=True)
            top1 = (sorted_hits[0].get("payload") or {}).get("Content", "")
            must("SGCC-STD-001" in top1, "rerank 后 top1 应匹配 SGCC-STD-001 文档")
            print("[rerank] PASS")
        else:
            print("[rerank] reranker_path 未设置，跳过 rerank 断言")

        print("\nPASS: 所有检索接口验证通过")

    finally:
        try:
            q.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
