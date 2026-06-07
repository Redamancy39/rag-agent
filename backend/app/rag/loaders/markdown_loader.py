from pathlib import Path

from app.rag.loaders.txt_loader import TxtLoader, _read_text_with_fallback
from app.rag.schemas import DocumentBlock


class MarkdownLoader(TxtLoader):
    def load(self, path: str | Path) -> list[DocumentBlock]:
        file_path = Path(path)
        return [
            DocumentBlock(
                text=_read_text_with_fallback(file_path),
                block_type="markdown_text",
                source=file_path.name,
                document_format="markdown",
                extraction_method="markdown_file",
            )
        ]
