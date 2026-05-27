from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agent.query_agent import QueryPlan
from app.core.config import get_settings
from app.core.logger import get_logger
from app.rag.llm_client import LLMConfigError, OpenAICompatibleLLM
from app.rag.search_tokenizer import compact_for_search, normalize_for_search
from app.schemas.chat import Citation

logger = get_logger(__name__)

EVIDENCE_JUDGE_PROMPT = """你是企业知识库 RAG 的证据充分性审查器。你的任务不是回答问题，而是判断给定检索证据是否足以支持回答。
要求：
1. 只能根据给定证据判断。
2. 如果证据没有直接覆盖问题中的对象、指标、标准号或限量，应判定 insufficient。
3. 只输出 JSON。
JSON 格式：
{
  "sufficient": true,
  "confidence": 0.8,
  "reason": "证据为什么足够或不足",
  "missing_requirements": []
}
"""


@dataclass(slots=True)
class EvidenceDecision:
    sufficient: bool
    source: str = "rule"
    reason: str = ""
    confidence: float = 0.0
    missing_requirements: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sufficient": self.sufficient,
            "source": self.source,
            "reason": self.reason,
            "confidence": self.confidence,
            "missing_requirements": self.missing_requirements,
            "warnings": self.warnings,
        }


class EvidenceJudge:
    def __init__(self) -> None:
        self.settings = get_settings()

    def judge(
        self,
        *,
        question: str,
        citations: list[Citation],
        query_plan: QueryPlan | None,
    ) -> EvidenceDecision:
        if not self.settings.QUERY_AGENT_EVIDENCE_JUDGE_ENABLED:
            return EvidenceDecision(
                sufficient=True,
                source="disabled",
                reason="QUERY_AGENT_EVIDENCE_JUDGE_ENABLED=false",
                confidence=1.0,
            )

        rule_decision = self._rule_judge(citations=citations, query_plan=query_plan)
        if (
            not self.settings.QUERY_AGENT_EVIDENCE_LLM_ENABLED
            or not citations
            or rule_decision.confidence >= 0.9
        ):
            return rule_decision

        try:
            return self._llm_judge(
                question=question,
                citations=citations,
                query_plan=query_plan,
                fallback=rule_decision,
            )
        except LLMConfigError as exc:
            rule_decision.warnings.append(str(exc))
            logger.info("Evidence judge LLM unavailable, using rule decision: %s", exc)
        except Exception as exc:
            rule_decision.warnings.append(f"evidence_judge_llm_failed: {exc}")
            logger.warning("Evidence judge LLM failed, using rule decision: %s", exc)
        return rule_decision

    def _rule_judge(
        self,
        *,
        citations: list[Citation],
        query_plan: QueryPlan | None,
    ) -> EvidenceDecision:
        if not citations:
            return EvidenceDecision(
                sufficient=False,
                reason="no usable citations",
                confidence=0.95,
            )

        combined = "\n".join(
            [
                citation.filename
                + "\n"
                + (citation.table or "")
                + "\n"
                + citation.text
                for citation in citations
            ]
        )
        compact_evidence = compact_for_search(combined)
        missing, strict_missing = _missing_requirements(query_plan, compact_evidence)
        if strict_missing:
            return EvidenceDecision(
                sufficient=False,
                reason="retrieved evidence misses required standard references",
                confidence=0.72,
                missing_requirements=strict_missing,
            )

        top_score = max((citation.score or 0.0 for citation in citations), default=0.0)
        if top_score < self.settings.RAG_MIN_SCORE:
            return EvidenceDecision(
                sufficient=False,
                reason="top citation score is below RAG_MIN_SCORE",
                confidence=0.85,
            )

        return EvidenceDecision(
            sufficient=True,
            reason=(
                "usable citations cover rule-based evidence requirements"
                if not missing
                else "usable citations found; some soft query terms were not matched exactly"
            ),
            confidence=0.78 if missing else 0.86,
            missing_requirements=missing,
        )

    def _llm_judge(
        self,
        *,
        question: str,
        citations: list[Citation],
        query_plan: QueryPlan | None,
        fallback: EvidenceDecision,
    ) -> EvidenceDecision:
        evidence = "\n\n".join(
            [
                f"[{index}] {citation.filename}; page={citation.page}; table={citation.table}; score={citation.score}\n{citation.text[:800]}"
                for index, citation in enumerate(citations[:8], start=1)
            ]
        )
        payload = OpenAICompatibleLLM().complete_json(
            EVIDENCE_JUDGE_PROMPT,
            (
                f"用户问题：{question}\n\n"
                f"查询计划：{query_plan.to_dict() if query_plan else {}}\n\n"
                f"规则判断：{fallback.to_dict()}\n\n"
                f"检索证据：\n{evidence}"
            ),
        )
        sufficient = bool(payload.get("sufficient", fallback.sufficient))
        return EvidenceDecision(
            sufficient=sufficient,
            source="llm",
            reason=str(payload.get("reason") or fallback.reason),
            confidence=_clean_confidence(payload.get("confidence"), fallback.confidence),
            missing_requirements=[
                str(item)
                for item in (payload.get("missing_requirements") or fallback.missing_requirements)
                if str(item)
            ][:12],
        )


def _missing_requirements(
    query_plan: QueryPlan | None,
    compact_evidence: str,
) -> tuple[list[str], list[str]]:
    if query_plan is None:
        return [], []

    strict_terms = [*query_plan.standard_refs]
    soft_terms: list[str] = []
    if query_plan.question_type in {"single_lookup", "cross_document", "multi_hop"}:
        soft_terms.extend(query_plan.entities[:3])
        soft_terms.extend(query_plan.metrics[:3])

    strict_missing = _missing_terms(strict_terms, compact_evidence)
    soft_missing = _missing_terms(soft_terms, compact_evidence)
    return [*strict_missing, *soft_missing][:8], strict_missing[:8]


def _missing_terms(terms: list[str], compact_evidence: str) -> list[str]:
    missing: list[str] = []
    for term in terms:
        normalized = compact_for_search(term)
        if not normalized:
            continue
        relaxed = normalize_for_search(term).replace(" ", "")
        if normalized not in compact_evidence and relaxed not in compact_evidence:
            missing.append(term)
    return missing[:8]


def _clean_confidence(value: object, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))
