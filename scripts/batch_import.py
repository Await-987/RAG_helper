#!/usr/bin/env python
"""
批量导入脚本 - 在命令行后台运行，避免前端超时

用法:
    # 激活虚拟环境后运行
    python scripts/batch_import.py

    # 或者后台运行（推荐）
    nohup python scripts/batch_import.py > import.log 2>&1 &

    # 查看进度
    tail -f import.log
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).absolute().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.file_manager_ui import batch_import_files
from loguru import logger


def get_all_pdf_files(storage_dir: Path) -> list:
    """获取存储目录中的所有 PDF 文件"""
    if not storage_dir.exists():
        logger.error(f"存储目录不存在: {storage_dir}")
        return []

    pdf_files = [
        str(storage_dir / f) for f in os.listdir(storage_dir)
        if f.lower().endswith('.pdf') and os.path.isfile(storage_dir / f)
    ]
    return sorted(pdf_files)


def get_imported_files(collection_name: str = "database") -> set:
    """获取已入库的文件标签"""
    try:
        from tools.qdrant import QdrantDB, QdrantDB_Init
        db = QdrantDB(input=QdrantDB_Init(collection_name=collection_name))
        client = db.storage_instance._client

        # 获取所有点的 payload
        scroll_result = client.scroll(
            collection_name=collection_name,
            limit=100000,
            with_payload=True,
            with_vectors=False
        )[0]

        imported = set()
        for point in scroll_result:
            tag = point.payload.get("Original_file", "")
            # 从 tag 中提取文件名
            if tag:
                imported.add(os.path.basename(tag))

        return imported
    except Exception as e:
        logger.warning(f"获取已入库文件失败: {e}")
        return set()


def main():
    """主函数"""
    start_time = datetime.now()
    logger.info(f"=== 批量导入开始 {start_time.strftime('%Y-%m-%d %H:%M:%S')} ===")

    # 存储目录
    storage_dir = PROJECT_ROOT / "data" / "stored_files"

    # 获取所有 PDF 文件
    all_files = get_all_pdf_files(storage_dir)
    logger.info(f"发现 {len(all_files)} 个 PDF 文件")

    if not all_files:
        logger.warning("没有找到 PDF 文件，退出")
        return

    # 获取已入库的文件
    imported_files = get_imported_files()
    logger.info(f"已入库 {len(imported_files)} 个文件")

    # 过滤出未入库的文件
    files_to_import = []
    for file_path in all_files:
        file_name = os.path.basename(file_path)
        if file_name not in imported_files:
            files_to_import.append(file_path)

    logger.info(f"待入库 {len(files_to_import)} 个文件")

    if not files_to_import:
        logger.info("所有文件已入库，无需处理")
        return

    # 执行批量导入
    logger.info("开始批量导入...")
    results = batch_import_files(
        file_paths=files_to_import,
        collection_name="database",
        dpi=200,
        debug=False  # 关闭调试输出，减少日志量
    )

    # 统计结果
    end_time = datetime.now()
    duration = end_time - start_time

    logger.info("=" * 60)
    logger.info("=== 批量导入完成 ===")
    logger.info(f"总文件数: {results['total']}")
    logger.info(f"成功: {results['success_count']}")
    logger.info(f"失败: {results['failed_count']}")
    logger.info(f"耗时: {duration}")
    logger.info("=" * 60)

    # 输出失败详情
    if results['failed']:
        logger.warning("失败文件列表:")
        for file_path, error_msg in results['failed']:
            logger.warning(f"  - {os.path.basename(file_path)}: {error_msg}")


if __name__ == "__main__":
    main()
