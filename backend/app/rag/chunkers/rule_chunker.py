from app.rag.chunkers.base_chunker import BaseChunker
from app.rag.schemas import DocumentChunk, LoadedDocumentPart
from app.rag.table_utils import (
    augment_text_with_table_reference,
    is_table_like_text,
    metadata_with_table_reference,
    split_table_text,
)


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
            metadata = metadata_with_table_reference(part.metadata, part.text)
            text = augment_text_with_table_reference(part.text, metadata)
            is_table = is_table_like_text(text, metadata)
            split_texts = (
                split_table_text(text, chunk_size=self.chunk_size)
                if is_table
                else self.split_text(text)
            )
            segment_count = len(split_texts)
            for local_index, chunk_text in enumerate(split_texts):
                chunk_metadata = dict(metadata)
                if is_table:
                    chunk_metadata["is_table_chunk"] = True
                    chunk_metadata.setdefault(
                        "table_chunking_strategy",
                        "row_aware" if segment_count > 1 else "single_table_chunk",
                    )
                    chunk_metadata["table_source_text_length"] = len(text)
                if segment_count > 1 and is_table:
                    chunk_metadata["table_segment_index"] = local_index + 1
                    chunk_metadata["table_segment_count"] = segment_count
                    chunk_metadata["table_chunking_strategy"] = "row_aware"
                chunk_metadata["local_chunk_index"] = local_index
                chunks.append(DocumentChunk(text=chunk_text, metadata=chunk_metadata))
        return chunks
