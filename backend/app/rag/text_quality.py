import re

GARBLED_TOKEN_PATTERN = re.compile(r"/G[0-9A-Fa-f]{2,4}")
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
READABLE_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9\uff10-\uff19]")
MOJIBAKE_MARKERS = ("�", "Ã", "Â", "Ð", "ð")


def is_text_usable(
    text: str,
    *,
    min_readable_chars: int = 30,
    max_garbled_token_ratio: float = 0.08,
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

    return True


def text_quality_summary(text: str) -> dict[str, float | int]:
    stripped = text.strip()
    length = len(stripped)
    return {
        "length": length,
        "readable_chars": len(READABLE_PATTERN.findall(stripped)),
        "cjk_chars": len(CJK_PATTERN.findall(stripped)),
        "garbled_token_ratio": garbled_token_ratio(stripped),
        "control_char_ratio": control_char_ratio(stripped),
        "mojibake_marker_ratio": mojibake_marker_ratio(stripped),
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
