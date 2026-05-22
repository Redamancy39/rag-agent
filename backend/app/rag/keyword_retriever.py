import math
from collections import Counter

from app.core.config import get_settings
from app.rag.search_tokenizer import compact_for_search, normalize_for_search, tokenize_for_search
from app.rag.vector_store import ChromaVectorStore


class KeywordRetriever:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.vector_store = ChromaVectorStore()

    def retrieve(
        self,
        question: str,
        *,
        allowed_document_ids: list[int],
        top_k: int,
        chunks: list[dict] | None = None,
    ) -> list[dict]:
        terms = tokenize_for_search(question)
        if not terms:
            return []

        if chunks is None:
            chunks = self.vector_store.get_chunks_for_documents(
                allowed_document_ids,
                limit=self.settings.HYBRID_KEYWORD_MAX_CHUNKS,
            )
        scored_hits: list[dict] = []
        for chunk in chunks:
            score, matched_terms = _score_text(question, terms, str(chunk.get("text") or ""))
            if score <= 0:
                continue
            scored_hits.append(
                {
                    "id": chunk.get("id"),
                    "text": chunk.get("text") or "",
                    "metadata": chunk.get("metadata") or {},
                    "distance": None,
                    "score": score,
                    "keyword_score": score,
                    "matched_terms": matched_terms,
                    "retrieval_source": "keyword",
                }
            )
        scored_hits.sort(key=lambda item: float(item.get("keyword_score") or 0.0), reverse=True)
        return scored_hits[:top_k]


def _score_text(question: str, terms: list[str], text: str) -> tuple[float, list[str]]:
    normalized_text = normalize_for_search(text)
    compact_question = compact_for_search(question)
    compact_text = compact_for_search(text)

    raw_score = 0.0
    matched: list[str] = []
    if compact_question and len(compact_question) >= 4 and compact_question in compact_text:
        raw_score += 8.0
        matched.append(compact_question[:24])

    term_counts = Counter(terms)
    for term, term_weight_multiplier in term_counts.items():
        count = normalized_text.count(term)
        if count <= 0:
            continue
        weight = _term_weight(term) * math.sqrt(term_weight_multiplier)
        raw_score += min(count, 4) * weight
        matched.append(term)

    if raw_score <= 0:
        return 0.0, []
    score = raw_score / (raw_score + 12.0)
    return min(1.0, score), matched[:12]


def _term_weight(term: str) -> float:
    if any(char.isdigit() for char in term):
        return 3.0
    if any("a" <= char <= "z" for char in term):
        return 2.2
    if len(term) >= 4:
        return 1.6
    return 0.75
