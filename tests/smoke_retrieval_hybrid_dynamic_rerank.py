# tests/smoke_retrieval_hybrid_dynamic_rerank.py
import os
import sys
import time
import re
from pathlib import Path

# -----------------------------
# 0) 解决导入路径问题：确保项目根目录在 sys.path
# -----------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# -----------------------------
# 1) 只从具体模块导入，避免 tools/__init__.py 可能的副作用
# -----------------------------
from tools.qdrant import QdrantDB, QdrantDB_Init, save2Qdrant_Input
from backend.app.core.model_runtime import backend_reranker_model


def count_results_in_tool_output(s: str) -> int:
    """
    如果你未来改成用 DatabaseToolkit.search_database 输出，可以用这个数结果条数；
    目前这个 smoke 不依赖 DatabaseToolkit，但保留这个 helper 也不影响。
    """
    if not s:
        return 0
    return len(re.findall(r"^File:\s", s, flags=re.M))


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
    print("\n==============================")
    print("SMOKE: keyword + hybrid + dynamic topk + optional rerank")
    print("==============================\n")

    # 1) 创建临时 collection（不会污染你的 database collection）
    collection = f"smoke_hybrid_{int(time.time())}"
    print("==> collection:", collection)

    q = QdrantDB(QdrantDB_Init(collection_name=collection))

    try:
        # 2) 写入可控文本（不依赖 MinerU，不依赖 PDF）
        docs = [
            "国网经济技术研究院（经研院）主要从事电力系统规划、技术研究与咨询等工作。",
            "变压器能效限定值及能效等级相关要求：本文件给出效率指标与测试方法。",
            "标准编号 SGCC-STD-001 给出了接口规范与字段说明，适用于系统对接。",
            "220kV 与 500kV 是常见电压等级，电压等级的选取与工程规模有关。",
            "这是一个无关文本，用于测试低相关召回时的阈值行为。",
        ]
        q.save2Qdrant(save2Qdrant_Input(text=docs, origin_file="smoke_doc", meta_data={"tag": "smoke"}))
        print("==> inserted docs:", len(docs))

        # 3) keyword_search 验证：用明显关键词/编号，必须命中
        kw_query_1 = "经济技术研究院"
        kw_hits_1 = q.keyword_search(kw_query_1, top_k=5)
        print("\n[keyword_search] query:", kw_query_1)
        print("hits:", len(kw_hits_1))
        must(len(kw_hits_1) > 0, "keyword_search should return hits for query_1")
        top_content = (kw_hits_1[0].get("payload", {}) or {}).get("Content", "")
        must(("经济技术研究院" in top_content) or ("经研院" in top_content),
             "keyword_search top hit should mention 经济技术研究院/经研院")

        kw_query_2 = "SGCC-STD-001"
        kw_hits_2 = q.keyword_search(kw_query_2, top_k=5)
        print("\n[keyword_search] query:", kw_query_2)
        print("hits:", len(kw_hits_2))
        must(len(kw_hits_2) > 0, "keyword_search should return hits for query_2")
        top_content2 = (kw_hits_2[0].get("payload", {}) or {}).get("Content", "")
        must("SGCC-STD-001" in top_content2, "keyword_search top hit should contain SGCC-STD-001")

        # 4) hybrid_search 结构验证：必须包含 vector_score/keyword_score/score(0~1)
        hy_query = "电压等级 怎么选"
        hy_hits = q.hybrid_search(
            query=hy_query,
            top_k=3,
            alpha=0.75,
            dynamic_topk=False,   # 固定返回 top_k
        )
        print("\n[hybrid_search] query:", hy_query)
        print("hits:", len(hy_hits))
        must(len(hy_hits) == 3, "hybrid_search dynamic_topk=False should return exactly top_k hits")

        for i, h in enumerate(hy_hits[:3], 1):
            must("score" in h, f"hybrid hit#{i} missing score")
            must("vector_score" in h, f"hybrid hit#{i} missing vector_score")
            must("keyword_score" in h, f"hybrid hit#{i} missing keyword_score")
            must(0.0 <= float(h["score"]) <= 1.0, f"hybrid hit#{i} score should be normalized to 0~1")

        # 5) dynamic_topk / threshold 验证：阈值很高时也必须 >= top_k（因为有 min_results 兜底）
        dyn_hits = q.hybrid_search(
            query=hy_query,
            top_k=3,
            alpha=0.75,
            dynamic_topk=True,
            score_threshold=0.95,   # 故意设高
            max_results=20,
        )
        print("\n[hybrid_search dynamic] threshold=0.95")
        print("hits:", len(dyn_hits))
        must(len(dyn_hits) >= 3, "dynamic_topk should keep at least top_k results")
        must(len(dyn_hits) <= 20, "dynamic_topk should not exceed max_results")

        # 6) rerank（可选）：如果你配置了 reranker_path，就验证 CrossEncoder 真的能 rerank
        reranker_path = os.getenv("reranker_path")
        print("\n[rerank] reranker_path:", reranker_path)

        if reranker_path:
            reranker = backend_reranker_model()
            must(reranker is not None, "reranker_path is set but backend_reranker_model() returned None")

            # 用 keyword query 的候选做 rerank 更直观
            base_hits = q.hybrid_search(query=kw_query_2, top_k=5, dynamic_topk=False)

            pairs = []
            valid_idx = []
            for idx, h in enumerate(base_hits):
                payload = h.get("payload", {}) or {}
                content = payload.get("Content") or payload.get("content") or ""
                if isinstance(content, str) and content.strip():
                    pairs.append((kw_query_2, content.strip()))
                    valid_idx.append(idx)

            must(len(pairs) > 0, "No valid (query, passage) pairs for rerank")

            scores = [float(s) for s in list(reranker.predict(pairs))]
            norm_scores = minmax_norm(scores)

            for i, (hit_idx, s_raw, s_norm) in enumerate(zip(valid_idx, scores, norm_scores)):
                base_hits[hit_idx]["rerank_score_raw"] = s_raw
                base_hits[hit_idx]["score"] = float(s_norm)

            reranker_enabled = any("rerank_score_raw" in h for h in base_hits)
            print("[rerank] enabled?:", reranker_enabled)
            must(reranker_enabled, "rerank should add rerank_score_raw to hits")

            # rerank 后重新排序看 top1 是否更合理（至少应包含 SGCC-STD-001 的那条）
            base_hits_sorted = sorted(base_hits, key=lambda x: float(x.get("score", 0.0)), reverse=True)
            top1_text = (base_hits_sorted[0].get("payload", {}) or {}).get("Content", "")
            must("SGCC-STD-001" in top1_text, "After rerank, top1 should strongly match SGCC-STD-001 passage")
            print("[rerank] top1 contains SGCC-STD-001 ✅")

        else:
            print("[rerank] reranker_path not set, skip rerank asserts.")

        print("\n✅ PASS: keyword / hybrid / dynamic topk / rerank(optional) all ok.")

    finally:
        try:
            q.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
