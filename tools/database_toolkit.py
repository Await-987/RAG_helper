import sys
import re
from loguru import logger
from typing import List, Optional, Any, Dict, Callable

from camel.toolkits.base import BaseToolkit, FunctionTool
from tools import QdrantDB, QdrantDB_Init


def _log_search(msg: str):
    """同时输出到 logger 和 print，确保日志可见"""
    logger.info(msg)
    print(msg)
    sys.stdout.flush()


class DatabaseToolkit(BaseToolkit):
    """A toolkit for retrieving information from your local Qdrant knowledge base."""

    DEFAULT_CANDIDATE_LIMIT = 20
    DEFAULT_FINAL_FULL_CHUNKS = 4
    DEFAULT_MAX_TOTAL_CHARS = 12000
    DEFAULT_MAX_CHARS_PER_CHUNK = 3200
    TABLE_QUERY_HINTS = ("表", "表格", "议程", "清单", "名单", "名录", "统计", "汇总")
    NUMERIC_QUERY_HINTS = (
        "多少", "多大", "参数", "电压", "电流", "容量", "功率", "温度",
        "压力", "频率", "比率", "百分比", "阈值", "上限", "下限", "范围",
        "数值", "系数", "等级", "尺寸", "长度",
    )
    NUMERIC_CONTENT_RE = re.compile(
        r"(\d+(?:\.\d+)?)\s*(kV|V|A|mA|MW|kW|W|Hz|%|℃|°C|mm|cm|m|km|kg|t|MPa|kPa|年|月|日|h|min|s|次|项|条|章)?",
        re.IGNORECASE,
    )

    def __init__(self):
        super().__init__()
        qdrant_init = QdrantDB_Init(collection_name="database")
        self.db = QdrantDB(input=qdrant_init)
        self._reranker = None  # lazy-load
        self._index_warmed_up = False  # 索引预热标志
        # 由 ChatService 注入的回调，签名: (session_id: str) -> set
        self._get_seen_keys_fn: Optional[Callable[[str], Optional[set]]] = None
        # 当前请求的 session_id（由 stream_chat 在调用前设置）
        self._current_session_id: Optional[str] = None

    def set_session_callbacks(
        self,
        get_seen_keys_fn: Callable[[str], Optional[set]],
    ) -> None:
        """
        由 ChatService 在初始化时注入回调，用于读取当前 session 的 seen_keys。
        toolkit 本身不存状态，所有 session 状态由 ChatService 管理。
        """
        self._get_seen_keys_fn = get_seen_keys_fn

    def set_current_session_id(self, session_id: Optional[str]) -> None:
        """由 stream_chat 在每次请求开始时设置当前 session_id。"""
        self._current_session_id = session_id

    def _get_seen_keys(self) -> Optional[set]:
        """获取当前 session 的 seen_keys，通过注入的回调从 ChatService 读取。"""
        if self._get_seen_keys_fn is None or self._current_session_id is None:
            return None
        return self._get_seen_keys_fn(self._current_session_id)

    def warmup_lexical_index(self):
        """预热词汇索引和 reranker 模型，避免首次搜索时长时间等待。"""
        if self._index_warmed_up:
            return
        logger.info("🔥 开始预热词汇索引...")
        try:
            self.db._maybe_build_lex_index(force=False)
            self._index_warmed_up = True
            logger.info("✅ 词汇索引预热完成")
        except Exception as e:
            logger.warning(f"⚠️ 词汇索引预热失败: {e}")
        logger.info("🔥 开始预热 Reranker 模型...")
        try:
            self._get_reranker()
            if self._reranker is not None:
                logger.info("✅ Reranker 模型预热完成")
            else:
                logger.info("ℹ️ Reranker 未配置，跳过")
        except Exception as e:
            logger.warning(f"⚠️ Reranker 预热失败: {e}")

    def close(self):
        """Close the database connection"""
        if hasattr(self, 'db'):
            self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def _get_reranker(self):
        if self._reranker is not None:
            return self._reranker
        try:
            from agents.backend_model import backend_reranker_model
            self._reranker = backend_reranker_model()
        except Exception as e:
            logger.warning(f"Failed to init reranker: {e}")
            self._reranker = None
        return self._reranker

    @staticmethod
    def _minmax_norm(vals: List[float]) -> List[float]:
        if not vals:
            return []
        vmin, vmax = min(vals), max(vals)
        if vmax <= vmin:
            return [1.0 for _ in vals]
        return [(v - vmin) / (vmax - vmin + 1e-9) for v in vals]

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
        thr = score_threshold if score_threshold is not None else max(auto_min_threshold, best - auto_delta)
        kept = [h for h in hits_sorted if float(h.get("score", 0.0)) >= thr]
        if len(kept) < min_results:
            kept = hits_sorted[:min_results]
        return kept[:max_results]

    def _rerank(
        self,
        query: str,
        hits: List[Dict[str, Any]],
        intent_description: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Rerank by CrossEncoder if available."""
        reranker = self._get_reranker()
        if reranker is None or not hits:
            return hits

        rerank_text = intent_description if intent_description else query
        pairs = []
        valid_hits = []
        for h in hits:
            payload = h.get("payload", {}) or {}
            metadata = payload.get("metadata", {}) or {}
            content = (
                metadata.get("child_content")
                or payload.get("child_content")
                or payload.get("Content")
                or payload.get("content")
                or ""
            )
            if not isinstance(content, str):
                content = str(content)
            content = content.strip()
            if not content:
                continue
            pairs.append((rerank_text, content))
            valid_hits.append(h)

        if not valid_hits:
            return hits

        try:
            scores = reranker.predict(pairs)
            scores = [float(s) for s in list(scores)]
        except Exception as e:
            logger.warning(f"Reranker predict failed, fallback to hybrid order: {e}")
            return hits

        norm_scores = DatabaseToolkit._minmax_norm(scores)
        for h, s_raw, s_norm in zip(valid_hits, scores, norm_scores):
            h["rerank_score_raw"] = s_raw
            h["score"] = float(s_norm)

        rest = [h for h in hits if h not in valid_hits]
        out = sorted(valid_hits, key=lambda x: float(x.get("score", 0.0)), reverse=True) + rest

        # 父子chunk架构去重：同一父chunk只保留分数最高的那条
        seen_content: set = set()
        deduped = []
        for h in out:
            payload = h.get("payload", {}) or {}
            content = payload.get("Content", "") or payload.get("content", "")
            if content not in seen_content:
                seen_content.add(content)
                deduped.append(h)
        return deduped

    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + "\n...[内容过长，已截断]"

    @classmethod
    def _is_table_like_query(cls, query: str) -> bool:
        query = (query or "").strip()
        if not query:
            return False
        return any(token in query for token in cls.TABLE_QUERY_HINTS)

    @classmethod
    def _is_numeric_like_query(cls, query: str) -> bool:
        query = (query or "").strip()
        if not query:
            return False
        if cls.NUMERIC_CONTENT_RE.search(query):
            return True
        return any(token in query for token in cls.NUMERIC_QUERY_HINTS)

    @classmethod
    def _hit_parent_key(cls, hit: Dict[str, Any]) -> str:
        payload = hit.get("payload", {}) or {}
        source = str(payload.get("Original_file", ""))
        content = payload.get("Content", "") or payload.get("content", "")
        return f"{source}::{content}"

    @classmethod
    def _hit_evidence_key(cls, hit: Dict[str, Any]) -> str:
        payload = hit.get("payload", {}) or {}
        metadata = payload.get("metadata", {}) or {}
        source = str(payload.get("Original_file", ""))
        page = metadata.get("page") or payload.get("page") or ""
        chunk_index = metadata.get("chunk_index")
        content = payload.get("Content", "") or payload.get("content", "")
        if isinstance(chunk_index, int):
            return f"{source}::page={page}::chunk={chunk_index}"
        return f"{source}::{content}"

    @classmethod
    def _hit_has_numeric_content(cls, hit: Dict[str, Any]) -> bool:
        payload = hit.get("payload", {}) or {}
        metadata = payload.get("metadata", {}) or {}
        text = (
            metadata.get("child_content")
            or payload.get("child_content")
            or payload.get("Content")
            or payload.get("content")
            or ""
        )
        if not isinstance(text, str):
            text = str(text)
        return bool(cls.NUMERIC_CONTENT_RE.search(text))

    @classmethod
    def _apply_query_type_bias(
        cls, hits: List[Dict[str, Any]], query: str
    ) -> List[Dict[str, Any]]:
        if not hits:
            return []
        is_table_query = cls._is_table_like_query(query)
        is_numeric_query = cls._is_numeric_like_query(query)
        if not is_table_query and not is_numeric_query:
            return hits
        adjusted: List[Dict[str, Any]] = []
        for hit in hits:
            h = dict(hit)
            payload = h.get("payload", {}) or {}
            metadata = payload.get("metadata", {}) or {}
            score = float(h.get("score", 0.0))
            if is_table_query and (payload.get("is_table") or metadata.get("is_table")):
                score += 0.18
            if is_numeric_query and cls._hit_has_numeric_content(h):
                score += 0.12
            h["score"] = score
            adjusted.append(h)
        adjusted.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
        return adjusted

    @classmethod
    def _dedupe_by_parent(
        cls, hits: List[Dict[str, Any]], max_per_parent: int = 1
    ) -> List[Dict[str, Any]]:
        """同一父文档内只保留得分最高的 max_per_parent 条。"""
        if not hits:
            return []
        kept: List[Dict[str, Any]] = []
        parent_counts: Dict[str, int] = {}
        for hit in hits:
            parent_key = cls._hit_parent_key(hit)
            current = parent_counts.get(parent_key, 0)
            if current >= max_per_parent:
                continue
            parent_counts[parent_key] = current + 1
            kept.append(hit)
        return kept

    def _expand_neighbor_context(
        self, hit: Dict[str, Any], neighbor_window: int = 1
    ) -> Dict[str, Any]:
        """将命中 chunk 的相邻 chunk 内容合并，扩展上下文窗口。"""
        payload = hit.get("payload", {}) or {}
        metadata = payload.get("metadata", {}) or {}

        if payload.get("is_table") or metadata.get("is_table"):
            return hit

        file_tag = payload.get("Original_file")
        chunk_index = metadata.get("chunk_index")
        if not file_tag or not isinstance(chunk_index, int):
            return hit

        neighbors = self.db.get_adjacent_chunks(
            file_tag=file_tag,
            chunk_index=chunk_index,
            window=neighbor_window,
        )
        if len(neighbors) <= 1:
            return hit

        ordered_contents: List[str] = []
        for neighbor in neighbors:
            neighbor_payload = neighbor.get("payload", {}) or {}
            c = neighbor_payload.get("Content", "") or neighbor_payload.get("content", "")
            if not isinstance(c, str):
                c = str(c)
            c = c.strip()
            if c:
                ordered_contents.append(c)

        if not ordered_contents:
            return hit

        expanded = dict(hit)
        expanded_payload = dict(payload)
        expanded_payload["Content"] = "\n".join(ordered_contents)
        expanded_payload["neighbor_expanded"] = True
        expanded["payload"] = expanded_payload
        return expanded

    def _filter_seen_turn_evidence(
        self, hits: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        过滤本 session 内已返回过的证据块。
        seen_keys 由 ChatService 管理，通过注入的回调读取。
        """
        seen_keys = self._get_seen_keys()
        if seen_keys is None:
            _log_search("\u26a0\ufe0f seen_keys \u4e3a None\uff0c\u8df3\u8fc7\u53bb\u91cd")
            return hits

        _log_search(
            f"\U0001f50d _filter_seen_turn_evidence: seen_keys={len(seen_keys)}, hits={len(hits)}"
        )
        fresh_hits: List[Dict[str, Any]] = []
        for hit in hits:
            key = self._hit_evidence_key(hit)
            if key in seen_keys:
                _log_search(f"  [\u91cd\u590d] {key[:80]}")
                continue
            fresh_hits.append(hit)

        for hit in fresh_hits:
            seen_keys.add(self._hit_evidence_key(hit))
            _log_search(f"  [\u65b0\u589e] {self._hit_evidence_key(hit)[:80]}")

        _log_search(
            f"\U0001f4ca \u53bb\u91cd\u7ed3\u679c: \u65b0\u589e {len(fresh_hits)} \u6761, "
            f"\u91cd\u590d {len(hits) - len(fresh_hits)} \u6761"
        )
        return fresh_hits

    def _select_full_chunk_hits(
        self,
        hits: List[Dict[str, Any]],
        *,
        full_chunk_limit: int,
        max_total_chars: int,
        max_chars_per_chunk: int,
    ) -> List[Dict[str, Any]]:
        """\u4fdd\u7559\u6700\u9ad8\u7f6e\u4fe1\u5ea6\u7684\u82e5\u5e72\u6761\uff0c\u63a7\u5236\u603b\u5b57\u7b26\u9884\u7b97\u3002"""
        selected: List[Dict[str, Any]] = []
        total_chars = 0
        for hit in hits:
            if len(selected) >= full_chunk_limit:
                break
            payload = hit.get("payload", {}) or {}
            content = payload.get("Content", "") or payload.get("content", "")
            if not isinstance(content, str):
                content = str(content)
            content = content.strip()
            if not content:
                continue
            content_chars = min(len(content), max_chars_per_chunk)
            if selected and total_chars + content_chars > max_total_chars:
                continue
            selected.append(hit)
            total_chars += content_chars
        if not selected and hits:
            selected = hits[:1]
        _log_search(
            f"\U0001f9e0 \u8bc1\u636e\u6536\u7f29: \u5019\u9009 {len(hits)} \u6761 -> \u5b8c\u6574\u539f\u6587 {len(selected)} \u6761, "
            f"\u603b\u5b57\u7b26\u9884\u7b97 {max_total_chars}, \u5355\u6761\u4e0a\u9650 {max_chars_per_chunk}"
        )
        return selected

    def search_database(
        self,
        query: str,
        intent_description: Optional[str] = None,
        **kwargs,
    ) -> str:
        """\u68c0\u7d22\u672c\u5730\u7535\u529b\u7cfb\u7edf\u77e5\u8bc6\u5e93\u7684\u5de5\u5177\u3002

        Args:
            query: \u7b80\u5316\u540e\u7684\u641c\u7d22 query\uff083-8 \u4e2a\u6838\u5fc3\u5173\u952e\u8bcd\uff09
            intent_description: \u7528\u6237\u771f\u5b9e\u610f\u56fe\u7684\u5b8c\u6574\u63cf\u8ff0\uff08\u7528\u4e8e\u91cd\u6392\u5e8f\uff09

        Returns:
            \u683c\u5f0f\u5316\u7684\u641c\u7d22\u7ed3\u679c\u5b57\u7b26\u4e32
        """
        return self._search_database(
            query=query, intent_description=intent_description, **kwargs
        )

    def _search_database(
        self,
        query: str,
        intent_description: Optional[str] = None,
        top_k: int = 8,
        *,
        use_hybrid: bool = True,
        use_rerank: bool = True,
        dynamic_topk: bool = True,
        score_threshold: Optional[float] = None,
        max_results: int = 12,
        alpha: float = 0.75,
        restore_table_context: bool = False,
        candidate_top_k: int = DEFAULT_CANDIDATE_LIMIT,
        full_chunk_limit: int = DEFAULT_FINAL_FULL_CHUNKS,
        max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
        max_chars_per_chunk: int = DEFAULT_MAX_CHARS_PER_CHUNK,
        max_per_parent: int = 1,
        neighbor_window: int = 1,
    ) -> str:
        # ===== \u53c2\u6570\u9632\u5fa1 =====
        if alpha is None: alpha = 0.75
        if max_results is None: max_results = 12
        if candidate_top_k is None: candidate_top_k = self.DEFAULT_CANDIDATE_LIMIT
        if full_chunk_limit is None: full_chunk_limit = self.DEFAULT_FINAL_FULL_CHUNKS
        if max_total_chars is None: max_total_chars = self.DEFAULT_MAX_TOTAL_CHARS
        if max_chars_per_chunk is None: max_chars_per_chunk = self.DEFAULT_MAX_CHARS_PER_CHUNK

        top_k = max(1, int(top_k))
        candidate_top_k = max(top_k, int(candidate_top_k))
        full_chunk_limit = max(1, min(int(full_chunk_limit), top_k))
        max_results = max(top_k, int(max_results))
        max_total_chars = max(1000, int(max_total_chars))
        max_chars_per_chunk = max(500, int(max_chars_per_chunk))

        if self._is_table_like_query(query):
            full_chunk_limit = max(full_chunk_limit, min(top_k, 5))
            max_total_chars = max(max_total_chars, 8000)
            max_chars_per_chunk = max(max_chars_per_chunk, 2400)
            restore_table_context = True

        if dynamic_topk:
            max_results = max(int(max_results), candidate_top_k)

        sep = "=" * 60
        _log_search("\n" + sep)
        _log_search("\U0001f50d [\u641c\u7d22\u5de5\u5177\u88ab\u8c03\u7528]")
        q_preview = query[:80] + ("..." if len(query) > 80 else "")
        _log_search(f"   query: '{q_preview}'")
        if intent_description:
            i_preview = intent_description[:80] + ("..." if len(intent_description) > 80 else "")
            _log_search(f"   intent: '{i_preview}'")
        _log_search(
            f"   hybrid={use_hybrid}, rerank={use_rerank}, "
            f"dynamic={dynamic_topk}, alpha={alpha}"
        )
        _log_search(sep + "\n")

        if not query or not query.strip():
            logger.warning("\u26a0\ufe0f \u641c\u7d22 query \u4e3a\u7a7a")
            return "No results from the vector database."

        # Step 1: \u68c0\u7d22
        if use_hybrid:
            _log_search("\U0001f4ca \u6267\u884c\u6df7\u5408\u641c\u7d22 (vector + BM25)...")
            hits = self.db.hybrid_search(
                query=query, top_k=candidate_top_k, alpha=alpha,
                dynamic_topk=False, score_threshold=score_threshold,
                max_results=max_results,
            )
        else:
            _log_search("\U0001f4ca \u6267\u884c\u7eaf\u5411\u91cf\u641c\u7d22...")
            hits = self.db.search(query=query, top_k=candidate_top_k)

        if not hits:
            return "No results from the vector database."

        # Step 2: Rerank + \u52a8\u6001\u9600\u5024
        if use_rerank:
            _log_search("\U0001f504 \u6267\u884c\u91cd\u6392\u5e8f (reranker)...")
            hits = self._rerank(query, hits, intent_description=intent_description)
            if dynamic_topk:
                hits = DatabaseToolkit._apply_dynamic_cut(
                    hits=hits, min_results=int(top_k),
                    max_results=int(candidate_top_k),
                    score_threshold=score_threshold,
                )
        else:
            hits = sorted(
                hits, key=lambda h: float(h.get("score", 0.0)), reverse=True
            )[:int(candidate_top_k)]

        # Step 3-6: \u540e\u5904\u7406
        hits = self._apply_query_type_bias(hits, query)
        hits = self._dedupe_by_parent(hits, max_per_parent=max_per_parent)
        if neighbor_window > 0:
            hits = [
                self._expand_neighbor_context(hit, neighbor_window=neighbor_window)
                for hit in hits
            ]
        hits = self._select_full_chunk_hits(
            hits, full_chunk_limit=full_chunk_limit,
            max_total_chars=max_total_chars, max_chars_per_chunk=max_chars_per_chunk,
        )

        # Step 7: Session \u7ea7\u53bb\u91cd
        hits = self._filter_seen_turn_evidence(hits)
        if not hits:
            _log_search("\u267b\ufe0f \u672c\u8f6e\u540e\u7eed\u68c0\u7d22\u672a\u53d1\u73b0\u65b0\u589e\u8bc1\u636e")
            return "No new results from the vector database in this turn."

        _log_search(f"\u2705 \u641c\u7d22\u5b8c\u6210: \u6700\u7ec8\u8fd4\u56de {len(hits)} \u6761\u7ed3\u679c")

        # Step 8: \u683c\u5f0f\u5316\u8f93\u51fa
        formatted_results = []
        for hit in hits:
            payload = hit.get("payload", {}) or {}
            metadata = payload.get("metadata", {}) or {}
            source = payload.get("Original_file", "Unknown Source")
            content = payload.get("Content", "") or payload.get("content", "")
            score = float(hit.get("score", 0.0))

            if restore_table_context and (
                payload.get("is_table") or metadata.get("is_table")
            ):
                ctx_before = (
                    payload.get("context_before", "")
                    or metadata.get("context_before", "")
                )
                ctx_after = (
                    payload.get("context_after", "")
                    or metadata.get("context_after", "")
                )
                if ctx_before or ctx_after:
                    content = (ctx_before + "\n" + content + "\n" + ctx_after).strip()

            content = DatabaseToolkit._truncate_text(content, max_chars_per_chunk)
            formatted_results.append(
                "File: " + source + "\n"
                + "Content: \n---\n" + content + "\n---\n"
                + "Confidence: " + f"{score:.4f}"
            )

        _log_search("\n" + sep)
        _log_search(f"\U0001f4cb [\u641c\u7d22\u7ed3\u679c\u6458\u8981] \u5171 {len(formatted_results)} \u6761")
        for i, hit in enumerate(hits[:5], 1):
            payload = hit.get("payload", {}) or {}
            source = payload.get("Original_file", "Unknown")
            content = payload.get("Content", "") or payload.get("content", "")
            score = float(hit.get("score", 0.0))
            file_name = (
                source.split("\\")[-1] if "\\" in source else source.split("/")[-1]
            )
            content_preview = content.replace("\n", " ").strip()[:100]
            if len(content) > 100:
                content_preview += "..."
            _log_search(f"   [{i}] \U0001f4c4 {file_name} | \U0001f3af {score:.4f}")
            _log_search(f"       {content_preview}")
        if len(hits) > 5:
            _log_search(f"   ... \u8fd8\u67096 {len(hits) - 5} \u6761")
        _log_search(sep + "\n")

        return "\n\n".join(formatted_results)

    def get_tools(self) -> List[FunctionTool]:
        return [FunctionTool(self.search_database)]
