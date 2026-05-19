import math
import re
import unicodedata
from collections import Counter

from app.core.config import get_settings
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
    ) -> list[dict]:
        terms = _query_terms(question)
        if not terms:
            return []

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


def _query_terms(question: str) -> list[str]:
    normalized = _normalize_text(question)
    raw_terms = re.findall(
        r"[a-z0-9]+(?:[./_-][a-z0-9]+)*|[\u4e00-\u9fff]{2,}|[μµ]g|mg|kg|ml",
        normalized,
    )
    terms: list[str] = []
    for term in raw_terms:
        if len(term) <= 1:
            continue
        if _is_cjk(term) and len(term) > 8:
            terms.extend(_cjk_ngrams(term, min_n=2, max_n=4))
            terms.append(term[:8])
            terms.append(term[-8:])
        else:
            terms.append(term)
    return list(dict.fromkeys(terms))[:80]


def _score_text(question: str, terms: list[str], text: str) -> tuple[float, list[str]]:
    normalized_text = _normalize_text(text)
    compact_question = _normalize_text(question).replace(" ", "")
    compact_text = normalized_text.replace(" ", "")

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
    if re.search(r"\d", term):
        return 3.0
    if re.search(r"[a-z]", term):
        return 2.2
    if len(term) >= 4:
        return 1.6
    return 0.75


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").lower()


def _is_cjk(value: str) -> bool:
    return bool(re.fullmatch(r"[\u4e00-\u9fff]+", value))


def _cjk_ngrams(value: str, *, min_n: int, max_n: int) -> list[str]:
    grams: list[str] = []
    for n in range(min_n, max_n + 1):
        if len(value) < n:
            continue
        grams.extend(value[index : index + n] for index in range(0, len(value) - n + 1))
    return grams
