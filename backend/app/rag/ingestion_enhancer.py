import re
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from app.rag.schemas import LoadedDocumentPart
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


def detect_bad_text_pages(
    parts: Iterable[LoadedDocumentPart],
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
    parts: list[LoadedDocumentPart],
    *,
    ocr_parts: list[LoadedDocumentPart] | None = None,
    replace_bad_pages: set[int] | None = None,
    replace_detected_bad_pages: bool = True,
    replace_all_text_layer: bool = False,
    repair_text: bool = True,
) -> list[LoadedDocumentPart]:
    bad_page_reasons = detect_bad_text_pages(parts)
    ocr_by_page = _group_parts_by_page(ocr_parts or [])
    pages_to_replace = set(replace_bad_pages or set())
    if replace_detected_bad_pages:
        pages_to_replace.update(page for page in bad_page_reasons if page in ocr_by_page)
    if replace_all_text_layer:
        pages_to_replace.update(
            page for page in _group_parts_by_page(parts) if page in ocr_by_page
        )

    enhanced_parts: list[LoadedDocumentPart] = []
    kept_pages: set[int] = set()
    for part in parts:
        page = _metadata_page(part.metadata)
        if (
            page is not None
            and page in pages_to_replace
            and page in ocr_by_page
            and not _is_ocr_part(part)
        ):
            continue
        enhanced = _enhance_part(
            part,
            bad_page_reasons=bad_page_reasons,
            repair_text=repair_text,
        )
        enhanced_parts.append(enhanced)
        if page is not None:
            kept_pages.add(page)

    for page, page_ocr_parts in sorted(ocr_by_page.items()):
        should_add = page in pages_to_replace or page not in kept_pages
        if not should_add:
            continue
        for part in page_ocr_parts:
            metadata = dict(part.metadata)
            metadata["ocr_replaced_bad_text_layer"] = page in pages_to_replace
            if page in bad_page_reasons:
                metadata["bad_text_layer_reasons"] = ",".join(bad_page_reasons[page])
            enhanced_parts.append(
                _enhance_part(
                    LoadedDocumentPart(text=part.text, metadata=metadata),
                    bad_page_reasons=bad_page_reasons,
                    repair_text=repair_text,
                )
            )

    return enhanced_parts


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
    part: LoadedDocumentPart,
    *,
    bad_page_reasons: dict[int, list[str]],
    repair_text: bool,
) -> LoadedDocumentPart:
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
    return LoadedDocumentPart(text=text, metadata=metadata)


def _group_parts_by_page(
    parts: Iterable[LoadedDocumentPart],
) -> dict[int, list[LoadedDocumentPart]]:
    grouped: dict[int, list[LoadedDocumentPart]] = defaultdict(list)
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


def _is_ocr_part(part: LoadedDocumentPart) -> bool:
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
