import unittest

from app.rag.chunkers.rule_chunker import RuleChunker
from app.rag.schemas import DocumentBlock, LoadedDocumentPart, SourceLocator
from app.schemas.chat import Citation, EvidenceRow, RetrievalTraceHit
from app.schemas.document import DocumentChunkRead


class DocumentBlockTests(unittest.TestCase):
    def test_legacy_metadata_is_promoted_to_typed_fields(self) -> None:
        block = LoadedDocumentPart(
            text="legacy page text",
            metadata={
                "source": "legacy.pdf",
                "page": "3",
                "chunk_type": "page_text",
                "extraction_method": "pymupdf_text",
            },
        )

        self.assertIsInstance(block, DocumentBlock)
        self.assertEqual(block.source, "legacy.pdf")
        self.assertEqual(block.document_format, "pdf")
        self.assertEqual(block.block_type, "page_text")
        self.assertEqual(block.locator.page, 3)
        self.assertEqual(block.metadata["block_type"], "page_text")
        self.assertEqual(block.metadata["page"], 3)

    def test_typed_locator_is_flattened_for_vector_metadata(self) -> None:
        block = DocumentBlock(
            text="slide table",
            block_type="table_row_fact",
            source="deck.pptx",
            document_format="pptx",
            extraction_method="python_pptx",
            locator=SourceLocator(
                slide=4,
                section_path="Quality / Limits",
                table_index=2,
                block_index=7,
            ),
        )

        metadata = block.to_metadata()

        self.assertEqual(metadata["source"], "deck.pptx")
        self.assertEqual(metadata["document_format"], "pptx")
        self.assertEqual(metadata["chunk_type"], "table_row_fact")
        self.assertEqual(metadata["slide"], 4)
        self.assertEqual(metadata["section_path"], "Quality / Limits")
        self.assertEqual(metadata["table_index"], 2)
        self.assertNotIn("locator", metadata)

    def test_chunker_preserves_document_block_provenance(self) -> None:
        block = DocumentBlock(
            text="A" * 45,
            block_type="paragraph",
            source="policy.docx",
            extraction_method="python_docx",
            locator=SourceLocator(
                section_path="3 Scope / 3.2 Limits",
                paragraph_index=6,
            ),
        )

        chunks = RuleChunker(chunk_size=20, chunk_overlap=5).split_documents([block])

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertEqual(chunk.metadata["source"], "policy.docx")
            self.assertEqual(chunk.metadata["block_type"], "paragraph")
            self.assertEqual(chunk.metadata["chunk_type"], "paragraph")
            self.assertEqual(
                chunk.metadata["section_path"],
                "3 Scope / 3.2 Limits",
            )
            self.assertEqual(chunk.metadata["paragraph_index"], 6)

    def test_source_locator_builds_stable_cross_format_references(self) -> None:
        cases = [
            (
                SourceLocator(page=6, table_index=2),
                "page",
                "page:6|table_index:2",
                "第 6 页 / 表格 2",
            ),
            (
                SourceLocator(slide=4, section_path="风险控制"),
                "slide",
                "slide:4|section_path:风险控制",
                "第 4 张幻灯片 / 章节 风险控制",
            ),
            (
                SourceLocator(
                    section_path="质量要求 / 限量",
                    paragraph_index=8,
                ),
                "section",
                "section_path:质量要求 / 限量|paragraph_index:8",
                "章节 质量要求 / 限量 / 段落 8",
            ),
            (
                SourceLocator(sheet="Standards", cell_range="A12:D12"),
                "sheet",
                "sheet:Standards|cell_range:A12:D12",
                "工作表 Standards / 单元格 A12:D12",
            ),
        ]

        for locator, kind, key, label in cases:
            with self.subTest(kind=kind):
                self.assertEqual(locator.kind, kind)
                self.assertEqual(locator.canonical_key(), key)
                self.assertEqual(locator.display_label(), label)
                self.assertEqual(locator.to_read_dict()["label"], label)

    def test_chat_models_upgrade_legacy_flat_location_fields(self) -> None:
        citation = Citation(
            document_id=1,
            filename="legacy.pdf",
            page=3,
            table_index=1,
            text="evidence",
        )
        evidence = EvidenceRow(
            index=1,
            filename="legacy.pdf",
            page=3,
            table_index=1,
            keywords="evidence",
        )
        trace_hit = RetrievalTraceHit(
            rank=1,
            filename="legacy.pdf",
            page=3,
            table_index=1,
        )

        for item in (citation, evidence, trace_hit):
            self.assertIsNotNone(item.location)
            self.assertEqual(item.location.kind, "page")
            self.assertEqual(item.location.key, "page:3|table_index:1")
            self.assertEqual(item.location.label, "第 3 页 / 表格 1")

        chunk = DocumentChunkRead(
            id="doc:1:chunk:1",
            text="spreadsheet row",
            metadata={"sheet": "Limits", "cell_range": "B7:E7"},
        )
        self.assertEqual(chunk.location.kind, "sheet")
        self.assertEqual(
            chunk.location.label,
            "工作表 Limits / 单元格 B7:E7",
        )


if __name__ == "__main__":
    unittest.main()
