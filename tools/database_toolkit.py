from loguru import logger
from typing import List, Optional, Any, Dict

from camel.toolkits.base import BaseToolkit, FunctionTool
from tools import QdrantDB, QdrantDB_Init


class DatabaseToolkit(BaseToolkit):
    """A toolkit for retrieving information from your local Qdrant knowledge base."""

    def __init__(self):
        super().__init__()
        qdrant_init = QdrantDB_Init(collection_name="database")
        self.db = QdrantDB(input=qdrant_init)
        self._reranker = None  # lazy-load

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

    def _rerank(self, query: str, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Rerank by CrossEncoder if available.
        We normalize rerank scores to 0~1 and overwrite hit['score'] for final sorting.
        """
        reranker = self._get_reranker()
        if reranker is None or not hits:
            return hits

        pairs = []
        valid_hits = []
        for h in hits:
            payload = h.get("payload", {}) or {}
            content = payload.get("Content") or payload.get("content") or ""
            if not isinstance(content, str):
                content = str(content)
            content = content.strip()
            if not content:
                continue
            pairs.append((query, content))
            valid_hits.append(h)

        if not valid_hits:
            return hits

        try:
            scores = reranker.predict(pairs)
            scores = [float(s) for s in list(scores)]
        except Exception as e:
            logger.warning(f"Reranker predict failed, fallback to hybrid order: {e}")
            return hits

        norm_scores = self._minmax_norm(scores)
        for h, s_raw, s_norm in zip(valid_hits, scores, norm_scores):
            h["rerank_score_raw"] = s_raw
            h["score"] = float(s_norm)  # final score for sorting

        # keep non-valid hits at the end
        rest = [h for h in hits if h not in valid_hits]
        out = sorted(valid_hits, key=lambda x: float(x.get("score", 0.0)), reverse=True) + rest
        return out

    def search_database(
        self,
        query: str,
        top_k: int = 5,
        *,
        # ---- new knobs (all optional; keep old usage compatible) ----
        use_hybrid: bool = True,
        use_rerank: bool = True,
        dynamic_topk: bool = True,
        score_threshold: Optional[float] = None,
        max_results: int = 20,
        alpha: float = 0.75,
    ) -> str:
        """
        Hybrid retrieval within local database.

        - use_hybrid=True: vector + keyword (BM25-like) fusion
        - use_rerank=True: optional cross-encoder rerank (if env `reranker_path` set)
        - dynamic_topk=True: return all chunks above threshold (capped by max_results)
          score_threshold is on normalized score (0~1). If None, an adaptive threshold is used.
        """
        # 放在 search_database() 开头，参数校正
        if dynamic_topk:
            # 领导演示用：保证动态 topk 有空间“变多”
            # 你可以把 20 改成 15/30，看你想演示的幅度
            max_results = max(int(max_results), 20)

        if not query or not query.strip():
            return "No results from the vector database."

        # 1) hybrid or vector-only
        if use_hybrid:
            hits = self.db.hybrid_search(
                query=query,
                top_k=top_k,
                alpha=alpha,
                dynamic_topk=False,
                score_threshold=score_threshold,
                max_results=max_results,
            )
        else:
            hits = self.db.search(query=query, top_k=top_k)

        if not hits:
            return "No results from the vector database."

        # 2) rerank (optional)
        if use_rerank:
            hits = self._rerank(query, hits)

            # 3) dynamic threshold cut should use final scores (after rerank)
            if dynamic_topk:
                hits = self._apply_dynamic_cut(
                    hits=hits,
                    min_results=int(top_k),
                    max_results=int(max_results),
                    score_threshold=score_threshold,
                )
            else:
                hits = sorted(hits, key=lambda h: float(h.get("score", 0.0)), reverse=True)[: int(top_k)]

        # 4) format output
        formatted_results = []
        for hit in hits:
            payload = hit.get("payload", {}) or {}
            source = payload.get("Original_file", "Unknown Source")
            content = payload.get("Content", "") or payload.get("content", "")
            score = float(hit.get("score", 0.0))

            result_str = (
                f"File: {source}\n"
                f"Content: \n---\n{content}\n---\n"
                f"Confidence: {score:.4f}"
            )
            formatted_results.append(result_str)

        logger.info(f"Database Search Results (n={len(formatted_results)}): {formatted_results}")
        return "\n\n".join(formatted_results)

    def get_tools(self) -> List[FunctionTool]:
        return [
            FunctionTool(self.search_database),
        ]