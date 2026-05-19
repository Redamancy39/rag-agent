from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logger import get_logger
from app.rag.llm_client import OpenAICompatibleLLM
from app.rag.text_quality import is_text_usable, text_quality_summary

logger = get_logger(__name__)

INGESTION_AGENT_PROMPT = """你是文档入库工具选择 Agent。你只能根据文件探测信息选择处理工具。

可选工具：
1. pymupdf_text_table：适合有正常 PDF 文本层、需要表格探测的 PDF。
2. pypdf_text：适合没有 PyMuPDF 时的普通文本层 PDF。
3. paddleocr：适合扫描件、文本层为空、乱码、不可读文本。
4. llm_table_normalizer：适合表格多、需要把表格行整理成事实句。

要求：
- 如果文本长度很低、readable=false、乱码比例高，应选择 OCR。
- 如果表格数量大于 0，建议启用 llm_table_normalizer。
- 不要建议不存在的工具。
- 只输出 JSON。

JSON:
{
  "primary_reader": "pymupdf_text_table",
  "use_ocr": false,
  "use_llm_preprocessing": true,
  "reason": "简短原因"
}
"""


@dataclass(slots=True)
class IngestionProbe:
    file_type: str
    file_size: int
    page_count: int | None = None
    sampled_pages: int = 0
    text_chars: int = 0
    table_count: int = 0
    readable: bool = False
    quality: dict[str, float | int] = field(default_factory=dict)
    sample_text: str = ""
    probe_error: str | None = None


@dataclass(slots=True)
class IngestionPlan:
    primary_reader: str
    use_ocr: bool
    use_llm_preprocessing: bool
    reason: str
    probe: IngestionProbe
    source: str = "rules"

    @property
    def status_message(self) -> str:
        tools = [self.primary_reader]
        if self.use_ocr:
            tools.append("paddleocr")
        if self.use_llm_preprocessing:
            tools.append("llm_table_normalizer")
        return f"入库 Agent 已选择工具：{', '.join(tools)}。原因：{self.reason}"


def plan_ingestion(path: str | Path, file_type: str) -> IngestionPlan:
    settings = get_settings()
    file_path = Path(path)
    probe = probe_document(file_path, file_type)
    plan = _rule_based_plan(probe)
    if settings.INGESTION_AGENT_LLM_ENABLED and settings.OPENAI_API_KEY:
        plan = _merge_llm_plan(probe, plan)
    return plan


def probe_to_dict(probe: IngestionProbe) -> dict[str, Any]:
    return asdict(probe)


def plan_to_dict(plan: IngestionPlan) -> dict[str, Any]:
    return {
        "primary_reader": plan.primary_reader,
        "use_ocr": plan.use_ocr,
        "use_llm_preprocessing": plan.use_llm_preprocessing,
        "reason": plan.reason,
        "source": plan.source,
    }


def probe_document(path: Path, file_type: str) -> IngestionProbe:
    settings = get_settings()
    probe = IngestionProbe(
        file_type=file_type,
        file_size=path.stat().st_size if path.exists() else 0,
    )
    if file_type != "pdf":
        probe.readable = True
        return probe

    try:
        import fitz
    except ImportError:
        probe.probe_error = "PyMuPDF is not installed"
        return probe

    try:
        sample_text_parts: list[str] = []
        with fitz.open(str(path)) as pdf:
            probe.page_count = pdf.page_count
            sample_pages = min(pdf.page_count, max(1, settings.INGESTION_AGENT_SAMPLE_PAGES))
            probe.sampled_pages = sample_pages
            for page_index in range(sample_pages):
                page = pdf[page_index]
                text = page.get_text("text") or ""
                sample_text_parts.append(text)
                probe.table_count += _safe_table_count(page)
        probe.sample_text = "\n".join(sample_text_parts).strip()[:1500]
        probe.text_chars = len(probe.sample_text)
        probe.quality = text_quality_summary(probe.sample_text)
        probe.readable = is_text_usable(probe.sample_text)
    except Exception as exc:
        probe.probe_error = str(exc)
    return probe


