import os
import sys
import time
import math
import re
import hashlib
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
        storages_dir = os.path.join(BASE_DIR, "data", "storages")
        os.makedirs(storages_dir, exist_ok=True)
        self.storage_path = storages_dir

        try:
            from agents.backend_model import backend_embedding_model
            self.embedding_instance = backend_embedding_model()
        except Exception as e:
            raise Exception(f"Failed to initialize embedding model via API: {e}")

        self.collection_name = input.collection_name

        try:
            vector_dim = self.embedding_instance.get_output_dim()
            self.storage_instance = QdrantStorage(
                vector_dim=vector_dim,
                path=self.storage_path,
                collection_name=self.collection_name
            )
        except Exception as e:
            raise Exception(f"QdrantStorage initialization failed: {e}")

        # ---------- keyword index cache ----------
        self._lex_index: Optional[Dict[str, Any]] = None
        self._lex_index_point_count: Optional[int] = None
        self._lex_index_built_at: float = 0.0
        # TTL: avoid rebuilding too often even if count() flaky; can override via env
        self._lex_index_ttl_sec: int = int(os.getenv("LEX_INDEX_TTL_SEC", "60"))

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
    def save2Qdrant(self, input: save2Qdrant_Input, vector_text: Optional[str] = None):
        """
        Input text and store the text data along with its source information into the Qdrant database.
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
        logger.info(f"嵌入向量生成完成，维度: {len(vectors[0]) if vectors else 'N/A'}")

        for vector, text_chunk in zip(vectors, texts_to_embed):
            payload = base_payload.copy()
            payload["Content"] = text_chunk
            record = VectorRecord(vector=vector, payload=payload)
            records.append(record)

        if records:
            self.storage_instance.add(records)

        # ingestion changed collection -> invalidate keyword index lazily
        self._lex_index = None
        self._lex_index_point_count = None
        self._lex_index_built_at = 0.0

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

    def _maybe_build_lex_index(self, force: bool = False):
        """
        Build / refresh lexical inverted index if:
        - force=True
        - index is missing
        - point count changed
        - TTL expired
        """
        now = time.time()
        if not force and self._lex_index is not None:
            # TTL guard
            if (now - self._lex_index_built_at) < self._lex_index_ttl_sec:
                # if count unchanged, keep
                current_cnt = self._get_collection_point_count()
                if current_cnt is None or current_cnt == self._lex_index_point_count:
                    return

        current_cnt = self._get_collection_point_count()
        if not force and self._lex_index is not None and current_cnt is not None:
            if self._lex_index_point_count == current_cnt and (now - self._lex_index_built_at) < self._lex_index_ttl_sec:
                return

        logger.info(f"Building lexical index for collection='{self.collection_name}' ...")
        points = self._scroll_points()

        doc_ids: List[Any] = []
        payloads: List[Dict[str, Any]] = []
        doc_lens: List[int] = []
        inv: Dict[str, List[Tuple[int, int]]] = defaultdict(list)  # token -> [(doc_idx, tf)]

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

            doc_ids.append(pid)
            payloads.append(payload)
            doc_lens.append(sum(tf.values()))

            for tok, freq in tf.items():
                inv[tok].append((doc_idx, int(freq)))

        avgdl = (sum(doc_lens) / len(doc_lens)) if doc_lens else 1.0
        self._lex_index = {
            "doc_ids": doc_ids,
            "payloads": payloads,
            "doc_lens": doc_lens,
            "avgdl": float(avgdl),
            "inv": inv,
            "N": int(len(doc_ids)),
        }
        self._lex_index_point_count = current_cnt
        self._lex_index_built_at = now

        logger.info(
            f"Lexical index ready: docs={len(doc_ids)}, avgdl={avgdl:.2f}, tokens={len(inv)}"
        )

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

    def delete_by_file_name(self, file_tag: str):
        """根据入库时记录的 file_tag 删除数据库中的所有切块"""
        from qdrant_client import models
        client = self.storage_instance._client

        logger.info(f"正在从 Qdrant 清理标签为: {file_tag} 的数据...")
        try:
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
            self._lex_index = None  # 清除关键词索引缓存
            logger.info("数据库切块清理完毕。")
        except Exception as e:
            logger.error(f"数据库清理失败: {e}")