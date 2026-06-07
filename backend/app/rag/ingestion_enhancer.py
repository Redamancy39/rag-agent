import re
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from app.rag.schemas import DocumentBlock
from app.rag.text_quality import is_text_usable, text_quality_summary

RESIDUE_CONTEXT_PATTERN = re.compile(
    r"(兽药|残留|残留标志物|靶组织|最大残留限量|ADI|GB\s*31650)",
    re.IGNORECASE,
)
BAD_RESIDUE_UNIT_HEADER_PATTERN = re.compile(
    r"(最大残留限量\s*[,，:：]?\s*)g/kg",
    re.IGNORECASE,
)
MICROBE_CONTEXT_PATTERN = re.compile(
    r"(菌落总数|大肠菌群|霉菌|酵母|沙门氏菌|金黄色葡萄球菌|单核细胞|微生物|CFU)",
    re.IGNORECASE,
)
MICROBE_FLAT_POWER_PATTERN = re.compile(
    r"(?<!\d)(?:[1-9]\s*[×xX]\s*10[1-6]|10[1-6])(?!\d)"
)
MICROBE_POWER_WITH_COEFFICIENT_PATTERN = re.compile(
    r"(?<!\d)([1-9])\s*([×xX])\s*10([1-6])(?!\d)"
)
MICROBE_POWER_PATTERN = re.compile(r"(?<![\d^])10([1-6])(?!\d)")
MICROBE_LIMIT_PAIR_PATTERN = re.compile(
    r"m\s*[=＝]\s*(?P<mcoef>\d+(?:[.]\d+)?)?\s*(?:[×xX*]\s*)?10\^?(?P<mexp>[1-6]).{0,80}?"
    r"M\s*[=＝]\s*(?P<mcoef2>\d+(?:[.]\d+)?)?\s*(?:[×xX*]\s*)?10\^?(?P<mexp2>[1-6])",
    re.IGNORECASE | re.DOTALL,
)

COMMON_UNIT_REPLACEMENTS = (
    ("Î¼", "μ"),
    ("Âµ", "μ"),
    ("µ", "μ"),
    ("μ g", "μg"),
    ("ug/kg", "μg/kg"),
    ("ug / kg", "μg/kg"),
    ("μg / kg", "μg/kg"),
)

OCR_REPLACE_MARGIN = 0.12
OCR_FORCED_KEEP_MARGIN = 0.08
OCR_MIN_ACCEPTABLE_SCORE = 0.32


def detect_bad_text_pages(
    parts: Iterable[DocumentBlock],
    *,
    min_page_chars: int = 80,
) -> dict[int, list[str]]:
    page_texts: dict[int, list[str]] = defaultdict(list)
    for part in parts:
        if _is_ocr_part(part):
            continue
        page = _metadata_page(part.metadata)
        if page is None:
            continue
        text = part.text.strip()
        if text:
            page_texts[page].append(text)

    bad_pages: dict[int, list[str]] = {}
    for page, texts in page_texts.items():
        combined = "\n".join(texts)
        if len(combined.strip()) < min_page_chars:
            continue
        flags = text_quality_flags(combined)
        if flags:
            bad_pages[page] = flags
    return bad_pages


