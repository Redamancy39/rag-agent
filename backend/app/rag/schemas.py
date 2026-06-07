from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SourceLocator:
    """Format-independent source position used for citations and traceability."""

    page: int | None = None
    slide: int | None = None
    sheet: str | None = None
    cell_range: str | None = None
    section_path: str | None = None
    paragraph_index: int | None = None
    table_index: int | None = None
    block_index: int | None = None

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any]) -> "SourceLocator":
        return cls(
            page=_as_int(metadata.get("page")),
            slide=_as_int(metadata.get("slide")),
            sheet=_as_text(metadata.get("sheet")),
            cell_range=_as_text(metadata.get("cell_range")),
            section_path=_as_text(
                metadata.get("section_path") or metadata.get("section")
            ),
            paragraph_index=_as_int(metadata.get("paragraph_index")),
            table_index=_as_int(metadata.get("table_index")),
            block_index=_as_int(metadata.get("block_index")),
        )

    def to_metadata(self) -> dict[str, str | int]:
        metadata: dict[str, str | int] = {}
        values = {
            "page": self.page,
            "slide": self.slide,
            "sheet": self.sheet,
            "cell_range": self.cell_range,
            "section_path": self.section_path,
            "paragraph_index": self.paragraph_index,
            "table_index": self.table_index,
            "block_index": self.block_index,
        }
        for key, value in values.items():
            if value is not None and value != "":
                metadata[key] = value
        return metadata

    @property
    def kind(self) -> str:
        if self.sheet:
            return "sheet"
        if self.slide is not None:
            return "slide"
        if self.page is not None:
            return "page"
        if self.section_path:
            return "section"
        if self.table_index is not None:
            return "table"
        if self.block_index is not None:
            return "block"
        return "document"

    def canonical_key(self) -> str:
        values = self.to_metadata()
        if not values:
            return "document"
        ordered_keys = (
            "page",
            "slide",
            "sheet",
            "cell_range",
            "section_path",
            "paragraph_index",
            "table_index",
            "block_index",
        )
        return "|".join(
            f"{key}:{values[key]}"
            for key in ordered_keys
            if key in values
        )

    def display_label(self, *, include_block: bool = False) -> str:
        parts: list[str] = []
        if self.page is not None:
            parts.append(f"第 {self.page} 页")
        if self.slide is not None:
            parts.append(f"第 {self.slide} 张幻灯片")
        if self.section_path:
            parts.append(f"章节 {self.section_path}")
        if self.paragraph_index is not None:
            parts.append(f"段落 {self.paragraph_index}")
        if self.sheet:
            parts.append(f"工作表 {self.sheet}")
        if self.cell_range:
            parts.append(f"单元格 {self.cell_range}")
        if self.table_index is not None:
            parts.append(f"表格 {self.table_index}")
        if include_block and self.block_index is not None:
            parts.append(f"区块 {self.block_index}")
        return " / ".join(parts) if parts else "文档级"

    def provenance_parts(self) -> list[str]:
        parts: list[str] = []
        if self.page is not None:
            parts.append(f"页码：第{self.page}页")
        if self.slide is not None:
            parts.append(f"幻灯片：第{self.slide}张")
        if self.section_path:
            parts.append(f"章节：{self.section_path}")
        if self.paragraph_index is not None:
            parts.append(f"段落：{self.paragraph_index}")
        if self.sheet:
            parts.append(f"工作表：{self.sheet}")
        if self.cell_range:
            parts.append(f"单元格：{self.cell_range}")
        if self.table_index is not None:
            parts.append(f"表格：{self.table_index}")
        return parts

    def to_read_dict(self) -> dict[str, str | int | None]:
        return {
            "kind": self.kind,
            "key": self.canonical_key(),
            "label": self.display_label(),
            "page": self.page,
            "slide": self.slide,
            "sheet": self.sheet,
            "cell_range": self.cell_range,
            "section_path": self.section_path,
            "paragraph_index": self.paragraph_index,
            "table_index": self.table_index,
            "block_index": self.block_index,
        }


@dataclass(slots=True)
class DocumentBlock:
    """Unified intermediate representation emitted by every document loader."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    block_type: str | None = None
    source: str | None = None
    document_format: str | None = None
    extraction_method: str | None = None
    locator: SourceLocator | None = None

    def __post_init__(self) -> None:
        self.text = str(self.text or "")
        self.metadata = dict(self.metadata or {})
        self.block_type = (
            _as_text(self.block_type)
            or _as_text(self.metadata.get("chunk_type"))
            or _as_text(self.metadata.get("block_type"))
            or "text"
        )
        self.source = (
            _as_text(self.source)
            or _as_text(self.metadata.get("source"))
            or _as_text(self.metadata.get("filename"))
        )
        self.document_format = (
            _as_text(self.document_format)
            or _as_text(self.metadata.get("document_format"))
            or _infer_document_format(self.source)
        )
        self.extraction_method = (
            _as_text(self.extraction_method)
            or _as_text(self.metadata.get("extraction_method"))
        )
        self.locator = self.locator or SourceLocator.from_metadata(self.metadata)
        self.metadata = self.to_metadata()

    @classmethod
    def from_legacy(
        cls,
        *,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> "DocumentBlock":
        return cls(text=text, metadata=dict(metadata or {}))

    def to_metadata(self) -> dict[str, Any]:
        """Return flat metadata compatible with ChromaDB."""

        metadata = dict(self.metadata)
        if self.source:
            metadata["source"] = self.source
        if self.document_format:
            metadata["document_format"] = self.document_format
        if self.block_type:
            metadata["block_type"] = self.block_type
            metadata.setdefault("chunk_type", self.block_type)
        if self.extraction_method:
            metadata["extraction_method"] = self.extraction_method
        if self.locator:
            metadata.update(self.locator.to_metadata())
        return {
            key: value
            for key, value in metadata.items()
            if value is not None
        }


# Compatibility alias for modules and persisted metadata created before DocumentBlock.
LoadedDocumentPart = DocumentBlock


@dataclass(slots=True)
class DocumentChunk:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _infer_document_format(source: str | None) -> str | None:
    if not source or "." not in source:
        return None
    suffix = source.rsplit(".", maxsplit=1)[-1].lower().strip()
    return suffix or None
