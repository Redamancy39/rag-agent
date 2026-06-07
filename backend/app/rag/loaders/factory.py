from app.rag.loaders.base import BaseLoader
from app.rag.loaders.docx_loader import DocxLoader
from app.rag.loaders.markdown_loader import MarkdownLoader
from app.rag.loaders.pdf_loader import PdfLoader
from app.rag.loaders.pptx_loader import PptxLoader
from app.rag.loaders.txt_loader import TxtLoader
from app.rag.loaders.xlsx_loader import XlsxLoader


def get_loader(file_type: str) -> BaseLoader:
    if file_type == "txt":
        return TxtLoader()
    if file_type == "markdown":
        return MarkdownLoader()
    if file_type == "pdf":
        return PdfLoader()
    if file_type == "docx":
        return DocxLoader()
    if file_type == "pptx":
        return PptxLoader()
    if file_type == "xlsx":
        return XlsxLoader()
    raise ValueError(f"Unsupported file type: {file_type}")
