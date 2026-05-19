from typing import Any

from app.rag.schemas import LoadedDocumentPart

SUBJECT_KEYWORDS = (
    "食品",
    "类别",
    "品种",
    "名称",
    "使用范围",
    "应用范围",
    "范围",
)
ITEM_KEYWORDS = (
    "添加剂",
    "项目",
    "指标",
    "物质",
    "污染物",
    "农药",
    "兽药",
    "名称",
)
LIMIT_KEYWORDS = (
    "限量",
    "最大使用量",
    "最大残留量",
    "残留限量",
    "允许量",
    "指标",
    "要求",
    "不得超过",
    "mg/kg",
    "g/kg",
    "ml/kg",
)
UNIT_KEYWORDS = ("单位", "mg/kg", "g/kg", "μg/kg", "ug/kg", "ml/kg")


def normalize_table(
    rows: list[list[Any]],
    *,
    page: int,
    table_index: int,
    table_title: str | None = None,
) -> list[LoadedDocumentPart]:
    cleaned_rows = _clean_rows(rows)
    if len(cleaned_rows) < 2:
        return []

    headers, data_rows = _split_header_and_rows(cleaned_rows)
    if not headers or not data_rows:
        return []

    parts: list[LoadedDocumentPart] = []
    markdown = table_to_markdown(headers, data_rows)
    if markdown:
        parts.append(
            LoadedDocumentPart(
                text=_with_table_source(
                    "表格原文转写：\n" + markdown,
                    page=page,
                    table_index=table_index,
                    table_title=table_title,
                ),
                metadata={
                    "page": page,
                    "table_index": table_index,
                    "table_title": table_title,
                    "chunk_type": "table_markdown",
                    "extraction_method": "pymupdf_table",
                },
            )
        )

    for row_index, row in enumerate(data_rows, start=1):
        row_map = _row_to_map(headers, row)
        text = verbalize_row(
            row_map,
            page=page,
            table_index=table_index,
            table_title=table_title,
            row_index=row_index,
        )
        if text:
            parts.append(
                LoadedDocumentPart(
                    text=text,
                    metadata={
                        "page": page,
                        "table_index": table_index,
                        "table_title": table_title,
                        "table_row_index": row_index,
                        "chunk_type": "table_row_fact",
                        "extraction_method": "pymupdf_table",
                    },
                )
            )
    return parts


def verbalize_row(
    row_map: dict[str, str],
    *,
    page: int,
    table_index: int,
    table_title: str | None,
    row_index: int,
) -> str:
    non_empty_items = [(key, value) for key, value in row_map.items() if value]
    if not non_empty_items:
        return ""

    subject_key = _find_best_key(row_map, SUBJECT_KEYWORDS)
    item_key = _find_best_key(row_map, ITEM_KEYWORDS, excluded={subject_key})
    unit_key = _find_unit_key(row_map)
    limit_keys = _find_keys(row_map, LIMIT_KEYWORDS, excluded={subject_key, item_key, unit_key})
    if not limit_keys:
        limit_keys = [
            key
            for key, value in non_empty_items
            if key not in {subject_key, item_key, unit_key} and _looks_like_limit_value(value)
        ]

    source = _table_source(page=page, table_index=table_index, table_title=table_title)
    facts = "；".join(f"{key}为{value}" for key, value in non_empty_items)

    if not limit_keys:
        return f"{source}。表格第{row_index}行记录：{facts}。"

    subject_value = row_map.get(subject_key or "", "")
    item_value = row_map.get(item_key or "", "")
    unit_value = row_map.get(unit_key or "", "")
    fact_sentences: list[str] = []
    for limit_key in limit_keys:
        limit_value = row_map.get(limit_key, "")
        if not limit_value:
            continue
        unit_clause = ""
        if unit_value and unit_value not in limit_value and unit_value not in limit_key:
            unit_clause = f"，单位为{unit_value}"
        elif _header_contains_unit(limit_key):
            unit_clause = f"，单位见字段“{limit_key}”"

        if item_value and subject_value:
            fact_sentences.append(
                f"{item_value}在{subject_value}中的{limit_key}为{limit_value}{unit_clause}"
            )
        elif subject_value:
            fact_sentences.append(f"{subject_value}的{limit_key}为{limit_value}{unit_clause}")
        elif item_value:
            fact_sentences.append(f"{item_value}的{limit_key}为{limit_value}{unit_clause}")
        else:
            fact_sentences.append(f"{limit_key}为{limit_value}{unit_clause}")

    if not fact_sentences:
        return f"{source}。表格第{row_index}行记录：{facts}。"

    question_hint = ""
    if item_value and subject_value:
        question_hint = f"可检索问法：{item_value}在{subject_value}中的限量是多少。"
    elif subject_value:
        question_hint = f"可检索问法：{subject_value}的限量或指标是多少。"

    facts_text = "；".join(fact_sentences)
    return f"{source}。检索事实：{facts_text}。{question_hint}完整字段：{facts}。"


