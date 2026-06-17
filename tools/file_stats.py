"""
Lightweight file-level chunk statistics backed by a JSON file.

Provides O(1) read/write for file management page stats,
decoupled from the heavy BM25 pickle used by keyword search.
"""
import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional

from loguru import logger


def _get_stats_path(collection_name: str) -> Path:
    lex_dir = Path(os.getenv("QDRANT_LEXICAL_INDEX_DIR", "data/lex_index"))
    lex_dir.mkdir(parents=True, exist_ok=True)
    return lex_dir / f"{collection_name}_file_stats.json"


def load_file_stats(collection_name: str = "database") -> Optional[Dict]:
    path = _get_stats_path(collection_name)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "files" in data and "total_chunks" in data:
            return data
        return None
    except Exception as e:
        logger.warning(f"加载 file_stats.json 失败: {e}")
        return None


def save_file_stats(collection_name: str, stats: Dict) -> None:
    path = _get_stats_path(collection_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False)
        os.replace(tmp_path, str(path))
    except Exception as e:
        logger.error(f"保存 file_stats.json 失败: {e}")
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def increment_file_stats(
    collection_name: str, file_tag: str, count: int
) -> None:
    stats = load_file_stats(collection_name) or {"files": {}, "total_chunks": 0}
    stats["files"][file_tag] = stats["files"].get(file_tag, 0) + count
    stats["total_chunks"] = stats.get("total_chunks", 0) + count
    save_file_stats(collection_name, stats)


def decrement_file_stats(
    collection_name: str, file_tag: str, count: int
) -> None:
    stats = load_file_stats(collection_name) or {"files": {}, "total_chunks": 0}
    new_val = stats["files"].get(file_tag, 0) - count
    if new_val <= 0:
        stats["files"].pop(file_tag, None)
    else:
        stats["files"][file_tag] = new_val
    stats["total_chunks"] = max(0, stats.get("total_chunks", 0) - count)
    save_file_stats(collection_name, stats)


def reconcile_file_stats(collection_name: str = "database") -> Dict:
    """Full scan from Qdrant to rebuild file_stats.json. Used on first run or repair."""
    from tools.qdrant import QdrantDB, QdrantDB_Init

    db = QdrantDB(input=QdrantDB_Init(collection_name=collection_name))
    client = db.storage_instance._client
    total_chunks = client.count(collection_name=collection_name).count

    files: Dict[str, int] = {}
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection_name,
            limit=1000,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            break
        for point in points:
            tag = point.payload.get("Original_file", "未知文件")
            files[tag] = files.get(tag, 0) + 1
        if offset is None:
            break

    stats = {"files": files, "total_chunks": total_chunks}
    save_file_stats(collection_name, stats)
    logger.info(f"file_stats reconcile 完成: {len(files)} 个文件, {total_chunks} 个切片")
    return stats
