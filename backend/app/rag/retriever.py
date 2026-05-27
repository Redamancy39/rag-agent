import re

from app.agent.query_agent import QueryAgent, QueryPlan
from app.core.config import get_settings
from app.core.logger import get_logger
from app.rag.bm25_retriever import BM25Retriever
from app.rag.embeddings import BgeEmbeddingModel
from app.rag.keyword_retriever import KeywordRetriever
from app.rag.reranker import get_optional_reranker
from app.rag.search_tokenizer import normalize_for_search
from app.rag.vector_store import ChromaVectorStore

logger = get_logger(__name__)

STANDARD_REF_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])GB(?:/T)?\s*\d+(?:\.\d+)?(?:[-\u2010-\u2014\u2212]\d{4})?",
    re.IGNORECASE,
)
CROSS_DOCUMENT_MARKERS = (
    "应符合",
    "引用",
    "参照",
    "同时符合",
    "根据现行",
    "有何不同",
    "分别",
    "都引用",
)
CROSS_DOCUMENT_TERMS = (
    "污染物限量",
    "食品添加剂",
    "致病菌",
    "微生物",
    "铅",
    "镉",
    "砷",
    "无机砷",
    "甲基汞",
    "黄曲霉毒素B1",
    "菌落总数",
    "大肠菌群",
    "沙门氏菌",
    "金黄色葡萄球菌",
    "氨基酸态氮",
    "酸价",
    "过氧化值",
    "限量",
    "检验方法",
)


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
    ) -> tuple[list[dict], list[dict], QueryPlan]:
        query_plan = QueryAgent().plan(question)
        hits, trace = self._retrieve_with_optional_trace(
            question,
            allowed_document_ids=allowed_document_ids,
            top_k=top_k,
            query_plan=query_plan,
        )
        return hits, trace, query_plan

    def _retrieve_with_optional_trace(
        self,
        question: str,
        *,
        allowed_document_ids: list[int],
        top_k: int | None,
        query_plan: QueryPlan | None,
    ) -> tuple[list[dict], list[dict]]:
        final_top_k = top_k or self.settings.RAG_TOP_K
        candidate_top_k = (
            max(final_top_k, self.settings.RERANKER_CANDIDATE_TOP_K)
            if self._should_rerank()
            else final_top_k
        )
        queries = self._queries_from_plan(question, query_plan)
        hits: list[dict] = []
        trace: list[dict] = []
        for query_index, query in enumerate(queries):
            query_top_k = (
                candidate_top_k
                if query_index == 0
                else max(final_top_k, self.settings.RAG_CHAIN_PER_QUERY_TOP_K)
            )
            query_hits = self._retrieve_single_query(
                query,
                allowed_document_ids=allowed_document_ids,
                top_k=query_top_k,
            )
            for hit in query_hits:
                updated = dict(hit)
                updated["chain_query"] = query
                updated["chain_query_index"] = query_index
                if query_index > 0:
                    updated["score"] = _safe_float(updated.get("score")) * self.settings.RAG_CHAIN_EXPANSION_SCORE_FACTOR
                    updated["chain_query_source"] = "expanded"
                else:
                    updated["chain_query_source"] = "original"
                hits.append(updated)
            trace.append(
                _trace_step(
                    query_index=query_index,
                    query=query,
                    source="original" if query_index == 0 else "expanded",
                    hits=query_hits,
                )
            )

        hits = self._merge_chain_hits(hits)
        if not self._should_rerank() or not hits:
            final_hits = hits[:final_top_k]
            trace.append(
                _trace_step(
                    query_index=len(trace),
                    query=question,
                    source="merged",
                    hits=final_hits,
                )
            )
            return final_hits, trace
        reranker = get_optional_reranker()
        if not reranker:
            final_hits = hits[:final_top_k]
            trace.append(
                _trace_step(
                    query_index=len(trace),
                    query=question,
                    source="merged_without_reranker",
                    hits=final_hits,
                )
            )
            return final_hits, trace
        try:
            final_hits = reranker.rerank(question, hits, final_top_k)
            trace.append(
                _trace_step(
                    query_index=len(trace),
                    query=question,
                    source="reranked",
                    hits=final_hits,
                )
            )
            return final_hits, trace
        except Exception as exc:
            logger.warning("Reranker failed, using merged retrieval hits: %s", exc)
        final_hits = hits[:final_top_k]
        trace.append(
            _trace_step(
                query_index=len(trace),
                query=question,
                source="reranker_failed",
                hits=final_hits,
            )
        )
        return final_hits, trace

    def _retrieve_single_query(
        self,
        question: str,
        *,
        allowed_document_ids: list[int],
        top_k: int,
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
            try:
                lexical_chunks = self.vector_store.get_chunks_for_documents(
                    allowed_document_ids,
                    limit=max(
                        self.settings.HYBRID_KEYWORD_MAX_CHUNKS,
                        self.settings.HYBRID_BM25_MAX_CHUNKS,
                    ),
                )
            except Exception as exc:
                logger.warning("Lexical chunk loading failed: %s", exc)
                lexical_chunks = []
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

    def _queries_from_plan(
        self,
        question: str,
        query_plan: QueryPlan | None,
    ) -> list[str]:
        if query_plan is not None and query_plan.rewritten_queries:
            return query_plan.rewritten_queries[: self.settings.QUERY_AGENT_MAX_QUERIES]
        return self._expanded_queries(question)

    def _should_rerank(self) -> bool:
        return bool(self.settings.RERANKER_ENABLED and self.settings.RERANKER_MODEL_NAME)

    def _expanded_queries(self, question: str) -> list[str]:
        if not self.settings.RAG_CHAIN_RETRIEVAL_ENABLED:
            return [question]
        if not _looks_like_cross_document_question(question):
            return [question]

        queries = [question]
        refs = _standard_refs(question)
        core_terms = _core_terms(question)
        target_tail = _target_standard_tail(question)

        for ref in refs:
            if target_tail:
                queries.append(f"{ref} {target_tail}")
            if core_terms:
                queries.append(f"{ref} {' '.join(core_terms)}")

        if len(refs) >= 2 and core_terms:
            queries.append(f"{refs[-1]} {' '.join(core_terms)}")
            queries.append(f"{refs[0]} 引用 {refs[-1]} {' '.join(core_terms[:3])}")

        return _unique_queries(queries, limit=self.settings.RAG_CHAIN_MAX_QUERIES)

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

    def _merge_chain_hits(self, hits: list[dict]) -> list[dict]:
        merged: dict[str, dict] = {}
        for hit in hits:
            chunk_id = str(hit.get("id") or "")
            if not chunk_id:
                continue
            if chunk_id not in merged:
                updated = dict(hit)
                updated["chain_queries"] = [hit.get("chain_query")]
                merged[chunk_id] = updated
                continue

            existing = merged[chunk_id]
            if _safe_float(hit.get("score")) > _safe_float(existing.get("score")):
                for key, value in hit.items():
                    if key != "chain_query":
                        existing[key] = value
            existing["chain_queries"] = _merge_terms(
                existing.get("chain_queries") or [],
                [hit.get("chain_query")],
            )
            existing["retrieval_sources"] = _merge_terms(
                existing.get("retrieval_sources") or [existing.get("retrieval_source") or "unknown"],
                hit.get("retrieval_sources") or [hit.get("retrieval_source") or "unknown"],
            )

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


def _trace_step(
    *,
    query_index: int,
    query: str,
    source: str,
    hits: list[dict],
) -> dict:
    return {
        "query_index": query_index,
        "query": query,
        "source": source,
        "hit_count": len(hits),
        "top_hits": [
            _trace_hit(rank=index, hit=hit)
            for index, hit in enumerate(hits[:5], start=1)
        ],
    }


def _trace_hit(*, rank: int, hit: dict) -> dict:
    metadata = hit.get("metadata") or {}
    return {
        "rank": rank,
        "score": hit.get("score"),
        "filename": str(metadata.get("filename") or ""),
        "page": _to_int_or_none(metadata.get("page")),
        "table": str(metadata.get("table_label") or metadata.get("table_number") or "") or None,
        "chunk_id": hit.get("id"),
        "retrieval_source": str(hit.get("retrieval_source") or ""),
        "matched_terms": [
            str(term)
            for term in (hit.get("matched_terms") or [])
            if str(term)
        ][:8],
    }


def _to_int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


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


def _looks_like_cross_document_question(question: str) -> bool:
    normalized = normalize_for_search(question)
    refs = _standard_refs(question)
    if len(refs) >= 2:
        return True
    if any(marker in question for marker in CROSS_DOCUMENT_MARKERS):
        return True
    return "crossdoc" in normalized


def _standard_refs(question: str) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for match in STANDARD_REF_PATTERN.finditer(question):
        ref = _normalize_standard_ref(match.group(0))
        key = normalize_for_search(ref).replace(" ", "")
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
    return refs


def _normalize_standard_ref(value: str) -> str:
    text = value.upper().replace(" ", "")
    text = re.sub(r"[\u2010-\u2014\u2212]", "-", text)
    return text.replace("GB/T", "GB/T ")


def _target_standard_tail(question: str) -> str:
    refs = _standard_refs(question)
    if not refs:
        return ""
    last_ref = refs[-1]
    compact_question = question.replace(" ", "")
    compact_ref = last_ref.replace(" ", "")
    index = compact_question.rfind(compact_ref)
    if index < 0:
        return ""
    tail = compact_question[index + len(compact_ref) :]
    tail = re.sub(r"^[中，,：:的]*", "", tail)
    tail = tail.replace("是多少？", "").replace("是什么？", "")
    return tail[:80]


def _core_terms(question: str) -> list[str]:
    terms: list[str] = []
    for term in CROSS_DOCUMENT_TERMS:
        if term in question and term not in terms:
            terms.append(term)
    for term in _food_or_subject_terms(question):
        if term not in terms:
            terms.append(term)
    return terms[:8]


def _food_or_subject_terms(question: str) -> list[str]:
    terms: list[str] = []
    for indicator in CROSS_DOCUMENT_TERMS:
        pattern = rf"([\u4e00-\u9fffA-Za-z0-9（）()、·\-]+?)的{re.escape(indicator)}"
        for match in re.finditer(pattern, question):
            value = _clean_subject_term(match.group(1))
            if value and value not in terms:
                terms.append(value)
    return terms[:4]


def _clean_subject_term(value: str) -> str:
    text = re.sub(STANDARD_REF_PATTERN, "", value)
    text = re.sub(r"^(中|，|,|和|与|及|根据|现行|标准体系)+", "", text)
    text = re.sub(r"^(GB)?\d+(?:\.\d+)?(?:-\d{4})?", "", text, flags=re.I)
    text = re.sub(r"^(中|，|,|和|与|及|根据|现行|标准体系)+", "", text)
    text = text.strip(" ，,：:。？")
    if len(text) > 24:
        text = text[-24:]
    return text


def _unique_queries(queries: list[str], *, limit: int) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = normalize_for_search(query).replace(" ", "")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(query)
        if len(unique) >= limit:
            break
    return unique or queries[:1]
