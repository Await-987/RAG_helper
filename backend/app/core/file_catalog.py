"""
Backend file catalog helpers extracted from the old Streamlit-era module.
"""
import os
import time
from pathlib import Path
from typing import Dict, List, Tuple

from loguru import logger

from storage_paths import (
    MINERU_OUTPUT_DIR as APP_MINERU_OUTPUT_DIR,
    PROJECT_ROOT as APP_PROJECT_ROOT,
    project_relative_path,
)

PROJECT_ROOT = APP_PROJECT_ROOT
MINERU_OUTPUT_DIR = APP_MINERU_OUTPUT_DIR

_database_stats_cache: Dict[str, Tuple[Dict[str, int], int]] = {}
_local_file_status_cache: Dict[str, Tuple[float, List[Dict], int]] = {}


def _clone_file_info_list(file_info_list: List[Dict]) -> List[Dict]:
    return [dict(item) for item in file_info_list]


def delete_images_by_document_prefix(document_name: str, output_dir: Path = None) -> Tuple[int, List[str]]:
    if output_dir is None:
        output_dir = MINERU_OUTPUT_DIR

    if not output_dir.exists():
        logger.info(f"图片目录不存在: {output_dir}")
        return 0, []

    prefix = f"{document_name}_"
    deleted_count = 0
    deleted_files = []

    for file_path in list(output_dir.iterdir()):
        if file_path.is_file() and file_path.name.startswith(prefix):
            if file_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".bmp"):
                try:
                    file_path.unlink()
                    deleted_files.append(file_path.name)
                    deleted_count += 1
                    logger.debug(f"已删除图片: {file_path.name}")
                except Exception as exc:
                    logger.error(f"删除图片失败: {file_path.name}, 错误: {exc}")

    if deleted_count > 0:
        logger.info(f"文档 '{document_name}' 关联图片已删除: {deleted_count} 个")

    return deleted_count, deleted_files


def get_document_name_from_tag(file_tag: str) -> str:
    return os.path.splitext(os.path.basename(file_tag))[0]


def _get_file_tag(file_path: Path) -> str:
    if not file_path.is_absolute():
        return file_path.as_posix()

    try:
        return project_relative_path(file_path)
    except Exception:
        return file_path.as_posix()


