import re

from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.evaluation import (
    RagEvalCase,
    RagEvalCaseResult,
    RagEvalRunRequest,
    RagEvalRunResponse,
)
from app.rag.search_tokenizer import compact_for_search, normalize_for_search, tokenize_for_search
from app.services.rag_service import NOT_FOUND_ANSWER, RagService


def run_rag_evaluation(
    db: Session,
    *,
    user: User,
    request: RagEvalRunRequest,
) -> RagEvalRunResponse:
    results: list[RagEvalCaseResult] = []
    rag_service = RagService()
    for case in request.cases:
        response = rag_service.answer(
            db,
            user=user,
            question=case.question,
            requested_document_ids=case.document_ids,
            top_k=case.top_k,
            force_retrieval=True,
        )
        actual_found = _actual_found(response.answer)
        answer_text = "\n".join(
            [
                response.sections.classification,
                response.sections.conclusion,
                response.sections.basis,
                response.sections.citation,
            ]
        )
        citation_text = "\n".join(
            [
                response.sections.citation,
                *[
                    f"{row.filename} {row.page or ''} {row.table or ''} {row.keywords}"
                    for row in response.evidence_rows
                ],
            ]
        )
        missing_answer_keywords = _missing_keywords(
            answer_text,
            case.expected_answer_keywords,
        )
        missing_citation_keywords = _missing_keywords(
            citation_text,
            case.expected_citation_keywords,
        )
        passed = _case_passed(
            case,
            actual_found=actual_found,
            missing_answer_keywords=missing_answer_keywords,
            missing_citation_keywords=missing_citation_keywords,
        )
        results.append(
            RagEvalCaseResult(
                id=case.id,
                question=case.question,
                tags=case.tags,
                passed=passed,
                expected_found=case.expected_found,
                actual_found=actual_found,
                missing_answer_keywords=missing_answer_keywords,
                missing_citation_keywords=missing_citation_keywords,
                response=response,
            )
        )

    passed_count = sum(1 for result in results if result.passed)
    total = len(results)
    return RagEvalRunResponse(
        name=request.name,
        total=total,
        passed=passed_count,
        failed=total - passed_count,
        pass_rate=round(passed_count / total, 4) if total else 0.0,
        results=results,
    )


def _actual_found(answer: str) -> bool:
    return NOT_FOUND_ANSWER not in answer


def _missing_keywords(text: str, keywords: list[str]) -> list[str]:
    return [
        keyword
        for keyword in keywords
        if keyword and not any(_keyword_matches(text, option) for option in _keyword_options(keyword))
    ]


def _keyword_matches(text: str, keyword: str) -> bool:
    normalized_text = normalize_for_search(text)
    normalized_keyword = normalize_for_search(keyword)
    if not normalized_keyword:
        return True
    if normalized_keyword in normalized_text:
        return True

    compact_text = compact_for_search(text)
    compact_keyword = compact_for_search(keyword)
    if compact_keyword and compact_keyword in compact_text:
        return True

    if _table_reference_matches(normalized_text, normalized_keyword):
        return True
    if _scientific_keyword_matches(normalized_text, normalized_keyword):
        return True
    if _negative_phrase_matches(normalized_text, normalized_keyword):
        return True

    if _is_unit_keyword(normalized_keyword):
        return False

    return _token_subset_matches(text, keyword)


def _token_subset_matches(text: str, keyword: str) -> bool:
    keyword_tokens = [
        token
        for token in tokenize_for_search(keyword)
        if _is_significant_eval_token(token)
    ]
    if not keyword_tokens:
        return False

    text_tokens = set(tokenize_for_search(text))
    compact_text = compact_for_search(text)
    matched_count = sum(
        1
        for token in keyword_tokens
        if token in text_tokens or compact_for_search(token) in compact_text
    )
    if len(keyword_tokens) == 1:
        return matched_count == 1

    strict_tokens = [token for token in keyword_tokens if _keyword_is_strict(token)]
    if any(token not in text_tokens and compact_for_search(token) not in compact_text for token in strict_tokens):
        return False
    return matched_count > 0


