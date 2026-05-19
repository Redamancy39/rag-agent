from app.rag.loaders.base import BaseLoader
from app.rag.loaders.markdown_loader import MarkdownLoader
from app.rag.loaders.pdf_loader import PdfLoader
from app.rag.loaders.txt_loader import TxtLoader


def get_loader(file_type: str) -> BaseLoader:
    if file_type == "txt":
        return TxtLoader()
    if file_type == "markdown":
        return MarkdownLoader()
    if file_type == "pdf":
        return PdfLoader()
    raise ValueError(f"Unsupported file type: {file_type}")
