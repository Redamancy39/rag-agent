from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.evaluation import (
    RagEvalCase,
    RagEvalCaseResult,
    RagEvalRunRequest,
    RagEvalRunResponse,
)
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
    return [keyword for keyword in keywords if keyword and keyword not in text]


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
    return not missing_answer_keywords and not missing_citation_keywords
