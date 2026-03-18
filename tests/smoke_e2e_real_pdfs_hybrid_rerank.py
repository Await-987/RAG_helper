import os
import sys
import time
import re
import shutil
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
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
    s = (s or "").strip()
    return s[:n]


def extract_anchors_from_mineru(mineru_data: List[dict], max_items: int = 3) -> List[str]:
    keys_priority = ["text", "title", "equation", "table_caption", "image_caption", "table_body", "content"]
    anchors: List[str] = []
    seen = set()

    for item in mineru_data:
        if not isinstance(item, dict):
            continue
        for k in keys_priority:
            v = item.get(k)
            if v is None:
                continue
            if isinstance(v, list):
                s = " ".join([str(x) for x in v if x is not None])
            else:
                s = str(v)
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


def ensure_in_stored_files(pdf_paths: List[str]) -> List[str]:
    stored_dir = PROJECT_ROOT / "data" / "stored_files"
    stored_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    for p in pdf_paths:
        src = Path(p).resolve()
        must(src.exists(), f"PDF not found: {src}")
        dst = stored_dir / src.name
        if src != dst:
            shutil.copy2(src, dst)
        saved_paths.append(str(dst))
    return saved_paths


def run_hybrid_assert(qdb: QdrantDB, query: str, expect_contains_any: List[str], top_k: int = 5):
    hits = qdb.hybrid_search(
        query=query,
        top_k=top_k,
        alpha=0.75,
        dynamic_topk=True,
        score_threshold=0.30,
        max_results=20,
    )
    must(len(hits) >= top_k, f"hybrid_search should return >= top_k results, got {len(hits)}")

    big = "\n".join([str((h.get("payload") or {}).get("Content", "")) for h in hits])
    big_n = norm_text(big)

    ok = False
    for x in expect_contains_any:
        x2 = norm_text(x)
        if x2 and x2 in big_n:
            ok = True
            break

    if not ok:
        print("\n❌ RETRIEVE FAIL")
        print("Query:", query)
        print("Expect contains any of (showing up to 3):", expect_contains_any[:3])
        print("Retrieved head:", big[:800])
        raise AssertionError("retrieval assert failed")

    print("✅ hybrid hit ok:", query)


def rerank_top1_should_contain(qdb: QdrantDB, query: str, top1_should_contain: str):
    reranker_path = os.getenv("reranker_path")
    if not reranker_path:
        print("[rerank] reranker_path not set, skip.")
        return

    reranker = backend_reranker_model()
    must(reranker is not None, "reranker_path is set but reranker failed to load")

    base_hits = qdb.hybrid_search(query=query, top_k=10, alpha=0.75, dynamic_topk=False)
    pairs, valid_hits = [], []
    for h in base_hits:
        content = ((h.get("payload") or {}).get("Content") or "").strip()
        if content:
            pairs.append((query, content))
            valid_hits.append(h)

    must(len(pairs) > 0, "No valid pairs for rerank")

    scores = [float(s) for s in list(reranker.predict(pairs))]
    vmin, vmax = min(scores), max(scores)
    if vmax <= vmin:
        norm_scores = [1.0] * len(scores)
    else:
        norm_scores = [(s - vmin) / (vmax - vmin + 1e-9) for s in scores]

    for h, s_raw, s_norm in zip(valid_hits, scores, norm_scores):
        h["rerank_score_raw"] = s_raw
        h["score"] = float(s_norm)

    valid_hits.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
    top1 = (valid_hits[0].get("payload") or {}).get("Content", "")
    must(norm_text(top1_should_contain) in norm_text(top1),
         f"rerank top1 should contain: {top1_should_contain}\nTop1 head: {top1[:200]}")
    print("✅ rerank top1 ok:", query)


def main():
    pdf_paths = sys.argv[1:]
    if not pdf_paths:
        print("Usage:")
        print("  python tests/smoke_e2e_real_pdfs_hybrid_rerank.py <pdf1> <pdf2> <pdf3> <pdf4>")
        sys.exit(2)

    print("\n==============================")
    print("E2E SMOKE: real PDFs ingest + hybrid + dynamic + rerank(optional)")
    print("==============================\n")

    stored_pdf_paths = ensure_in_stored_files(pdf_paths)
    print("==> PDFs copied to:", PROJECT_ROOT / "data" / "stored_files")

    collection = f"e2e_real_{int(time.time())}"
    print("==> collection:", collection)

    ingest_res = load_multiple_files(
        file_paths=stored_pdf_paths,
        collection_name=collection,
        dpi=200,
    )
    print("==> ingest result:", ingest_res)
    must(len(ingest_res.get("success", [])) > 0, "No PDF ingested successfully.")

    mineru = MineruComponent()
    qdb = QdrantDB(QdrantDB_Init(collection_name=collection))

    try:
        for p in stored_pdf_paths:
            name = Path(p).name
            print("\n------------------------------")
            print("PDF:", name)

            out = mineru.run(pdf_file_path=str(Path(p).resolve()))
            if getattr(out, "status", None) != "success" or getattr(out, "data", None) is None:
                print("⚠️ MinerU failed, skip:", name, "error:", getattr(out, "error", None))
                continue

            anchors = extract_anchors_from_mineru(out.data, max_items=3)
            print("anchors:")
            for a in anchors:
                print(" -", a)

            # 只用 anchors 做检索验证（这是最“真实且合理”的测试）
            for a in anchors:
                q = first_n_chars(a, 40)
                run_hybrid_assert(qdb, q, expect_contains_any=[a], top_k=5)

                # rerank 也用 anchor 来验证 top1 更准
                rerank_top1_should_contain(qdb, q, top1_should_contain=a[:20])

        print("\n✅ ALL DONE: real PDFs e2e smoke passed.")
    finally:
        try:
            qdb.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
