#!/usr/bin/env python
"""
Qdrant 检索测试工具

对指定 collection 执行向量检索，打印返回结果。
用于验证入库是否成功、检索是否正常。

用法:
    python scripts/search_qdrant.py <查询词>
    python scripts/search_qdrant.py 供电营业规则
    python scripts/search_qdrant.py 供电营业规则 --collection database --top-k 5
"""
import sys
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools import QdrantDB, QdrantDB_Init


def main():
    parser = argparse.ArgumentParser(description="对 Qdrant 知识库执行向量检索")
    parser.add_argument("query", help="检索查询词")
    parser.add_argument("--collection", default="database", help="Qdrant collection 名称（默认: database）")
    parser.add_argument("--top-k", type=int, default=5, help="返回结果数量（默认: 5）")
    args = parser.parse_args()

    print(f"查询: {args.query}")
    print(f"Collection: {args.collection}")
    print(f"Top-K: {args.top_k}")
    print("-" * 60)

    qdrant_init = QdrantDB_Init(collection_name=args.collection)
    qdrant = QdrantDB(input=qdrant_init)

    try:
        results = qdrant.search(args.query, top_k=args.top_k)
        print(results)
    finally:
        qdrant.close()


if __name__ == "__main__":
    main()
