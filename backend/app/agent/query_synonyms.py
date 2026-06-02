from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class SynonymExpansion:
    canonical: str
    aliases: list[str]
    matched: list[str]
    category: str = "metric"

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical": self.canonical,
            "aliases": self.aliases,
            "matched": self.matched,
            "category": self.category,
        }


@dataclass(frozen=True, slots=True)
class SynonymGroup:
    canonical: str
    aliases: tuple[str, ...]
    category: str = "metric"


SYNONYM_GROUPS: tuple[SynonymGroup, ...] = (
    SynonymGroup(
        canonical="挥发性盐基氮",
        aliases=("tvb-n", "tvbn", "tvb n", "t-vbn", "挥发性盐基氮"),
        category="metric",
    ),
)


ASCII_ALIAS_PATTERNS: dict[str, re.Pattern[str]] = {
    "tvbn": re.compile(r"(?<![A-Za-z0-9])t\s*-?\s*vb\s*-?\s*n(?![A-Za-z0-9])", re.I),
    "tvb-n": re.compile(r"(?<![A-Za-z0-9])tvb\s*-\s*n(?![A-Za-z0-9])", re.I),
    "tvb n": re.compile(r"(?<![A-Za-z0-9])tvb\s+n(?![A-Za-z0-9])", re.I),
}


def apply_query_synonyms(question: str) -> tuple[str, list[SynonymExpansion]]:
    text = unicodedata.normalize("NFKC", question or "")
    expansions = detect_query_synonyms(text)
    if not expansions:
        return text, []

    rewritten = text
    for expansion in expansions:
        display = _display_term(expansion)
        for alias in expansion.matched:
            rewritten = _replace_alias(rewritten, alias, display)
    return rewritten, expansions


def detect_query_synonyms(question: str) -> list[SynonymExpansion]:
    text = unicodedata.normalize("NFKC", question or "")
    normalized = text.lower()
    expansions: list[SynonymExpansion] = []
    for group in SYNONYM_GROUPS:
        matched: list[str] = []
        for alias in group.aliases:
            if _alias_matches(text, normalized, alias):
                matched.append(alias)
        if matched:
            expansions.append(
                SynonymExpansion(
                    canonical=group.canonical,
                    aliases=list(group.aliases),
                    matched=_unique(matched),
                    category=group.category,
                )
            )
    return expansions


def synonym_search_terms(expansions: list[SynonymExpansion]) -> list[str]:
    terms: list[str] = []
    for expansion in expansions:
        terms.append(expansion.canonical)
        terms.extend(expansion.aliases)
        terms.append(_display_term(expansion))
    return _unique(terms)


def synonym_expansions_to_dicts(
    expansions: list[SynonymExpansion],
) -> list[dict[str, Any]]:
    return [expansion.to_dict() for expansion in expansions]


def _alias_matches(text: str, normalized: str, alias: str) -> bool:
    pattern = ASCII_ALIAS_PATTERNS.get(alias.lower())
    if pattern is not None:
        return bool(pattern.search(text))
    if _is_ascii_alias(alias):
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", text, re.I))
    return alias in text or alias.lower() in normalized


def _replace_alias(text: str, alias: str, replacement: str) -> str:
    if alias == replacement or replacement in text:
        return text
    pattern = ASCII_ALIAS_PATTERNS.get(alias.lower())
    if pattern is not None:
        return pattern.sub(replacement, text)
    if _is_ascii_alias(alias):
        return re.sub(
            rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])",
            replacement,
            text,
            flags=re.I,
        )
    return text.replace(alias, replacement)


def _display_term(expansion: SynonymExpansion) -> str:
    preferred_alias = "TVB-N" if any(alias.lower() == "tvb-n" for alias in expansion.aliases) else ""
    if not preferred_alias:
        preferred_alias = next(
            (alias.upper() for alias in expansion.aliases if alias.lower() == "tvbn"),
            "",
        )
    return (
        f"{expansion.canonical}({preferred_alias})"
        if preferred_alias
        else expansion.canonical
    )


def _is_ascii_alias(alias: str) -> bool:
    return all(ord(char) < 128 for char in alias)


def _unique(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(value.strip())
    return unique
