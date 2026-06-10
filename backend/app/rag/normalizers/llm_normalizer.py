from dataclasses import dataclass
from math import ceil
from typing import Any
from collections.abc import Callable

from app.core.config import get_settings
from app.core.logger import get_logger
from app.rag.llm_client import LLMConfigError, OpenAICompatibleLLM
from app.rag.schemas import DocumentBlock, DocumentChunk

logger = get_logger(__name__)


@dataclass(slots=True)
class LlmNormalizationSelection:
    candidates: list[DocumentChunk]
    eligible_count: int
    skipped_existing_count: int
    limit: int


SYSTEM_PROMPT = """你是企业知识库入库预处理器。你的任务是把国标、法规、检测限量类文本整理成可检索事实。
只输出 JSON，不要输出 Markdown 或解释。
要求：
1. 不要编造原文没有的信息。
2. 保留食品类别、项目名称、限量值、单位、适用条件、页码或表格来源。
3. 如果无法确定字段，使用空字符串。
4. 每个 facts 元素应可直接用于向量检索。
JSON 格式：
{
  "facts": [
    {
      "question": "用户可能会怎么问",
      "answer": "简洁答案",
      "subject": "食品类别或适用对象",
      "item": "污染物/农药/指标/项目",
      "limit_value": "限量值",
      "unit": "单位",
      "condition": "适用条件",
      "evidence": "原文证据短句"
    }
  ]
}
"""


CHUNK_NORMALIZATION_PROMPT = """你是严谨的 RAG 入库清洗助手。你的任务是把 OCR 或表格型切块整理成更适合检索的中文事实文本。

要求：
1. 只能使用原始切块中的信息，禁止补充未出现的数值、单位、页码、条款或结论。
2. 可以修复明显的断行、表格行列关系、单位空格和 OCR 中的轻微排版问题。
3. 如果某个数值或列关系无法从原文确定，必须写“待核验”或“无法确定”，不能猜测。
4. 保留文件名、页码、条款号、表号、项目名、限量值、单位、适用条件等可溯源信息。
5. 只返回 JSON，不要返回 Markdown。
6. LiteParse/OCR 结果可能来自格式转换或版面投影；应优先恢复标题、段落和表格行列语义，但不得改写数字事实。

JSON 格式：
{
  "should_use": true,
  "normalized_text": "整理后的事实文本",
  "quality_notes": "说明做了哪些整理，以及哪些内容仍需核验",
  "confidence": 0.0
}
"""


SYSTEM_PROMPT += """
补充规则：
1. 表格表头出现单位时，行内数值默认沿用表头单位；不要把 μg/kg 写成 g/kg。
2. 兽药残留限量表如单位显示为 g/kg 但上下文为 GB 31650、残留限量、靶组织等，优先标注“单位疑似 μg/kg，待核验”，不要武断改成更大的 g/kg。
3. 微生物限量表中的 101/102/103/104/105/106、5×101 等形式可能是 10 的上标被 OCR 拉平；只有上下文明确时才整理为 10^n，否则写“待核验”。
4. 如果原文主要是乱码、私用区字符、韩文噪声或无法形成可信事实，facts 返回空数组。
"""

CHUNK_NORMALIZATION_PROMPT += """
补充规则：
1. 如果 metadata 或文本中包含 preprocess_repair_hint、residue_unit_hint、microbe_power_hint，要把它当成“需要谨慎核验”的提示，而不是事实本身。
2. 对限量值必须保留原始数字、比较符号和单位；表头单位可继承到行值，但不能凭空补充未出现的项目。
3. 兽药残留限量表优先使用 μg/kg；如果 OCR 显示 g/kg 但上下文明显是残留限量，应写“单位疑似 μg/kg，待核验”。
4. 微生物限量表遇到疑似上标丢失时，可在 normalized_text 中同时保留原始形式和“疑似 10^n”的说明。
5. 如果出现“结构化校验提示”，只能在原始文本同一标准、同一表或同一条款能对应时使用，并在输出中保留表号。
6. 如果文本层明显乱码，返回 should_use=false。
"""


