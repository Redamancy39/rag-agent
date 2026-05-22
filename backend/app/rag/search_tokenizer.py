import math
import re
import unicodedata

SUPERSCRIPT_DIGITS = str.maketrans(
    {
        "\u2070": "0",
        "\u00b9": "1",
        "\u00b2": "2",
        "\u00b3": "3",
        "\u2074": "4",
        "\u2075": "5",
        "\u2076": "6",
        "\u2077": "7",
        "\u2078": "8",
        "\u2079": "9",
        "\u207b": "-",
    }
)
SUPERSCRIPT_CHARS = "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079\u207b"
DASH_CHARS = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)

TOKEN_PATTERN = re.compile(
    r"[a-z]+(?:/[a-z]+)?|[a-z]*\d+(?:[./_-]\d+)*(?:\^\-?\d+)?|\d+(?:\.\d+)?|[\u4e00-\u9fff]{2,}",
)
STANDARD_PATTERN = re.compile(
    r"\b([a-z]{1,8})\s*[-/]?\s*(\d{2,6}(?:\.\d+)?)\s*(?:[-–—]\s*(\d{4}))?\b",
)
SCIENTIFIC_PATTERN = re.compile(
    r"(?P<coef>\d+(?:\.\d+)?)\s*(?:x|\*)\s*10\^(?P<exp>-?\d+)"
)
POWER_PATTERN = re.compile(r"(?<![\w.])10\^(?P<exp>-?\d+)(?![\w.])")
UNIT_PATTERN = re.compile(r"\b(?:u|μ|µ|渭|碌)g\s*/\s*kg\b|\b(?:u|μ|µ|渭|碌)g\b")
STOP_TOKENS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "是否",
    "多少",
    "什么",
    "哪些",
    "如何",
    "要求",
    "规定",
    "文档",
    "文件",
}


def normalize_for_search(value: str) -> str:
    text = _normalize_scientific_notation(value or "")
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.translate(DASH_CHARS)
    text = _normalize_common_mojibake(text)
    text = text.replace("\u00d7", "x").replace("\u2715", "x").replace("\uff0a", "*")
    text = text.replace("\uff0f", "/").replace("\\", "/")
    text = text.replace("\uff5e", "~").replace("\u301c", "~")
    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compact_for_search(value: str) -> str:
    text = normalize_for_search(value)
    return re.sub(r"[\s\-_./:;，。、“”\"'（）()【】\[\]{}<>《》]+", "", text)


def tokenize_for_search(value: str, *, include_ngrams: bool = True) -> list[str]:
    normalized = normalize_for_search(value)
    tokens: list[str] = []
    tokens.extend(_standard_tokens(normalized))
    tokens.extend(_scientific_tokens(normalized))
    tokens.extend(_unit_tokens(normalized))

    for token in TOKEN_PATTERN.findall(normalized):
        if not _keep_token(token):
            continue
        if _is_cjk(token):
            tokens.extend(_cjk_tokens(token, include_ngrams=include_ngrams))
        else:
            tokens.extend(_latin_numeric_tokens(token))

    return _unique_tokens(tokens)


def matched_query_terms(query_tokens: list[str], text: str, *, limit: int = 12) -> list[str]:
    normalized_text = normalize_for_search(text)
    compact_text = compact_for_search(text)
    matched: list[str] = []
    for token in query_tokens:
        if token in STOP_TOKENS or len(token) <= 1:
            continue
        if token in normalized_text or token in compact_text:
            matched.append(token)
        if len(matched) >= limit:
            break
    return _unique_tokens(matched)[:limit]


def _normalize_scientific_notation(value: str) -> str:
    text = re.sub(
        rf"10(?P<exp>[{SUPERSCRIPT_CHARS}]+)",
        lambda match: f"10^{match.group('exp').translate(SUPERSCRIPT_DIGITS)}",
        value,
    )
    text = re.sub(r"\s*[\u00d7\u2715xX*]\s*", "x", text)
    return text


def _normalize_common_mojibake(value: str) -> str:
    text = value
    text = UNIT_PATTERN.sub(
        lambda match: match.group(0)
        .replace("μ", "u")
        .replace("µ", "u")
        .replace("渭", "u")
        .replace("碌", "u"),
        text,
    )
    text = re.sub(r"\bu\s*g\b", "ug", text)
    text = re.sub(r"\bu\s*g\s*/\s*kg\b", "ug/kg", text)
    text = re.sub(r"\bm\s*g\s*/\s*kg\b", "mg/kg", text)
    text = re.sub(r"\bg\s*/\s*kg\b", "g/kg", text)
    text = text.replace("gb/t", "gbt")
    return text


def _standard_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for prefix, number, year in STANDARD_PATTERN.findall(text):
        if not prefix or not number:
            continue
        compact_prefix = prefix.replace("/", "")
        compact_number = number.replace(" ", "")
        tokens.append(f"{compact_prefix}{compact_number}")
        tokens.append(compact_number)
        if year:
            tokens.append(f"{compact_prefix}{compact_number}-{year}")
            tokens.append(year)
    return tokens


def _scientific_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in SCIENTIFIC_PATTERN.finditer(text):
        coef = match.group("coef")
        exp = match.group("exp")
        tokens.append(f"{coef}x10^{exp}")
        tokens.append(f"10^{exp}")
        expanded = _expand_scientific(coef, exp)
        if expanded:
            tokens.append(expanded)
    for match in POWER_PATTERN.finditer(text):
        exp = match.group("exp")
        tokens.append(f"10^{exp}")
        expanded = _expand_scientific("1", exp)
        if expanded:
            tokens.append(expanded)
    return tokens


def _unit_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    if re.search(r"(?<![a-z])ug/kg(?![a-z])", text):
        tokens.extend(["ug/kg", "ug", "kg"])
    if re.search(r"(?<![a-z])mg/kg(?![a-z])", text):
        tokens.extend(["mg/kg", "mg", "kg"])
    if re.search(r"(?<![a-z])g/kg(?![a-z])", text):
        tokens.extend(["g/kg", "g", "kg"])
    return tokens


def _latin_numeric_tokens(token: str) -> list[str]:
    tokens = [token]
    if "/" in token:
        tokens.extend(part for part in token.split("/") if part)
    if "-" in token:
        tokens.extend(part for part in token.split("-") if part)
    if re.fullmatch(r"[a-z]+\d+(?:\.\d+)?", token):
        prefix = re.match(r"[a-z]+", token)
        number = re.search(r"\d+(?:\.\d+)?", token)
        if prefix and number:
            tokens.append(prefix.group(0))
            tokens.append(number.group(0))
    return tokens


def _cjk_tokens(token: str, *, include_ngrams: bool) -> list[str]:
    if not include_ngrams:
        return [token]
    if len(token) <= 4:
        return [token]

    tokens = [token]
    max_n = 4 if len(token) <= 30 else 3
    for n in range(2, max_n + 1):
        tokens.extend(token[index : index + n] for index in range(0, len(token) - n + 1))
    if len(token) > 12:
        tokens.append(token[:8])
        tokens.append(token[-8:])
    return tokens


def _expand_scientific(coef: str, exp: str) -> str | None:
    try:
        value = float(coef) * math.pow(10, int(exp))
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    if value.is_integer():
        return str(int(value))
    return f"{value:g}"


def _keep_token(token: str) -> bool:
    if not token or token in STOP_TOKENS:
        return False
    if len(token) == 1 and not token.isdigit():
        return False
    return True


def _is_cjk(value: str) -> bool:
    return bool(re.fullmatch(r"[\u4e00-\u9fff]+", value))


def _unique_tokens(tokens: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        normalized = token.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique
