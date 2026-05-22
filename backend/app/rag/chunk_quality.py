import re

from app.core.config import get_settings
from app.rag.schemas import DocumentChunk
from app.rag.text_quality import is_text_usable, text_quality_summary

TABLE_KEYWORDS = (
    "表",
    "限量",
    "最大残留",
    "μg/kg",
    "mg/kg",
    "g/kg",
    "动物种类",
    "靶组织",
    "残留标志物",
    "ADI",
)
NUMBER_ONLY_PATTERN = re.compile(r"^[0-9０-９.．,，\-~～]+$")
SUSPICIOUS_POWER_PATTERN = re.compile(
    r"(?<!\d)(?:[1-9]\s*[×xX]\s*10[1-6]|10[1-6])(?!\d)"
)
LLM_REPAIR_FLAGS = {
    "residue_unit_hint",
    "residue_unit_repaired",
    "microbe_power_hint",
    "microbe_power_repaired",
    "common_unit_mojibake_repaired",
    "standard_specific_hint",
}


def annotate_chunk_quality(chunks: list[DocumentChunk]) -> list[DocumentChunk]:
    settings = get_settings()
    if not settings.CHUNK_QUALITY_ENABLED:
        return chunks
    return [annotate_one_chunk(chunk) for chunk in chunks]


def annotate_one_chunk(chunk: DocumentChunk) -> DocumentChunk:
    metadata = dict(chunk.metadata)
    score, flags, metrics = score_chunk(chunk.text, metadata)
    metadata.update(metrics)
    metadata["chunk_quality_score"] = round(score, 4)
    metadata["chunk_quality_label"] = _quality_label(score)
    metadata["chunk_quality_flags"] = ",".join(flags)
    metadata["is_table_like"] = bool(metrics["is_table_like"])
    metadata["needs_llm_normalization"] = _needs_llm_normalization(score, flags, metadata)
    return DocumentChunk(text=chunk.text, metadata=metadata)


def score_chunk(
    text: str,
    metadata: dict,
) -> tuple[float, list[str], dict[str, float | int | bool]]:
    stripped = text.strip()
    quality = text_quality_summary(stripped)
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    line_count = len(lines)
    short_line_count = sum(1 for line in lines if len(line) <= 8)
    numeric_line_count = sum(1 for line in lines if NUMBER_ONLY_PATTERN.match(line))
    repeated_line_count = line_count - len(set(lines))

    short_line_ratio = short_line_count / line_count if line_count else 1.0
    numeric_line_ratio = numeric_line_count / line_count if line_count else 1.0
    repeated_line_ratio = repeated_line_count / line_count if line_count else 0.0
    table_like = _is_table_like(stripped, metadata, lines, short_line_ratio, numeric_line_ratio)
    preprocess_flags = _split_flags(metadata.get("preprocess_quality_flags"))
    repair_flags = _split_flags(metadata.get("preprocess_repair_flags"))

    score = 1.0
    flags: list[str] = []

    if quality["length"] < 80:
        score -= 0.18
        flags.append("short_text")
    if not is_text_usable(stripped):
        score -= 0.28
        flags.append("low_readability")
    if float(quality["garbled_token_ratio"]) > 0.02:
        score -= 0.2
        flags.append("garbled_tokens")
    if float(quality["mojibake_marker_ratio"]) > 0.02:
        score -= 0.2
        flags.append("mojibake")
    if float(quality["hangul_char_ratio"]) > 0.015:
        score -= 0.24
        flags.append("hangul_noise")
    if float(quality["private_use_char_ratio"]) > 0.002:
        score -= 0.24
        flags.append("private_use_noise")
    if float(quality["replacement_char_ratio"]) > 0.002:
        score -= 0.18
        flags.append("replacement_char_noise")
    if float(quality["question_mark_run_ratio"]) > 0.02:
        score -= 0.12
        flags.append("question_mark_noise")
    if short_line_ratio > 0.55 and line_count >= 6:
        score -= 0.08
        flags.append("fragmented_lines")
    if numeric_line_ratio > 0.2 and line_count >= 5:
        score -= 0.06
        flags.append("many_numeric_lines")
    if repeated_line_ratio > 0.25:
        score -= 0.08
        flags.append("repeated_lines")

    ocr_avg_score = _metadata_float(metadata.get("ocr_avg_score"))
    if ocr_avg_score and ocr_avg_score < 0.88:
        score -= min(0.2, (0.88 - ocr_avg_score) * 0.8)
        flags.append("low_ocr_confidence")

    if table_like:
        flags.append("table_like")
    if metadata.get("bad_text_layer") or "unusable_text" in preprocess_flags:
        score -= 0.2
        flags.append("bad_text_layer")
    if repair_flags & LLM_REPAIR_FLAGS:
        score -= 0.04
        flags.append("preprocess_repair_hint")
    if _has_suspicious_power_notation(stripped):
        score -= 0.06
        flags.append("suspicious_power_notation")

    score = max(0.0, min(1.0, score))
    metrics: dict[str, float | int | bool] = {
        "text_length": int(quality["length"]),
        "readable_chars": int(quality["readable_chars"]),
        "readable_char_ratio": round(float(quality["readable_char_ratio"]), 4),
        "cjk_char_ratio": round(float(quality["cjk_char_ratio"]), 4),
        "hangul_char_ratio": round(float(quality["hangul_char_ratio"]), 4),
        "private_use_char_ratio": round(float(quality["private_use_char_ratio"]), 4),
        "replacement_char_ratio": round(float(quality["replacement_char_ratio"]), 4),
        "question_mark_run_ratio": round(float(quality["question_mark_run_ratio"]), 4),
        "line_count": line_count,
        "short_line_ratio": round(short_line_ratio, 4),
        "numeric_line_ratio": round(numeric_line_ratio, 4),
        "repeated_line_ratio": round(repeated_line_ratio, 4),
        "is_table_like": table_like,
    }
    return score, flags, metrics


