"""Bounded, local vocabulary assistance. Fuzzy matches never rewrite a question."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

CATEGORIES = {"additive": "添加剂", "contaminant": "污染物", "microorganism": "微生物", "metric": "检测指标"}
LITERAL_REFERENCE = re.compile(r"https?://\S+|[\w./\\-]+\.(?:pdf|docx?|xlsx?|txt)\b", re.I)
PROTECTED = re.compile(
    r"https?://\S+|[\w./\\-]+\.(?:pdf|docx?|xlsx?|txt)\b|"
    r"(?<![A-Za-z0-9])(?:GB(?:\s*/\s*T)?|NY(?:\s*/\s*T)?|SN(?:\s*/\s*T)?)\s*[\d.]+(?:[-—–]\d{4})?|"
    r"[A-Za-z0-9]+(?:[./:\-][A-Za-z0-9]+)*", re.I
)


@lru_cache(maxsize=1)
def load_hotwords() -> dict[str, Any]:
    data = json.loads(Path(__file__).with_name("food_hotwords.json").read_text(encoding="utf-8"))
    known: set[str] = set()
    typo_targets: dict[str, str] = {}
    for entry in data["entries"]:
        if entry["category"] not in CATEGORIES or entry["source"] not in data["sources"]:
            raise ValueError("Invalid hotword category or source")
        for value in [entry["term"], *entry["aliases"]]:
            known.add(value.casefold())
        for value in entry["typos"]:
            key = value.casefold()
            if key in typo_targets and typo_targets[key] != entry["term"]:
                raise ValueError("Ambiguous configured typo")
            typo_targets[key] = entry["term"]
    if known.intersection(typo_targets):
        raise ValueError("A valid term cannot also be an automatic typo")
    return data


def hotword_catalogue() -> dict[str, Any]:
    data = load_hotwords()
    return {"version": data["version"], "categories": CATEGORIES, "entries": [
        {**entry, "source": data["sources"][entry["source"]]} for entry in data["entries"]
    ]}


@lru_cache(maxsize=256)
def _pattern(value: str) -> re.Pattern[str]:
    left = r"(?<![A-Za-z0-9])" if value[0].isascii() else ""
    right = r"(?![A-Za-z0-9])" if value[-1].isascii() else ""
    return re.compile(left + re.escape(value) + right, re.I)


def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < b and end > a for a, b in spans)


def analyze_hotwords(question: str) -> dict[str, Any]:
    if len(question) > 4000:
        raise ValueError("Question exceeds 4000 characters")
    data = load_hotwords()
    valid_spans = [(item["start"], item["end"]) for item in analyze_matches(question)]

    protected = [match.span() for match in PROTECTED.finditer(question)]
    corrections: list[dict[str, Any]] = []
    used = list(valid_spans)
    typos = [(value, entry) for entry in data["entries"] for value in entry["typos"]]
    for value, entry in sorted(typos, key=lambda item: -len(item[0])):
        for match in _pattern(value).finditer(question):
            # A typo containing B1 may intersect its own suffix; forbid protected spans only
            # when the typo starts inside one (URLs, filenames, IDs, standard references).
            if _overlaps(*match.span(), used) or any(a <= match.start() < b for a, b in protected):
                continue
            used.append(match.span())
            corrections.append({"original": match.group(), "replacement": entry["term"], "category": entry["category"],
                                "start": match.start(), "end": match.end(), "reason": "configured_typo"})
    corrections.sort(key=lambda item: item["start"])
    corrected = question
    for item in reversed(corrections):
        corrected = corrected[:item["start"]] + item["replacement"] + corrected[item["end"]:]

    suggestions: list[dict[str, Any]] = []
    # Only a single Chinese-character substitution in words of 4+ characters is suggested.
    # Never guess Latin suffixes, numbers, short words, deletions, or insertions.
    blocked = [*used, *protected]
    candidates: dict[tuple[int, int, str], list[str]] = {}
    for entry in data["entries"]:
        term = entry["term"]
        if not (len(term) >= 4 and re.fullmatch(r"[\u4e00-\u9fff]+", term)):
            continue
        for run in re.finditer(r"[\u4e00-\u9fff]{4,}", question):
            for start in range(run.start(), run.end() - len(term) + 1):
                end = start + len(term)
                if _overlaps(start, end, blocked):
                    continue
                value = question[start:end]
                if sum(a != b for a, b in zip(value, term)) == 1:
                    candidates.setdefault((start, end, value), []).append(term)
    for (start, end, value), terms in sorted(candidates.items(), key=lambda item: (item[0][0], -(item[0][1]-item[0][0]))):
        if _overlaps(start, end, blocked):
            continue
        blocked.append((start, end))
        suggestions.append({"original": value, "candidates": terms[:3], "start": start, "end": end,
                            "reason": "similar_spelling_requires_confirmation"})
        if len(suggestions) >= 5:
            break
    corrected_matches = analyze_matches(corrected)
    return {"original_question": question, "corrected_question": corrected, "lexicon_version": data["version"],
            "hotword_matches": corrected_matches, "corrections": corrections, "suggestions": suggestions}


def analyze_matches(question: str) -> list[dict[str, Any]]:
    spans: list[tuple[int, int]] = []
    matches: list[dict[str, Any]] = []
    variants = [(value, entry) for entry in load_hotwords()["entries"] for value in [entry["term"], *entry["aliases"]]]
    for value, entry in sorted(variants, key=lambda item: -len(item[0])):
        for match in _pattern(value).finditer(question):
            if _overlaps(*match.span(), spans):
                continue
            spans.append(match.span())
            matches.append({"original": match.group(), "term": entry["term"], "category": entry["category"],
                            "start": match.start(), "end": match.end(), "kind": "term" if value == entry["term"] else "alias"})
    return sorted(matches, key=lambda item: item["start"])


def apply_hotword_aliases(question: str) -> str:
    protected = [match.span() for match in LITERAL_REFERENCE.finditer(question)]
    for item in reversed(analyze_matches(question)):
        if item["kind"] != "alias" or _overlaps(item["start"], item["end"], protected):
            continue
        question = question[:item["start"]] + item["term"] + question[item["end"]:]
    return question
