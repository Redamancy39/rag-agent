from collections.abc import Callable
from pathlib import Path

from app.core.config import get_settings
from app.core.logger import get_logger
from app.rag.ingestion_enhancer import detect_bad_text_pages, enhance_loaded_parts
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

        if stage_callback:
            stage_callback("preprocessing", "正在检查文本层质量、OCR 需求和表格/单位异常")

        parts_usable = _parts_are_usable(processed_parts)
        bad_text_pages = (
            detect_bad_text_pages(processed_parts)
            if file_type == "pdf" and settings.PREPROCESS_LOCAL_BAD_PAGE_OCR_ENABLED
            else {}
        )
        should_run_targeted_ocr = bool(bad_text_pages) and parts_usable and not force_ocr
        should_run_full_ocr = (
            force_ocr
            or _text_length(processed_parts) < settings.OCR_MIN_EXTRACTED_CHARS
            or not parts_usable
        )
        ocr_parts: list[LoadedDocumentPart] = []

        if (
            file_type == "pdf"
            and settings.PREPROCESS_OCR_FALLBACK_ENABLED
            and (should_run_full_ocr or should_run_targeted_ocr)
        ):
            page_numbers = set(bad_text_pages) if should_run_targeted_ocr else None
            if stage_callback:
                if page_numbers:
                    stage_callback(
                        "ocr",
                        f"检测到 {len(page_numbers)} 个文本层异常页，正在按页调用 PaddleOCR",
                    )
                else:
                    stage_callback("ocr", "PDF 文本层不可用或策略要求 OCR，正在调用 PaddleOCR")
            logger.info(
                "Running OCR fallback for path=%s pages=%s quality=%s",
                path,
                sorted(page_numbers) if page_numbers else "all",
                _parts_quality_summary(processed_parts),
            )
            ocr_parts = PaddleOcrEngine().extract_pdf(path, page_numbers=page_numbers)

        processed_parts = enhance_loaded_parts(
            processed_parts,
            ocr_parts=ocr_parts,
            replace_bad_pages=(
                set(bad_text_pages)
                if settings.PREPROCESS_DROP_BAD_TEXT_LAYER_WHEN_OCR_AVAILABLE
                else set()
            ),
            replace_detected_bad_pages=settings.PREPROCESS_DROP_BAD_TEXT_LAYER_WHEN_OCR_AVAILABLE,
            replace_all_text_layer=bool(ocr_parts and should_run_full_ocr),
            repair_text=settings.PREPROCESS_TEXT_REPAIR_ENABLED,
        )
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
                stage_callback("llm_preprocessing", "正在对表格事实进行 LLM 结构化整理")
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
