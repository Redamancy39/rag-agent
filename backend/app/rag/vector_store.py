import os
from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.core.logger import get_logger
from app.rag.schemas import DocumentChunk
from app.rag.vector_batches import VectorWriteResult, write_vector_batches

logger = get_logger(__name__)


class VectorStore:
    def add_documents(
        self,
        ids: list[str],
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> None:
        raise NotImplementedError("ChromaDB persistence will be implemented in stage 2")

    def search(self, query: str, filters: dict, top_k: int = 5) -> list[dict]:
        raise NotImplementedError("ChromaDB retrieval will be implemented in stage 3")


class ChromaVectorStore(VectorStore):
    def __init__(self, collection_name: str | None = None) -> None:
        settings = get_settings()
        self.max_batch_size = _get_client(str(settings.CHROMA_DIR)).get_max_batch_size()
        self.last_write_result: VectorWriteResult | None = None
        self.collection = _get_collection(
            path=str(settings.CHROMA_DIR),
            name=collection_name or settings.CHROMA_COLLECTION_NAME,
        )

    def add_documents(
        self,
        ids: list[str],
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> None:
        self.last_write_result = None
        self.last_write_result = write_vector_batches(
            self.collection, ids, chunks, embeddings,
            max_batch_size=self.max_batch_size, normalize_metadata=_normalize_metadata,
        )
        logger.info(
            'Vector write completed: rows=%s batches=%s max_batch_size=%s',
            self.last_write_result.row_count, self.last_write_result.batch_count,
            self.last_write_result.max_batch_size,
        )

    def delete_document(self, document_id: int) -> None:
        self.collection.delete(where={"document_id": document_id})

    def get_document_chunks(self, document_id: int, limit: int = 100) -> list[dict]:
        result = self.collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"],
            limit=limit,
        )
        ids = result.get("ids") or []
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        chunks = [
            {
                "id": chunk_id,
                "text": text,
                "metadata": metadata or {},
            }
            for chunk_id, text, metadata in zip(ids, documents, metadatas, strict=False)
        ]
        return sorted(
            chunks,
            key=lambda item: int(item["metadata"].get("chunk_index", 0)),
        )

    def get_chunks_for_documents(
        self,
        allowed_document_ids: list[int],
        *,
        limit: int = 3000,
    ) -> list[dict]:
        if not allowed_document_ids:
            return []

        where = _document_where(allowed_document_ids)
        result = self.collection.get(
            where=where,
            include=["documents", "metadatas"],
            limit=limit,
        )
        ids = result.get("ids") or []
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        return [
            {
                "id": chunk_id,
                "text": text,
                "metadata": metadata or {},
            }
            for chunk_id, text, metadata in zip(ids, documents, metadatas, strict=False)
        ]

    def search_by_embedding(
        self,
        query_embedding: list[float],
        *,
        allowed_document_ids: list[int],
        top_k: int = 5,
    ) -> list[dict]:
        if not query_embedding or not allowed_document_ids:
            return []

        where = _document_where(allowed_document_ids)

        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        hits = []
        for chunk_id, text, metadata, distance in zip(
            ids,
            documents,
            metadatas,
            distances,
            strict=False,
        ):
            hits.append(
                {
                    "id": chunk_id,
                    "text": text,
                    "metadata": metadata or {},
                    "distance": distance,
                    "score": _distance_to_score(distance),
                }
            )
        return hits


def _normalize_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
    normalized: dict[str, str | int | float | bool] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            normalized[key] = value
        else:
            normalized[key] = str(value)
    return normalized


def _distance_to_score(distance: Any) -> float | None:
    if not isinstance(distance, (int, float)):
        return None
    return max(0.0, min(1.0, 1.0 - float(distance)))


def _document_where(document_ids: list[int]) -> dict[str, Any]:
    if len(document_ids) == 1:
        return {"document_id": document_ids[0]}
    return {"document_id": {"$in": document_ids}}


@lru_cache(maxsize=4)
def _get_client(path: str):
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError(
            "ChromaDB persistence requires chromadb. "
            "Install: pip install -r requirements-rag.txt"
        ) from exc

    try:
        from chromadb.config import Settings

        client = chromadb.PersistentClient(
            path=path,
            settings=Settings(anonymized_telemetry=False),
        )
    except TypeError:
        client = chromadb.PersistentClient(path=path)
    return client


@lru_cache(maxsize=4)
def _get_collection(path: str, name: str):
    return _get_client(path).get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )
