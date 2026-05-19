from app.core.config import get_settings
from app.core.logger import get_logger
from app.rag.embeddings import BgeEmbeddingModel
from app.rag.keyword_retriever import KeywordRetriever
from app.rag.reranker import get_optional_reranker
from app.rag.vector_store import ChromaVectorStore

logger = get_logger(__name__)


class PermissionAwareRetriever:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.embedding_model = BgeEmbeddingModel()
        self.vector_store = ChromaVectorStore()
        self.keyword_retriever = KeywordRetriever()

    def retrieve(
        self,
        question: str,
        allowed_document_ids: list[int],
        top_k: int | None = None,
    ) -> list[dict]:
        final_top_k = top_k or self.settings.RAG_TOP_K
        candidate_top_k = (
            max(final_top_k, self.settings.RERANKER_CANDIDATE_TOP_K)
            if self._should_rerank()
            else final_top_k
        )
        query_embedding = self.embedding_model.embed_query(question)
        hits = self.vector_store.search_by_embedding(
            query_embedding,
            allowed_document_ids=allowed_document_ids,
            top_k=candidate_top_k,
        )
        if self.settings.HYBRID_RETRIEVAL_ENABLED:
            keyword_hits = self.keyword_retriever.retrieve(
                question,
                allowed_document_ids=allowed_document_ids,
                top_k=max(candidate_top_k, self.settings.HYBRID_KEYWORD_CANDIDATE_TOP_K),
            )
            hits = self._merge_hybrid_hits(hits, keyword_hits)
        if not self._should_rerank() or not hits:
            return hits[:final_top_k]
        reranker = get_optional_reranker()
        if not reranker:
            return hits[:final_top_k]
        try:
            return reranker.rerank(question, hits, final_top_k)
        except Exception as exc:
            logger.warning("Reranker failed, using vector search only: %s", exc)
        return hits[:final_top_k]

    def _should_rerank(self) -> bool:
        return bool(self.settings.RERANKER_ENABLED and self.settings.RERANKER_MODEL_NAME)

    def _merge_hybrid_hits(self, vector_hits: list[dict], keyword_hits: list[dict]) -> list[dict]:
        merged: dict[str, dict] = {}
        for hit in vector_hits:
            chunk_id = str(hit.get("id") or "")
            if not chunk_id:
                continue
            updated = dict(hit)
            vector_score = _safe_float(updated.get("score"))
            updated["vector_score"] = vector_score
            updated["keyword_score"] = 0.0
            updated["retrieval_source"] = "vector"
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
                merged_hit["retrieval_source"] = "hybrid"
            else:
                updated = dict(hit)
                updated["vector_score"] = 0.0
                updated["keyword_score"] = keyword_score
                updated["retrieval_source"] = "keyword"
                merged[chunk_id] = updated

        for hit in merged.values():
            vector_score = _safe_float(hit.get("vector_score"))
            keyword_score = _safe_float(hit.get("keyword_score"))
            hybrid_score = (
                vector_score * self.settings.HYBRID_VECTOR_WEIGHT
                + keyword_score * self.settings.HYBRID_KEYWORD_WEIGHT
            )
            hit["score"] = max(vector_score, keyword_score, hybrid_score)

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
