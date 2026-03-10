"""
文件管理功能 - Streamlit UI 辅助函数
提供文件列表展示、切片统计、删除等功能
"""
import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from loguru import logger

# 获取项目根目录（与 load_files.py 保持一致）
PROJECT_ROOT = Path(__file__).absolute().parent.parent
# 图片存储目录
MINERU_OUTPUT_DIR = PROJECT_ROOT / "data" / "stored_files" / "mineru_output"


def delete_images_by_document_prefix(document_name: str, output_dir: Path = None) -> Tuple[int, List[str]]:
    """
    删除指定文档关联的所有图片文件

    根据文档名前缀查找并删除图片（格式：文档名_数字.jpg）

    Args:
        document_name: 文档名称（不含扩展名）
        output_dir: 图片输出目录，默认为 MINERU_OUTPUT_DIR

    Returns:
        (删除数量, 删除的文件名列表)
    """
    if output_dir is None:
        output_dir = MINERU_OUTPUT_DIR

    if not output_dir.exists():
        logger.info(f"图片目录不存在: {output_dir}")
        return 0, []

    # 查找以 "文档名_" 开头的图片文件
    prefix = f"{document_name}_"
    deleted_count = 0
    deleted_files = []

    for f in list(output_dir.iterdir()):
        if f.is_file() and f.name.startswith(prefix):
            # 检查是否是图片文件
            if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.gif', '.bmp'):
                try:
                    f.unlink()  # 删除文件
                    deleted_files.append(f.name)
                    deleted_count += 1
                    logger.debug(f"已删除图片: {f.name}")
                except Exception as e:
                    logger.error(f"删除图片失败: {f.name}, 错误: {e}")

    if deleted_count > 0:
        logger.info(f"文档 '{document_name}' 关联图片已删除: {deleted_count} 个")

    return deleted_count, deleted_files


def get_document_name_from_tag(file_tag: str) -> str:
    """
    从 file_tag 中提取文档名（不含扩展名）

    Args:
        file_tag: 文件标签，如 "data/stored_files/document.pdf" 或 "document.pdf"

    Returns:
        文档名（不含路径和扩展名），如 "document"
    """
    # 获取文件名（不含路径）
    filename = os.path.basename(file_tag)
    # 去除扩展名
    document_name = os.path.splitext(filename)[0]
    return document_name


