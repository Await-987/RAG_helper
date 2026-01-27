import os
import sys
import time
import json
from pathlib import Path
from collections import Counter
from typing import Any, Dict, List, Tuple

# -----------------------------
# 0) 解决 “tests/tools 抢占 tools 包名” 的问题
# -----------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# -----------------------------
# 1) 只从具体模块导入，避免 tools/__init__.py & 命名冲突
# -----------------------------
from tools.mineru_toolkit import MineruComponent, MineruResponse
from tools.load_files import load_multiple_files
from tools.qdrant import QdrantDB, QdrantDB_Init


# -----------------------------
# 2) Helper: 跟业务逻辑保持一致：最终 MinerU 实际读取的是 data/stored_files/<basename>
#    （即使你传了别的路径，业务代码也会这样处理）
# -----------------------------
def effective_pdf_path(user_pdf_path: str) -> str:
    base = os.path.basename(user_pdf_path)
    return os.path.join(PROJECT_ROOT, "data", "stored_files", base)


def safe_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    try:
        return str(x)
    except Exception:
        return ""


def extract_text_candidates(mineru_data: List[dict], max_items: int = 3) -> List[str]:
    """
    从 MinerU 的 data 里抽几个“锚点短语”：
    - 优先 text / title / list / index / equation 这类字段（你们实际 data key 可能不同，所以做多 key 兜底）
    - 再尝试 image_caption / table_caption / table_body
    """
    keys_priority = [
        "text",
        "title",
        "list",
        "index",
        "equation",
        "image_caption",
        "table_caption",
        "table_body",
        "content",
    ]

    candidates: List[str] = []
    seen = set()

    for item in mineru_data:
        if not isinstance(item, dict):
            continue

        # 尽量抓“有意义、可检索”的文本
        for k in keys_priority:
            v = item.get(k)
            s = ""
            if isinstance(v, list):
                s = ",".join([safe_str(x) for x in v])
            else:
                s = safe_str(v)

            s = " ".join(s.split())  # 压缩空白
            if not s:
                continue

            # 取一段中等长度，避免太短/太长
            anchor = s[:80]
            if len(anchor) < 12:
                continue

            if anchor not in seen:
                seen.add(anchor)
                candidates.append(anchor)
                break

        if len(candidates) >= max_items:
            break

    return candidates


def flatten_results_to_text(results: Any) -> str:
    """
    把 Qdrant search 返回揉成一个大字符串，方便 contains 断言
    """
    if results is None:
        return ""
    if isinstance(results, str):
        return results
    if isinstance(results, dict):
        results = [results]
    if not isinstance(results, list):
        return str(results)

    texts: List[str] = []
    for r in results:
        if r is None:
            continue
        if isinstance(r, str):
            texts.append(r)
            continue
        if isinstance(r, dict):
            # 常见结构里会有 payload
            p = r.get("payload")
            if isinstance(p, dict):
                for k in ("Content", "content", "text"):
                    if p.get(k):
                        texts.append(str(p[k]))
            # 兜底把 dict 也串起来（便于看到 Original_file 等字段）
            texts.append(json.dumps(r, ensure_ascii=False))
        else:
            texts.append(str(r))
    return "\n".join(texts)


def assert_contains_any(haystack: str, needles: List[str], title: str):
    ok = any(n in haystack for n in needles if n)
    if not ok:
        print("\n❌ FAIL:", title)
        print("   Expected ANY of anchors (showing up to 3):")
        for n in needles[:3]:
            print("   -", n)
        print("   ---- retrieved text head (1200 chars) ----")
        print(haystack[:1200])
        raise AssertionError(title)


