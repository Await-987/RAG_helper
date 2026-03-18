# -*- coding: utf-8 -*-
import sys
import threading
import re
from loguru import logger
from typing import List, Optional, Any, Dict

from camel.toolkits.base import BaseToolkit, FunctionTool
from tools import QdrantDB, QdrantDB_Init


def _log_search(msg: str):
    """同时输出到 logger 和 print，确保日志可见"""
    logger.info(msg)
    print(msg)
    sys.stdout.flush()


_thread_local = threading.local()


def _get_turn_seen_keys():
    return getattr(_thread_local, 'seen_keys', None)


def _set_turn_seen_keys(s):
    _thread_local.seen_keys = s


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

    def warmup_lexical_index(self):
        """
        预热词汇索引和 reranker 模型，避免首次搜索时长时间等待。
        应在服务启动时调用。
        """
        if self._index_warmed_up:
            return

        logger.info("🔥 开始预热词汇索引...")
        try:
            # 触发索引构建
            self.db._maybe_build_lex_index(force=False)
            self._index_warmed_up = True
            logger.info("✅ 词汇索引预热完成")
        except Exception as e:
            logger.warning(f"⚠️ 词汇索引预热失败: {e}")

        # 同时预热 reranker 模型
        logger.info("🔥 开始预热 Reranker 模型...")
        try:
            self._get_reranker()  # 触发 lazy-load
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

    def begin_turn(self) -> None:
        """Start per-turn evidence dedup state."""
        self._turn_seen_keys: set = set()

    def end_turn(self) -> None:
        """Clear per-turn evidence dedup state."""
        self._turn_seen_keys = set()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def _get_reranker(self):
        """
        Optional reranker (cross-encoder). If not configured, returns None.
        Controlled by env var `reranker_path`.
        """
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

    def _rerank(self, query: str, hits: List[Dict[str, Any]], intent_description: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Rerank by CrossEncoder if available.
        We normalize rerank scores to 0~1 and overwrite hit['score'] for final sorting.

        @shengwanying：20260306修改：rerank用子chunk，精度更高
        @shengwanying：20260313修改：支持用意图描述进行重排，而不是简化后的query
        
        Args:
            query: 简化后的搜索query（用于日志）
            hits: 候选结果列表
            intent_description: 用户真实意图的完整描述（用于重排），消除代词、补全背景主体
                如果为None则使用query
        """
        reranker = self._get_reranker()
        if reranker is None or not hits:
            return hits

        # 使用意图描述进行重排，如果没有则使用query
        rerank_text = intent_description if intent_description else query

        pairs = []
        valid_hits = []
        for h in hits:
            payload = h.get("payload", {}) or {}
            # 优先使用 child_content（子chunk），fallback 到 Content
            # 注意：child_content 可能在 payload.metadata 中或 payload 顶级
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
            h["score"] = float(s_norm)  # final score for sorting

        # keep non-valid hits at the end
        rest = [h for h in hits if h not in valid_hits]
        out = sorted(valid_hits, key=lambda x: float(x.get("score", 0.0)), reverse=True) + rest

        # @shengwanying：20260306修改：父子chunk架构去重
        # 同一个父chunk可能被多个子chunk命中，这里按Content去重，只保留分数最高的那条
        seen_content = set()
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
    def _apply_query_type_bias(cls, hits: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
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
    def _dedupe_by_parent(cls, hits: List[Dict[str, Any]], max_per_parent: int = 1) -> List[Dict[str, Any]]:
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

    def _expand_neighbor_context(self, hit: Dict[str, Any], neighbor_window: int = 1) -> Dict[str, Any]:
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
            content = neighbor_payload.get("Content", "") or neighbor_payload.get("content", "")
            if not isinstance(content, str):
                content = str(content)
            content = content.strip()
            if content:
                ordered_contents.append(content)

        if not ordered_contents:
            return hit

        expanded = dict(hit)
        expanded_payload = dict(payload)
        expanded_payload["Content"] = "\n".join(ordered_contents)
        expanded_payload["neighbor_expanded"] = True
        expanded["payload"] = expanded_payload
        return expanded

    def _filter_seen_turn_evidence(self, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen_keys = getattr(self, '_turn_seen_keys', None)
        if seen_keys is None:
            return hits

        fresh_hits: List[Dict[str, Any]] = []
        for hit in hits:
            evidence_key = self._hit_evidence_key(hit)
            if evidence_key in seen_keys:
                continue
            fresh_hits.append(hit)

        _log_search(
            f"🔍 去重过滤: 候选 {len(hits)} 条 -> 新增 {len(fresh_hits)} 条"
            f"（已见 {len(hits) - len(fresh_hits)} 条重复）"
        )
        for hit in fresh_hits:
            payload = hit.get("payload", {}) or {}
            source = payload.get("Original_file", "Unknown")
            file_name = source.split("\\")[-1] if "\\" in source else source.split("/")[-1]
            content = payload.get("Content", "") or payload.get("content", "")
            preview = content.replace("\n", " ").strip()[:60]
            _log_search(f"  [新] 📄 {file_name} | {preview}...")

        if fresh_hits:
            for hit in fresh_hits:
                seen_keys.add(self._hit_evidence_key(hit))
            return fresh_hits

        return []

    def _select_full_chunk_hits(
        self,
        hits: List[Dict[str, Any]],
        *,
        full_chunk_limit: int,
        max_total_chars: int,
        max_chars_per_chunk: int,
    ) -> List[Dict[str, Any]]:
        """
        Keep only a few highest-confidence chunks, while preserving their original content.
        This balances answer fidelity and context budget.
        """
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
            f"🧠 证据收缩: 候选 {len(hits)} 条 -> 完整原文 {len(selected)} 条, "
            f"总字符预算 {max_total_chars}, 单条上限 {max_chars_per_chunk}"
        )
        return selected

    def search_database(self, query: str, intent_description: Optional[str] = None, **kwargs) -> str:
        """检索本地电力系统知识库的工具。
        Agent-friendly entrypoint：仅需传入 query 和 intent_description。
        
        Args:
            query: 简化后的搜索query（3-8个核心关键词，用于向量检索）
            intent_description: 用户真实意图的完整描述（用于重排序，消除代词、补全背景主体）
                应该是一个完整的自然语言句子，最接近用户的真实意图。
                如果为None，重排序将使用query。建议总是传入意图描述以获得更好的重排准确性。
        
        Returns:
            格式化的搜索结果字符串
        
        Note:
            其他参数（如 top_k、max_results 等）使用默认值，无需传入。
        """
        return self._search_database(query=query, intent_description=intent_description, **kwargs)

    def _search_database(
        self,
        query: str,
        intent_description: Optional[str] = None,
        top_k: int = 8,
        seen_keys: Optional[set] = None,
        *,
        # ---- new knobs (all optional; keep old usage compatible) ----
        use_hybrid: bool = True,
        use_rerank: bool = True,
        dynamic_topk: bool = True,
        score_threshold: Optional[float] = None,
        max_results: int = 12,
        alpha: float = 0.75,
        restore_table_context: bool = False,  # 是否恢复表格上下文
        candidate_top_k: int = DEFAULT_CANDIDATE_LIMIT,
        full_chunk_limit: int = DEFAULT_FINAL_FULL_CHUNKS,
        max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
        max_chars_per_chunk: int = DEFAULT_MAX_CHARS_PER_CHUNK,
        max_per_parent: int = 1,
        neighbor_window: int = 1,
    ) -> str:
        """
        Hybrid retrieval within local database.

        - use_hybrid=True: vector + keyword (BM25-like) fusion
        - use_rerank=True: optional cross-encoder rerank (if env `reranker_path` set)
        - dynamic_topk=True: return all chunks above threshold (capped by max_results)
          score_threshold is on normalized score (0~1). If None, an adaptive threshold is used.
        - restore_table_context=True: 检索到表格时，合并上下文返回
        """
        # ===== 参数默认值处理 =====
        # 如果 LLM 传入 None，使用默认值
        if alpha is None:
            alpha = 0.75
        if max_results is None:
            max_results = 12
        if candidate_top_k is None:
            candidate_top_k = self.DEFAULT_CANDIDATE_LIMIT
        if full_chunk_limit is None:
            full_chunk_limit = self.DEFAULT_FINAL_FULL_CHUNKS
        if max_total_chars is None:
            max_total_chars = self.DEFAULT_MAX_TOTAL_CHARS
        if max_chars_per_chunk is None:
            max_chars_per_chunk = self.DEFAULT_MAX_CHARS_PER_CHUNK

        top_k = max(1, int(top_k))
        candidate_top_k = max(top_k, int(candidate_top_k))
        full_chunk_limit = max(1, min(int(full_chunk_limit), top_k))
        max_results = max(top_k, int(max_results))
        max_total_chars = max(1000, int(max_total_chars))
        max_chars_per_chunk = max(500, int(max_chars_per_chunk))

        # 表格/议程类问题对证据长度敏感，避免模型传入过小预算导致表格被截断。
        if self._is_table_like_query(query):
            full_chunk_limit = max(full_chunk_limit, min(top_k, 5))
            max_total_chars = max(max_total_chars, 8000)
            max_chars_per_chunk = max(max_chars_per_chunk, 2400)
            restore_table_context = True

        # ===== 搜索开始日志 =====
        _log_search(f"\n{'='*60}")
        _log_search(f"🔍 [搜索工具被调用]")
        _log_search(f"   query: '{query[:80]}{'...' if len(query) > 80 else ''}'")
        if intent_description:
            _log_search(f"   intent_description: '{intent_description[:80]}{'...' if len(intent_description) > 80 else ''}'")
        _log_search(
            f"   配置: hybrid={use_hybrid}, rerank={use_rerank}, dynamic={dynamic_topk}, alpha={alpha}"
        )
        _log_search(
            f"   预算: max_total_chars={max_total_chars}, "
            f"max_chars_per_chunk={max_chars_per_chunk}, "
            f"restore_table_context={restore_table_context}"
        )
        _log_search(f"{'='*60}\n")

        # 放在 search_database() 开头，参数校正
        if dynamic_topk:
            max_results = max(int(max_results), candidate_top_k)

        if not query or not query.strip():
            logger.warning("⚠️ 搜索 query 为空，返回无结果")
            return "No results from the vector database."

        # 1) hybrid or vector-only
        if use_hybrid:
            _log_search(f"📊 执行混合搜索 (vector + keyword BM25)...")
            hits = self.db.hybrid_search(
                query=query,
                top_k=candidate_top_k,
                alpha=alpha,
                dynamic_topk=False,
                score_threshold=score_threshold,
                max_results=max_results,
            )
        else:
            _log_search(f"📊 执行纯向量搜索...")
            hits = self.db.search(query=query, top_k=candidate_top_k)

        if not hits:
            return "No results from the vector database."

        # 2) rerank (optional)
        if use_rerank:
            _log_search(f"🔄 执行重排序 (reranker)...")
            hits = self._rerank(query, hits, intent_description=intent_description)

            # 3) dynamic threshold cut should use final scores (after rerank)
            if dynamic_topk:
                _log_search(
                    f"✂️ 执行动态阈值过滤 (min_results={top_k}, max_results={candidate_top_k})..."
                )
                hits = DatabaseToolkit._apply_dynamic_cut(
                    hits=hits,
                    min_results=int(top_k),
                    max_results=int(candidate_top_k),
                    score_threshold=score_threshold,
                )
            else:
                hits = sorted(hits, key=lambda h: float(h.get("score", 0.0)), reverse=True)[
                    : int(candidate_top_k)
                ]

        hits = self._apply_query_type_bias(hits, query)
        hits = self._dedupe_by_parent(hits, max_per_parent=max_per_parent)

        if neighbor_window > 0:
            hits = [self._expand_neighbor_context(hit, neighbor_window=neighbor_window) for hit in hits]

        hits = self._select_full_chunk_hits(
            hits,
            full_chunk_limit=full_chunk_limit,
            max_total_chars=max_total_chars,
            max_chars_per_chunk=max_chars_per_chunk,
        )
        hits = self._filter_seen_turn_evidence(hits)
        if not hits:
            _log_search("♻️ 本轮后续检索未发现新增证据，已过滤重复结果")
            return "No new results from the vector database in this turn."

        _log_search(f"✅ 搜索完成: 最终返回 {len(hits)} 条完整原文结果")

        # 4) format output
        formatted_results = []
        for hit in hits:
            payload = hit.get("payload", {}) or {}
            metadata = payload.get("metadata", {}) or {}
            source = payload.get("Original_file", "Unknown Source")
            content = payload.get("Content", "") or payload.get("content", "")
            score = float(hit.get("score", 0.0))

            # 表格上下文恢复（可选）
            if restore_table_context and (payload.get("is_table") or metadata.get("is_table")):
                context_before = (
                    payload.get("context_before", "")
                    or metadata.get("context_before", "")
                )
                context_after = (
                    payload.get("context_after", "")
                    or metadata.get("context_after", "")
                )
                if context_before or context_after:
                    # 合并上下文
                    content = f"{context_before}\n{content}\n{context_after}".strip()
                    _log_search(f"   📊 表格上下文已恢复 (前{len(context_before)}字 + 后{len(context_after)}字)")

            content = DatabaseToolkit._truncate_text(content, max_chars_per_chunk)

            result_str = (
                f"File: {source}\n"
                f"Content: \n---\n{content}\n---\n"
                f"Confidence: {score:.4f}"
            )
            formatted_results.append(result_str)

        # ===== 搜索结果摘要 =====
        _log_search(f"\n{'='*60}")
        _log_search(f"📋 [搜索结果摘要] 共 {len(formatted_results)} 条")
        for i, hit in enumerate(hits[:5], 1):  # 打印前5条
            payload = hit.get("payload", {}) or {}
            source = payload.get("Original_file", "Unknown")
            content = payload.get("Content", "") or payload.get("content", "")
            score = float(hit.get("score", 0.0))

            # 提取文件名
            file_name = source.split("\\")[-1] if "\\" in source else source.split("/")[-1]

            # 内容预览（前100字符）
            content_clean = content.replace("\n", " ").strip()[:100]
            if len(content) > 100:
                content_clean += "..."

            _log_search(f"   [{i}] 📄 {file_name}")
            _log_search(f"       📝 {content_clean}")
            _log_search(f"       🎯 置信度: {score:.4f}")

        if len(hits) > 5:
            _log_search(f"   ... 还有 {len(hits) - 5} 条结果")
        _log_search(f"{'='*60}\n")

        return "\n\n".join(formatted_results)

    def get_tools(self) -> List[FunctionTool]:
        return [
            FunctionTool(self.search_database),
        ]
