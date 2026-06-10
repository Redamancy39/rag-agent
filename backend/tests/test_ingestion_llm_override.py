import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.agent.graph import _llm_route
from app.agent.ingestion_nodes import (
    IngestionCallbacks,
    IngestionContext,
    ParseOcrNode,
)
from app.rag.schemas import DocumentBlock
from app.services.document_service import (
    _is_chunk_llm_enabled_for_document,
    _parse_llm_chunk_normalization_mode,
    _processing_llm_normalization_mode,
)


class IngestionLlmOverrideTests(unittest.TestCase):
    def _context(self, *, enabled: bool) -> IngestionContext:
        callbacks = IngestionCallbacks(
            set_status=lambda _status, _message: None,
            update_progress=lambda _current, _total, _detail: None,
            update_trace=lambda _event: None,
            store_plan=lambda _plan: None,
            should_normalize_chunks=lambda _plan: enabled,
            attach_metadata=lambda chunks: chunks,
            parser_status_message=lambda file_type: f"parse {file_type}",
        )
        document = SimpleNamespace(
            id=1,
            filename="sample.pptx",
            file_type="pptx",
            storage_path="sample.pptx",
            status="queued",
            chunk_count=0,
        )
        context = IngestionContext(
            db=MagicMock(),
            document=document,
            callbacks=callbacks,
        )
        context.plan = SimpleNamespace(
            primary_reader="pptx_loader",
            use_ocr=False,
            use_llm_preprocessing=True,
        )
        return context

    def test_user_override_controls_graph_route(self) -> None:
        context = self._context(enabled=False)

        self.assertEqual(
            _llm_route({"context": context}),
            "skip_llm_normalize",
        )

    @patch("app.agent.ingestion_nodes.DocumentPreprocessor")
    @patch("app.agent.ingestion_nodes.get_loader")
    def test_user_override_reaches_preprocessor(
        self,
        get_loader_mock: MagicMock,
        preprocessor_class_mock: MagicMock,
    ) -> None:
        context = self._context(enabled=False)
        get_loader_mock.return_value.load.return_value = [
            DocumentBlock(text="可读取文本", document_format="pptx")
        ]
        preprocessor_class_mock.return_value.preprocess.return_value = [
            DocumentBlock(text="可读取文本", document_format="pptx")
        ]

        ParseOcrNode().run(context)

        kwargs = preprocessor_class_mock.return_value.preprocess.call_args.kwargs
        self.assertFalse(kwargs["use_llm_preprocessing"])
        self.assertFalse(context.report["effective_llm_preprocessing"])

    def test_three_state_mode_parser_keeps_legacy_boolean_compatibility(self) -> None:
        self.assertEqual(_parse_llm_chunk_normalization_mode(None), "auto")
        self.assertEqual(_parse_llm_chunk_normalization_mode("auto"), "auto")
        self.assertEqual(_parse_llm_chunk_normalization_mode("enabled"), "enabled")
        self.assertEqual(_parse_llm_chunk_normalization_mode("disabled"), "disabled")
        self.assertEqual(_parse_llm_chunk_normalization_mode(True), "enabled")
        self.assertEqual(_parse_llm_chunk_normalization_mode(False), "disabled")
        self.assertEqual(
            _processing_llm_normalization_mode(
                {"enable_llm_chunk_normalization": True}
            ),
            "enabled",
        )

    @patch("app.services.document_service._get_processing_options")
    @patch("app.services.document_service.get_settings")
    def test_auto_mode_uses_ingestion_plan(
        self,
        get_settings_mock: MagicMock,
        get_options_mock: MagicMock,
    ) -> None:
        get_settings_mock.return_value = SimpleNamespace(
            PREPROCESS_LLM_ENABLED=True,
            CHUNK_LLM_NORMALIZATION_ENABLED=True,
        )
        get_options_mock.return_value = {"llm_chunk_normalization_mode": "auto"}

        enabled = _is_chunk_llm_enabled_for_document(
            MagicMock(),
            SimpleNamespace(id=1),
            ingestion_plan_use_llm=True,
        )
        disabled = _is_chunk_llm_enabled_for_document(
            MagicMock(),
            SimpleNamespace(id=1),
            ingestion_plan_use_llm=False,
        )

        self.assertTrue(enabled)
        self.assertFalse(disabled)

    @patch("app.services.document_service._get_processing_options")
    @patch("app.services.document_service.get_settings")
    def test_explicit_modes_override_ingestion_plan(
        self,
        get_settings_mock: MagicMock,
        get_options_mock: MagicMock,
    ) -> None:
        get_settings_mock.return_value = SimpleNamespace(
            PREPROCESS_LLM_ENABLED=True,
            CHUNK_LLM_NORMALIZATION_ENABLED=True,
        )
        get_options_mock.return_value = {"llm_chunk_normalization_mode": "enabled"}
        self.assertTrue(
            _is_chunk_llm_enabled_for_document(
                MagicMock(),
                SimpleNamespace(id=1),
                ingestion_plan_use_llm=False,
            )
        )

        get_options_mock.return_value = {"llm_chunk_normalization_mode": "disabled"}
        self.assertFalse(
            _is_chunk_llm_enabled_for_document(
                MagicMock(),
                SimpleNamespace(id=1),
                ingestion_plan_use_llm=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