def _needs_llm_normalization(
    score: float,
    flags: list[str],
    metadata: dict,
) -> bool:
    settings = get_settings()
    if not settings.CHUNK_LLM_NORMALIZATION_ENABLED:
        return False
    chunk_type = str(metadata.get("chunk_type") or "")
    if chunk_type == "llm_normalized_chunk":
        return False
    if metadata.get("llm_normalized"):
        return False
    is_ocr = chunk_type.startswith("ocr") or metadata.get("extraction_method") == "paddleocr"
    high_value_flags = {
        "preprocess_repair_hint",
        "suspicious_power_notation",
        "bad_text_layer",
        "hangul_noise",
        "private_use_noise",
    }
    is_candidate = (
        is_ocr
        or "table_like" in flags
        or bool(set(flags) & high_value_flags)
        or score < settings.CHUNK_LLM_MIN_QUALITY_SCORE
    )
    return bool(is_candidate and metadata.get("text_length", 0) >= settings.CHUNK_LLM_MIN_INPUT_CHARS)


def _is_table_like(
    text: str,
    metadata: dict,
    lines: list[str],
    short_line_ratio: float,
    numeric_line_ratio: float,
) -> bool:
    if metadata.get("ocr_table_like") is True:
        return True
    if "|" in text and len(lines) >= 2:
        return True
    keyword_hits = sum(1 for keyword in TABLE_KEYWORDS if keyword in text)
    if keyword_hits >= 2 and len(lines) >= 4:
        return True
    return bool(keyword_hits >= 1 and short_line_ratio > 0.45 and numeric_line_ratio > 0.1)


def _metadata_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _split_flags(value: object) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in str(value).split(",") if item.strip()}


def _has_suspicious_power_notation(text: str) -> bool:
    if not SUSPICIOUS_POWER_PATTERN.search(text):
        return False
    context_keywords = ("菌落总数", "大肠菌群", "微生物", "CFU", "霉菌", "酵母")
    return any(keyword in text for keyword in context_keywords)


def _quality_label(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.65:
        return "medium"
    return "low"
