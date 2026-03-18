#!/usr/bin/env python
"""
MinerU 解析结构取证 + 入库 + 检索 Smoke Test

对指定 PDF 执行完整的端到端验证：
  Step 1: 用 MinerU 解析 PDF，打印 type 分布和锚点文本（不入库）
  Step 2: 走真实入库链路（load_multiple_files）
  Step 3: 对每个 PDF 的锚点文本执行检索断言

用法:
    python scripts/smoke_mineru_ingest_retrieve.py <pdf1> <pdf2> ...
"""
import os
import sys
import time
import json
from pathlib import Path
from collections import Counter
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.mineru_toolkit import MineruComponent, MineruResponse
from tools.load_files import load_multiple_files
from tools.qdrant import QdrantDB, QdrantDB_Init


def must(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


def effective_pdf_path(user_pdf_path: str) -> str:
    """返回业务代码实际读取的路径（data/stored_files/<basename>）"""
    base = os.path.basename(user_pdf_path)
    return str(PROJECT_ROOT / "data" / "stored_files" / base)


def safe_str(x: Any) -> str:
    if x is None:
        return ""
    return x if isinstance(x, str) else str(x)


def extract_anchors(mineru_data: List[dict], max_items: int = 3) -> List[str]:
    """从 MinerU 输出中提取若干可检索锚点文本"""
    keys_priority = ["text", "title", "list", "equation",
                     "image_caption", "table_caption", "table_body", "content"]
    candidates: List[str] = []
    seen = set()
    for item in mineru_data:
        if not isinstance(item, dict):
            continue
        for k in keys_priority:
            v = item.get(k)
            s = ",".join(safe_str(x) for x in v) if isinstance(v, list) else safe_str(v)
            s = " ".join(s.split())
            anchor = s[:80]
            if len(anchor) < 12 or anchor in seen:
                continue
            seen.add(anchor)
            candidates.append(anchor)
            break
        if len(candidates) >= max_items:
            break
    return candidates


def flatten_results(results: Any) -> str:
    """把 Qdrant search 结果展平成字符串用于 contains 断言"""
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
        if isinstance(r, str):
            texts.append(r)
        elif isinstance(r, dict):
            p = r.get("payload")
            if isinstance(p, dict):
                for k in ("Content", "content", "text"):
                    if p.get(k):
                        texts.append(str(p[k]))
            texts.append(json.dumps(r, ensure_ascii=False))
        else:
            texts.append(str(r))
    return "\n".join(texts)


def step1_mineru_debug(pdf_paths: List[str]) -> Dict[str, Dict[str, Any]]:
    print("\n" + "=" * 60)
    print("Step 1: MinerU 解析结构取证（不入库）")
    print("=" * 60)

    mineru = MineruComponent()
    debug_info: Dict[str, Dict[str, Any]] = {}

    for user_path in pdf_paths:
        eff = effective_pdf_path(user_path)
        name = Path(user_path).name
        print(f"\n--- {name} ---")
        print(f"Effective path: {eff}  exists={os.path.exists(eff)}")

        try:
            out: MineruResponse = mineru.run(pdf_file_path=eff)
        except Exception as e:
            print(f"MinerU 异常: {e!r}")
            debug_info[name] = {"status": "exception", "error": repr(e), "anchors": []}
            continue

        status = getattr(out, "status", None)
        data = getattr(out, "data", None)

        if status != "success" or data is None:
            print(f"MinerU 失败: status={status} error={getattr(out, 'error', None)}")
            debug_info[name] = {"status": status, "anchors": []}
            continue

        dist = Counter(d.get("type") for d in data if isinstance(d, dict))
        print(f"Type 分布: {dict(dist)}")

        covered = {"text", "equation", "image", "table"}
        unknown = [t for t in dist if t not in covered]
        if unknown:
            print(f"未覆盖类型: {unknown}")

        anchors = extract_anchors(data, max_items=3)
        print("锚点文本:")
        for a in anchors:
            print(f"  - {a}")

        debug_info[name] = {"status": status, "anchors": anchors}

    return debug_info


def step2_ingest(pdf_paths: List[str], collection: str) -> dict:
    print("\n" + "=" * 60)
    print(f"Step 2: 入库  collection={collection}")
    print("=" * 60)

    res = load_multiple_files(
        file_paths=[str(Path(p).resolve()) for p in pdf_paths],
        collection_name=collection,
        dpi=200,
    )
    print(f"入库结果: {res}")
    must(len(res.get("success", [])) > 0, "没有任何 PDF 入库成功")
    return res


def step3_retrieve(pdf_paths: List[str], debug_info: Dict[str, Dict[str, Any]], collection: str):
    print("\n" + "=" * 60)
    print("Step 3: 检索断言")
    print("=" * 60)

    qdrant = QdrantDB(QdrantDB_Init(collection_name=collection))
    try:
        for user_path in pdf_paths:
            name = Path(user_path).name
            anchors = (debug_info.get(name) or {}).get("anchors", [])
            print(f"\n--- {name} ---")

            if not anchors:
                print("  无锚点，跳过检索断言")
                continue

            for q in anchors:
                print(f"  [QUERY] {q}")
                results = qdrant.search(q)
                text = flatten_results(results)
                ok = any(n in text for n in [q] if n)
                if not ok:
                    print(f"  FAIL: 检索结果中未找到锚点")
                    print(f"  retrieved head: {text[:400]}")
                    raise AssertionError(f"{name} 检索断言失败: {q}")
                print("  PASS")
    finally:
        qdrant.close()


def main():
    pdf_paths = sys.argv[1:]
    if not pdf_paths:
        print("用法: python scripts/smoke_mineru_ingest_retrieve.py <pdf1> <pdf2> ...")
        sys.exit(2)

    collection = f"smoke_{int(time.time())}"

    debug_info = step1_mineru_debug(pdf_paths)
    step2_ingest(pdf_paths, collection)
    step3_retrieve(pdf_paths, debug_info, collection)

    print("\nALL DONE: MinerU 取证 + 入库 + 检索断言全部通过")


if __name__ == "__main__":
    main()