def mineru_debug_only(pdf_paths: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    对每个 PDF 跑一次 MinerU，打印 type 分布 + unknown type + 样例 keys
    同时抽取 anchors，用于后续检索断言
    """
    print("\n==============================")
    print("Step 1) MinerU Debug (NO ingest)")
    print("==============================\n")

    mineru = MineruComponent()
    debug_info: Dict[str, Dict[str, Any]] = {}

    for user_path in pdf_paths:
        eff = effective_pdf_path(user_path)
        name = Path(user_path).name

        print("\n====== MinerU TYPE DEBUG ======")
        print("User path:", user_path)
        print("Effective path used by pipeline:", eff)
        print("Exists(effective):", os.path.exists(eff))

        try:
            out: MineruResponse = mineru.run(pdf_file_path=eff)
        except Exception as e:
            print("MinerU run raised exception:", repr(e))
            debug_info[name] = {"status": "exception", "error": repr(e), "effective_path": eff}
            continue

        status = getattr(out, "status", None)
        data = getattr(out, "data", None)
        err = getattr(out, "error", None)

        if status != "success" or data is None:
            print("MinerU status:", status, "error:", err)
            debug_info[name] = {
                "status": status,
                "error": err,
                "effective_path": eff,
                "types": {},
                "unknown_types": [],
                "anchors": [],
            }
            continue

        # 统计 type
        types = [d.get("type") for d in data if isinstance(d, dict)]
        dist = Counter(types)
        print("Type distribution:", dist)

        # 你们当前 preprocess(type2key) 只覆盖的类型（按你们 load_files.py 里的 type2key）
        covered = {"text", "equation", "image", "table"}
        unknown = [t for t in dist.keys() if t not in covered]
        print("Unknown types (NOT covered by preprocess type2key):", unknown)

        # 打印未知类型样例 keys（每种 type 打 1 个）
        for t in unknown[:8]:
            sample = next((d for d in data if isinstance(d, dict) and d.get("type") == t), None)
            if sample:
                print(f"Sample keys for type='{t}':", list(sample.keys()))

        anchors = extract_text_candidates(data, max_items=3)
        print("Auto anchors (for retrieval asserts):")
        for a in anchors:
            print("  -", a)

        debug_info[name] = {
            "status": status,
            "error": err,
            "effective_path": eff,
            "types": dict(dist),
            "unknown_types": unknown,
            "anchors": anchors,
        }

    return debug_info


def ingest_and_retrieve(pdf_paths: List[str], debug_info: Dict[str, Dict[str, Any]]):
    """
    走真实入库链路（load_multiple_files），并在成功后对每个 PDF 做检索断言
    """
    print("\n==============================")
    print("Step 2) Real ingest (load_multiple_files)")
    print("==============================\n")

    collection = f"smoke_{int(time.time())}"
    print("==> Using collection:", collection)

    # 真实入库（会复现你们现在的 KeyError: discarded）
    ingest_res = load_multiple_files(
        file_paths=[str(Path(p).resolve()) for p in pdf_paths],
        collection_name=collection,
        dpi=200,
    )
    print("==> Ingest result:", ingest_res)

    # 入库后检索验证
    print("\n==============================")
    print("Step 3) Retrieval asserts (Qdrant.search)")
    print("==============================\n")

    qdrant_init = QdrantDB_Init(collection_name=collection)
    qdrant = QdrantDB(input=qdrant_init)

    try:
        for user_path in pdf_paths:
            name = Path(user_path).name
            info = debug_info.get(name, {})
            anchors = info.get("anchors", []) or []

            print("\n------ RETRIEVE CHECK ------")
            print("PDF:", name)

            if not anchors:
                print("⚠️ No anchors extracted from MinerU output, skip retrieve assert.")
                continue

            # 用每个 anchor 当 query 试一次，只要命中任意一个即可
            #（如果你想更严格，可以每个 anchor 都 assert）
            for q in anchors:
                print("[QUERY]", q)
                results = qdrant.search(q)
                text = flatten_results_to_text(results)
                assert_contains_any(text, [q], title=f"{name} retrieve should contain anchor")
                print("✅ PASS")

        print("\n🎉 ALL DONE: MinerU debug + ingest + retrieve checks finished.")
    finally:
        qdrant.close()


def main():
    pdf_paths = sys.argv[1:]
    if not pdf_paths:
        print("Usage: python tests\\smoke_mineru_debug_and_retrieve.py <pdf1> <pdf2> ...")
        sys.exit(2)

    # Step 1: 先做 MinerU 输出结构取证（不会改库、不会入库）
    debug_info = mineru_debug_only(pdf_paths)

    # Step 2/3: 再走真实入库链路 + 检索断言（这里会复现 discarded KeyError）
    ingest_and_retrieve(pdf_paths, debug_info)


if __name__ == "__main__":
    main()