from app.rag.chunkers.base_chunker import BaseChunker
from app.rag.schemas import DocumentChunk, LoadedDocumentPart


class RuleChunker(BaseChunker):
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 120) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> list[str]:
        normalized = text.strip()
        if not normalized:
            return []

        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(start + self.chunk_size, len(normalized))
            chunks.append(normalized[start:end])
            if end == len(normalized):
                break
            start = max(end - self.chunk_overlap, start + 1)
        return chunks

    def split_documents(self, parts: list[LoadedDocumentPart]) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        for part in parts:
            for local_index, text in enumerate(self.split_text(part.text)):
                metadata = dict(part.metadata)
                metadata["local_chunk_index"] = local_index
                chunks.append(DocumentChunk(text=text, metadata=metadata))
        return chunks