def table_to_markdown(headers: list[str], rows: list[list[str]]) -> str:
    if not headers:
        return ""
    normalized_rows = [_pad_row(row, len(headers)) for row in rows]
    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join("---" for _ in headers) + " |"
    body_lines = ["| " + " | ".join(row) + " |" for row in normalized_rows]
    return "\n".join([header_line, separator_line, *body_lines])


def _clean_rows(rows: list[list[Any]]) -> list[list[str]]:
    cleaned: list[list[str]] = []
    for row in rows:
        values = [_clean_cell(cell) for cell in row]
        if any(values):
            cleaned.append(values)
    return cleaned


def _split_header_and_rows(rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    header_index = 0
    for index, row in enumerate(rows[:3]):
        if _looks_like_header(row):
            header_index = index
            break
    headers = _dedupe_headers(rows[header_index])
    data_rows = rows[header_index + 1 :]
    return headers, data_rows


def _looks_like_header(row: list[str]) -> bool:
    joined = "".join(row)
    keywords = SUBJECT_KEYWORDS + ITEM_KEYWORDS + LIMIT_KEYWORDS + UNIT_KEYWORDS
    return any(keyword in joined for keyword in keywords)


def _dedupe_headers(headers: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: dict[str, int] = {}
    for index, header in enumerate(headers, start=1):
        base = header or f"列{index}"
        seen[base] = seen.get(base, 0) + 1
        deduped.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return deduped


def _row_to_map(headers: list[str], row: list[str]) -> dict[str, str]:
    padded_row = _pad_row(row, len(headers))
    return dict(zip(headers, padded_row, strict=False))


def _pad_row(row: list[str], length: int) -> list[str]:
    if len(row) >= length:
        return row[:length]
    return [*row, *([""] * (length - len(row)))]


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", "\n")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return " ".join(line for line in lines if line).strip()


def _find_best_key(
    row_map: dict[str, str],
    keywords: tuple[str, ...],
    excluded: set[str | None] | None = None,
) -> str | None:
    matches = _find_keys(row_map, keywords, excluded=excluded)
    return matches[0] if matches else None


def _find_unit_key(row_map: dict[str, str]) -> str | None:
    for key, value in row_map.items():
        if value and key.strip() in {"单位", "计量单位"}:
            return key
    return None


def _find_keys(
    row_map: dict[str, str],
    keywords: tuple[str, ...],
    excluded: set[str | None] | None = None,
) -> list[str]:
    excluded = excluded or set()
    keys: list[str] = []
    for key, value in row_map.items():
        if key in excluded or not value:
            continue
        if any(keyword in key for keyword in keywords):
            keys.append(key)
    return keys


def _looks_like_limit_value(value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    return any(char.isdigit() for char in value) or value in {"不得检出", "不得使用", "按生产需要适量使用"}


def _header_contains_unit(header: str) -> bool:
    return any(unit in header for unit in UNIT_KEYWORDS)


def _with_table_source(
    text: str,
    *,
    page: int,
    table_index: int,
    table_title: str | None,
) -> str:
    return f"{_table_source(page=page, table_index=table_index, table_title=table_title)}。\n{text}"


def _table_source(page: int, table_index: int, table_title: str | None) -> str:
    title = f"，表题：{table_title}" if table_title else ""
    return f"来源：第{page}页，表格{table_index}{title}"
