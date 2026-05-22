import re

GARBLED_TOKEN_PATTERN = re.compile(r"/G[0-9A-Fa-f]{2,4}")
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
READABLE_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9\uff10-\uff19]")
HANGUL_PATTERN = re.compile(r"[\uac00-\ud7af]")
PRIVATE_USE_PATTERN = re.compile(r"[\ue000-\uf8ff]")
REPLACEMENT_CHAR_PATTERN = re.compile(r"\ufffd")
QUESTION_MARK_RUN_PATTERN = re.compile(r"\?{3,}")
MOJIBAKE_MARKERS = ("�", "Ã", "Â", "Ð", "ð")


def is_text_usable(
    text: str,
    *,
    min_readable_chars: int = 30,
    max_garbled_token_ratio: float = 0.08,
    max_hangul_char_ratio: float = 0.03,
    max_private_use_char_ratio: float = 0.005,
    max_replacement_char_ratio: float = 0.005,
    max_question_mark_run_ratio: float = 0.03,
) -> bool:
    stripped = text.strip()
    if len(stripped) < min_readable_chars:
        return False

    readable_chars = len(READABLE_PATTERN.findall(stripped))
    if readable_chars < min_readable_chars:
        return False

    if garbled_token_ratio(stripped) > max_garbled_token_ratio:
        return False

    if control_char_ratio(stripped) > 0.01:
        return False

    if mojibake_marker_ratio(stripped) > 0.05:
        return False

    if hangul_char_ratio(stripped) > max_hangul_char_ratio:
        return False

    if private_use_char_ratio(stripped) > max_private_use_char_ratio:
        return False

    if replacement_char_ratio(stripped) > max_replacement_char_ratio:
        return False

    if question_mark_run_ratio(stripped) > max_question_mark_run_ratio:
        return False

    return True


def text_quality_summary(text: str) -> dict[str, float | int]:
    stripped = text.strip()
    length = len(stripped)
    readable_chars = len(READABLE_PATTERN.findall(stripped))
    cjk_chars = len(CJK_PATTERN.findall(stripped))
    return {
        "length": length,
        "readable_chars": readable_chars,
        "cjk_chars": cjk_chars,
        "readable_char_ratio": readable_chars / length if length else 1.0,
        "cjk_char_ratio": cjk_chars / length if length else 0.0,
        "garbled_token_ratio": garbled_token_ratio(stripped),
        "control_char_ratio": control_char_ratio(stripped),
        "mojibake_marker_ratio": mojibake_marker_ratio(stripped),
        "hangul_char_ratio": hangul_char_ratio(stripped),
        "private_use_char_ratio": private_use_char_ratio(stripped),
        "replacement_char_ratio": replacement_char_ratio(stripped),
        "question_mark_run_ratio": question_mark_run_ratio(stripped),
    }


def garbled_token_ratio(text: str) -> float:
    if not text:
        return 1.0
    garbled_chars = sum(len(token) for token in GARBLED_TOKEN_PATTERN.findall(text))
    return garbled_chars / len(text)


def control_char_ratio(text: str) -> float:
    if not text:
        return 1.0
    return len(CONTROL_CHAR_PATTERN.findall(text)) / len(text)


def mojibake_marker_ratio(text: str) -> float:
    if not text:
        return 1.0
    marker_count = sum(text.count(marker) for marker in MOJIBAKE_MARKERS)
    return marker_count / len(text)


def hangul_char_ratio(text: str) -> float:
    if not text:
        return 1.0
    return len(HANGUL_PATTERN.findall(text)) / len(text)


def private_use_char_ratio(text: str) -> float:
    if not text:
        return 1.0
    return len(PRIVATE_USE_PATTERN.findall(text)) / len(text)


def replacement_char_ratio(text: str) -> float:
    if not text:
        return 1.0
    return len(REPLACEMENT_CHAR_PATTERN.findall(text)) / len(text)


def question_mark_run_ratio(text: str) -> float:
    if not text:
        return 1.0
    noisy_chars = sum(len(match.group(0)) for match in QUESTION_MARK_RUN_PATTERN.finditer(text))
    return noisy_chars / len(text)
