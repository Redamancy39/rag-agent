import re
from typing import Any

STANDARD_TABLE_REF_PATTERN = re.compile(r"表\s*([A-Za-z]?\d+(?:\.\d+)*)")
LOCAL_TABLE_REF_PATTERN = re.compile(r"表格\s*([A-Za-z]?\d+(?:\.\d+)*)")
SECTION_PATTERN = re.compile(r"\b4\.(\d{1,3})(?:\.\d+)?\b")
TABLE_CONTEXT_KEYWORDS = (
    "表",
    "表格",
    "限量",
    "最大残留限量",
    "菌落总数",
    "大肠菌群",
    "CFU",
    "μg/kg",
    "mg/kg",
    "g/kg",
    "不得检出",
)


def infer_table_reference(
    text: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[str | None, str | None]:
    metadata = metadata or {}
    label = _clean_value(metadata.get("table_label"))
    number = _clean_value(metadata.get("table_number"))
    if label:
        return label, number or _number_from_label(label)

    candidates = [
        _clean_value(metadata.get("table_title")),
        text,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        match = STANDARD_TABLE_REF_PATTERN.search(candidate)
        if match:
            number = match.group(1).replace(" ", "")
            return f"表{number}", number

    for candidate in candidates:
        if not candidate:
            continue
        match = LOCAL_TABLE_REF_PATTERN.search(candidate)
        if match:
            number = match.group(1).replace(" ", "")
            return f"表格{number}", number

    inferred = _infer_table_number_from_section(text)
    if inferred:
        return f"表{inferred}", inferred
    return None, None


def metadata_with_table_reference(
    metadata: dict[str, Any],
    text: str,
) -> dict[str, Any]:
    updated = dict(metadata)
    label, number = infer_table_reference(text, updated)
    if label:
        updated["table_label"] = label
    if number:
        updated["table_number"] = number
    return updated


def augment_text_with_table_reference(
    text: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    label, _ = infer_table_reference(text, metadata)
    if not label or label in text:
        return text
    return f"表号：{label}。\n{text}"


def is_table_like_text(text: str, metadata: dict[str, Any] | None = None) -> bool:
    metadata = metadata or {}
    chunk_type = str(metadata.get("chunk_type") or "")
    if "table" in chunk_type:
        return True
    if metadata.get("table_index") is not None or metadata.get("table_label"):
        return True
    if "|" in text and text.count("|") >= 4:
        return True
    keyword_hits = sum(1 for keyword in TABLE_CONTEXT_KEYWORDS if keyword in text)
    return keyword_hits >= 2


def split_table_text(
    text: str,
    *,
    chunk_size: int,
) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []
    if len(normalized) <= chunk_size:
        return [normalized]

    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    if len(lines) < 4:
        return _split_by_chars(normalized, chunk_size=chunk_size, overlap=0)

    prefix, body = _split_table_prefix_and_body(lines)
    if not body:
        return _split_by_chars(normalized, chunk_size=chunk_size, overlap=0)

    chunks: list[str] = []
    current: list[str] = []
    for line in body:
        candidate_lines = [*prefix, *current, line]
        candidate = "\n".join(candidate_lines)
        if len(candidate) <= chunk_size:
            current.append(line)
            continue
        if current:
            chunks.append("\n".join([*prefix, *current]))
            current = []
        if len("\n".join([*prefix, line])) > chunk_size:
            chunks.extend(
                _split_by_chars(
                    "\n".join([*prefix, line]),
                    chunk_size=chunk_size,
                    overlap=0,
                )
            )
        else:
            current.append(line)
    if current:
        chunks.append("\n".join([*prefix, *current]))
    return chunks or [normalized]


def _split_table_prefix_and_body(lines: list[str]) -> tuple[list[str], list[str]]:
    markdown_indices = [index for index, line in enumerate(lines) if line.startswith("|")]
    if len(markdown_indices) >= 2:
        first_table_index = markdown_indices[0]
        prefix = lines[:first_table_index]
        prefix.extend(lines[first_table_index : first_table_index + 2])
        body = lines[first_table_index + 2 :]
        return _trim_prefix(prefix), body

    prefix_count = min(8, len(lines) - 1)
    for index, line in enumerate(lines[:12]):
        if "表" in line or "最大残留限量" in line or "菌落总数" in line:
            prefix_count = min(max(index + 4, prefix_count), len(lines) - 1)
    return _trim_prefix(lines[:prefix_count]), lines[prefix_count:]


def _trim_prefix(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    prefix: list[str] = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        prefix.append(line)
        if len("\n".join(prefix)) > 360:
            break
    return prefix


def _split_by_chars(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _infer_table_number_from_section(text: str) -> str | None:
    if "最大残留限量" not in text and "残留限量" not in text:
        return None
    matches = SECTION_PATTERN.findall(text)
    if not matches:
        return None
    return matches[-1]


def _number_from_label(label: str) -> str | None:
    match = STANDARD_TABLE_REF_PATTERN.search(label) or LOCAL_TABLE_REF_PATTERN.search(label)
    return match.group(1).replace(" ", "") if match else None


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
