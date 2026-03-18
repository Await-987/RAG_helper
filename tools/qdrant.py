import os
import sys
import time
import math
import re
import hashlib
import pickle
from pathlib import Path
from dataclasses import dataclass
from collections import defaultdict, Counter
from typing import List, Dict, Optional, Any, Tuple

from camel.storages import QdrantStorage
from camel.storages import VectorRecord
from camel.storages.vectordb_storages import VectorDBQuery, VectorDBQueryResult
from loguru import logger
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
load_dotenv()


def _resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return BASE_DIR / path


def _get_qdrant_runtime_config() -> Dict[str, Any]:
    mode = os.getenv("QDRANT_MODE", "local").strip().lower()
    if mode not in {"local", "server"}:
        raise ValueError("QDRANT_MODE must be either 'local' or 'server'")

    local_path = _resolve_path(os.getenv("QDRANT_LOCAL_PATH", "data/storages"))
    lex_index_dir = _resolve_path(os.getenv("QDRANT_LEXICAL_INDEX_DIR", "data/lex_index"))
    url = os.getenv("QDRANT_URL", "").strip()
    api_key = os.getenv("QDRANT_API_KEY", "").strip()
    timeout = int(os.getenv("QDRANT_TIMEOUT_SEC", "30"))
    retries_default = "10" if mode == "server" else "1"
    init_retries = max(1, int(os.getenv("QDRANT_INIT_RETRIES", retries_default)))
    init_delay = max(0.5, float(os.getenv("QDRANT_INIT_DELAY_SEC", "3")))

    if mode == "server" and not url:
        raise ValueError("QDRANT_URL is required when QDRANT_MODE=server")

    if mode == "local":
        local_path.mkdir(parents=True, exist_ok=True)
    lex_index_dir.mkdir(parents=True, exist_ok=True)

    return {
        "mode": mode,
        "local_path": local_path,
        "lex_index_dir": lex_index_dir,
        "url": url,
        "api_key": api_key or None,
        "timeout": timeout,
        "init_retries": init_retries,
        "init_delay": init_delay,
    }


@dataclass
class QdrantDB_Init:
    collection_name: str = None


@dataclass
class save2Qdrant_Input:
    text: List[str] | str
    origin_file: str = None
    meta_data: dict = None


