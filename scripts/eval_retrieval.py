#!/usr/bin/env python
"""
Retrieval strategy evaluation tool.

Compares vector_only / hybrid / hybrid_dynamic / hybrid_rerank_dynamic
and prints hit-rate, MRR, and average latency.

Usage:
    python scripts/eval_retrieval.py
    EVAL_TOP_K=10 EVAL_ALPHA=0.75 python scripts/eval_retrieval.py

Env vars:
    EVAL_TOP_K            top-k results (default 10)
    EVAL_MAX_RESULTS      candidate pool for dynamic topk (default 50)
    EVAL_ALPHA            vector weight in hybrid (default 0.75)
    EVAL_SCORE_THRESHOLD  score cutoff (default unset)
"""
import os
import sys
import time
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.database_toolkit import DatabaseToolkit


@dataclass
class EvalCase:
    name: str
    query: str
    anchors: List[str]


DEFAULT_CASES = [
    EvalCase(
        name="power-grid-rules-date",
        query="电网运行规则是什么时候发布施行的？",
        anchors=["2007 年 1 月 1日起施行", "国家电力监管委员会"],
    ),
    EvalCase(
        name="GB20052-title",
        query="GB20052-2020 这个标准的名称是什么？",
        anchors=["电力变压器能效限定値及能效等级"],
    ),
    EvalCase(
        name="software-cert-id",
        query="这个电子证书的证书号是什么？",
        anchors=["软著登字16503502号"],
    ),
    EvalCase(
        name="paper-authors",
        query="Giuliano Andrea Pagani Marco Aiello 作者是谁？",
        anchors=["Giuliano", "Aiello", "Pagani"],
    ),
]

STRATEGIES = [
    ("vector_only",           dict(use_hybrid=False, use_rerank=False, dynamic_topk=False)),
    ("hybrid",                dict(use_hybrid=True,  use_rerank=False, dynamic_topk=False)),
    ("hybrid_dynamic",        dict(use_hybrid=True,  use_rerank=False, dynamic_topk=True)),
    ("hybrid_rerank_dynamic", dict(use_hybrid=True,  use_rerank=True,  dynamic_topk=True)),
]


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def parse_hits(text: str) -> List[Dict[str, Any]]:
    if not text or "No results" in text:
        return []
    hits = []
    for blk in text.split("\n\n"):
        file_, conf, content_lines, mode = "", None, [], None
        for ln in blk.splitlines():
            if ln.startswith("File:"):
                file_ = ln.replace("File:", "").strip()
            elif ln.startswith("Confidence:"):
                try:
                    conf = float(ln.replace("Confidence:", "").strip())
                except Exception:
                    pass
            elif ln.startswith("Content:"):
                mode = "content"
            elif mode == "content" and ln.strip() != "---":
                content_lines.append(ln)
        hits.append({"file": file_, "content": "\n".join(content_lines).strip(), "confidence": conf})
    return hits


def match_case(hits: List[Dict], anchors: List[str]) -> Tuple[bool, Optional[int]]:
    anchors_n = [normalize(a) for a in anchors if a.strip()]
    for idx, h in enumerate(hits, start=1):
        c = normalize(h.get("content", ""))
        if any(a in c for a in anchors_n):
            return True, idx
    return False, None


def run_strategy(
    toolkit: DatabaseToolkit,
    case: EvalCase,
    top_k: int,
    max_results: int,
    alpha: float,
    score_threshold: Optional[float],
    **strategy_kwargs,
) -> Dict[str, Any]:
    t0 = time.time()
    out = toolkit.search_database(
        query=case.query,
        top_k=top_k,
        max_results=max_results,
        alpha=alpha,
        score_threshold=score_threshold,
        **strategy_kwargs,
    )
    dt = time.time() - t0
    hits = parse_hits(out)
    ok, rank = match_case(hits[:top_k], case.anchors)
    return {
        "ok": ok, "rank": rank, "latency_sec": dt,
        "n_hits": len(hits),
        "top_content_head": (hits[0]["content"][:160] if hits else ""),
    }


def main():
    top_k = int(os.getenv("EVAL_TOP_K", "10"))
    max_results = int(os.getenv("EVAL_MAX_RESULTS", "50"))
    alpha = float(os.getenv("EVAL_ALPHA", "0.75"))
    score_threshold_env = os.getenv("EVAL_SCORE_THRESHOLD")
    score_threshold = float(score_threshold_env) if score_threshold_env else None

    with DatabaseToolkit() as toolkit:
        print(f"top_k={top_k} max_results={max_results} alpha={alpha} score_threshold={score_threshold}")
        print("-" * 80)

        summary = {name: {"hit": 0, "mrr": 0.0, "lat": 0.0} for name, _ in STRATEGIES}

        for case in DEFAULT_CASES:
            print(f"\nCASE: {case.name}")
            print(f"Q: {case.query}")
            for strat_name, strat_kwargs in STRATEGIES:
                r = run_strategy(
                    toolkit, case,
                    top_k=top_k, max_results=max_results,
                    alpha=alpha, score_threshold=score_threshold,
                    **strat_kwargs,
                )
                hit = 1 if r["ok"] else 0
                mrr = (1.0 / r["rank"]) if r["rank"] else 0.0
                summary[strat_name]["hit"] += hit
                summary[strat_name]["mrr"] += mrr
                summary[strat_name]["lat"] += r["latency_sec"]
                print(
                    f"  {strat_name:25s} | hit={hit} rank={r['rank']} "
                    f"n_hits={r['n_hits']:<3d} latency={r['latency_sec']:.2f}s"
                )

        n = len(DEFAULT_CASES)
        print("\n" + "=" * 80)
        print(f"{'strategy':25s} | {'hit_rate':>10} {'mrr':>8} {'avg_lat':>10}")
        print("-" * 60)
        for strat_name, agg in summary.items():
            print(
                f"{strat_name:25s} | "
                f"{agg['hit'] / n:>10.2%} "
                f"{agg['mrr'] / n:>8.3f} "
                f"{agg['lat'] / n:>10.2f}s"
            )
        print("=" * 80)
        print("Tip: add more EvalCase rows in DEFAULT_CASES for your real business queries.")


if __name__ == "__main__":
    main()