class StructuredFactNormalizer:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._llm: OpenAICompatibleLLM | None = None

    def normalize(self, part: DocumentBlock) -> list[DocumentBlock]:
        chunk_type = str(part.metadata.get("chunk_type") or "")
        if chunk_type not in self.settings.PREPROCESS_LLM_TARGET_CHUNK_TYPES:
            return []
        if not part.text.strip():
            return []

        llm = self._get_llm()
        payload = llm.complete_json(SYSTEM_PROMPT, self._build_user_prompt(part))
        facts = payload.get("facts")
        if not isinstance(facts, list):
            return []

        normalized_parts: list[DocumentBlock] = []
        for fact_index, fact in enumerate(facts, start=1):
            if not isinstance(fact, dict):
                continue
            text = _fact_to_text(fact)
            if not text:
                continue
            metadata = dict(part.metadata)
            metadata.update(
                {
                    "chunk_type": "llm_structured_fact",
                    "source_chunk_type": chunk_type,
                    "llm_fact_index": fact_index,
                    "extraction_method": "llm_structured_normalization",
                    "llm_model": self.settings.OPENAI_MODEL_NAME,
                }
            )
            normalized_parts.append(DocumentBlock(text=text, metadata=metadata))
        return normalized_parts

    def _get_llm(self) -> OpenAICompatibleLLM:
        if self._llm is None:
            self._llm = OpenAICompatibleLLM()
        return self._llm

    def _build_user_prompt(self, part: DocumentBlock) -> str:
        text = part.text[: self.settings.PREPROCESS_LLM_MAX_INPUT_CHARS]
        page = part.metadata.get("page") or ""
        table_index = part.metadata.get("table_index") or ""
        table_title = part.metadata.get("table_title") or ""
        return (
            f"页码：{page}\n"
            f"表格序号：{table_index}\n"
            f"表题：{table_title}\n"
            f"预处理标记：{part.metadata.get('preprocess_quality_flags') or ''}\n"
            f"预处理修复提示：{part.metadata.get('preprocess_repair_flags') or ''}\n"
            "待整理文本：\n"
            f"{text}"
        )


def normalize_with_llm(parts: list[DocumentBlock]) -> list[DocumentBlock]:
    settings = get_settings()
    if not settings.PREPROCESS_LLM_ENABLED:
        return []

    normalizer = StructuredFactNormalizer()
    normalized_parts: list[DocumentBlock] = []
    for part in parts:
        try:
            normalized_parts.extend(normalizer.normalize(part))
        except LLMConfigError:
            raise
        except Exception as exc:
            logger.warning(
                "LLM preprocessing failed chunk_type=%s page=%s error=%s",
                part.metadata.get("chunk_type"),
                part.metadata.get("page"),
                exc,
            )
    return normalized_parts


