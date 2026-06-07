from pathlib import Path
from typing import Any

from app.core.logger import get_logger
from app.rag.loaders.base import BaseLoader
from app.rag.normalizers.table_normalizer import normalize_table
from app.rag.schemas import DocumentBlock, SourceLocator

logger = get_logger(__name__)


class PdfLoader(BaseLoader):
    def load(self, path: str | Path) -> list[DocumentBlock]:
        try:
            return self._load_with_pymupdf(path)
        except Exception as pymupdf_exc:
            logger.warning(
                "PyMuPDF PDF parsing failed, trying pypdf fallback: path=%s error=%s",
                path,
                pymupdf_exc,
            )
            try:
                return self._load_with_pypdf(path)
            except Exception as pypdf_exc:
                raise RuntimeError(
                    "PDF parsing failed with both PyMuPDF and pypdf. "
                    f"PyMuPDF error: {pymupdf_exc}; pypdf error: {pypdf_exc}"
                ) from pypdf_exc

    def _load_with_pymupdf(self, path: str | Path) -> list[DocumentBlock]:
        try:
            import fitz
        except ImportError as exc:
            raise exc

        file_path = Path(path)
        parts: list[DocumentBlock] = []
        with fitz.open(str(file_path)) as pdf:
            for page_index, page in enumerate(pdf, start=1):
                tables = _find_tables(page)
                table_bboxes = [_normalize_bbox(getattr(table, "bbox", None)) for table in tables]
                table_bboxes = [bbox for bbox in table_bboxes if bbox is not None]

                text = _extract_text_outside_tables(page, table_bboxes)
                if text.strip():
                    parts.append(
                        DocumentBlock(
                            text=text,
                            block_type="page_text",
                            source=file_path.name,
                            document_format="pdf",
                            extraction_method="pymupdf_text",
                            locator=SourceLocator(page=page_index),
                        )
                    )

                for table_index, table in enumerate(tables, start=1):
                    rows = table.extract()
                    title = _find_table_title(page, _normalize_bbox(getattr(table, "bbox", None)))
                    parts.extend(
                        normalize_table(
                            rows,
                            page=page_index,
                            table_index=table_index,
                            table_title=title,
                            source=file_path.name,
                        )
                    )

        return parts

    def _load_with_pypdf(self, path: str | Path) -> list[DocumentBlock]:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError(
                "PDF parsing requires PyMuPDF or pypdf. Install: pip install -r requirements-rag.txt"
            ) from exc

        file_path = Path(path)
        reader = PdfReader(str(file_path))
        parts: list[DocumentBlock] = []
        for page_index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                parts.append(
                    DocumentBlock(
                        text=text,
                        block_type="page_text",
                        source=file_path.name,
                        document_format="pdf",
                        extraction_method="pypdf_text",
                        locator=SourceLocator(page=page_index),
                    )
                )
        return parts


def _find_tables(page: Any) -> list[Any]:
    find_tables = getattr(page, "find_tables", None)
    if find_tables is None:
        return []
    try:
        table_finder = find_tables()
    except Exception:
        return []
    return list(getattr(table_finder, "tables", []) or [])


def _extract_text_outside_tables(page: Any, table_bboxes: list[tuple[float, float, float, float]]) -> str:
    blocks = page.get_text("blocks")
    text_blocks: list[tuple[float, str]] = []
    for block in blocks:
        bbox = _normalize_bbox(block[:4])
        if bbox is None or _intersects_any(bbox, table_bboxes):
            continue
        text = str(block[4]).strip()
        if text:
            text_blocks.append((bbox[1], text))
    text_blocks.sort(key=lambda item: item[0])
    return "\n".join(text for _, text in text_blocks)


def _find_table_title(
    page: Any,
    table_bbox: tuple[float, float, float, float] | None,
) -> str | None:
    if table_bbox is None:
        return None
    blocks = page.get_text("blocks")
    candidates: list[tuple[float, str]] = []
    table_top = table_bbox[1]
    for block in blocks:
        bbox = _normalize_bbox(block[:4])
        if bbox is None:
            continue
        block_bottom = bbox[3]
        if block_bottom > table_top:
            continue
        text = _last_non_empty_line(str(block[4]))
        if not text:
            continue
        distance = table_top - block_bottom
        if distance <= 120:
            candidates.append((distance, text))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (0 if "表" in item[1] else 1, item[0]))
    return candidates[0][1][:120]


def _last_non_empty_line(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    return lines[-1] if lines else ""


def _normalize_bbox(value: Any) -> tuple[float, float, float, float] | None:
    if value is None or len(value) < 4:
        return None
    return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))


def _intersects_any(
    bbox: tuple[float, float, float, float],
    table_bboxes: list[tuple[float, float, float, float]],
) -> bool:
    return any(_intersects(bbox, table_bbox) for table_bbox in table_bboxes)


def _intersects(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    return not (
        left[2] <= right[0]
        or left[0] >= right[2]
        or left[3] <= right[1]
        or left[1] >= right[3]
    )
