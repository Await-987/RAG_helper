import sys
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


class DatabaseToolkit(BaseToolkit):
    """A toolkit for retrieving information from your local Qdrant knowledge base."""

    DEFAULT_CANDIDATE_LIMIT = 20
    DEFAULT_FINAL_FULL_CHUNKS = 4
    DEFAULT_MAX_TOTAL_CHARS = 12000
    DEFAULT_MAX_CHARS_PER_CHUNK = 4000  # 父chunk 2000字以上，留足余量
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
        """对表格命中 +0.18、数值内容命中 +0.12，提升相关结果的排名。"""
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
    def _hit_evidence_key(cls, hit: Dict[str, Any]) -> str:
        """生成用于跨轮次去重的唯一 key。"""
        payload = hit.get("payload", {}) or {}
        metadata = payload.get("metadata", {}) or {}
        source = str(payload.get("Original_file", ""))
        page = metadata.get("page") or payload.get("page") or ""
        chunk_index = metadata.get("chunk_index")
        content = payload.get("Content", "") or payload.get("content", "")
        if isinstance(chunk_index, int):
            return f"{source}::page={page}::chunk={chunk_index}"
        return f"{source}::{content}"

    def _filter_seen_turn_evidence(self, hits: List[Dict[str, Any]], seen_keys: Optional[set]) -> List[Dict[str, Any]]:
        _log_search(f"🔍 _filter_seen_turn_evidence: seen_keys={type(seen_keys).__name__}, len={len(seen_keys) if seen_keys else 0}")
        if seen_keys is None:
            _log_search("⚠️ seen_keys为None，跳过去重")
            return hits

        _log_search(f"📝 当前seen_keys中的内容数: {len(seen_keys)}, 待检查的hit数: {len(hits)}")
        
        all_hits: List[Dict[str, Any]] = []
        duplicate_count = 0
        new_count = 0
        
        for hit in hits:
            evidence_key = self._hit_evidence_key(hit)
            
            payload = hit.get("payload", {}) or {}
            raw_content = payload.get("Content", "") or payload.get("content", "")
            # 替换换行符并截取前50字
            content_preview = str(raw_content).replace("\n", " ").strip()[:50] + "..."
            
            if evidence_key in seen_keys:
                duplicate_count += 1
                hit['payload'] = hit.get('payload') or {}
                hit['payload']['_is_duplicate'] = True
                all_hits.append(hit)
                # 使用已经定义好的 content_preview
                _log_search(f"  [重复] {evidence_key[:60]}... | 内容: {content_preview}")
            else:
                new_count += 1
                hit['payload'] = hit.get('payload') or {}
                hit['payload']['_is_duplicate'] = False
                all_hits.append(hit)
                seen_keys.add(evidence_key)
                # 使用已经定义好的 content_preview
                _log_search(f"  [新增] {evidence_key[:60]}... | 内容: {content_preview}")
        
        _log_search(f"📊 去重结果: 新增{new_count}条, 重复{duplicate_count}条")
        return all_hits

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

    def search_database(self, query: str, intent_description: Optional[str] = None, seen_keys: Optional[set] = None, **kwargs) -> str:
        """检索本地电力系统知识库的工具。
        Agent-friendly entrypoint：仅需传入 query 和 intent_description。
        
        Args:
            query: 简化后的搜索query（3-8个核心关键词，用于向量检索）
            intent_description: 用户真实意图的完整描述（用于重排序，消除代词、补全背景主体）
                应该是一个完整的自然语言句子，最接近用户的真实意图。
                如果为None，重排序将使用query。建议总是传入意图描述以获得更好的重排准确性。
            seen_keys: 本会话内已返回过的证据块的去重集合（由调用方传入，不在toolkit内部存储）
        
        Returns:
            格式化的搜索结果字符串
        
        Note:
            其他参数（如 top_k、max_results 等）使用默认值，无需传入。
        """
        return self._search_database(query=query, intent_description=intent_description, seen_keys=seen_keys, **kwargs)

    def _search_database(
        self,
        query: str,
        intent_description: Optional[str] = None,
        *,
        seen_keys: Optional[set] = None,
        use_hybrid: bool = True,
        use_rerank: bool = True,
        score_threshold: Optional[float] = None,
        alpha: float = 0.75,
        restore_table_context: bool = False,
        max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
        max_chars_per_chunk: int = DEFAULT_MAX_CHARS_PER_CHUNK,
    ) -> str:
        """
        简化流水线：
          1. 混合检索 20 条候选
          2. 子 chunk 向量 rerank（cross-encoder）
          3. rerank 内部父 chunk 去重（已有逻辑）
          4. 动态阈值筛选，保留 5-10 条
          5. 单条字数截断 + 总字数守卫
          6. 直接输出，不再经过 _select_full_chunk_hits
        """
        CANDIDATE_K  = 20   # 固定检索条数
        MIN_FINAL    = 5    # 动态筛选下限
        MAX_FINAL    = 10   # 动态筛选上限

        # ===== None 防御 =====
        if alpha is None:
            alpha = 0.75
        if max_total_chars is None:
            max_total_chars = self.DEFAULT_MAX_TOTAL_CHARS
        if max_chars_per_chunk is None:
            max_chars_per_chunk = self.DEFAULT_MAX_CHARS_PER_CHUNK
        max_total_chars = max(12000, int(max_total_chars))
        max_chars_per_chunk = max(4000, int(max_chars_per_chunk))

        # 表格类问题单条预算再放宽（表格可能超 4000 字）
        if self._is_table_like_query(query):
            max_chars_per_chunk = max(max_chars_per_chunk, 6000)
            restore_table_context = True

        # ===== 搜索开始日志 =====
        _log_search(f"\n{'='*60}")
        _log_search(f"🔍 [搜索工具被调用]")
        _log_search(f"   query: '{query[:80]}{'...' if len(query) > 80 else ''}'")
        if intent_description:
            _log_search(f"   intent_description: '{intent_description[:80]}{'...' if len(intent_description) > 80 else ''}'")
        _log_search(
            f"   配置: hybrid={use_hybrid}, rerank={use_rerank}, alpha={alpha}, "
            f"candidate={CANDIDATE_K}, final={MIN_FINAL}~{MAX_FINAL}"
        )
        _log_search(
            f"   预算: max_total_chars={max_total_chars}, "
            f"max_chars_per_chunk={max_chars_per_chunk}, "
            f"restore_table_context={restore_table_context}"
        )
        _log_search(f"{'='*60}\n")

        if not query or not query.strip():
            logger.warning("⚠️ 搜索 query 为空，返回无结果")
            return "No results from the vector database."

        # ===== Step 1: 检索 20 条 =====
        if use_hybrid:
            _log_search(f"📊 执行混合搜索 (vector + keyword BM25), top_k={CANDIDATE_K}...")
            hits = self.db.hybrid_search(
                query=query,
                top_k=CANDIDATE_K,
                alpha=alpha,
                dynamic_topk=False,
                score_threshold=score_threshold,
                max_results=CANDIDATE_K,
            )
        else:
            _log_search(f"📊 执行纯向量搜索, top_k={CANDIDATE_K}...")
            hits = self.db.search(query=query, top_k=CANDIDATE_K)

        if not hits:
            return "No results from the vector database."

        # ===== Step 2: 子 chunk rerank（内含父 chunk 去重） =====
        if use_rerank:
            _log_search(f"🔄 执行子 chunk rerank...")
            hits = self._rerank(query, hits, intent_description=intent_description)

        # ===== Step 3: 本轮去重（在筛选之前，避免浪费 quota） =====
        hits = self._filter_seen_turn_evidence(hits, seen_keys)
        
        # 检查是否有新增内容（不只是重复内容）
        has_new_content = any(not hit.get('payload', {}).get('_is_duplicate', False) for hit in hits)
        if not has_new_content:
            if hits:
                # 有搜到结果，但全是重复
                _log_search(f"♻️ 会话去重：{len(hits)}条结果全部为重复，已标记占位符")
                # 注意：这里不return，让占位符继续显示给Agent
            else:
                # 真的没有找到任何结果
                _log_search("❌ 向量数据库未返回任何结果")
                return "No results from the vector database."
        
        _log_search(f"   新内容: {sum(1 for h in hits if not h.get('payload', {}).get('_is_duplicate', False))} 条, 重复内容占位: {sum(1 for h in hits if h.get('payload', {}).get('_is_duplicate', False))} 条")

        # ===== Step 4: 动态阈值筛选，保留 5-10 条（仅对新内容筛选，重复占位符不计quota） =====
        # 分离新内容和重复内容
        new_hits = [h for h in hits if not h.get('payload', {}).get('_is_duplicate', False)]
        duplicate_hits = [h for h in hits if h.get('payload', {}).get('_is_duplicate', False)]
        
        _log_search(f"✂️ 执行动态阈值过滤 (只对{len(new_hits)}条新内容，忽略{len(duplicate_hits)}条重复占位)...")
        new_hits = DatabaseToolkit._apply_dynamic_cut(
            hits=new_hits,
            min_results=MIN_FINAL,
            max_results=MAX_FINAL,
            score_threshold=score_threshold,
            auto_delta=0.30,  # 放宽：rerank 分布集中时避免过度裁剪
        )
        
        # 重新合并：新内容在前，重复占位在后（这样Agent优先看新信息）
        hits = new_hits + duplicate_hits

        # ===== Step 5: 分数偏置（表格/数值类型提权） =====
        hits = self._apply_query_type_bias(hits, query)

        _log_search(f"✅ 搜索完成: 最终返回 {len(hits)} 条结果")

        # ===== Step 6: 格式化输出，字数截断 + 总字数守卫 =====
        formatted_results = []
        total_chars_used = 0
        for hit_idx, hit in enumerate(hits):
            payload = hit.get("payload", {}) or {}
            source = payload.get("Original_file", "Unknown Source")
            is_duplicate = payload.get("_is_duplicate", False)
            score = float(hit.get("score", 0.0))

            if is_duplicate:
                # 重复的hit：显示占位符而不是完整内容
                result_str = (
                    f"File: {source}\n"
                    f"Content: \n---\n"
                    f"【占位符】本条信息已在之前的对话中详细提供过（置信度: {score:.4f}），"
                    f"请基于历史对话记录进行参考。\n"
                    f"---\n"
                    f"Confidence: {score:.4f}"
                )
                formatted_results.append(result_str)
                continue  # 占位符不计入total_chars_used，避免字数超限

            content = payload.get("Content", "") or payload.get("content", "")

            # 先截断 content 本体
            content = DatabaseToolkit._truncate_text(content, max_chars_per_chunk)

            # 再合并表格上下文（context 本身不截断，保留完整）
            if restore_table_context and (payload.get("is_table") or (payload.get("metadata", {}) or {}).get("is_table")):
                metadata = payload.get("metadata", {}) or {}
                context_before = payload.get("context_before", "") or metadata.get("context_before", "")
                context_after = payload.get("context_after", "") or metadata.get("context_after", "")
                if context_before or context_after:
                    content = f"{context_before}\n{content}\n{context_after}".strip()
                    _log_search(f"   📊 表格上下文已恢复 (前{len(context_before)}字 + 后{len(context_after)}字)")

            # 总字数守卫：已够 MIN_FINAL 条才允许 break，否则强制收录
            if total_chars_used + len(content) > max_total_chars:
                if hit_idx < MIN_FINAL:
                    _log_search(f"   ⚠️ 第{hit_idx + 1}条超预算，但未达最小返回数 {MIN_FINAL}，强制收录")
                else:
                    _log_search(f"   ⚠️ 总字数已达上限 {max_total_chars}，停止收录")
                    break
            total_chars_used += len(content)

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