class ChunkTextNormalizer:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._llm: OpenAICompatibleLLM | None = None

    def normalize(self, chunk: DocumentChunk) -> DocumentChunk | None:
        text = chunk.text.strip()
        if len(text) < self.settings.CHUNK_LLM_MIN_INPUT_CHARS:
            return None
        payload = self._get_llm().complete_json(
            CHUNK_NORMALIZATION_PROMPT,
            self._build_user_prompt(chunk),
        )
        if payload.get("should_use") is False:
            return None
        normalized_text = _clean_value(payload.get("normalized_text"))
        if len(normalized_text) < self.settings.CHUNK_LLM_MIN_INPUT_CHARS:
            return None
        if _same_text(normalized_text, text):
            return None

        metadata = dict(chunk.metadata)
        metadata.update(
            {
                "chunk_type": "llm_normalized_chunk",
                "source_chunk_type": chunk.metadata.get("chunk_type"),
                "source_local_chunk_index": chunk.metadata.get("local_chunk_index"),
                "source_chunk_index": chunk.metadata.get("chunk_index"),
                "source_chunk_key": _chunk_source_key(chunk),
                "extraction_method": "llm_chunk_normalization",
                "llm_model": self.settings.OPENAI_MODEL_NAME,
                "llm_normalized": True,
                "llm_confidence": _safe_confidence(payload.get("confidence")),
                "llm_quality_notes": _clean_value(payload.get("quality_notes"))[:500],
                "raw_text_preview": text[:800],
                "needs_llm_normalization": False,
            }
        )
        return DocumentChunk(text=normalized_text, metadata=metadata)

    def _get_llm(self) -> OpenAICompatibleLLM:
        if self._llm is None:
            self._llm = OpenAICompatibleLLM()
        return self._llm

    def _build_user_prompt(self, chunk: DocumentChunk) -> str:
        metadata = chunk.metadata
        text = chunk.text[: self.settings.PREPROCESS_LLM_MAX_INPUT_CHARS]
        return (
            f"文件名: {metadata.get('filename') or metadata.get('source') or ''}\n"
            f"页码: {metadata.get('page') or ''}\n"
            f"幻灯片: {metadata.get('slide') or ''}\n"
            f"工作表/单元格: {metadata.get('sheet') or ''} {metadata.get('cell_range') or ''}\n"
            f"内容类型: {metadata.get('chunk_type') or ''}\n"
            f"解析器: {metadata.get('parser_family') or metadata.get('extraction_method') or ''}\n"
            f"质量分: {metadata.get('chunk_quality_score') or ''}\n"
            f"质量标记: {metadata.get('chunk_quality_flags') or ''}\n"
            f"预处理标记: {metadata.get('preprocess_quality_flags') or ''}\n"
            f"预处理修复提示: {metadata.get('preprocess_repair_flags') or ''}\n"
            f"OCR平均置信度: {metadata.get('ocr_avg_score') or ''}\n"
            "原始切块:\n"
            f"{text}"
        )


def normalize_chunks_with_llm(
    chunks: list[DocumentChunk],
    progress_callback: Callable[[int, int, str], None] | None = None,
    *,
    force: bool = False,
) -> list[DocumentChunk]:
    settings = get_settings()
    if not (
        (settings.PREPROCESS_LLM_ENABLED or force)
        and settings.CHUNK_LLM_NORMALIZATION_ENABLED
    ):
        return []

    normalizer = ChunkTextNormalizer()
    normalized_chunks: list[DocumentChunk] = []
    selection = select_llm_normalization_candidates(chunks)
    candidates = selection.candidates
    total = len(candidates)
    if progress_callback:
        progress_callback(
            0,
            total,
            (
                f"待整理切块 {total} 个"
                f"（候选 {selection.eligible_count} 个，"
                f"已跳过已整理 {selection.skipped_existing_count} 个）"
            ),
        )
    for index, chunk in enumerate(candidates, start=1):
        if progress_callback:
            progress_callback(
                index - 1,
                total,
                f"正在整理 OCR/表格切块：第 {index} / {total} 个（已完成 {index - 1} 个）",
            )
        try:
            normalized = normalizer.normalize(chunk)
        except LLMConfigError as exc:
            logger.warning("Chunk LLM normalization skipped: %s", exc)
            return normalized_chunks
        except Exception as exc:
            logger.warning(
                "Chunk LLM normalization failed page=%s local_chunk=%s error=%s",
                chunk.metadata.get("page"),
                chunk.metadata.get("local_chunk_index"),
                exc,
            )
            continue
        if normalized:
            normalized_chunks.append(normalized)
        if progress_callback:
            progress_callback(
                index,
                total,
                f"已处理 OCR/表格切块：{index} / {total}",
            )
    if progress_callback:
        progress_callback(total, total, f"LLM 切块整理完成：{total} / {total}")
    return normalized_chunks