def _get_file_tag(file_path: Path) -> str:
    """
    生成文件标签（相对路径），与 load_files.py 保持一致

    Args:
        file_path: 文件路径（可以是绝对路径或相对路径）

    Returns:
        相对于项目根目录的路径（POSIX 格式，正斜杠）
    """
    # 如果已经是相对路径，直接返回 POSIX 格式
    if not file_path.is_absolute():
        return file_path.as_posix()

    # 如果是绝对路径，转换为相对路径
    try:
        return file_path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        # 如果不在 PROJECT_ROOT 下，返回原路径的 POSIX 格式
        return file_path.as_posix()


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
        # 生成 file_tag：使用相对路径（与 load_files.py 一致）
        file_tag = _get_file_tag(target_path)

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
                        dpi: int = 200, debug: bool = False, num_workers: Optional[int] = None) -> Dict:
    """
    批量导入文件到数据库（串行版本，避免 PDFium 线程安全问题）

    Args:
        file_paths: 文件路径列表
        collection_name: 集合名称
        dpi: MinerU 处理 DPI
        debug: 是否启用调试模式
        num_workers: 保留参数但暂不使用（PDFium 不是线程安全的）

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

    if not file_paths:
        return results

    logger.info(f"开始串行导入 {len(file_paths)} 个文件（PDFium 不支持多线程）")

    # 串行处理每个文件（PDFium 不是线程安全的）
    for i, file_path in enumerate(file_paths, 1):
        try:
            logger.info(f"[{i}/{len(file_paths)}] 正在导入: {os.path.basename(file_path)}")
            success, msg, chunks = import_file_to_database(
                file_path=file_path,
                collection_name=collection_name,
                dpi=dpi,
                debug=debug
            )

            if success:
                results["success"].append(file_path)
                results["success_count"] += 1
                logger.info(f"✅ [{i}/{len(file_paths)}] 成功导入: {os.path.basename(file_path)}")
            else:
                results["failed"].append((file_path, msg))
                results["failed_count"] += 1
                logger.error(f"❌ [{i}/{len(file_paths)}] 导入失败: {os.path.basename(file_path)} - {msg}")

        except Exception as e:
            results["failed"].append((file_path, str(e)))
            results["failed_count"] += 1
            logger.error(f"❌ [{i}/{len(file_paths)}] 导入异常: {os.path.basename(file_path)} - {e}")

    logger.info(f"批量导入完成：成功 {results['success_count']} 个，失败 {results['failed_count']} 个")
    return results


def get_database_stats(collection_name: str = "database", use_cache: bool = True) -> Tuple[Dict[str, int], int]:
    """
    获取数据库统计信息

    Args:
        collection_name: 集合名称
        use_cache: 是否使用缓存（对于大数据量建议使用）

    Returns:
        (stats_dict, total_chunks)
        - stats_dict: {file_tag: chunk_count, ...}
        - total_chunks: 总切片数
    """
    # 使用模块级缓存
    global _db_stats_cache, _db_stats_time, _db_stats_collection
    import time

    cache_ttl = 60  # 缓存 60 秒
    current_time = time.time()

    if use_cache and _db_stats_cache is not None:
        if (_db_stats_collection == collection_name and
            current_time - _db_stats_time < cache_ttl):
            return _db_stats_cache

    try:
        from tools.qdrant import QdrantDB, QdrantDB_Init
        db = QdrantDB(input=QdrantDB_Init(collection_name=collection_name))
        client = db.storage_instance._client

        # 获取数据库点数（快速操作）
        count_result = client.count(collection_name=collection_name)
        total_chunks = count_result.count

        # 获取点的 payload 以统计各文件分布
        # 对于大数据量，使用分页 scroll
        stats = {}
        if total_chunks > 0:
            batch_size = 1000
            offset = None
            total_scrolled = 0
            max_scroll = 100000  # 最多扫描 10 万条，避免太慢

            while total_scrolled < max_scroll:
                scroll_result = client.scroll(
                    collection_name=collection_name,
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False
                )
                points = scroll_result[0]
                offset = scroll_result[1]

                if not points:
                    break

                for point in points:
                    tag = point.payload.get("Original_file", "未知文件")
                    stats[tag] = stats.get(tag, 0) + 1

                total_scrolled += len(points)

                if offset is None:
                    break

        # 缓存结果
        _db_stats_cache = (stats, total_chunks)
        _db_stats_time = current_time
        _db_stats_collection = collection_name

        return stats, total_chunks
    except Exception as e:
        logger.error(f"获取数据库统计失败: {e}")
        return {}, 0


# 缓存变量
_db_stats_cache = None
_db_stats_time = 0
_db_stats_collection = None


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
        # 生成 file_tag：使用相对路径（与 load_files.py 一致）
        file_tag = _get_file_tag(target_path)

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
        display_name = ghost_tag.split("/")[-1]  # 使用 / 分隔（数据库中存储的是 posix 格式）
        chunk_count = db_stats.get(ghost_tag, 0)

        file_info_list.append({
            "type": "ghost",
            "name": display_name,
            "tag": ghost_tag,
            "path": None,
            "chunk_count": chunk_count
        })

    return file_info_list, total_chunks


def delete_file_by_tag(file_tag: str, collection_name: str = "database", delete_images: bool = True) -> bool:
    """
    根据文件标签删除数据库中的切片，并可选删除关联图片

    Args:
        file_tag: 文件标签（相对路径）
        collection_name: 集合名称
        delete_images: 是否同时删除关联的图片文件

    Returns:
        是否删除成功
    """
    try:
        from tools.qdrant import QdrantDB, QdrantDB_Init
        db = QdrantDB(input=QdrantDB_Init(collection_name=collection_name))
        # 不使用 normpath，保持 POSIX 格式（正斜杠）与数据库存储格式一致
        db.delete_by_file_name(file_tag)

        # 删除关联的图片文件
        if delete_images:
            document_name = get_document_name_from_tag(file_tag)
            deleted_count, deleted_files = delete_images_by_document_prefix(document_name)
            if deleted_count > 0:
                logger.info(f"已删除文档 '{document_name}' 关联的 {deleted_count} 个图片文件")

        return True
    except Exception as e:
        logger.error(f"删除数据库切片失败: {e}")
        return False


def delete_local_file(file_path: Path, delete_images: bool = False) -> bool:
    """
    删除本地文件

    Args:
        file_path: 文件路径
        delete_images: 是否同时删除关联的图片文件

    Returns:
        是否删除成功
    """
    try:
        if file_path and file_path.exists():
            # 可选删除关联图片
            if delete_images:
                document_name = os.path.splitext(file_path.name)[0]
                deleted_count, _ = delete_images_by_document_prefix(document_name)
                if deleted_count > 0:
                    logger.info(f"已删除文档 '{document_name}' 关联的 {deleted_count} 个图片文件")

            # 删除本地文件
            os.remove(file_path)
            return True
        return False
    except Exception as e:
        logger.error(f"删除本地文件失败: {e}")
        return False


def delete_file_completely(
    file_tag: str,
    file_path: Path = None,
    collection_name: str = "database",
    delete_local: bool = True,
    delete_images: bool = True
) -> Dict:
    """
    完整删除文件：数据库记录 + 本地文件 + 关联图片

    Args:
        file_tag: 文件标签（相对路径）
        file_path: 本地文件路径（可选）
        collection_name: 集合名称
        delete_local: 是否删除本地文件
        delete_images: 是否删除关联图片

    Returns:
        {
            "success": bool,
            "db_deleted": bool,
            "local_deleted": bool,
            "images_deleted_count": int,
            "error": str or None
        }
    """
    result = {
        "success": False,
        "db_deleted": False,
        "local_deleted": False,
        "images_deleted_count": 0,
        "error": None
    }

    try:
        # 1. 删除数据库记录
        if delete_file_by_tag(file_tag, collection_name, delete_images=False):
            result["db_deleted"] = True
            logger.info(f"数据库切片已删除: {file_tag}")
        else:
            result["error"] = "数据库删除失败"
            return result

        # 2. 删除关联图片
        if delete_images:
            document_name = get_document_name_from_tag(file_tag)
            deleted_count, _ = delete_images_by_document_prefix(document_name)
            result["images_deleted_count"] = deleted_count
            if deleted_count > 0:
                logger.info(f"关联图片已删除: {deleted_count} 个")

        # 3. 删除本地文件
        if delete_local and file_path:
            if delete_local_file(file_path, delete_images=False):  # 图片已删除，不重复删除
                result["local_deleted"] = True
                logger.info(f"本地文件已删除: {file_path}")

        result["success"] = True
        return result

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"完整删除文件失败: {e}")
        return result


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
        # 生成 file_tag：使用相对路径（与 load_files.py 一致）
        file_tag = _get_file_tag(target_path)
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