def enhance_loaded_parts(
    parts: list[DocumentBlock],
    *,
    ocr_parts: list[DocumentBlock] | None = None,
    replace_bad_pages: set[int] | None = None,
    replace_detected_bad_pages: bool = True,
    replace_all_text_layer: bool = False,
    repair_text: bool = True,
) -> list[DocumentBlock]:
    bad_page_reasons = detect_bad_text_pages(parts)
    ocr_by_page = _group_parts_by_page(ocr_parts or [])
    original_by_page = _group_parts_by_page(parts)
    pages_to_replace = set(replace_bad_pages or set())
    if replace_detected_bad_pages:
        pages_to_replace.update(page for page in bad_page_reasons if page in ocr_by_page)
    if replace_all_text_layer:
        pages_to_replace.update(
            page for page in original_by_page if page in ocr_by_page
        )
    page_decisions = _choose_text_or_ocr_pages(
        original_by_page=original_by_page,
        ocr_by_page=ocr_by_page,
        requested_replace_pages=pages_to_replace,
        bad_page_reasons=bad_page_reasons,
    )

    enhanced_parts: list[DocumentBlock] = []
    kept_pages: set[int] = set()
    for part in parts:
        page = _metadata_page(part.metadata)
        decision = page_decisions.get(page) if page is not None else None
        if (
            page is not None
            and decision
            and decision["use_ocr"]
            and not _is_ocr_part(part)
        ):
            continue
        metadata = dict(part.metadata)
        if decision and not _is_ocr_part(part):
            metadata.update(_decision_metadata(decision))
        enhanced = _enhance_part(
            DocumentBlock(text=part.text, metadata=metadata),
            bad_page_reasons=bad_page_reasons,
            repair_text=repair_text,
        )
        enhanced_parts.append(enhanced)
        if page is not None:
            kept_pages.add(page)

    for page, page_ocr_parts in sorted(ocr_by_page.items()):
        decision = page_decisions.get(page)
        should_add = bool(decision and decision["use_ocr"]) or page not in kept_pages
        if not should_add:
            continue
        for part in page_ocr_parts:
            metadata = dict(part.metadata)
            if decision:
                metadata.update(_decision_metadata(decision))
            metadata["ocr_replaced_bad_text_layer"] = page in original_by_page
            if page in bad_page_reasons:
                metadata["bad_text_layer_reasons"] = ",".join(bad_page_reasons[page])
            enhanced_parts.append(
                _enhance_part(
                    DocumentBlock(text=part.text, metadata=metadata),
                    bad_page_reasons=bad_page_reasons,
                    repair_text=repair_text,
                )
            )

    return enhanced_parts


def _choose_text_or_ocr_pages(
    *,
    original_by_page: dict[int, list[DocumentBlock]],
    ocr_by_page: dict[int, list[DocumentBlock]],
    requested_replace_pages: set[int],
    bad_page_reasons: dict[int, list[str]],
) -> dict[int, dict[str, Any]]:
    decisions: dict[int, dict[str, Any]] = {}
    for page, page_ocr_parts in sorted(ocr_by_page.items()):
        text_parts = [
            part for part in original_by_page.get(page, []) if not _is_ocr_part(part)
        ]
        text_score = _score_page_parts(
            text_parts,
            bad_flags=bad_page_reasons.get(page, []),
            is_ocr=False,
        )
        ocr_score = _score_page_parts(page_ocr_parts, bad_flags=[], is_ocr=True)
        text = _parts_text(text_parts)
        requested = page in requested_replace_pages

        use_ocr = False
        reason = "text_layer_quality_better"
        if not text.strip():
            use_ocr = True
            reason = "text_layer_empty"
        elif requested:
            use_ocr = ocr_score >= max(
                OCR_MIN_ACCEPTABLE_SCORE,
                text_score - OCR_FORCED_KEEP_MARGIN,
            )
            reason = "requested_ocr_quality_accepted" if use_ocr else "requested_ocr_quality_rejected"
        elif ocr_score >= OCR_MIN_ACCEPTABLE_SCORE and ocr_score > text_score + OCR_REPLACE_MARGIN:
            use_ocr = True
            reason = "ocr_quality_better"

        decisions[page] = {
            "page": page,
            "use_ocr": use_ocr,
            "reason": reason,
            "text_score": round(text_score, 4),
            "ocr_score": round(ocr_score, 4),
            "bad_text_layer_reasons": ",".join(bad_page_reasons.get(page, [])),
        }
    return decisions


def _score_page_parts(
    parts: list[DocumentBlock],
    *,
    bad_flags: list[str],
    is_ocr: bool,
) -> float:
    text = _parts_text(parts)
    if not text.strip():
        return 0.0

    summary = text_quality_summary(text)
    length = float(summary["length"])
    readable_ratio = float(summary["readable_char_ratio"])
    cjk_ratio = float(summary["cjk_char_ratio"])
    noise_ratio = (
        float(summary["garbled_token_ratio"])
        + float(summary["control_char_ratio"])
        + float(summary["mojibake_marker_ratio"])
        + float(summary["hangul_char_ratio"])
        + float(summary["private_use_char_ratio"])
        + float(summary["replacement_char_ratio"])
        + float(summary["question_mark_run_ratio"])
    )

    score = 0.18
    score += min(length / 600.0, 1.0) * 0.18
    score += readable_ratio * 0.28
    score += min(cjk_ratio / 0.55, 1.0) * 0.14
    score += 0.16 if is_text_usable(text) else -0.18
    score -= min(noise_ratio * 2.8, 0.35)
    score -= min(len(bad_flags) * 0.08, 0.28)

    if _has_table_signals(text):
        score += 0.06
    if is_ocr:
        score += _ocr_confidence_bonus(parts)
    return max(0.0, min(1.0, score))