def select_llm_normalization_candidates(
    chunks: list[DocumentChunk],
) -> LlmNormalizationSelection:
    settings = get_settings()
    existing_source_keys = (
        _existing_normalized_source_keys(chunks)
        if settings.CHUNK_LLM_SKIP_ALREADY_NORMALIZED_SOURCES
        else set()
    )
    eligible: list[DocumentChunk] = []
    skipped_existing_count = 0
    for chunk in chunks:
        if not bool(chunk.metadata.get("needs_llm_normalization")):
            continue
        if _is_llm_normalized_chunk(chunk):
            continue
        source_key = _chunk_source_key(chunk)
        if source_key and source_key in existing_source_keys:
            skipped_existing_count += 1
            continue
        eligible.append(chunk)

    eligible.sort(key=lambda chunk: (-_candidate_priority(chunk), _chunk_order(chunk)))
    limit = _dynamic_candidate_limit(len(eligible), settings)
    return LlmNormalizationSelection(
        candidates=eligible[:limit],
        eligible_count=len(eligible),
        skipped_existing_count=skipped_existing_count,
        limit=limit,
    )


def dedupe_llm_normalized_chunks(chunks: list[DocumentChunk]) -> list[DocumentChunk]:
    latest_by_source: dict[str, int] = {}
    for index, chunk in enumerate(chunks):
        if not _is_llm_normalized_chunk(chunk):
            continue
        source_key = _normalized_source_key(chunk)
        if source_key:
            latest_by_source[source_key] = index

    deduped: list[DocumentChunk] = []
    for index, chunk in enumerate(chunks):
        if not _is_llm_normalized_chunk(chunk):
            deduped.append(chunk)
            continue
        source_key = _normalized_source_key(chunk)
        if not source_key or latest_by_source.get(source_key) == index:
            deduped.append(chunk)
    return deduped


def merge_llm_normalized_chunks(
    chunks: list[DocumentChunk],
    normalized_chunks: list[DocumentChunk],
    *,
    merge_mode: str | None = None,
) -> list[DocumentChunk]:
    merged = dedupe_llm_normalized_chunks([*chunks, *normalized_chunks])
    mode = (merge_mode or get_settings().CHUNK_LLM_MERGE_MODE).strip().lower()
    if mode not in {"replace_source", "replace", "replace_original"}:
        return merged

    normalized_source_keys = {
        source_key
        for chunk in merged
        if _is_llm_normalized_chunk(chunk)
        for source_key in [_normalized_source_key(chunk)]
        if source_key
    }
    if not normalized_source_keys:
        return merged

    compacted: list[DocumentChunk] = []
    for chunk in merged:
        if (
            not _is_llm_normalized_chunk(chunk)
            and _chunk_source_key(chunk) in normalized_source_keys
        ):
            continue
        compacted.append(chunk)
    return compacted


def _dynamic_candidate_limit(total: int, settings: Any) -> int:
    if total <= 0:
        return 0
    min_limit = max(1, int(settings.CHUNK_LLM_MIN_CHUNKS_PER_DOCUMENT))
    max_limit = max(min_limit, int(settings.CHUNK_LLM_MAX_CHUNKS_PER_DOCUMENT))
    ratio = max(0.0, float(settings.CHUNK_LLM_CANDIDATE_RATIO))
    ratio_limit = ceil(total * ratio)
    return min(total, max_limit, max(min_limit, ratio_limit))


def _existing_normalized_source_keys(chunks: list[DocumentChunk]) -> set[str]:
    keys: set[str] = set()
    for chunk in chunks:
        if not _is_llm_normalized_chunk(chunk):
            continue
        source_key = _normalized_source_key(chunk)
        if source_key:
            keys.add(source_key)
    return keys


def _is_llm_normalized_chunk(chunk: DocumentChunk) -> bool:
    metadata = chunk.metadata
    return bool(metadata.get("llm_normalized")) or str(metadata.get("chunk_type") or "") == "llm_normalized_chunk"