def _get_database_stats_impl(collection_name: str) -> Tuple[Dict[str, int], int]:
    try:
        from tools.qdrant import QdrantDB, QdrantDB_Init

        db = QdrantDB(input=QdrantDB_Init(collection_name=collection_name))
        lex_index = None

        # 文件管理只需要按 Original_file 统计切片数，不值得因为点数变化就
        # 在这里触发整库 BM25 词汇索引重建。优先复用磁盘缓存；如果缓存与
        # 当前点数不一致，则直接走 scroll 统计，避免导入后刷新文件列表时
        # 卡在全量重建上。
        if db._load_lex_index_from_disk():
            current_cnt = db._get_collection_point_count()
            cached_cnt = db._lex_index_point_count
            if current_cnt is not None and current_cnt == cached_cnt:
                lex_index = db._lex_index
            else:
                logger.info(
                    "词汇索引点数已变化，跳过文件管理场景下的全量重建 | "
                    f"collection={collection_name} cached={cached_cnt} current={current_cnt}"
                )

        if lex_index and lex_index.get("N", 0) > 0:
            stats: Dict[str, int] = {}
            for payload in lex_index.get("payloads", []):
                tag = payload.get("Original_file", "未知文件")
                stats[tag] = stats.get(tag, 0) + 1
            total_chunks = lex_index.get("N", 0)
            logger.debug(f"从词汇索引获取文件统计: {len(stats)} 个文件, {total_chunks} 个切片")
            return stats, total_chunks

        logger.info("词汇索引不可用，使用 scroll 获取文件统计...")
        client = db.storage_instance._client
        total_chunks = client.count(collection_name=collection_name).count

        stats: Dict[str, int] = {}
        if total_chunks > 0:
            batch_size = 1000
            offset = None
            total_scrolled = 0
            max_scroll = 100000

            while total_scrolled < max_scroll:
                points, offset = client.scroll(
                    collection_name=collection_name,
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                if not points:
                    break

                for point in points:
                    tag = point.payload.get("Original_file", "未知文件")
                    stats[tag] = stats.get(tag, 0) + 1

                total_scrolled += len(points)
                if offset is None:
                    break

        return stats, total_chunks
    except Exception as exc:
        logger.error(f"获取数据库统计失败: {exc}")
        return {}, 0


def get_database_stats(collection_name: str = "database", use_cache: bool = True) -> Tuple[Dict[str, int], int]:
    if use_cache and collection_name in _database_stats_cache:
        stats, total_chunks = _database_stats_cache[collection_name]
        return dict(stats), total_chunks

    if not use_cache:
        _database_stats_cache.pop(collection_name, None)

    stats, total_chunks = _get_database_stats_impl(collection_name)
    _database_stats_cache[collection_name] = (dict(stats), total_chunks)
    return dict(stats), total_chunks


def clear_database_stats_cache():
    _database_stats_cache.clear()
    clear_local_file_status_cache()
    logger.info("数据库统计缓存已清除")


def clear_local_file_status_cache():
    _local_file_status_cache.clear()


def import_file_to_database(
    file_path: str,
    collection_name: str = "database",
    dpi: int = 200,
    debug: bool = False,
) -> Tuple[bool, str, int]:
    try:
        from tools.load_files import load_and_store_file

        result = load_and_store_file(
            file_path=file_path,
            collection_name=collection_name,
            dpi=dpi,
            debug=debug,
        )
        if result:
            clear_database_stats_cache()
            return True, "文件导入成功", 0
        return False, "文件导入失败", 0
    except Exception as exc:
        logger.error(f"导入文件失败: {exc}")
        return False, f"导入失败: {exc}", 0


def delete_file_by_tag(
    file_tag: str,
    collection_name: str = "database",
    delete_images: bool = True,
    db_instance=None,
    skip_cache_clear: bool = False,
) -> bool:
    try:
        from tools.qdrant import QdrantDB, QdrantDB_Init

        db = db_instance or QdrantDB(input=QdrantDB_Init(collection_name=collection_name))
        db.delete_by_file_name(file_tag)

        if delete_images:
            document_name = get_document_name_from_tag(file_tag)
            deleted_count, _deleted_files = delete_images_by_document_prefix(document_name)
            if deleted_count > 0:
                logger.info(f"已删除文档 '{document_name}' 关联的 {deleted_count} 个图片文件")

        if not skip_cache_clear:
            clear_database_stats_cache()

        return True
    except Exception as exc:
        logger.error(f"删除数据库切片失败: {exc}")
        return False


def batch_delete_files_by_tags(
    file_tags: List[str],
    collection_name: str = "database",
    delete_images: bool = True,
) -> Dict:
    from tools.qdrant import QdrantDB, QdrantDB_Init

    result = {
        "success_count": 0,
        "failed_count": 0,
        "failed_tags": [],
    }

    if not file_tags:
        return result

    db = QdrantDB(input=QdrantDB_Init(collection_name=collection_name))
    for file_tag in file_tags:
        try:
            success = delete_file_by_tag(
                file_tag=file_tag,
                collection_name=collection_name,
                delete_images=delete_images,
                db_instance=db,
                skip_cache_clear=True,
            )
            if success:
                result["success_count"] += 1
            else:
                result["failed_count"] += 1
                result["failed_tags"].append((file_tag, "删除失败"))
        except Exception as exc:
            result["failed_count"] += 1
            result["failed_tags"].append((file_tag, str(exc)))

    clear_database_stats_cache()
    logger.info(f"批量删除完成：成功 {result['success_count']}，失败 {result['failed_count']}")
    return result


def delete_local_file(file_path: Path, delete_images: bool = False) -> bool:
    try:
        if file_path and file_path.exists():
            if delete_images:
                document_name = os.path.splitext(file_path.name)[0]
                deleted_count, _deleted_files = delete_images_by_document_prefix(document_name)
                if deleted_count > 0:
                    logger.info(f"已删除文档 '{document_name}' 关联的 {deleted_count} 个图片文件")
            os.remove(file_path)
            return True
        return False
    except Exception as exc:
        logger.error(f"删除本地文件失败: {exc}")
        return False


def get_local_files_with_db_status(
    storage_dir: Path,
    cache_ttl_seconds: int = 60,
    force_refresh: bool = False,
) -> Tuple[List[Dict], int]:
    cache_key = str(storage_dir.resolve())
    if force_refresh:
        _local_file_status_cache.pop(cache_key, None)
    cached = _local_file_status_cache.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < cache_ttl_seconds:
        return _clone_file_info_list(cached[1]), cached[2]

    db_stats, total_chunks = get_database_stats(use_cache=not force_refresh)
    file_info_list = []

    local_files = []
    if storage_dir.exists():
        local_files = [name for name in os.listdir(storage_dir) if os.path.isfile(storage_dir / name)]

    matched_db_tags = set()
    for name in local_files:
        target_path = storage_dir / name
        file_tag = _get_file_tag(target_path)
        chunk_count = db_stats.get(file_tag, 0)
        if chunk_count > 0:
            matched_db_tags.add(file_tag)

        file_info_list.append(
            {
                "type": "imported" if chunk_count > 0 else "not_imported",
                "name": name,
                "tag": file_tag,
                "path": target_path,
                "chunk_count": chunk_count,
            }
        )

    for db_tag in db_stats.keys():
        if db_tag not in matched_db_tags:
            display_name = os.path.basename(db_tag)
            chunk_count = db_stats.get(db_tag, 0)
            logger.info(f"残留数据: {display_name}, tag: {db_tag}, chunk_count: {chunk_count}")
            file_info_list.append(
                {
                    "type": "ghost",
                    "name": display_name,
                    "tag": db_tag,
                    "path": None,
                    "chunk_count": chunk_count,
                }
            )

    _local_file_status_cache[cache_key] = (now, _clone_file_info_list(file_info_list), total_chunks)
    return _clone_file_info_list(file_info_list), total_chunks
