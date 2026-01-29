import os
import sys
import time
import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

# 保证能 import 项目
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from tools.database_toolkit import DatabaseToolkit


@dataclass
class EvalCase:
    name: str
    query: str
    anchors: List[str]  # 任一 anchor 命中即可


def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_hits_from_toolkit_output(text: str) -> List[Dict[str, Any]]:
    """
    DatabaseToolkit.search_database() 返回的是拼好的字符串。
    这里把它解析成 list[{"file":..., "content":..., "confidence":...}]
    """
    if not text or "No results" in text:
        return []
    chunks = text.split("\n\n")
    hits = []
    cur = {}
    for blk in chunks:
        lines = blk.splitlines()
        file_ = ""
        conf = None
        content_lines = []
        mode = None
        for ln in lines:
            if ln.startswith("File:"):
                file_ = ln.replace("File:", "").strip()
            elif ln.startswith("Confidence:"):
                try:
                    conf = float(ln.replace("Confidence:", "").strip())
                except Exception:
                    conf = None
            elif ln.startswith("Content:"):
                mode = "content"
            elif mode == "content":
                # 跳过分隔线 ---
                if ln.strip() == "---":
                    continue
                content_lines.append(ln)
        hits.append({
            "file": file_,
            "content": "\n".join(content_lines).strip(),
            "confidence": conf,
        })
    return hits


def match_case(hits: List[Dict[str, Any]], anchors: List[str]) -> Tuple[bool, Optional[int]]:
    """
    返回 (是否命中, 命中排名从1开始)
    命中规则：topK 中任一 hit 的 content 包含任一 anchor（大小写/空白弱归一化）
    """
    anchors_n = [normalize(a) for a in anchors if a and a.strip()]
    for idx, h in enumerate(hits, start=1):
        c = normalize(h.get("content", ""))
        for a in anchors_n:
            if a in c:
                return True, idx
    return False, None


def run_strategy(toolkit: DatabaseToolkit, case: EvalCase, *, top_k: int,
                 use_hybrid: bool, use_rerank: bool, dynamic_topk: bool,
                 max_results: int, alpha: float, score_threshold: Optional[float]) -> Dict[str, Any]:
    t0 = time.time()
    out = toolkit.search_database(
        query=case.query,
        top_k=top_k,
        use_hybrid=use_hybrid,
        use_rerank=use_rerank,
        dynamic_topk=dynamic_topk,
        max_results=max_results,
        alpha=alpha,
        score_threshold=score_threshold,
    )
    dt = time.time() - t0
    hits = parse_hits_from_toolkit_output(out)
    ok, rank = match_case(hits[:top_k], case.anchors)
    return {
        "ok": ok,
        "rank": rank,
        "latency_sec": dt,
        "n_hits": len(hits),
        "top_content_head": (hits[0]["content"][:160] if hits else ""),
    }


def main():
    # 你可以在这里继续加 case（越贴近业务越好）
    cases = [
        EvalCase(
            name="电网运行规则-发布与施行",
            query="电网运行规则是什么时候发布施行的？",
            anchors=["2007 年 1 月 1日起施行", "国家电力监管委员会"],
        ),
        EvalCase(
            name="GB20052-标准标题",
            query="GB20052-2020 这个标准的名称是什么？",
            anchors=["电力变压器能效限定值及能效等级"],
        ),
        EvalCase(
            name="软著证书号",
            query="这个电子证书的证书号是什么？",
            anchors=["软著登字第16503502号"],
        ),
        EvalCase(
            name="英文论文-作者名（关键词场景）",
            query="Giuliano Andrea Pagani Marco Aiello 作者是谁？",
            anchors=["Giuliano", "Aiello", "Pagani"],  # 用 token 作为锚点，更稳
        ),
    ]

    # 评测策略：你这次优化点相关的对比组
    strategies = [
        ("vector_only", dict(use_hybrid=False, use_rerank=False, dynamic_topk=False)),
        ("hybrid", dict(use_hybrid=True, use_rerank=False, dynamic_topk=False)),
        ("hybrid_dynamic", dict(use_hybrid=True, use_rerank=False, dynamic_topk=True)),
        ("hybrid_rerank_dynamic", dict(use_hybrid=True, use_rerank=True, dynamic_topk=True)),
    ]

    # 一些默认参数（你可以按需要调整）
    top_k = int(os.getenv("EVAL_TOP_K", "10"))
    max_results = int(os.getenv("EVAL_MAX_RESULTS", "50"))
    alpha = float(os.getenv("EVAL_ALPHA", "0.75"))
    score_threshold = os.getenv("EVAL_SCORE_THRESHOLD")
    score_threshold = float(score_threshold) if score_threshold else None

    with DatabaseToolkit() as toolkit:
        print(f"Eval top_k={top_k}, max_results={max_results}, alpha={alpha}, score_threshold={score_threshold}")
        print("-" * 80)

        # 汇总统计
        summary = {name: {"hit": 0, "mrr": 0.0, "lat": 0.0} for name, _ in strategies}

        for case in cases:
            print(f"\nCASE: {case.name}")
            print(f"Q: {case.query}")
            for strat_name, strat_kwargs in strategies:
                r = run_strategy(
                    toolkit, case,
                    top_k=top_k,
                    max_results=max_results,
                    alpha=alpha,
                    score_threshold=score_threshold,
                    **strat_kwargs,
                )
                hit = 1 if r["ok"] else 0
                mrr = (1.0 / r["rank"]) if r["rank"] else 0.0
                summary[strat_name]["hit"] += hit
                summary[strat_name]["mrr"] += mrr
                summary[strat_name]["lat"] += r["latency_sec"]

                print(f"  - {strat_name:20s} | hit={hit} rank={r['rank']} "
                      f"hits_returned={r['n_hits']:<3d} latency={r['latency_sec']:.2f}s "
                      f"top1_head={r['top_content_head']!r}")

        # 输出总览
        print("\n" + "=" * 80)
        print("SUMMARY (higher is better for hit/MRR; lower is better for latency)")
        n = len(cases)
        for strat_name, agg in summary.items():
            hit_rate = agg["hit"] / n
            mrr_avg = agg["mrr"] / n
            lat_avg = agg["lat"] / n
            print(f"{strat_name:20s} | hit_rate={hit_rate:.2%}  mrr={mrr_avg:.3f}  avg_latency={lat_avg:.2f}s")

        print("=" * 80)
        print("Tip: You can add more EvalCase rows to cover your real business queries.")


if __name__ == "__main__":
    main()