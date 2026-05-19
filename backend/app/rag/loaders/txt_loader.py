from pathlib import Path

from app.rag.loaders.base import BaseLoader
from app.rag.schemas import LoadedDocumentPart


class TxtLoader(BaseLoader):
    def load(self, path: str | Path) -> list[LoadedDocumentPart]:
        file_path = Path(path)
        text = _read_text_with_fallback(file_path)
        return [LoadedDocumentPart(text=text, metadata={"source": file_path.name})]


def _read_text_with_fallback(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")
