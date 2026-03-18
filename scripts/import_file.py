#!/usr/bin/env python
"""
单文件入库工具

将指定 PDF 文件解析并写入 Qdrant 知识库。

用法:
    python scripts/import_file.py <pdf路径>
    python scripts/import_file.py data/stored_files/example.pdf
    python scripts/import_file.py data/stored_files/example.pdf --collection database --dpi 200
"""
import sys
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools import load_multiple_files


def main():
    parser = argparse.ArgumentParser(description="将 PDF 文件解析并写入 Qdrant 知识库")
    parser.add_argument("pdf_path", help="PDF 文件路径（相对或绝对路径均可）")
    parser.add_argument("--collection", default="database", help="Qdrant collection 名称（默认: database）")
    parser.add_argument("--dpi", type=int, default=200, help="PDF 渲染 DPI（默认: 200）")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.is_absolute():
        pdf_path = PROJECT_ROOT / pdf_path

    if not pdf_path.exists():
        print(f"文件不存在: {pdf_path}")
        sys.exit(1)

    print(f"入库文件: {pdf_path}")
    print(f"Collection: {args.collection}")
    print(f"DPI: {args.dpi}")
    print("-" * 60)

    results = load_multiple_files(
        file_paths=[str(pdf_path)],
        collection_name=args.collection,
        dpi=args.dpi,
    )

    print("结果:", results)


if __name__ == "__main__":
    main()
