"""
文件管理功能 - Streamlit UI 辅助函数
提供文件列表展示、切片统计、删除等功能
"""
import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from loguru import logger


def get_files_without_chunks(storage_dir: Path, collection_name: str = "database") -> List[Dict]:
    """
    获取本地存在但没有数据库切片的文件

    Returns:
        [
            {
                "name": "文件名",
                "path": Path对象,
                "size": 文件大小（字节）
            },
            ...
        ]
    """
    # 获取数据库统计
    db_stats, _ = get_database_stats(collection_name)

    # 获取本地文件
    local_files = [f for f in os.listdir(storage_dir) if os.path.isfile(storage_dir / f)]

    files_without_chunks = []

    for name in local_files:
        target_path = storage_dir / name
        file_tag = str(target_path).split(".")[0]

        # 检查是否有切片
        chunk_count = db_stats.get(file_tag, 0)

        if chunk_count == 0:
            files_without_chunks.append({
                "name": name,
                "path": target_path,
                "size": target_path.stat().st_size if target_path.exists() else 0
            })

    return files_without_chunks


def import_file_to_database(file_path: str, collection_name: str = "database",
                               dpi: int = 200, debug: bool = False) -> Tuple[bool, str, int]:
    """
    导入单个文件到数据库

    Args:
        file_path: 文件路径
        collection_name: 集合名称
        dpi: MinerU 处理 DPI
        debug: 是否启用调试模式

    Returns:
        (是否成功, 消息, 切片数)
    """
    try:
        from tools.load_files import load_and_store_file

        result = load_and_store_file(
            file_path=file_path,
            collection_name=collection_name,
            dpi=dpi,
            debug=debug
        )

        if result:
            return True, "文件导入成功", 0  # TODO: 返回实际切片数
        else:
            return False, "文件导入失败", 0

    except Exception as e:
        logger.error(f"导入文件失败: {e}")
        return False, f"导入失败: {str(e)}", 0


def batch_import_files(file_paths: List[str], collection_name: str = "database",
                        dpi: int = 200, debug: bool = False) -> Dict:
    """
    批量导入文件到数据库

    Args:
        file_paths: 文件路径列表
        collection_name: 集合名称
        dpi: MinerU 处理 DPI
        debug: 是否启用调试模式

    Returns:
        {
            "success": [成功导入的文件路径],
            "failed": [(文件路径, 错误信息), ...],
            "total": 总数,
            "success_count": 成功数,
            "failed_count": 失败数
        }
    """
    results = {
        "success": [],
        "failed": [],
        "total": len(file_paths),
        "success_count": 0,
        "failed_count": 0
    }

    for file_path in file_paths:
        success, msg, chunks = import_file_to_database(
            file_path=file_path,
            collection_name=collection_name,
            dpi=dpi,
            debug=debug
        )

        if success:
            results["success"].append(file_path)
            results["success_count"] += 1
            logger.info(f"✅ 成功导入: {file_path}")
        else:
            results["failed"].append((file_path, msg))
            results["failed_count"] += 1
            logger.error(f"❌ 导入失败: {file_path} - {msg}")

    return results


def get_database_stats(collection_name: str = "database") -> Tuple[Dict[str, int], int]:
    """
    获取数据库统计信息

    Returns:
        (stats_dict, total_chunks)
        - stats_dict: {file_tag: chunk_count, ...}
        - total_chunks: 总切片数
    """
    try:
        from tools.qdrant import QdrantDB, QdrantDB_Init
        db = QdrantDB(input=QdrantDB_Init(collection_name=collection_name))
        client = db.storage_instance._client

        # 获取数据库点数
        count_result = client.count(collection_name=collection_name)
        total_chunks = count_result.count

        # 获取所有点的 payload 以统计各文件分布
        stats = {}
        if total_chunks > 0:
            scroll_result = client.scroll(
                collection_name=collection_name,
                limit=10000,
                with_payload=True,
                with_vectors=False
            )[0]

            for point in scroll_result:
                tag = point.payload.get("Original_file", "未知文件")
                # 使用 os.path.normpath 标准化路径，确保跨平台兼容
                original_tag = tag
                tag = os.path.normpath(tag)
                stats[tag] = stats.get(tag, 0) + 1

        # 调试：打印数据库中的文件标签
        # logger.info(f"数据库中的文件标签 (前5个): {list(stats.keys())[:5]}")
        return stats, total_chunks
    except Exception as e:
        logger.error(f"获取数据库统计失败: {e}")
        return {}, 0


