import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.agent.graph import _parse_route
from app.agent.ingestion_agent import IngestionPlan, IngestionProbe, _rule_based_plan
from app.agent.ingestion_nodes import (
    IngestionCallbacks,
    IngestionContext,
    ParseOcrNode,
)
from app.rag.chunk_quality import annotate_one_chunk
from app.rag.loaders.liteparse_loader import blocks_from_liteparse_payload
from app.rag.schemas import DocumentBlock, DocumentChunk


class LiteParseIngestionTests(unittest.TestCase):
    def test_payload_maps_pages_and_ocr_metadata_to_document_blocks(self) -> None:
        payload = {
            "pages": [
                {
                    "page_number": 2,
                    "text_items": [
                        {
                            "text": "最大残留限量",
                            "bbox": [10, 10, 120, 30],
                            "confidence": 0.96,
                        },
                        {
                            "text": "禽肉 0.05 mg/kg",
                            "bbox": [10, 40, 180, 60],
                            "confidence": 0.92,
                        },
                    ],
                }
            ]
        }

        blocks = blocks_from_liteparse_payload(
            payload,
            source="legacy.doc",
            document_format="doc",
        )

        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        self.assertEqual(block.locator.page, 2)
        self.assertEqual(block.document_format, "doc")
        self.assertEqual(block.extraction_method, "liteparse_ocr")
        self.assertEqual(block.metadata["parser_family"], "liteparse")
        self.assertAlmostEqual(block.metadata["ocr_avg_score"], 0.94)
        self.assertIn("禽肉 0.05 mg/kg", block.text)

    @patch("app.agent.ingestion_agent.get_settings")
    def test_legacy_office_is_forced_to_liteparse_and_llm_bias(
        self,
        get_settings_mock,
    ) -> None:
        get_settings_mock.return_value = SimpleNamespace(
            LITEPARSE_OCR_ENABLED=True,
            PREPROCESS_LLM_ENABLED=True,
        )

        plan = _rule_based_plan(
            IngestionProbe(
                file_type="doc",
                file_size=100,
                readable=True,
            )
        )

        self.assertEqual(plan.primary_reader, "liteparse")
        self.assertTrue(plan.use_liteparse)
        self.assertFalse(plan.use_ocr)
        self.assertTrue(plan.use_llm_preprocessing)
        self.assertEqual(
            _parse_route({"context": SimpleNamespace(plan=plan)}),
            "liteparse",
        )

    @patch("app.agent.ingestion_agent.get_settings")
    def test_unreadable_modern_office_falls_back_to_liteparse(
        self,
        get_settings_mock,
    ) -> None:
        get_settings_mock.return_value = SimpleNamespace(
            LITEPARSE_ENABLED=True,
            LITEPARSE_OCR_ENABLED=True,
            PREPROCESS_LLM_ENABLED=True,
        )

        plan = _rule_based_plan(
            IngestionProbe(
                file_type="pptx",
                file_size=100,
                readable=False,
                probe_error="no readable text",
            )
        )

        self.assertEqual(plan.primary_reader, "liteparse")
        self.assertTrue(plan.use_liteparse)
        self.assertTrue(plan.use_llm_preprocessing)

    def test_liteparse_chunks_are_llm_normalization_candidates(self) -> None:
        with patch("app.rag.chunk_quality.get_settings") as get_settings_mock:
            get_settings_mock.return_value = SimpleNamespace(
                CHUNK_QUALITY_ENABLED=True,
                CHUNK_LLM_NORMALIZATION_ENABLED=True,
                CHUNK_LLM_MIN_QUALITY_SCORE=0.82,
                CHUNK_LLM_MIN_INPUT_CHARS=20,
            )
            chunk = annotate_one_chunk(
                DocumentChunk(
                    text="这是由 LiteParse 提取的版面文本，包含需要恢复的标题与表格行关系。",
                    metadata={
                        "parser_family": "liteparse",
                        "extraction_method": "liteparse_layout_text",
                        "chunk_type": "liteparse_page_text",
                    },
                )
            )

        self.assertTrue(chunk.metadata["needs_llm_normalization"])
        self.assertIn(
            "liteparse_extraction",
            chunk.metadata["chunk_quality_flags"],
        )

    @patch("app.agent.ingestion_nodes.DocumentPreprocessor")
    @patch("app.agent.ingestion_nodes.get_loader")
    def test_native_office_failure_replans_liteparse_and_llm_normalization(
        self,
        get_loader_mock: MagicMock,
        preprocessor_class_mock: MagicMock,
    ) -> None:
        native_loader = MagicMock()
        native_loader.load.side_effect = RuntimeError("native parse failed")
        liteparse_loader = MagicMock()
        liteparse_block = DocumentBlock(
            text="LiteParse 提取的版面文本",
            metadata={"parser_family": "liteparse"},
            document_format="docx",
            extraction_method="liteparse_layout_text",
        )
        liteparse_loader.load.return_value = [liteparse_block]
        get_loader_mock.side_effect = [native_loader, liteparse_loader]
        preprocessor_class_mock.return_value.preprocess.return_value = [
            liteparse_block
        ]

        stored_plans: list[IngestionPlan] = []
        callbacks = IngestionCallbacks(
            set_status=lambda _status, _message: None,
            update_progress=lambda _current, _total, _detail: None,
            update_trace=lambda _event: None,
            store_plan=stored_plans.append,
            should_normalize_chunks=lambda plan: bool(
                plan and plan.use_llm_preprocessing
            ),
            attach_metadata=lambda chunks: chunks,
            parser_status_message=lambda file_type: f"parse {file_type}",
        )
        probe = IngestionProbe(file_type="docx", file_size=100, readable=True)
        plan = IngestionPlan(
            primary_reader="docx_loader",
            use_ocr=False,
            use_liteparse=False,
            use_llm_preprocessing=False,
            reason="native",
            probe=probe,
        )
        context = IngestionContext(
            db=MagicMock(),
            document=SimpleNamespace(
                id=1,
                filename="sample.docx",
                file_type="docx",
                storage_path="sample.docx",
                status="queued",
                chunk_count=0,
            ),
            callbacks=callbacks,
            settings=SimpleNamespace(
                LITEPARSE_ENABLED=True,
                LITEPARSE_OCR_ENABLED=True,
                PREPROCESS_LLM_ENABLED=True,
                PREPROCESS_OCR_FALLBACK_ENABLED=True,
            ),
            probe=probe,
            plan=plan,
        )

        ParseOcrNode().run(context)

        self.assertTrue(context.plan.use_liteparse)
        self.assertTrue(context.plan.use_llm_preprocessing)
        self.assertTrue(context.report["effective_llm_preprocessing"])
        self.assertEqual(len(stored_plans), 1)
        kwargs = preprocessor_class_mock.return_value.preprocess.call_args.kwargs
        self.assertTrue(kwargs["use_llm_preprocessing"])


if __name__ == "__main__":
    unittest.main()