def _rule_based_plan(probe: IngestionProbe) -> IngestionPlan:
    settings = get_settings()
    if probe.file_type != "pdf":
        return IngestionPlan(
            primary_reader=f"{probe.file_type}_loader",
            use_ocr=False,
            use_llm_preprocessing=False,
            reason="非 PDF 文件，直接使用对应文本 loader。",
            probe=probe,
        )

    needs_ocr = (
        bool(probe.probe_error)
        or probe.text_chars < settings.OCR_MIN_EXTRACTED_CHARS
        or not probe.readable
    )
    use_ocr = settings.PREPROCESS_OCR_FALLBACK_ENABLED and needs_ocr
    use_llm = settings.PREPROCESS_LLM_ENABLED and (probe.table_count > 0 or use_ocr)
    if use_ocr:
        reason = "PDF 文本层为空、乱码或不可读，优先使用 OCR。"
        primary_reader = "paddleocr"
    elif probe.probe_error:
        reason = "PyMuPDF 探测失败，回退到 pypdf 文本读取。"
        primary_reader = "pypdf_text"
    else:
        reason = "PDF 文本层可读，优先使用 PyMuPDF 读取文本和表格。"
        primary_reader = "pymupdf_text_table"
    if probe.table_count > 0 and use_llm:
        reason += f" 探测到 {probe.table_count} 个表格，启用大模型表格事实整理。"
    return IngestionPlan(
        primary_reader=primary_reader,
        use_ocr=use_ocr,
        use_llm_preprocessing=use_llm,
        reason=reason,
        probe=probe,
    )


def _merge_llm_plan(probe: IngestionProbe, fallback: IngestionPlan) -> IngestionPlan:
    try:
        payload = OpenAICompatibleLLM().complete_json(
            INGESTION_AGENT_PROMPT,
            _probe_prompt(probe, fallback),
        )
    except Exception as exc:
        logger.warning("Ingestion LLM planner failed, using rule plan: %s", exc)
        return fallback

    primary_reader = str(payload.get("primary_reader") or fallback.primary_reader)
    if primary_reader not in {
        "pymupdf_text_table",
        "pypdf_text",
        "paddleocr",
        "txt_loader",
        "markdown_loader",
    }:
        primary_reader = fallback.primary_reader

    llm_use_ocr = bool(payload.get("use_ocr", fallback.use_ocr))
    llm_use_llm = bool(payload.get("use_llm_preprocessing", fallback.use_llm_preprocessing))

    # Deterministic safety gates: do not let the LLM turn off OCR when probing found unusable text.
    use_ocr = fallback.use_ocr or llm_use_ocr
    use_llm = fallback.use_llm_preprocessing or llm_use_llm
    reason = str(payload.get("reason") or fallback.reason).strip()[:500]
    if not reason:
        reason = fallback.reason
    return IngestionPlan(
        primary_reader="paddleocr" if use_ocr else primary_reader,
        use_ocr=use_ocr,
        use_llm_preprocessing=use_llm,
        reason=reason,
        probe=probe,
        source="llm+rules",
    )


def _probe_prompt(probe: IngestionProbe, fallback: IngestionPlan) -> str:
    return (
        "文件探测信息：\n"
        f"- file_type: {probe.file_type}\n"
        f"- file_size: {probe.file_size}\n"
        f"- page_count: {probe.page_count}\n"
        f"- sampled_pages: {probe.sampled_pages}\n"
        f"- text_chars: {probe.text_chars}\n"
        f"- table_count: {probe.table_count}\n"
        f"- readable: {probe.readable}\n"
        f"- quality: {probe.quality}\n"
        f"- probe_error: {probe.probe_error}\n"
        f"- rule_plan: {fallback.primary_reader}, "
        f"use_ocr={fallback.use_ocr}, "
        f"use_llm_preprocessing={fallback.use_llm_preprocessing}, "
        f"reason={fallback.reason}\n"
        f"文本样本：\n{probe.sample_text[:800]}"
    )


def _safe_table_count(page: Any) -> int:
    find_tables = getattr(page, "find_tables", None)
    if find_tables is None:
        return 0
    try:
        table_finder = find_tables()
    except Exception:
        return 0
    return len(getattr(table_finder, "tables", []) or [])