def _normalized_source_key(chunk: DocumentChunk) -> str | None:
    metadata = chunk.metadata
    explicit_key = _clean_value(metadata.get("source_chunk_key"))
    if explicit_key:
        return _canonical_source_key(explicit_key)
    source_chunk_type = metadata.get("source_chunk_type")
    if not source_chunk_type:
        return None
    source_metadata = dict(metadata)
    source_metadata["chunk_type"] = source_chunk_type
    if metadata.get("source_local_chunk_index") is not None:
        source_metadata["local_chunk_index"] = metadata.get("source_local_chunk_index")
    return _metadata_source_key(source_metadata)


def _chunk_source_key(chunk: DocumentChunk) -> str:
    return _metadata_source_key(chunk.metadata)


def _metadata_source_key(metadata: dict[str, Any]) -> str:
    fields = (
        "page",
        "chunk_type",
        "local_chunk_index",
        "table_index",
        "table_row_index",
        "table_segment_index",
        "table_label",
        "table_number",
        "source",
    )
    return _canonical_source_key(
        "|".join(_clean_value(metadata.get(field)) for field in fields)
    )


def _canonical_source_key(value: str) -> str:
    parts = value.split("|")
    # Older normalized chunks included document_id as the first source-key field.
    if len(parts) == 10:
        return "|".join(parts[1:])
    return value


def _candidate_priority(chunk: DocumentChunk) -> int:
    metadata = chunk.metadata
    flags = _split_flags(metadata.get("chunk_quality_flags"))
    repair_flags = _split_flags(metadata.get("preprocess_repair_flags"))
    chunk_type = str(metadata.get("chunk_type") or "")
    text = chunk.text
    priority = 0
    if repair_flags:
        priority += 80
    if flags & {"suspicious_power_notation", "preprocess_repair_hint", "bad_text_layer"}:
        priority += 70
    if "table_like" in flags or "table" in chunk_type or metadata.get("table_label"):
        priority += 55
    if chunk_type.startswith("ocr") or metadata.get("extraction_method") == "paddleocr":
        priority += 35
    extraction_method = str(metadata.get("extraction_method") or "").lower()
    if extraction_method == "liteparse_ocr":
        priority += 65
    elif (
        str(metadata.get("parser_family") or "").lower() == "liteparse"
        or extraction_method.startswith("liteparse")
    ):
        priority += 45
    quality_score = _safe_float(metadata.get("chunk_quality_score"))
    if quality_score is not None:
        priority += max(0, int((1.0 - quality_score) * 40))
    high_value_terms = (
        "限量",
        "最大使用量",
        "最大残留限量",
        "不得检出",
        "表",
        "μg/kg",
        "mg/kg",
        "CFU",
    )
    priority += min(30, 6 * sum(1 for term in high_value_terms if term in text))
    return priority


def _chunk_order(chunk: DocumentChunk) -> tuple[int, int, int]:
    metadata = chunk.metadata
    return (
        _safe_int(metadata.get("chunk_index")) or 0,
        _safe_int(metadata.get("page")) or 0,
        _safe_int(metadata.get("local_chunk_index")) or 0,
    )


def _split_flags(value: object) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in str(value).split(",") if item.strip()}


def _safe_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fact_to_text(fact: dict[str, Any]) -> str:
    fields = {
        "可检索问法": fact.get("question"),
        "答案": fact.get("answer"),
        "适用对象": fact.get("subject"),
        "项目": fact.get("item"),
        "限量值": fact.get("limit_value"),
        "单位": fact.get("unit"),
        "适用条件": fact.get("condition"),
        "原文证据": fact.get("evidence"),
    }
    lines = [f"{key}：{_clean_value(value)}" for key, value in fields.items() if _clean_value(value)]
    if not lines:
        return ""
    return "结构化检索事实：\n" + "\n".join(lines)


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _safe_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


def _same_text(left: str, right: str) -> bool:
    return "".join(left.split()) == "".join(right.split())
