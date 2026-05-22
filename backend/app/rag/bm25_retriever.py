import math
from collections import Counter
from dataclasses import dataclass

from app.core.config import get_settings
from app.rag.search_tokenizer import (
    compact_for_search,
    matched_query_terms,
    normalize_for_search,
    tokenize_for_search,
)
from app.rag.vector_store import ChromaVectorStore


@dataclass(slots=True)
class _IndexedChunk:
    chunk: dict
    tokens: list[str]
    token_counts: Counter[str]
    length: int


class BM25Retriever:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.vector_store = ChromaVectorStore()
        self.k1 = self.settings.HYBRID_BM25_K1
        self.b = self.settings.HYBRID_BM25_B

    def retrieve(
        self,
        question: str,
        *,
        allowed_document_ids: list[int],
        top_k: int,
        chunks: list[dict] | None = None,
    ) -> list[dict]:
        query_tokens = tokenize_for_search(question)
        if not query_tokens or not allowed_document_ids:
            return []

        if chunks is None:
            chunks = self.vector_store.get_chunks_for_documents(
                allowed_document_ids,
                limit=self.settings.HYBRID_BM25_MAX_CHUNKS,
            )
        indexed_chunks = [_index_chunk(chunk) for chunk in chunks]
        indexed_chunks = [chunk for chunk in indexed_chunks if chunk.length > 0]
        if not indexed_chunks:
            return []

        document_frequencies = _document_frequencies(indexed_chunks)
        avg_document_length = sum(chunk.length for chunk in indexed_chunks) / len(indexed_chunks)
        query_token_counts = Counter(query_tokens)

        scored_hits: list[tuple[float, dict, list[str]]] = []
        for indexed_chunk in indexed_chunks:
            score = self._score_chunk(
                query_token_counts=query_token_counts,
                indexed_chunk=indexed_chunk,
                document_frequencies=document_frequencies,
                corpus_size=len(indexed_chunks),
                avg_document_length=avg_document_length,
            )
            text = str(indexed_chunk.chunk.get("text") or "")
            score += _phrase_boost(question, text)
            if score <= 0:
                continue
            matched_terms = matched_query_terms(query_tokens, text)
            scored_hits.append((score, indexed_chunk.chunk, matched_terms))

        if not scored_hits:
            return []

        scored_hits.sort(key=lambda item: item[0], reverse=True)
        max_score = scored_hits[0][0]
        results: list[dict] = []
        for raw_score, chunk, matched_terms in scored_hits[:top_k]:
            normalized_score = raw_score / max_score if max_score > 0 else 0.0
            results.append(
                {
                    "id": chunk.get("id"),
                    "text": chunk.get("text") or "",
                    "metadata": chunk.get("metadata") or {},
                    "distance": None,
                    "score": normalized_score,
                    "bm25_score": normalized_score,
                    "raw_bm25_score": round(raw_score, 6),
                    "matched_terms": matched_terms,
                    "retrieval_source": "bm25",
                }
            )
        return results

    def _score_chunk(
        self,
        *,
        query_token_counts: Counter[str],
        indexed_chunk: _IndexedChunk,
        document_frequencies: Counter[str],
        corpus_size: int,
        avg_document_length: float,
    ) -> float:
        score = 0.0
        length_norm = self.k1 * (
            1 - self.b + self.b * (indexed_chunk.length / max(avg_document_length, 1e-9))
        )
        for token, query_weight in query_token_counts.items():
            term_frequency = indexed_chunk.token_counts.get(token, 0)
            if term_frequency <= 0:
                continue
            idf = _idf(
                corpus_size=corpus_size,
                document_frequency=document_frequencies.get(token, 0),
            )
            term_score = (
                idf
                * ((term_frequency * (self.k1 + 1)) / (term_frequency + length_norm))
                * math.sqrt(query_weight)
            )
            score += term_score
        return score


def _index_chunk(chunk: dict) -> _IndexedChunk:
    metadata = chunk.get("metadata") or {}
    text = str(chunk.get("text") or "")
    metadata_text = " ".join(
        str(value or "")
        for value in (
            metadata.get("filename"),
            metadata.get("source"),
            metadata.get("table_title"),
            metadata.get("chunk_type"),
        )
    )
    tokens = tokenize_for_search(f"{metadata_text}\n{text}")
    return _IndexedChunk(
        chunk=chunk,
        tokens=tokens,
        token_counts=Counter(tokens),
        length=len(tokens),
    )


def _document_frequencies(chunks: list[_IndexedChunk]) -> Counter[str]:
    frequencies: Counter[str] = Counter()
    for chunk in chunks:
        frequencies.update(set(chunk.tokens))
    return frequencies


def _idf(*, corpus_size: int, document_frequency: int) -> float:
    return math.log(1 + (corpus_size - document_frequency + 0.5) / (document_frequency + 0.5))


def _phrase_boost(question: str, text: str) -> float:
    normalized_question = normalize_for_search(question)
    normalized_text = normalize_for_search(text)
    compact_question = compact_for_search(question)
    compact_text = compact_for_search(text)

    boost = 0.0
    if normalized_question and len(normalized_question) >= 4 and normalized_question in normalized_text:
        boost += 2.0
    if compact_question and len(compact_question) >= 4 and compact_question in compact_text:
        boost += 3.0
    return boost