class QdrantDB:
    """
    Vector search + (optional) keyword BM25-like search + hybrid fusion.

    Keyword search index is built lazily from Qdrant payload (scroll),
    and auto-refreshed when collection point count changes.
    """

    # --- simple tokenizer patterns (supports Chinese + alnum) ---
    _RE_EN = re.compile(r"[A-Za-z0-9]+")
    _RE_ZH_SEQ = re.compile(r"[\u4e00-\u9fff]+")

    def __init__(self, input: QdrantDB_Init):
        try:
            from agents.backend_model import backend_embedding_model
            self.embedding_instance = backend_embedding_model()
        except Exception as e:
            raise Exception(f"Failed to initialize embedding model via API: {e}")

        self.collection_name = input.collection_name
        self.runtime_config = _get_qdrant_runtime_config()
        self.storage_mode = self.runtime_config["mode"]
        self.storage_path = str(self.runtime_config["local_path"])

        # --- 实例级别词汇索引缓存（随实例持久化，适合 Streamlit @st.cache_resource）---
        # 格式: {"index": dict, "point_count": int, "build_time": float, "collection_name": str}
        self._lex_index_cache: Dict[str, Any] = {}

        # --- 词汇索引持久化路径 ---
        self._lex_index_dir = self.runtime_config["lex_index_dir"]
        self._lex_index_file = self._lex_index_dir / f"{self.collection_name}_lex_index.pkl"

        try:
            vector_dim = self.embedding_instance.get_output_dim()
            self.storage_instance = self._create_storage_instance(vector_dim)
        except Exception as e:
            raise Exception(f"QdrantStorage initialization failed: {e}")

    def _create_storage_instance(self, vector_dim: int) -> QdrantStorage:
        retries = self.runtime_config["init_retries"]
        delay = self.runtime_config["init_delay"]
        last_error = None

        for attempt in range(1, retries + 1):
            try:
                if self.storage_mode == "server":
                    storage = QdrantStorage(
                        vector_dim=vector_dim,
                        url_and_api_key=(
                            self.runtime_config["url"],
                            self.runtime_config["api_key"],
                        ),
                        collection_name=self.collection_name,
                        timeout=self.runtime_config["timeout"],
                    )
                    logger.info(
                        "Initialized Qdrant server connection | url={} collection={} attempt={}/{}",
                        self.runtime_config["url"],
                        self.collection_name,
                        attempt,
                        retries,
                    )
                    return storage

                storage = QdrantStorage(
                    vector_dim=vector_dim,
                    path=self.storage_path,
                    collection_name=self.collection_name,
                    timeout=self.runtime_config["timeout"],
                )
                logger.info(
                    "Initialized local Qdrant storage | path={} collection={}",
                    self.storage_path,
                    self.collection_name,
                )
                return storage
            except Exception as exc:
                last_error = exc
                if attempt >= retries:
                    break
                logger.warning(
                    "Qdrant init failed | mode={} target={} collection={} attempt={}/{} error={}",
                    self.storage_mode,
                    self.runtime_config["url"] if self.storage_mode == "server" else self.storage_path,
                    self.collection_name,
                    attempt,
                    retries,
                    exc,
                )
                time.sleep(delay)

        raise RuntimeError(
            "Unable to initialize Qdrant storage "
            f"(mode={self.storage_mode}, collection={self.collection_name})"
        ) from last_error

    def close(self):
        """close qdrant client"""
        try:
            if hasattr(self, 'storage_instance') and hasattr(self.storage_instance, '_client'):
                self.storage_instance._client.close()
        except Exception as e:
            logger.warning(f"Error closing Qdrant client: {e}")

    def __enter__(self):
        """support context manager"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """close qdrant client when exit"""
        self.close()
        return False

    # ----------------------
    # Ingest
    # ----------------------
    def save2Qdrant(self, input: save2Qdrant_Input, vector_text: Optional[str] = None) -> List[Tuple[str, Dict]]:
        """
        Input text and store the text data along with its source information into the Qdrant database.
        返回新增的 [(point_id, payload)] 列表，用于增量更新词汇索引。
        """
        base_payload = {'Original_file': '', 'metadata': {}, 'Content': ''}

        if input.origin_file:
            base_payload["Original_file"] = input.origin_file
        if input.meta_data:
            base_payload["metadata"] = input.meta_data

        records = []
        texts_to_embed = [input.text] if isinstance(input.text, str) else input.text

        # 新增：如果传了 vector_text 就用它算向量，否则和原来一样用 input.text
        if vector_text is not None:
            texts_for_vector = [vector_text] if isinstance(vector_text, str) else [vector_text]
        else:
            texts_for_vector = texts_to_embed

        vectors = self.embedding_instance.embed_list(list(texts_for_vector))
        # 改为 DEBUG 级别，避免大量日志输出
        logger.debug(f"嵌入向量生成完成，维度: {len(vectors[0]) if vectors else 'N/A'}")

        for vector, text_chunk in zip(vectors, texts_to_embed):
            payload = base_payload.copy()
            payload["Content"] = text_chunk
            record = VectorRecord(vector=vector, payload=payload)
            records.append(record)

        new_points: List[Tuple[str, Dict]] = []
        if records:
            self.storage_instance.add(records)
            # 记录新增的 point_id 和 payload
            new_points = [(str(record.id), record.payload) for record in records]

            # 增量更新词汇索引
            if self._lex_index_cache:
                self._update_lex_index_for_new_points(new_points)
            else:
                # 如果索引不存在，更新 point_count 以便下次构建时知道数据变化
                pass

        return new_points

    # ----------------------
    # Vector search (existing)
    # ----------------------
    def search(self, query: str, top_k: int = 3) -> List[Dict]:
        """Performs semantic (vector) search in the database based on a text query."""
        query_vector = self.embedding_instance.embed(query)
        query_object = VectorDBQuery(query_vector=query_vector, top_k=top_k)

        try:
            search_results: List[VectorDBQueryResult] = self.storage_instance.query(query_object)
        except Exception as e:
            logger.error(f"Error occurred while calling storage_instance.query: {e}")
            return []

        formatted_hits = []
        try:
            for hit in search_results:
                payload_data = {}
                score_data = 0.0

                if hasattr(hit, 'record') and hit.record is not None and hasattr(hit.record, 'payload'):
                    payload_data = hit.record.payload
                else:
                    logger.warning(f"Search result missing 'record' or 'record.payload' attribute: {hit}")

                if hasattr(hit, 'similarity'):
                    score_data = hit.similarity
                else:
                    logger.warning(f"Search result missing 'similarity' attribute: {hit}")

                # Try to keep a stable id if available
                point_id = None
                if hasattr(hit, "record") and hit.record is not None and hasattr(hit.record, "id"):
                    point_id = getattr(hit.record, "id", None)
                if point_id is None and hasattr(hit, "id"):
                    point_id = getattr(hit, "id", None)

                formatted_hits.append({
                    "id": point_id,
                    "payload": payload_data,
                    "score": float(score_data),
                    "source": "vector",
                })
        except Exception as e:
            logger.error(f"Error occurred while formatting search results: {e}")
            return [{"raw_result": str(r)} for r in search_results]
        return formatted_hits

    # ----------------------
    # Keyword index helpers
    # ----------------------
    @classmethod
    def _tokenize(cls, text: str) -> List[str]:
        """
        Lightweight tokenizer:
        - English/number tokens: split by regex
        - Chinese: generate bigrams over Chinese sequences
        """
        if not text:
            return []
        tokens: List[str] = []

        # alnum tokens
        tokens.extend([w.lower() for w in cls._RE_EN.findall(text)])

        # Chinese bigrams
        for seq in cls._RE_ZH_SEQ.findall(text):
            s = seq.strip()
            if not s:
                continue
            if len(s) == 1:
                tokens.append(s)
            else:
                tokens.extend([s[i:i+2] for i in range(len(s) - 1)])
                # also add short full-seq token to help exact phrase-ish match
                if 2 <= len(s) <= 6:
                    tokens.append(s)

        return tokens

    def _get_collection_point_count(self) -> Optional[int]:
        client = self.storage_instance._client
        try:
            res = client.count(collection_name=self.collection_name, exact=False)
            if hasattr(res, "count"):
                return int(res.count)
            if isinstance(res, int):
                return res
            return None
        except Exception as e:
            logger.warning(f"count() failed for collection={self.collection_name}: {e}")
            return None

    def _scroll_points(self, limit: Optional[int] = None) -> List[Tuple[Any, Dict[str, Any]]]:
        """
        Returns list of (point_id, payload).
        """
        client = self.storage_instance._client
        out: List[Tuple[Any, Dict[str, Any]]] = []
        offset_val = None

        while True:
            points, next_page_offset = client.scroll(
                collection_name=self.collection_name,
                with_payload=True,
                with_vectors=False,
                limit=256,
                offset=offset_val
            )

            for p in points or []:
                pid = getattr(p, "id", None)
                payload = getattr(p, "payload", {}) or {}
                out.append((pid, payload))

            if not next_page_offset or (limit and len(out) >= limit):
                break
            offset_val = next_page_offset

        return out[:limit] if limit else out

    # ----------------------
    # 词汇索引持久化
    # ----------------------
    def _get_lex_index_path(self) -> Path:
        """获取词汇索引持久化文件路径"""
        return self._lex_index_file

    def _load_lex_index_from_disk(self) -> bool:
        """从磁盘加载词汇索引，返回是否成功"""
        if not self._lex_index_file.exists():
            return False
        try:
            with open(self._lex_index_file, 'rb') as f:
                loaded_cache = pickle.load(f)

            # 验证基本结构
            if not isinstance(loaded_cache, dict):
                return False
            if "index" not in loaded_cache:
                return False

            idx = loaded_cache.get("index", {})
            required_keys = {"doc_ids", "payloads", "doc_lens", "avgdl", "inv", "N"}
            if not required_keys.issubset(idx.keys()):
                return False

            # 确保 point_id_to_doc_idx 存在（用于增量删除）
            if "point_id_to_doc_idx" not in idx:
                # 旧格式，重建映射
                idx["point_id_to_doc_idx"] = {
                    str(pid): doc_idx
                    for doc_idx, pid in enumerate(idx["doc_ids"])
                }

            self._lex_index_cache = loaded_cache
            logger.info(f"从磁盘加载词汇索引: {loaded_cache.get('point_count', 0)} 个点")
            return True
        except Exception as e:
            logger.warning(f"加载词汇索引失败: {e}")
            return False

    def _save_lex_index_to_disk(self):
        """保存词汇索引到磁盘"""
        if not self._lex_index_cache:
            return
        try:
            self._lex_index_dir.mkdir(parents=True, exist_ok=True)
            with open(self._lex_index_file, 'wb') as f:
                pickle.dump(self._lex_index_cache, f)
            logger.debug(f"词汇索引已保存到磁盘: {self._lex_index_file}")
        except Exception as e:
            logger.warning(f"保存词汇索引失败: {e}")

    # ----------------------
    # 增量更新
    # ----------------------
    def _update_lex_index_for_new_points(self, new_points: List[Tuple[str, Dict]]):
        """增量添加新点到词汇索引"""
        if not new_points:
            return

        # 确保索引已初始化
        if not self._lex_index_cache or "index" not in self._lex_index_cache:
            logger.warning("词汇索引未初始化，跳过增量更新")
            return

        idx = self._lex_index_cache["index"]

        for point_id, payload in new_points:
            content = payload.get("Content", "") or payload.get("content", "") or ""
            if not isinstance(content, str):
                continue
            content = content.strip()
            if not content:
                continue

            tokens = self._tokenize(content)
            if not tokens:
                continue

            doc_idx = len(idx["doc_ids"])
            tf = Counter(tokens)

            idx["doc_ids"].append(point_id)
            idx["payloads"].append(payload)
            idx["doc_lens"].append(sum(tf.values()))
            idx["point_id_to_doc_idx"][point_id] = doc_idx

            for tok, freq in tf.items():
                idx["inv"].setdefault(tok, []).append((doc_idx, int(freq)))

        # 更新统计信息
        idx["N"] = len(idx["doc_ids"])
        idx["avgdl"] = sum(idx["doc_lens"]) / idx["N"] if idx["N"] > 0 else 1.0
        self._lex_index_cache["point_count"] = idx["N"]

        logger.info(f"词汇索引增量添加 {len(new_points)} 个点，总计 {idx['N']} 个点")

        # 保存到磁盘
        self._save_lex_index_to_disk()

    def _update_lex_index_for_deleted_points(self, deleted_point_ids: List[str]):
        """增量删除点（紧凑删除）"""
        if not deleted_point_ids or not self._lex_index_cache:
            return

        idx = self._lex_index_cache["index"]

        # 1. 找到要删除的 doc_indices
        to_delete = set()
        for pid in deleted_point_ids:
            pid_str = str(pid)
            if pid_str in idx["point_id_to_doc_idx"]:
                to_delete.add(idx["point_id_to_doc_idx"][pid_str])

        if not to_delete:
            logger.debug("没有找到需要删除的点")
            return

        # 2. 紧凑删除：重建数组
        new_doc_ids = []
        new_payloads = []
        new_doc_lens = []
        new_point_id_to_idx = {}
        old_to_new_idx = {}  # 旧索引 -> 新索引

        for old_idx, (doc_id, payload, doc_len) in enumerate(zip(
            idx["doc_ids"], idx["payloads"], idx["doc_lens"]
        )):
            if old_idx in to_delete:
                continue
            new_idx = len(new_doc_ids)
            old_to_new_idx[old_idx] = new_idx
            new_doc_ids.append(doc_id)
            new_payloads.append(payload)
            new_doc_lens.append(doc_len)
            new_point_id_to_idx[str(doc_id)] = new_idx

        # 3. 重建倒排索引
        new_inv = defaultdict(list)
        for token, postings in idx["inv"].items():
            for old_doc_idx, tf in postings:
                if old_doc_idx in old_to_new_idx:
                    new_doc_idx = old_to_new_idx[old_doc_idx]
                    new_inv[token].append((new_doc_idx, tf))

        # 4. 更新索引
        idx["doc_ids"] = new_doc_ids
        idx["payloads"] = new_payloads
        idx["doc_lens"] = new_doc_lens
        idx["point_id_to_doc_idx"] = new_point_id_to_idx
        idx["inv"] = dict(new_inv)
        idx["N"] = len(new_doc_ids)
        idx["avgdl"] = sum(new_doc_lens) / idx["N"] if idx["N"] > 0 else 1.0
        self._lex_index_cache["point_count"] = idx["N"]

        logger.info(f"词汇索引增量删除 {len(to_delete)} 个点，剩余 {idx['N']} 个点")

        # 5. 保存到磁盘
        self._save_lex_index_to_disk()

    def _maybe_build_lex_index(self, force: bool = False):
        """
        Build lexical inverted index if:
        - force=True
        - index is missing
        - point count changed (有新数据入库)

        优先从磁盘加载持久化索引，加载失败或数据不一致时才全量重建。
        """
        # 如果不强制重建，先尝试从磁盘加载
        if not force:
            cache = self._lex_index_cache

            # 1. 如果内存缓存已存在，检查是否需要刷新
            if cache:
                current_cnt = self._get_collection_point_count()
                if current_cnt is None or current_cnt == cache.get("point_count"):
                    return  # 缓存有效，直接返回
            else:
                # 2. 尝试从磁盘加载
                if self._load_lex_index_from_disk():
                    current_cnt = self._get_collection_point_count()
                    if current_cnt is not None and current_cnt == self._lex_index_cache.get("point_count"):
                        return  # 磁盘缓存有效

        # 3. 全量重建
        logger.info(f"Building lexical index for collection='{self.collection_name}' ...")
        points = self._scroll_points()

        doc_ids: List[Any] = []
        payloads: List[Dict[str, Any]] = []
        doc_lens: List[int] = []
        inv: Dict[str, List[Tuple[int, int]]] = defaultdict(list)  # token -> [(doc_idx, tf)]
        point_id_to_doc_idx: Dict[str, int] = {}  # point_id -> doc_idx 映射

        for pid, payload in points:
            # payload content field (your ingest uses 'Content')
            content = payload.get("Content") or payload.get("content") or payload.get("text") or ""
            if not isinstance(content, str):
                continue
            content = content.strip()
            if not content:
                continue

            tokens = self._tokenize(content)
            if not tokens:
                continue

            tf = Counter(tokens)
            doc_idx = len(doc_ids)

            pid_str = str(pid)
            doc_ids.append(pid_str)
            payloads.append(payload)
            doc_lens.append(sum(tf.values()))
            point_id_to_doc_idx[pid_str] = doc_idx

            for tok, freq in tf.items():
                inv[tok].append((doc_idx, int(freq)))

        avgdl = (sum(doc_lens) / len(doc_lens)) if doc_lens else 1.0
        current_cnt = len(doc_ids)

        # 存储到实例级别缓存
        self._lex_index_cache = {
            "index": {
                "doc_ids": doc_ids,
                "payloads": payloads,
                "doc_lens": doc_lens,
                "avgdl": float(avgdl),
                "inv": inv,
                "N": int(len(doc_ids)),
                "point_id_to_doc_idx": point_id_to_doc_idx,
            },
            "point_count": current_cnt,
            "build_time": time.time(),
            "collection_name": self.collection_name,
        }

        logger.info(
            f"Lexical index ready: docs={len(doc_ids)}, avgdl={avgdl:.2f}, tokens={len(inv)}"
        )

        # 4. 保存到磁盘
        self._save_lex_index_to_disk()

    @property
    def _lex_index(self) -> Optional[Dict[str, Any]]:
        """获取当前实例的词汇索引"""
        cache = self._lex_index_cache
        if cache:
            return cache.get("index")
        return None

    @property
    def _lex_index_point_count(self) -> Optional[int]:
        """获取当前实例的点数"""
        cache = self._lex_index_cache
        if cache:
            return cache.get("point_count")
        return None

    # ----------------------
    # Keyword search
    # ----------------------
    def keyword_search(self, query: str, top_k: int = 10, k1: float = 1.5, b: float = 0.75) -> List[Dict]:
        """
        BM25-like keyword search over payload Content.
        Returns hits with raw BM25 scores (not normalized).
        """
        if not query or not query.strip():
            return []

        self._maybe_build_lex_index(force=False)
        if not self._lex_index or self._lex_index.get("N", 0) <= 0:
            return []

        idx = self._lex_index
        q_tokens = self._tokenize(query)
        if not q_tokens:
            return []

        N: int = idx["N"]
        inv: Dict[str, List[Tuple[int, int]]] = idx["inv"]
        doc_lens: List[int] = idx["doc_lens"]
        avgdl: float = idx["avgdl"] or 1.0

        scores: Dict[int, float] = defaultdict(float)

        for tok in set(q_tokens):
            postings = inv.get(tok)
            if not postings:
                continue
            df = len(postings)
            # BM25 idf
            idf = math.log(1.0 + (N - df + 0.5) / (df + 0.5))

            for doc_idx, tf in postings:
                dl = doc_lens[doc_idx] if doc_idx < len(doc_lens) else 0
                denom = tf + k1 * (1.0 - b + b * (dl / avgdl))
                score = idf * (tf * (k1 + 1.0) / (denom + 1e-9))
                scores[doc_idx] += score

        if not scores:
            return []

        top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        hits: List[Dict] = []
        for doc_idx, score in top:
            hits.append({
                "id": idx["doc_ids"][doc_idx],
                "payload": idx["payloads"][doc_idx],
                "score": float(score),
                "source": "keyword",
            })
        return hits

    # ----------------------
    # Hybrid search (vector + keyword)
    # ----------------------
    @staticmethod
    def _minmax_norm(values: List[float]) -> Tuple[float, float]:
        if not values:
            return 0.0, 0.0
        return float(min(values)), float(max(values))

    @staticmethod
    def _norm(x: Optional[float], vmin: float, vmax: float) -> float:
        if x is None:
            return 0.0
        if vmax <= vmin:
            return 1.0
        return float((x - vmin) / (vmax - vmin + 1e-9))

    @staticmethod
    def _stable_key(hit: Dict[str, Any]) -> str:
        """
        Prefer qdrant point id; fallback to sha1(Original_file + Content).
        """
        pid = hit.get("id")
        if pid is not None:
            return str(pid)

        payload = hit.get("payload") or {}
        of = str(payload.get("Original_file", ""))
        content = payload.get("Content") or payload.get("content") or ""
        if not isinstance(content, str):
            content = str(content)
        digest = hashlib.sha1((of + "::" + content).encode("utf-8", errors="ignore")).hexdigest()
        return f"sha1::{digest}"

    @staticmethod
    def _apply_dynamic_cut(
        hits: List[Dict[str, Any]],
        min_results: int,
        max_results: int,
        score_threshold: Optional[float],
        auto_min_threshold: float = 0.20,
        auto_delta: float = 0.15,
    ) -> List[Dict[str, Any]]:
        if not hits:
            return []

        hits_sorted = sorted(hits, key=lambda h: float(h.get("score", 0.0)), reverse=True)
        best = float(hits_sorted[0].get("score", 0.0))

        thr = score_threshold
        if thr is None:
            thr = max(auto_min_threshold, best - auto_delta)

        kept = [h for h in hits_sorted if float(h.get("score", 0.0)) >= thr]

        if len(kept) < min_results:
            kept = hits_sorted[:min_results]

        return kept[:max_results]

    def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        *,
        alpha: float = 0.75,
        vector_candidate_k: Optional[int] = None,
        keyword_candidate_k: Optional[int] = None,
        dynamic_topk: bool = True,
        score_threshold: Optional[float] = None,
        max_results: int = 20,
    ) -> List[Dict]:
        """
        Hybrid search:
          - candidates from vector search + keyword search
          - min-max normalize each channel
          - hybrid_score = alpha * vec_norm + (1-alpha) * kw_norm
          - if dynamic_topk: return all above threshold (with cap), else return top_k
        """
        if not query or not query.strip():
            return []

        # candidates sizing
        cand = vector_candidate_k if vector_candidate_k is not None else max(50, top_k * 10)
        cand = min(int(cand), 200)
        kw_cand = keyword_candidate_k if keyword_candidate_k is not None else cand
        kw_cand = min(int(kw_cand), 200)

        vec_hits = self.search(query=query, top_k=cand)
        kw_hits = self.keyword_search(query=query, top_k=kw_cand)

        vec_scores = [float(h.get("score", 0.0)) for h in vec_hits if isinstance(h, dict)]
        kw_scores = [float(h.get("score", 0.0)) for h in kw_hits if isinstance(h, dict)]
        vmin, vmax = self._minmax_norm(vec_scores)
        kmin, kmax = self._minmax_norm(kw_scores)

        merged: Dict[str, Dict[str, Any]] = {}

        def upsert(hit: Dict[str, Any], channel: str):
            key = self._stable_key(hit)
            if key not in merged:
                merged[key] = {
                    "id": hit.get("id"),
                    "payload": hit.get("payload", {}),
                    "vector_score": None,
                    "keyword_score": None,
                    "score": 0.0,
                    "source": "hybrid",
                }
            if channel == "vector":
                merged[key]["vector_score"] = float(hit.get("score", 0.0))
            elif channel == "keyword":
                merged[key]["keyword_score"] = float(hit.get("score", 0.0))

        for h in vec_hits:
            if isinstance(h, dict):
                upsert(h, "vector")
        for h in kw_hits:
            if isinstance(h, dict):
                upsert(h, "keyword")

        hits: List[Dict[str, Any]] = []
        for m in merged.values():
            v = self._norm(m.get("vector_score"), vmin, vmax)
            k = self._norm(m.get("keyword_score"), kmin, kmax)
            m["score"] = float(alpha * v + (1.0 - alpha) * k)
            hits.append(m)

        if not hits:
            return []

        if dynamic_topk:
            return self._apply_dynamic_cut(
                hits=hits,
                min_results=int(top_k),
                max_results=int(max_results),
                score_threshold=score_threshold,
            )

        hits_sorted = sorted(hits, key=lambda h: float(h.get("score", 0.0)), reverse=True)
        return hits_sorted[:int(top_k)]

    # ----------------------
    # Existing utilities
    # ----------------------
    def check_storage(self, limit: int = None) -> List[Dict]:
        """
        Extracts all text fields from data stored in the Qdrant vector database.
        """
        client = self.storage_instance._client
        all_contents = []
        offset_val = None

        while True:
            points, next_page_offset = client.scroll(
                collection_name=self.collection_name,
                with_payload=True,
                with_vectors=False,
                limit=100,
                offset=offset_val
            )

            if points:
                contents = [p.payload for p in points]
                all_contents.extend(contents)

            if not next_page_offset or (limit and len(all_contents) >= limit):
                break

            offset_val = next_page_offset

        return all_contents[:limit] if limit else all_contents

    def delete_or_reset_collection(self, collectionname: str = None, reset: bool = False):
        """
        Deletes or clears a collection in the Qdrant database.
        """
        name = collectionname if collectionname else self.collection_name
        if reset:
            self.storage_instance.clear()
            logger.info(f"Collection '{name}' has been cleared.")
        else:
            self.storage_instance._client.delete_collection(collection_name=name)
            logger.info(f"Collection '{name}' has been deleted.")

    def delete_by_file_name(self, file_tag: str) -> List[str]:
        """
        根据入库时记录的 file_tag 删除数据库中的所有切块。
        返回被删除的 point_ids 列表。
        """
        from qdrant_client import models
        client = self.storage_instance._client

        logger.info(f"正在从 Qdrant 清理标签为: {file_tag} 的数据...")

        deleted_ids: List[str] = []
        try:
            # 1. 先获取要删除的 point_ids
            points_to_delete = client.scroll(
                collection_name=self.collection_name,
                scroll_filter=models.Filter(
                    must=[models.FieldCondition(
                        key="Original_file",
                        match=models.MatchValue(value=file_tag)
                    )]
                ),
                with_payload=False,
                with_vectors=False,
                limit=10000
            )[0]
            deleted_ids = [str(p.id) for p in points_to_delete]
            logger.info(f"找到 {len(deleted_ids)} 个待删除点")

            # 2. 执行删除
            client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="Original_file",
                                match=models.MatchValue(value=file_tag),
                            ),
                        ]
                    )
                ),
            )

            # 3. 增量更新词汇索引
            if deleted_ids and self._lex_index_cache:
                self._update_lex_index_for_deleted_points(deleted_ids)

            logger.info("数据库切块清理完毕。")
        except Exception as e:
            logger.error(f"数据库清理失败: {e}")

        return deleted_ids