def _is_unit_keyword(keyword: str) -> bool:
    return "/" in keyword and any(unit in keyword for unit in ("ug", "mg", "g", "kg", "ml"))


def _keyword_options(keyword: str) -> list[str]:
    options = [option.strip() for option in keyword.split("||")]
    return [option for option in options if option]


def _table_reference_matches(text: str, keyword: str) -> bool:
    expected = _table_number(keyword)
    if not expected:
        return False
    for match in re.finditer(r"表\s*(?:\d+\.)?(?P<number>\d+)", text):
        if match.group("number").lstrip("0") == expected:
            return True
    if re.search(rf"(?:^|\D)\d+\.{re.escape(expected)}(?:\.\d+)?\s*表", text):
        return True
    return False


def _table_number(value: str) -> str | None:
    match = re.fullmatch(r"\s*表\s*(?:\d+\.)?(?P<number>\d+)\s*", value)
    if not match:
        return None
    return match.group("number").lstrip("0") or "0"


def _scientific_keyword_matches(text: str, keyword: str) -> bool:
    for variant in _scientific_variants(keyword):
        if variant in text or compact_for_search(variant) in compact_for_search(text):
            return True
    return False


def _scientific_variants(value: str) -> set[str]:
    variants: set[str] = set()
    normalized = normalize_for_search(value)
    for match in re.finditer(r"(?:(?P<coef>\d+(?:\.\d+)?)x)?10\^(?P<exp>-?\d+)", normalized):
        coef = match.group("coef") or "1"
        exp = match.group("exp")
        power = f"10^{exp}"
        scientific = f"{coef}x{power}" if coef != "1" else power
        variants.add(scientific)
        variants.add(scientific.replace("^", ""))
        expanded = _expand_scientific_value(coef, exp)
        if expanded:
            variants.add(expanded)
    return variants


def _expand_scientific_value(coef: str, exp: str) -> str | None:
    try:
        value = float(coef) * (10 ** int(exp))
    except (OverflowError, ValueError):
        return None
    if value.is_integer():
        return str(int(value))
    return f"{value:g}"


def _negative_phrase_matches(text: str, keyword: str) -> bool:
    if not keyword.startswith("无") or len(keyword) <= 2:
        return False
    phrase = keyword[1:]
    start = text.find(phrase)
    while start >= 0:
        prefix = text[max(0, start - 8) : start]
        if "无" in prefix:
            return True
        start = text.find(phrase, start + 1)
    return False


def _is_significant_eval_token(token: str) -> bool:
    if not token:
        return False
    if "/" in token:
        return True
    if "^" in token:
        return True
    if any(char.isdigit() for char in token):
        return len(token) >= 2
    return len(token) >= 4


def _answer_keywords_passed(expected_keywords: list[str], missing_keywords: list[str]) -> bool:
    if not missing_keywords:
        return True
    expected = [keyword for keyword in expected_keywords if keyword]
    if len(expected) < 6:
        return False
    if any(_keyword_is_strict(keyword) for keyword in missing_keywords):
        return False
    matched_count = len(expected) - len(missing_keywords)
    return matched_count / len(expected) >= 0.75


def _keyword_is_strict(keyword: str) -> bool:
    normalized = normalize_for_search(keyword)
    if not normalized:
        return False
    if _is_unit_keyword(normalized):
        return True
    if re.fullmatch(r"gb\s*\d+(?:[.-]\d+)*", normalized):
        return True
    if re.fullmatch(r"\d+(?:\.\d+){1,5}", normalized):
        return True
    if any(char.isdigit() for char in normalized) and len(compact_for_search(normalized)) <= 12:
        return True
    if "/" in normalized or "^" in normalized:
        return True
    return False


def _case_passed(
    case: RagEvalCase,
    *,
    actual_found: bool,
    missing_answer_keywords: list[str],
    missing_citation_keywords: list[str],
) -> bool:
    if case.expected_found != actual_found:
        return False
    if not case.expected_found:
        return True
    if not _answer_keywords_passed(case.expected_answer_keywords, missing_answer_keywords):
        return False
    if "strict_citation" in case.tags:
        return not missing_citation_keywords
    return True