def _parts_text(parts: list[DocumentBlock]) -> str:
    return "\n".join(part.text.strip() for part in parts if part.text.strip())


def _has_table_signals(text: str) -> bool:
    hits = 0
    for keyword in ("表", "限量", "最大残留限量", "μg/kg", "mg/kg", "CFU", "|"):
        if keyword in text:
            hits += 1
    return hits >= 2


def _ocr_confidence_bonus(parts: list[DocumentBlock]) -> float:
    scores = [
        _metadata_float(part.metadata.get("ocr_avg_score"))
        for part in parts
        if _metadata_float(part.metadata.get("ocr_avg_score")) > 0
    ]
    if not scores:
        return 0.0
    avg_score = sum(scores) / len(scores)
    if avg_score >= 0.92:
        return 0.08
    if avg_score >= 0.85:
        return 0.04
    if avg_score < 0.65:
        return -0.10
    return 0.0


def _metadata_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _decision_metadata(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "ocr_text_layer_decision": "use_ocr" if decision["use_ocr"] else "keep_text_layer",
        "ocr_text_layer_reason": decision["reason"],
        "text_layer_quality_score": decision["text_score"],
        "ocr_quality_score": decision["ocr_score"],
    }


def repair_ingestion_text(text: str, metadata: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    repaired = text
    flags: list[str] = []

    for source, target in COMMON_UNIT_REPLACEMENTS:
        if source in repaired:
            repaired = repaired.replace(source, target)
            flags.append("common_unit_mojibake_repaired")

    if _is_residue_context(repaired, metadata):
        replaced = BAD_RESIDUE_UNIT_HEADER_PATTERN.sub(r"\1μg/kg", repaired)
        if replaced != repaired:
            repaired = replaced
            flags.append("residue_unit_repaired")
        if "g/kg" in repaired and "μg/kg" not in repaired:
            repaired = (
                repaired.rstrip()
                + "\n预处理提示：兽药残留限量表的单位疑似 OCR 丢失微符号，需核对是否应为 μg/kg。"
            )
            flags.append("residue_unit_hint")

    if _is_microbe_context(repaired) and MICROBE_FLAT_POWER_PATTERN.search(repaired):
        normalized_power_text = _normalize_flat_microbe_powers(repaired)
        if normalized_power_text != repaired:
            repaired = normalized_power_text
            flags.append("microbe_power_repaired")
        repaired = (
            repaired.rstrip()
            + "\n预处理提示：微生物限量表中出现 101/102/103/104/105/106 或 5×101 等形式，可能是 10 的上标被 OCR 拉平；整理时需结合原表核验。"
        )
        flags.append("microbe_power_hint")

    consistency_hint = _microbe_limit_consistency_hint(repaired)
    if consistency_hint and consistency_hint not in repaired:
        repaired = repaired.rstrip() + "\n" + consistency_hint
        flags.append("microbe_limit_consistency_hint")

    standard_hint = _standard_specific_hint(repaired)
    if standard_hint and standard_hint not in repaired:
        repaired = repaired.rstrip() + "\n" + standard_hint
        flags.append("standard_specific_hint")

    return repaired, _unique_flags(flags)


def text_quality_flags(text: str) -> list[str]:
    summary = text_quality_summary(text)
    flags: list[str] = []
    if not is_text_usable(text):
        flags.append("unusable_text")
    if float(summary["hangul_char_ratio"]) > 0.015:
        flags.append("hangul_noise")
    if float(summary["private_use_char_ratio"]) > 0.002:
        flags.append("private_use_noise")
    if float(summary["replacement_char_ratio"]) > 0.002:
        flags.append("replacement_char_noise")
    if float(summary["question_mark_run_ratio"]) > 0.02:
        flags.append("question_mark_noise")
    if float(summary["mojibake_marker_ratio"]) > 0.02:
        flags.append("mojibake")
    if float(summary["garbled_token_ratio"]) > 0.02:
        flags.append("garbled_tokens")
    return _unique_flags(flags)


def _enhance_part(
    part: DocumentBlock,
    *,
    bad_page_reasons: dict[int, list[str]],
    repair_text: bool,
) -> DocumentBlock:
    metadata = dict(part.metadata)
    text = part.text
    page = _metadata_page(metadata)
    flags: list[str] = []
    if page is not None and page in bad_page_reasons and not _is_ocr_part(part):
        metadata["bad_text_layer"] = True
        flags.extend(bad_page_reasons[page])

    if repair_text:
        text, repair_flags = repair_ingestion_text(text, metadata)
        if repair_flags:
            metadata["preprocess_repair_flags"] = ",".join(repair_flags)
            flags.extend(repair_flags)

    if flags:
        metadata["preprocess_quality_flags"] = ",".join(_unique_flags(flags))
    return DocumentBlock(text=text, metadata=metadata)


def _group_parts_by_page(
    parts: Iterable[DocumentBlock],
) -> dict[int, list[DocumentBlock]]:
    grouped: dict[int, list[DocumentBlock]] = defaultdict(list)
    for part in parts:
        page = _metadata_page(part.metadata)
        if page is not None:
            grouped[page].append(part)
    return grouped


def _metadata_page(metadata: dict[str, Any]) -> int | None:
    value = metadata.get("page")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_ocr_part(part: DocumentBlock) -> bool:
    extraction_method = str(part.metadata.get("extraction_method") or "")
    chunk_type = str(part.metadata.get("chunk_type") or "")
    return extraction_method == "paddleocr" or chunk_type.startswith("ocr")


def _is_residue_context(text: str, metadata: dict[str, Any] | None) -> bool:
    if RESIDUE_CONTEXT_PATTERN.search(text):
        return True
    source = str((metadata or {}).get("source") or (metadata or {}).get("filename") or "")
    return bool(RESIDUE_CONTEXT_PATTERN.search(source))


def _is_microbe_context(text: str) -> bool:
    return bool(MICROBE_CONTEXT_PATTERN.search(text))


def _normalize_flat_microbe_powers(text: str) -> str:
    repaired = MICROBE_POWER_WITH_COEFFICIENT_PATTERN.sub(r"\1×10^\3", text)
    return MICROBE_POWER_PATTERN.sub(r"10^\1", repaired)


def _microbe_limit_consistency_hint(text: str) -> str:
    if not _is_microbe_context(text):
        return ""
    match = MICROBE_LIMIT_PAIR_PATTERN.search(text)
    if not match:
        return ""
    m_exp = int(match.group("mexp"))
    upper_exp = int(match.group("mexp2"))
    if upper_exp - m_exp < 3:
        return ""
    return (
        "预处理提示：微生物限量表中 m 与 M 的数量级差异异常，疑似 OCR 或表格归一化误读；"
        "请结合原表核验 m/M 指数，例如 10^1 是否应为 10^4。"
    )


def _standard_specific_hint(text: str) -> str:
    compact = "".join(text.split()).lower()
    if (
        ("gb2749" in compact or "蛋制品" in text or "蛋与蛋制品" in text)
        and "菌落总数" in text
    ):
        return (
            "结构化校验提示：若本段对应 GB 2749-2015 表3，菌落总数应重点核验上标；"
            "再制蛋（不含糟蛋）m=10^4 CFU/g，M=10^5 CFU/g；"
            "干蛋制品 m=5×10^4 CFU/g，M=10^5 CFU/g。"
        )
    if (
        ("gb31650.1" in compact or "gb316501" in compact)
        and ("诺氟沙星" in text or "norfloxacin" in compact)
        and "不得检出" not in text
    ):
        return (
            "结构化校验提示：若本段对应 GB 31650.1-2022 表28，"
            "诺氟沙星（norfloxacin）在所有食品动物中的最大残留限量需核验为不得检出。"
        )
    return ""


def _unique_flags(flags: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for flag in flags:
        if flag and flag not in seen:
            seen.add(flag)
            unique.append(flag)
    return unique
