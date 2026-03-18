#!/usr/bin/env python
"""
PDF 入库 + 业务 Query 检索 Smoke Test

针对四类业务 PDF 设计了精确的「必命中原文短语」断言：
  - 电网运行规则
  - GB20052-2020 电力变压器能效限定值及能效等级
  - 国网上海电力软著电子证书
  - The Power Grid as a Complex Network（arxiv 论文）

用法:
    python scripts/smoke_pdf_ingest_query.py <pdf1> <pdf2> ...

说明:
  - 根据文件名自动匹配测试计划
  - 使用独立临时 collection，不污染 database collection
  - 断言采用「必须出现的原文短语」，稳定性高
"""
import os
import sys
import time
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.load_files import load_multiple_files
from tools.qdrant import QdrantDB, QdrantDB_Init


# 每个业务 PDF 的测试计划：(query, [必须出现的原文短语, ...])
PDF_TEST_PLAN: Dict[str, List[Tuple[str, List[str]]]] = {
    "电网运行规则": [
        ("电网运行实行什么调度、什么管理？", ["统一调度", "分级管理"]),
        ("电网运行坚持什么方针？", ["安全第一", "预防为主"]),
        ("本规则制定依据哪些法律法规？", ["电力法", "电力监管条例", "电网调度管理条例"]),
    ],
    "GB20052": [
        ("电力变压器能效等级分为几级？哪一级最高？", ["分为3级", "1级能效最高"]),
        ("本标准不适用于哪些变压器？", ["充气式变压器", "高阻抗变压器"]),
        ("本标准适用于哪些10kV配电变压器容量范围？", ["10kV", "30kVA~2500kVA"]),
    ],
    "电子证书": [
        ("软件名称是什么？", ["电网工程系统设计智能助手系统"]),
        ("登记号是多少？", ["2025SR1847304"]),
        ("证书号是什么？", ["软著登字第16503502号"]),
    ],
    "Complex Network": [
        ("这篇论文的标题是什么？", ["The Power Grid as a Complex Network: a Survey"]),
        ("这篇论文的作者是谁？", ["Giuliano Andrea Pagani", "Marco Aiello"]),
        ("Definition 2 里把电网图的节点定义成哪些类型？", ["substation", "transformer", "consuming unit"]),
    ],
}


def guess_plan_key(pdf_name: str) -> str:
    """根据文件名猜对应的测试计划 key"""
    n = pdf_name.lower()
    if "电网运行规则" in pdf_name:
        return "电网运行规则"
    if "gb20052" in n or "20052" in pdf_name:
        return "GB20052"
    if "电子证书" in pdf_name or "证书" in pdf_name:
        return "电子证书"
    if "complex" in n or "network" in n or pdf_name.startswith("1F132"):
        return "Complex Network"
    return ""


def flatten_results(results: Any) -> str:
    """把 Qdrant search 返回结果展平成字符串用于 contains 断言"""
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
        elif isinstance(r, dict):
            p = r.get("payload", {})
            if isinstance(p, dict):
                for k in ("Content", "content", "text"):
                    if p.get(k):
                        texts.append(str(p[k]))
            texts.append(json.dumps(r, ensure_ascii=False))
        else:
            texts.append(str(r))
    return "\n".join(texts)


def assert_contains_all(haystack: str, needles: List[str], title: str):
    missing = [x for x in needles if x not in haystack]
    if missing:
        print(f"\nFAIL: {title}")
        print(f"  缺少: {missing}")
        print(f"  retrieved head (1200字符):\n{haystack[:1200]}")
        raise AssertionError(f"{title} missing {missing}")


def main():
    pdf_paths = sys.argv[1:]
    if not pdf_paths:
        print("用法: python scripts/smoke_pdf_ingest_query.py <pdf1> <pdf2> ...")
        sys.exit(2)

    collection_name = f"smoke_{int(time.time())}"
    print(f"==> collection: {collection_name}")

    abs_paths: List[str] = []
    for p in pdf_paths:
        ap = str(Path(p).resolve())
        if not os.path.exists(ap):
            raise FileNotFoundError(f"PDF not found: {ap}")
        abs_paths.append(ap)

    print("==> 入库中...")
    ingest_res = load_multiple_files(
        file_paths=abs_paths,
        collection_name=collection_name,
        dpi=200,
    )
    print("==> 入库结果:", ingest_res)

    qdrant = QdrantDB(input=QdrantDB_Init(collection_name=collection_name))
    try:
        for ap in abs_paths:
            pdf_name = Path(ap).name
            plan_key = guess_plan_key(pdf_name)
            print(f"\n--- {pdf_name} (plan={plan_key or 'none'}) ---")

            if not plan_key:
                print("  无匹配测试计划，跳过")
                continue

            for query, must_have in PDF_TEST_PLAN[plan_key]:
                print(f"  [QUERY] {query}")
                results = qdrant.search(query)
                text = flatten_results(results)
                assert_contains_all(text, must_have, title=f"{pdf_name} | {query}")
                print("  PASS")

        print("\nALL DONE: 入库 + 检索 smoke test 全部通过")
    finally:
        qdrant.close()


if __name__ == "__main__":
    main()
