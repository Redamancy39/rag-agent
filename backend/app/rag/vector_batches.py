"""Shared preflight validation and bounded writes for vector collections."""
from dataclasses import dataclass
from typing import Any, Callable

from app.rag.schemas import DocumentChunk


@dataclass(frozen=True, slots=True)
class VectorWriteResult:
    row_count: int
    batch_count: int
    max_batch_size: int


class VectorBatchWriteError(RuntimeError):
    def __init__(self, batch_index: int, batch_count: int, completed_count: int, cause: Exception):
        self.batch_index = batch_index
        self.batch_count = batch_count
        self.completed_count = completed_count
        super().__init__(
            f'Vector batch {batch_index}/{batch_count} write failure '
            f'({type(cause).__name__}); {completed_count} rows completed. '
            'The document was not fully indexed.'
        )


def write_vector_batches(
    collection: Any,
    ids: list[str],
    chunks: list[DocumentChunk],
    embeddings: list[list[float]],
    *,
    max_batch_size: int,
    normalize_metadata: Callable[[dict], dict],
) -> VectorWriteResult:
    """Validate the full input before the first write and preserve row alignment."""
    if len(ids) != len(chunks) or len(ids) != len(embeddings):
        raise ValueError('Vector batch count mismatch: IDs, chunks and embeddings must align')
    if not isinstance(max_batch_size, int) or isinstance(max_batch_size, bool) or max_batch_size < 1:
        raise ValueError('ChromaDB returned an invalid maximum batch size')
    if any(not isinstance(value, str) or not value.strip() for value in ids):
        raise ValueError('Vector IDs must be nonempty strings')
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate vector IDs are not allowed')
    if not ids:
        return VectorWriteResult(0, 0, max_batch_size)
    dimension = len(embeddings[0])
    if not dimension or any(len(vector) != dimension for vector in embeddings):
        raise ValueError('Embedding dimensions must be nonempty and consistent')

    batch_count = (len(ids) + max_batch_size - 1) // max_batch_size
    for index, start in enumerate(range(0, len(ids), max_batch_size), start=1):
        stop = start + max_batch_size
        try:
            collection.add(
                ids=ids[start:stop],
                documents=[chunk.text for chunk in chunks[start:stop]],
                embeddings=embeddings[start:stop],
                metadatas=[normalize_metadata(chunk.metadata) for chunk in chunks[start:stop]],
            )
        except Exception as exc:
            raise VectorBatchWriteError(index, batch_count, start, exc) from exc
    return VectorWriteResult(len(ids), batch_count, max_batch_size)