def get_file_info_list(storage_dir: Path) -> List[Dict]:
    """
    获取文件信息列表（包含本地文件和数据库残留）

    Returns:
        [
            {
                "type": "local" | "ghost",
                "name": "文件名",
                "tag": "file_tag",
                "path": Path对象 | None,
                "chunk_count": 切片数
            },
            ...
        ]
    """
    # 获取数据库统计
    db_stats, total_chunks = get_database_stats()

    # 获取本地文件
    local_files = [f for f in os.listdir(storage_dir) if os.path.isfile(storage_dir / f)]

    file_info_list = []
    tags_in_db = set(db_stats.keys())

    # 处理本地存在的文件
    for name in local_files:
        target_path = storage_dir / name
        file_tag = str(target_path).split(".")[0]

        chunk_count = db_stats.get(file_tag, 0)

        file_info_list.append({
            "type": "local",
            "name": name,
            "tag": file_tag,
            "path": target_path,
            "chunk_count": chunk_count
        })

        if file_tag in tags_in_db:
            tags_in_db.remove(file_tag)

    # 处理数据库残留（本地已删除但数据库还有的）
    for ghost_tag in tags_in_db:
        # 简化显示路径，只取最后一部分
        display_name = ghost_tag.split(os.sep)[-1]
        chunk_count = db_stats.get(ghost_tag, 0)

        file_info_list.append({
            "type": "ghost",
            "name": display_name,
            "tag": ghost_tag,
            "path": None,
            "chunk_count": chunk_count
        })

    return file_info_list, total_chunks


def delete_file_by_tag(file_tag: str, collection_name: str = "database") -> bool:
    """
    根据文件标签删除数据库中的切片

    Returns:
        是否删除成功
    """
    try:
        from tools.qdrant import QdrantDB, QdrantDB_Init
        db = QdrantDB(input=QdrantDB_Init(collection_name=collection_name))
        # 使用 os.path.normpath 标准化路径，确保跨平台兼容
        file_tag = os.path.normpath(file_tag)
        db.delete_by_file_name(file_tag)
        return True
    except Exception as e:
        logger.error(f"删除数据库切片失败: {e}")
        return False


def delete_local_file(file_path: Path) -> bool:
    """
    删除本地文件

    Returns:
        是否删除成功
    """
    try:
        if file_path and file_path.exists():
            os.remove(file_path)
            return True
        return False
    except Exception as e:
        logger.error(f"删除本地文件失败: {e}")
        return False


def get_local_files_with_db_status(storage_dir: Path) -> List[Dict]:
    """
    获取所有本地文件和数据库残留数据

    Returns:
        [
            {
                "type": "imported" | "not_imported" | "ghost",
                "name": "文件名",
                "tag": "file_tag",
                "path": Path对象 | None,
                "chunk_count": 切片数
            },
            ...
        ]
    """
    # 获取数据库统计
    db_stats, total_chunks = get_database_stats()

    file_info_list = []

    # 获取所有本地文件
    local_files = []
    if storage_dir.exists():
        local_files = [f for f in os.listdir(storage_dir) if os.path.isfile(storage_dir / f)]

    # 用于记录数据库中已匹配的 tag
    matched_db_tags = set()

    # 处理本地文件
    for name in local_files:
        target_path = storage_dir / name
        # 生成 file_tag，去掉扩展名并标准化路径
        # 使用 resolve() 获取绝对路径，确保与数据库中的绝对路径匹配
        file_tag = os.path.normpath(str(target_path.resolve().parent / target_path.stem))
        chunk_count = db_stats.get(file_tag, 0)

        # 记录匹配的数据库 tag
        if chunk_count > 0:
            matched_db_tags.add(file_tag)

        # 调试信息
        # logger.info(f"本地文件: {name}, tag: {file_tag}, chunk_count: {chunk_count}")

        if chunk_count > 0:
            file_type = "imported"
        else:
            file_type = "not_imported"

        file_info_list.append({
            "type": file_type,
            "name": name,
            "tag": file_tag,
            "path": target_path,
            "chunk_count": chunk_count
        })

    # 处理数据库残留（本地已删除但数据库还有记录的）
    for db_tag in db_stats.keys():
        if db_tag not in matched_db_tags:
            # 这是残留数据
            display_name = os.path.basename(db_tag)
            chunk_count = db_stats.get(db_tag, 0)

            logger.info(f"残留数据: {display_name}, tag: {db_tag}, chunk_count: {chunk_count}")

            file_info_list.append({
                "type": "ghost",
                "name": display_name,
                "tag": db_tag,
                "path": None,  # 本地没有文件
                "chunk_count": chunk_count
            })

    return file_info_list, total_chunks
