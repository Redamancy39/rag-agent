from pathlib import Path
from collections.abc import Callable

from app.core.config import get_settings
from app.core.logger import get_logger
from app.rag.normalizers.llm_normalizer import normalize_with_llm
from app.rag.ocr.paddleocr_engine import PaddleOcrEngine
from app.rag.schemas import LoadedDocumentPart
from app.rag.text_quality import is_text_usable, text_quality_summary

logger = get_logger(__name__)


class DocumentPreprocessor:
    def preprocess(
        self,
        *,
        file_type: str,
        path: str | Path,
        parts: list[LoadedDocumentPart],
        stage_callback: Callable[[str, str], None] | None = None,
        force_ocr: bool = False,
        use_llm_preprocessing: bool | None = None,
    ) -> list[LoadedDocumentPart]:
        settings = get_settings()
        processed_parts = list(parts)
        parts_usable = _parts_are_usable(processed_parts)
        if stage_callback:
            stage_callback("preprocessing", "正在检查文本层质量和表格抽取结果")

        if (
            file_type == "pdf"
            and settings.PREPROCESS_OCR_FALLBACK_ENABLED
            and (
                force_ocr
                or
                _text_length(processed_parts) < settings.OCR_MIN_EXTRACTED_CHARS
                or not parts_usable
            )
        ):
            if stage_callback:
                stage_callback("ocr", "文本层为空或质量较差，正在使用 PaddleOCR 进行 OCR 识别")
            logger.info(
                "Running OCR fallback for path=%s quality=%s",
                path,
                _parts_quality_summary(processed_parts),
            )
            ocr_parts = PaddleOcrEngine().extract_pdf(path)
            if ocr_parts:
                processed_parts = ocr_parts if not parts_usable else [*processed_parts, *ocr_parts]
                parts_usable = _parts_are_usable(processed_parts)

        if file_type == "pdf" and settings.PDF_REJECT_GARBLED_TEXT and not parts_usable:
            raise ValueError(
                "PDF text layer appears garbled or unreadable. "
                "Enable PREPROCESS_OCR_FALLBACK_ENABLED=true and re-upload, "
                "or preprocess the PDF with OCR before indexing."
            )

        should_run_llm = (
            settings.PREPROCESS_LLM_ENABLED
            and processed_parts
            and (use_llm_preprocessing is not False)
        )
        if should_run_llm:
            if stage_callback:
                stage_callback("llm_preprocessing", "正在使用大模型整理表格事实和检索文本")
            logger.info("Running LLM preprocessing for path=%s parts=%s", path, len(processed_parts))
            llm_parts = normalize_with_llm(processed_parts)
            processed_parts.extend(llm_parts)

        return processed_parts


def _text_length(parts: list[LoadedDocumentPart]) -> int:
    return sum(len(part.text.strip()) for part in parts)


def _parts_are_usable(parts: list[LoadedDocumentPart]) -> bool:
    if not parts:
        return False
    combined_text = "\n".join(part.text for part in parts[:8])
    return is_text_usable(combined_text)


def _parts_quality_summary(parts: list[LoadedDocumentPart]) -> dict:
    combined_text = "\n".join(part.text for part in parts[:8])
    return text_quality_summary(combined_text)
