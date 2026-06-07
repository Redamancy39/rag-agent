import json
import re
from pathlib import Path
from typing import Any, Iterator

from app.rag.loaders.base import BaseLoader
from app.rag.schemas import DocumentBlock, SourceLocator

MAX_SECTION_TEXT_CHARS = 3000
HEADING_STYLE_PATTERN = re.compile(r"(?:heading|标题)\s*([1-9])", re.IGNORECASE)


class DocxLoader(BaseLoader):
    """Extract headings, paragraph groups, and tables from a DOCX file."""

    def load(self, path: str | Path) -> list[DocumentBlock]:
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError(
                "DOCX parsing requires python-docx. "
                "Install: pip install -r requirements-rag.txt"
            ) from exc

        file_path = Path(path)
        document = Document(str(file_path))
        blocks: list[DocumentBlock] = []
        heading_path: list[str] = []
        paragraph_buffer: list[str] = []
        paragraph_start: int | None = None
        paragraph_end: int | None = None
        paragraph_index = 0
        table_index = 0
        last_text = ""

        def flush_paragraphs() -> None:
            nonlocal paragraph_buffer, paragraph_start, paragraph_end
            if not paragraph_buffer:
                return
            text = "\n".join(paragraph_buffer).strip()
            metadata: dict[str, Any] = {}
            if paragraph_end is not None:
                metadata["paragraph_end_index"] = paragraph_end
            blocks.append(
                DocumentBlock(
                    text=text,
                    block_type="section_text",
                    source=file_path.name,
                    document_format="docx",
                    extraction_method="python_docx",
                    locator=SourceLocator(
                        section_path=_section_path(heading_path),
                        paragraph_index=paragraph_start,
                    ),
                    metadata=metadata,
                )
            )
            paragraph_buffer = []
            paragraph_start = None
            paragraph_end = None

        for item in _iter_block_items(document):
            if _is_paragraph(item):
                paragraph_index += 1
                text = _clean_text(item.text)
                if not text:
                    continue
                heading_level = _heading_level(item)
                if heading_level is not None:
                    flush_paragraphs()
                    _update_heading_path(heading_path, heading_level, text)
                    last_text = text
                    continue

                if paragraph_start is None:
                    paragraph_start = paragraph_index
                paragraph_end = paragraph_index
                paragraph_buffer.append(text)
                last_text = text
                if sum(len(value) for value in paragraph_buffer) >= MAX_SECTION_TEXT_CHARS:
                    flush_paragraphs()
                continue

            flush_paragraphs()
            table_index += 1
            blocks.extend(
                _table_blocks(
                    item,
                    source=file_path.name,
                    table_index=table_index,
                    section_path=_section_path(heading_path),
                    table_title=last_text if _looks_like_table_title(last_text) else None,
                )
            )

        flush_paragraphs()
        return blocks


def _iter_block_items(document: Any) -> Iterator[Any]:
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _is_paragraph(item: Any) -> bool:
    from docx.text.paragraph import Paragraph

    return isinstance(item, Paragraph)


def _heading_level(paragraph: Any) -> int | None:
    style_name = str(getattr(getattr(paragraph, "style", None), "name", "") or "")
    match = HEADING_STYLE_PATTERN.search(style_name)
    if match:
        return int(match.group(1))

    paragraph_properties = getattr(paragraph._p, "pPr", None)
    outline_level = getattr(paragraph_properties, "outlineLvl", None)
    value = getattr(outline_level, "val", None)
    try:
        return int(value) + 1 if value is not None else None
    except (TypeError, ValueError):
        return None


def _update_heading_path(path: list[str], level: int, text: str) -> None:
    level = max(1, min(level, 9))
    del path[level - 1 :]
    while len(path) < level - 1:
        path.append("")
    path.append(text)


def _section_path(path: list[str]) -> str | None:
    values = [value for value in path if value]
    return " / ".join(values) if values else None


def _table_blocks(
    table: Any,
    *,
    source: str,
    table_index: int,
    section_path: str | None,
    table_title: str | None,
) -> list[DocumentBlock]:
    rows = [
        [_clean_text(cell.text) for cell in row.cells]
        for row in table.rows
    ]
    rows = [row for row in rows if any(row)]
    if not rows:
        return []

    column_count = max(len(row) for row in rows)
    rows = [_pad_row(row, column_count) for row in rows]
    headers = _dedupe_headers(rows[0])
    data_rows = rows[1:]
    table_id = f"docx:t{table_index}"
    common_metadata = {
        "table_id": table_id,
        "table_title": table_title,
        "table_row_count": len(data_rows),
        "table_column_count": len(headers),
        "table_columns": " | ".join(headers),
        "table_chunking_strategy": "row_aware",
    }
    locator = SourceLocator(
        section_path=section_path,
        table_index=table_index,
    )
    blocks = [
        DocumentBlock(
            text=_table_markdown(headers, data_rows),
            block_type="table_markdown",
            source=source,
            document_format="docx",
            extraction_method="python_docx_table",
            locator=locator,
            metadata=common_metadata,
        )
    ]

    for row_index, row in enumerate(data_rows, start=1):
        row_map = dict(zip(headers, row, strict=False))
        facts = "；".join(
            f"{key}：{value}"
            for key, value in row_map.items()
            if value
        )
        if not facts:
            continue
        prefix = f"{table_title}。" if table_title else ""
        blocks.append(
            DocumentBlock(
                text=f"{prefix}表格第{row_index}行：{facts}。",
                block_type="table_row_fact",
                source=source,
                document_format="docx",
                extraction_method="python_docx_table",
                locator=SourceLocator(
                    section_path=section_path,
                    table_index=table_index,
                    block_index=row_index,
                ),
                metadata={
                    **common_metadata,
                    "table_row_index": row_index,
                    "table_row_fields_json": json.dumps(
                        row_map,
                        ensure_ascii=False,
                    ),
                    "table_chunking_strategy": "row_fact",
                },
            )
        )
    return blocks


def _table_markdown(headers: list[str], rows: list[list[str]]) -> str:
    header_line = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_line, separator, *body])


def _dedupe_headers(values: list[str]) -> list[str]:
    headers: list[str] = []
    counts: dict[str, int] = {}
    for index, value in enumerate(values, start=1):
        base = value or f"列{index}"
        counts[base] = counts.get(base, 0) + 1
        headers.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
    return headers


def _pad_row(row: list[str], column_count: int) -> list[str]:
    return [*row, *([""] * (column_count - len(row)))]


def _clean_text(value: Any) -> str:
    lines = [" ".join(line.split()) for line in str(value or "").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _looks_like_table_title(text: str) -> bool:
    compact = text.strip()
    return bool(compact) and (
        compact.startswith("表")
        or re.match(r"^Table\s+\d+", compact, re.IGNORECASE) is not None
    )
