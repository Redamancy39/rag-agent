from collections.abc import Callable
from time import perf_counter

from app.agent.query_agent import QueryAgent, QueryPlan
from app.core.config import get_settings
from app.core.logger import get_logger
from app.rag.bm25_retriever import BM25Retriever
from app.rag.embeddings import BgeEmbeddingModel
from app.rag.keyword_retriever import KeywordRetriever
from app.rag.reranker import get_optional_reranker
from app.rag.schemas import SourceLocator
from app.rag.search_tokenizer import normalize_for_search
from app.rag.vector_store import ChromaVectorStore

logger = get_logger(__name__)


class PermissionAwareRetriever:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.embedding_model = BgeEmbeddingModel()
        self.vector_store = ChromaVectorStore()
        self.keyword_retriever = KeywordRetriever()
        self.bm25_retriever = BM25Retriever()

    def retrieve(
        self,
        question: str,
        allowed_document_ids: list[int],
        top_k: int | None = None,
    ) -> list[dict]:
        hits, _trace = self._retrieve_with_optional_trace(
            question,
            allowed_document_ids=allowed_document_ids,
            top_k=top_k,
            query_plan=None,
        )
        return hits

    def retrieve_with_trace(
        self,
        question: str,
        allowed_document_ids: list[int],
        top_k: int | None = None,
    ) -> tuple[list[dict], list[dict]]:
        hits, trace, _query_plan = self.retrieve_with_plan(
            question,
            allowed_document_ids=allowed_document_ids,
            top_k=top_k,
        )
        return hits, trace

    def retrieve_with_plan(
        self,
        question: str,
        allowed_document_ids: list[int],
        top_k: int | None = None,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> tuple[list[dict], list[dict], QueryPlan]:
        query_plan = QueryAgent().plan(question)
        retrieval_queries = _retrieval_queries_from_plan(
            query_plan,
            enabled=self.settings.QUERY_DECOMPOSITION_ENABLED,
            max_queries=self.settings.QUERY_AGENT_MAX_QUERIES,
        )
        _emit_progress(
            progress_callback,
            stage="query_decompose",
            message=(
                f"复杂问题已拆分为 {len(retrieval_queries)} 条检索查询"
                if len(retrieval_queries) > 1
                else "问题无需分解，使用归一化查询"
            ),
            progress=20,
            query_count=len(retrieval_queries),
            queries=[query for query, _source in retrieval_queries],
            decomposed=len(retrieval_queries) > 1,
        )
        hits, trace = self._retrieve_with_optional_trace(
            question,
            allowed_document_ids=allowed_document_ids,
            top_k=top_k,
            query_plan=query_plan,
            retrieval_queries=retrieval_queries,
        )
        return hits, trace, query_plan

    def _retrieve_with_optional_trace(
        self,
        question: str,
        *,
        allowed_document_ids: list[int],
        top_k: int | None,
        query_plan: QueryPlan | None,
        retrieval_queries: list[tuple[str, str]] | None = None,
    ) -> tuple[list[dict], list[dict]]:
        final_top_k = top_k or self.settings.RAG_TOP_K
        candidate_top_k = (
            max(final_top_k, self.settings.RERANKER_CANDIDATE_TOP_K)
            if self._should_rerank()
            else final_top_k
        )
        planned_queries = retrieval_queries or [
            (
                query_plan.normalized_question
                if query_plan is not None and query_plan.normalized_question
                else question,
                "normalized",
            )
        ]
        primary_query = planned_queries[0][0]
        lexical_chunks = self._load_lexical_chunks(allowed_document_ids)
        all_hits: list[dict] = []
        trace: list[dict] = []
        for query_index, (query, query_source) in enumerate(planned_queries):
            query_started = perf_counter()
            query_top_k = (
                candidate_top_k
                if query_index == 0
                else max(
                    final_top_k,
                    self.settings.QUERY_DECOMPOSITION_PER_QUERY_TOP_K,
                )
            )
            query_hits = self._retrieve_single_query(
                query,
                allowed_document_ids=allowed_document_ids,
                top_k=query_top_k,
                lexical_chunks=lexical_chunks,
            )
            for hit in query_hits:
                updated = dict(hit)
                updated["retrieval_query"] = query
                updated["retrieval_query_index"] = query_index
                updated["retrieval_query_source"] = query_source
                if query_index > 0:
                    updated["score"] = (
                        _safe_float(updated.get("score"))
                        * self.settings.QUERY_DECOMPOSITION_SCORE_FACTOR
                    )
                all_hits.append(updated)
            trace.append(
                _trace_step(
                    query_index=query_index,
                    query=query,
                    source=query_source,
                    hits=query_hits,
                    duration_ms=_elapsed_ms(query_started),
                )
            )

        merge_started = perf_counter()
        candidate_limit = (
            max(
                final_top_k,
                self.settings.QUERY_DECOMPOSITION_MAX_CANDIDATES,
            )
            if len(planned_queries) > 1
            else candidate_top_k
        )
        hits = _merge_decomposed_hits(all_hits)[:candidate_limit]
        if len(planned_queries) > 1:
            trace.append(
                _trace_step(
                    query_index=len(trace),
                    query=primary_query,
                    source="decomposition_merged",
                    hits=hits,
                    duration_ms=_elapsed_ms(merge_started),
                )
            )
        if not self._should_rerank() or not hits:
            final_hits = hits[:final_top_k]
            trace.append(
                _trace_step(
                    query_index=len(trace),
                    query=primary_query,
                    source="merged",
                    hits=final_hits,
                    duration_ms=_elapsed_ms(merge_started),
                )
            )
            return final_hits, trace
        reranker = get_optional_reranker()
        if not reranker:
            final_hits = hits[:final_top_k]
            trace.append(
                _trace_step(
                    query_index=len(trace),
                    query=primary_query,
                    source="merged_without_reranker",
                    hits=final_hits,
                    duration_ms=_elapsed_ms(merge_started),
                )
            )
            return final_hits, trace
        preserved_hits = hits[: self.settings.RAG_PRESERVE_PRE_RERANK_TOP_K]
        rerank_started = perf_counter()
        try:
            reranked_hits = reranker.rerank(primary_query, hits, final_top_k)
            final_hits = _merge_preserved_hits(
                reranked_hits,
                preserved_hits,
                limit=_return_limit(
                    final_top_k=final_top_k,
                    preserve_top_k=self.settings.RAG_PRESERVE_PRE_RERANK_TOP_K,
                    max_returned_hits=self.settings.RAG_MAX_RETURNED_HITS,
                ),
            )
            trace.append(
                _trace_step(
                    query_index=len(trace),
                    query=primary_query,
                    source="reranked_with_preserved_recall",
                    hits=final_hits,
                    duration_ms=_elapsed_ms(rerank_started),
                )
            )
            return final_hits, trace
        except Exception as exc:
            logger.warning("Reranker failed, using merged retrieval hits: %s", exc)
        final_hits = hits[:final_top_k]
        trace.append(
            _trace_step(
                query_index=len(trace),
                query=primary_query,
                source="reranker_failed",
                hits=final_hits,
                duration_ms=_elapsed_ms(rerank_started),
            )
        )
        return final_hits, trace

    def _retrieve_single_query(
        self,
        question: str,
        *,
        allowed_document_ids: list[int],
        top_k: int,
        lexical_chunks: list[dict] | None = None,
    ) -> list[dict]:
        hits: list[dict] = []
        try:
            query_embedding = self.embedding_model.embed_query(question)
            hits = self.vector_store.search_by_embedding(
                query_embedding,
                allowed_document_ids=allowed_document_ids,
                top_k=top_k,
            )
        except Exception as exc:
            logger.warning("Vector retrieval failed, falling back to lexical retrieval: %s", exc)
        if self.settings.HYBRID_RETRIEVAL_ENABLED:
            if lexical_chunks is None:
                lexical_chunks = self._load_lexical_chunks(allowed_document_ids)
            keyword_hits = self.keyword_retriever.retrieve(
                question,
                allowed_document_ids=allowed_document_ids,
                top_k=max(top_k, self.settings.HYBRID_KEYWORD_CANDIDATE_TOP_K),
                chunks=lexical_chunks,
            )
            bm25_hits = (
                self.bm25_retriever.retrieve(
                    question,
                    allowed_document_ids=allowed_document_ids,
                    top_k=max(top_k, self.settings.HYBRID_BM25_CANDIDATE_TOP_K),
                    chunks=lexical_chunks,
                )
                if self.settings.HYBRID_BM25_ENABLED
                else []
            )
            hits = self._merge_hybrid_hits(hits, keyword_hits, bm25_hits)
        return hits[:top_k]

    def _load_lexical_chunks(self, allowed_document_ids: list[int]) -> list[dict]:
        if not self.settings.HYBRID_RETRIEVAL_ENABLED:
            return []
        try:
            return self.vector_store.get_chunks_for_documents(
                allowed_document_ids,
                limit=max(
                    self.settings.HYBRID_KEYWORD_MAX_CHUNKS,
                    self.settings.HYBRID_BM25_MAX_CHUNKS,
                ),
            )
        except Exception as exc:
            logger.warning("Lexical chunk loading failed: %s", exc)
            return []

    def _should_rerank(self) -> bool:
        return bool(self.settings.RERANKER_ENABLED and self.settings.RERANKER_MODEL_NAME)

    def _merge_hybrid_hits(
        self,
        vector_hits: list[dict],
        keyword_hits: list[dict],
        bm25_hits: list[dict],
    ) -> list[dict]:
        merged: dict[str, dict] = {}
        for hit in vector_hits:
            chunk_id = str(hit.get("id") or "")
            if not chunk_id:
                continue
            updated = dict(hit)
            vector_score = _safe_float(updated.get("score"))
            updated["vector_score"] = vector_score
            updated["keyword_score"] = 0.0
            updated["bm25_score"] = 0.0
            updated["retrieval_source"] = "vector"
            updated["retrieval_sources"] = ["vector"]
            merged[chunk_id] = updated

        for hit in keyword_hits:
            chunk_id = str(hit.get("id") or "")
            if not chunk_id:
                continue
            keyword_score = _safe_float(hit.get("keyword_score") or hit.get("score"))
            if chunk_id in merged:
                merged_hit = merged[chunk_id]
                merged_hit["keyword_score"] = max(
                    _safe_float(merged_hit.get("keyword_score")),
                    keyword_score,
                )
                merged_hit["matched_terms"] = hit.get("matched_terms") or []
                _append_source(merged_hit, "keyword")
            else:
                updated = dict(hit)
                updated["vector_score"] = 0.0
                updated["bm25_score"] = 0.0
                updated["keyword_score"] = keyword_score
                updated["retrieval_sources"] = ["keyword"]
                merged[chunk_id] = updated

        for hit in bm25_hits:
            chunk_id = str(hit.get("id") or "")
            if not chunk_id:
                continue
            bm25_score = _safe_float(hit.get("bm25_score") or hit.get("score"))
            if chunk_id in merged:
                merged_hit = merged[chunk_id]
                merged_hit["bm25_score"] = max(
                    _safe_float(merged_hit.get("bm25_score")),
                    bm25_score,
                )
                merged_hit["raw_bm25_score"] = hit.get("raw_bm25_score")
                merged_hit["matched_terms"] = _merge_terms(
                    merged_hit.get("matched_terms") or [],
                    hit.get("matched_terms") or [],
                )
                _append_source(merged_hit, "bm25")
            else:
                updated = dict(hit)
                updated["vector_score"] = 0.0
                updated["keyword_score"] = 0.0
                updated["bm25_score"] = bm25_score
                updated["retrieval_sources"] = ["bm25"]
                merged[chunk_id] = updated

        for hit in merged.values():
            vector_score = _safe_float(hit.get("vector_score"))
            keyword_score = _safe_float(hit.get("keyword_score"))
            bm25_score = _safe_float(hit.get("bm25_score"))
            hybrid_score = (
                vector_score * self.settings.HYBRID_VECTOR_WEIGHT
                + keyword_score * self.settings.HYBRID_KEYWORD_WEIGHT
                + bm25_score * self.settings.HYBRID_BM25_WEIGHT
            )
            hit["score"] = _final_hybrid_score(
                vector_score=vector_score,
                keyword_score=keyword_score,
                bm25_score=bm25_score,
                hybrid_score=hybrid_score,
                lexical_only_max_score=self.settings.HYBRID_LEXICAL_ONLY_MAX_SCORE,
            )
            sources = hit.get("retrieval_sources") or [hit.get("retrieval_source") or "unknown"]
            hit["retrieval_source"] = "hybrid" if len(sources) > 1 else str(sources[0])

        return sorted(
            merged.values(),
            key=lambda item: float(item.get("score") or 0.0),
            reverse=True,
        )



def _safe_float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _final_hybrid_score(
    *,
    vector_score: float,
    keyword_score: float,
    bm25_score: float,
    hybrid_score: float,
    lexical_only_max_score: float,
) -> float:
    if vector_score > 0:
        return min(1.0, max(vector_score, hybrid_score))
    lexical_score = keyword_score * 0.25 + bm25_score * 0.75
    return min(lexical_only_max_score, max(hybrid_score, lexical_score))


def _append_source(hit: dict, source: str) -> None:
    sources = list(hit.get("retrieval_sources") or [])
    if source not in sources:
        sources.append(source)
    hit["retrieval_sources"] = sources


def _merge_preserved_hits(
    primary_hits: list[dict],
    preserved_hits: list[dict],
    *,
    limit: int,
) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for hit in [*primary_hits, *preserved_hits]:
        chunk_id = str(hit.get("id") or "")
        if not chunk_id or chunk_id in seen:
            continue
        updated = dict(hit)
        if hit in preserved_hits and hit not in primary_hits:
            updated["preserved_from_pre_rerank"] = True
        merged.append(updated)
        seen.add(chunk_id)
        if len(merged) >= limit:
            break
    return merged


def _return_limit(
    *,
    final_top_k: int,
    preserve_top_k: int,
    max_returned_hits: int,
) -> int:
    if preserve_top_k <= 0:
        return final_top_k
    return max(final_top_k, min(max_returned_hits, final_top_k + preserve_top_k))


def _trace_step(
    *,
    query_index: int,
    query: str,
    source: str,
    hits: list[dict],
    duration_ms: int | None = None,
) -> dict:
    trace_limit = max(1, get_settings().RAG_TRACE_TOP_HITS)
    return {
        "query_index": query_index,
        "query": query,
        "source": source,
        "hit_count": len(hits),
        "duration_ms": duration_ms,
        "top_hits": [
            _trace_hit(rank=index, hit=hit)
            for index, hit in enumerate(hits[:trace_limit], start=1)
        ],
    }


def _trace_hit(*, rank: int, hit: dict) -> dict:
    metadata = hit.get("metadata") or {}
    locator = SourceLocator.from_metadata(metadata)
    return {
        "rank": rank,
        "score": hit.get("score"),
        "vector_score": hit.get("vector_score"),
        "keyword_score": hit.get("keyword_score"),
        "bm25_score": hit.get("bm25_score"),
        "raw_bm25_score": hit.get("raw_bm25_score"),
        "pre_rerank_score": hit.get("pre_rerank_score"),
        "rerank_score": hit.get("rerank_score"),
        "distance": hit.get("distance"),
        "filename": str(metadata.get("filename") or ""),
        "page": locator.page,
        "slide": locator.slide,
        "section_path": locator.section_path,
        "sheet": locator.sheet,
        "cell_range": locator.cell_range,
        "paragraph_index": locator.paragraph_index,
        "table_index": locator.table_index,
        "block_index": locator.block_index,
        "location": locator.to_read_dict(),
        "table": str(metadata.get("table_label") or metadata.get("table_number") or "") or None,
        "chunk_id": hit.get("id"),
        "retrieval_source": str(hit.get("retrieval_source") or ""),
        "matched_terms": [
            str(term)
            for term in (hit.get("matched_terms") or [])
            if str(term)
        ][:8],
        "preserved_from_pre_rerank": bool(hit.get("preserved_from_pre_rerank")),
        "selected_for_answer": False,
        "citation_id": None,
        "text_preview": " ".join(str(hit.get("text") or "").split())[:220],
    }


def _elapsed_ms(started: float) -> int:
    return max(0, int((perf_counter() - started) * 1000))


def _merge_terms(left: list, right: list) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in [*left, *right]:
        term = str(value)
        if not term or term in seen:
            continue
        seen.add(term)
        merged.append(term)
    return merged[:16]


def _retrieval_queries_from_plan(
    plan: QueryPlan,
    *,
    enabled: bool,
    max_queries: int,
) -> list[tuple[str, str]]:
    primary = plan.normalized_question or plan.original_question
    queries: list[tuple[str, str]] = [(primary, "normalized")]
    if not enabled or max_queries <= 1 or not _should_decompose(plan):
        return queries

    candidates = [
        *[(query, "decomposed") for query in plan.sub_questions],
        *[(query, "rewritten") for query in plan.rewritten_queries],
    ]
    seen = {normalize_for_search(primary).replace(" ", "")}
    for query, source in candidates:
        text = str(query or "").strip()
        key = normalize_for_search(text).replace(" ", "")
        if not key or key in seen:
            continue
        seen.add(key)
        queries.append((text, source))
        if len(queries) >= max_queries:
            break
    return queries


def _should_decompose(plan: QueryPlan) -> bool:
    if plan.question_type in {"cross_document", "comparison", "multi_hop"}:
        return True
    if len(plan.standard_refs) >= 2 or len(plan.entities) >= 2:
        return True
    return len(plan.sub_questions) >= 2


def _merge_decomposed_hits(hits: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for hit in hits:
        chunk_id = str(hit.get("id") or "")
        if not chunk_id:
            continue
        query = str(hit.get("retrieval_query") or "")
        query_source = str(hit.get("retrieval_query_source") or "")
        if chunk_id not in merged:
            updated = dict(hit)
            updated["retrieval_queries"] = [query] if query else []
            updated["retrieval_query_sources"] = (
                [query_source] if query_source else []
            )
            merged[chunk_id] = updated
            continue

        existing = merged[chunk_id]
        existing_queries = _merge_terms(
            existing.get("retrieval_queries") or [],
            [query] if query else [],
        )
        existing_query_sources = _merge_terms(
            existing.get("retrieval_query_sources") or [],
            [query_source] if query_source else [],
        )
        existing_retrieval_sources = _merge_terms(
            existing.get("retrieval_sources")
            or [existing.get("retrieval_source") or "unknown"],
            hit.get("retrieval_sources")
            or [hit.get("retrieval_source") or "unknown"],
        )
        existing_matched_terms = _merge_terms(
            existing.get("matched_terms") or [],
            hit.get("matched_terms") or [],
        )
        if _safe_float(hit.get("score")) > _safe_float(existing.get("score")):
            replacement = dict(hit)
            replacement["retrieval_queries"] = existing_queries
            replacement["retrieval_query_sources"] = existing_query_sources
            replacement["retrieval_sources"] = existing_retrieval_sources
            replacement["matched_terms"] = existing_matched_terms
            merged[chunk_id] = replacement
        else:
            existing["retrieval_queries"] = existing_queries
            existing["retrieval_query_sources"] = existing_query_sources
            existing["retrieval_sources"] = existing_retrieval_sources
            existing["matched_terms"] = existing_matched_terms

    return sorted(
        merged.values(),
        key=lambda item: _safe_float(item.get("score")),
        reverse=True,
    )


def _emit_progress(
    callback: Callable[[dict], None] | None,
    **event: object,
) -> None:
    if callback is not None:
        callback(dict(event))
