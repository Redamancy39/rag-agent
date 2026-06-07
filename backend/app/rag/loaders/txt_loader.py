from pathlib import Path

from app.rag.loaders.base import BaseLoader
from app.rag.schemas import DocumentBlock


class TxtLoader(BaseLoader):
    def load(self, path: str | Path) -> list[DocumentBlock]:
        file_path = Path(path)
        text = _read_text_with_fallback(file_path)
        return [
            DocumentBlock(
                text=text,
                block_type="document_text",
                source=file_path.name,
                document_format="txt",
                extraction_method="text_file",
            )
        ]


def _read_text_with_fallback(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")
