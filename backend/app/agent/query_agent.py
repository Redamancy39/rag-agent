from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.agent.query_synonyms import (
    apply_query_synonyms,
    detect_query_synonyms,
    synonym_expansions_to_dicts,
    synonym_search_terms,
)
from app.core.config import get_settings
from app.core.logger import get_logger
from app.rag.llm_client import LLMConfigError, OpenAICompatibleLLM
from app.rag.search_tokenizer import normalize_for_search

logger = get_logger(__name__)

STANDARD_REF_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])GB(?:/T)?\s*\d+(?:\.\d+)?(?:[-\u2010-\u2014\u2212]\d{4})?",
    re.IGNORECASE,
)

COMPLEX_MARKERS = (
    "分别",
    "同时",
    "对比",
    "比较",
    "引用",
    "参照",
    "应符合",
    "是否符合",
    "限量",
    "最大残留",
    "添加剂",
    "污染物",
    "致病菌",
    "表",
)

METRIC_TERMS = (
    "限量",
    "最大残留限量",
    "残留限量",
    "添加量",
    "ADI",
    "菌落总数",
    "大肠菌群",
    "沙门氏菌",
    "金黄色葡萄球菌",
    "铅",
    "镉",
    "砷",
    "无机砷",
    "甲基汞",
    "黄曲霉毒素B1",
    "酸价",
    "过氧化值",
)

QUERY_PLANNER_PROMPT = """你是企业知识库 RAG 的查询规划器。你的任务不是回答问题，而是把用户问题改写成适合检索的查询计划。
要求：
1. 不要使用外部知识回答问题。
2. 只输出 JSON。
3. 如果问题简单，不需要改写，也要返回 normalized_question 和 rewritten_queries。
4. rewritten_queries 用于向量检索、BM25 和关键词检索，应该保留标准号、食品类别、指标名、限量/表号等关键词。
5. sub_questions 只在跨文档、对比、多实体问题中生成。
JSON 格式：
{
  "needs_rewrite": true,
  "question_type": "single_lookup/cross_document/comparison/multi_hop/definition/unknown",
  "normalized_question": "归一化后的原问题",
  "standard_refs": ["GB xxxx-yyyy"],
  "entities": ["食品类别或对象"],
  "metrics": ["指标或限量"],
  "sub_questions": ["需要分解检索的子问题"],
  "rewritten_queries": ["用于检索的查询"],
  "evidence_requirements": ["判断答案必须满足的证据条件"],
  "confidence": 0.8,
  "reason": "为什么需要或不需要改写"
}
"""


@dataclass(slots=True)
class QueryPlan:
    original_question: str
    normalized_question: str
    needs_rewrite: bool
    question_type: str = "single_lookup"
    source: str = "rule"
    reason: str = ""
    standard_refs: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    sub_questions: list[str] = field(default_factory=list)
    rewritten_queries: list[str] = field(default_factory=list)
    evidence_requirements: list[str] = field(default_factory=list)
    synonym_expansions: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    llm_used: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_question": self.original_question,
            "normalized_question": self.normalized_question,
            "needs_rewrite": self.needs_rewrite,
            "question_type": self.question_type,
            "source": self.source,
            "reason": self.reason,
            "standard_refs": self.standard_refs,
            "entities": self.entities,
            "metrics": self.metrics,
            "sub_questions": self.sub_questions,
            "rewritten_queries": self.rewritten_queries,
            "evidence_requirements": self.evidence_requirements,
            "synonym_expansions": self.synonym_expansions,
            "confidence": self.confidence,
            "llm_used": self.llm_used,
            "warnings": self.warnings,
        }


class QueryAgent:
    def __init__(self) -> None:
        self.settings = get_settings()

    def plan(self, question: str) -> QueryPlan:
        normalized_question = normalize_question(question)
        if not self.settings.QUERY_AGENT_ENABLED:
            return QueryPlan(
                original_question=question,
                normalized_question=normalized_question,
                needs_rewrite=False,
                question_type="single_lookup",
                source="disabled",
                reason="QUERY_AGENT_ENABLED=false",
                rewritten_queries=[normalized_question],
                synonym_expansions=synonym_expansions_to_dicts(
                    detect_query_synonyms(question)
                ),
                confidence=1.0,
            )

        rule_plan = self._rule_plan(question, normalized_question)
        if not rule_plan.needs_rewrite or not self.settings.QUERY_AGENT_LLM_ENABLED:
            return rule_plan

        try:
            llm_plan = self._llm_plan(question, rule_plan)
            if llm_plan.rewritten_queries:
                return llm_plan
        except LLMConfigError as exc:
            rule_plan.warnings.append(str(exc))
            logger.info("Query agent LLM unavailable, using rule plan: %s", exc)
        except Exception as exc:
            rule_plan.warnings.append(f"query_agent_llm_failed: {exc}")
            logger.warning("Query agent LLM failed, using rule plan: %s", exc)
        return rule_plan

    def _rule_plan(self, question: str, normalized_question: str) -> QueryPlan:
        synonym_expansions = detect_query_synonyms(question)
        synonym_terms = synonym_search_terms(synonym_expansions)
        search_question = f"{question}\n{normalized_question}\n{' '.join(synonym_terms)}"
        refs = extract_standard_refs(search_question)
        metrics = extract_metric_terms(search_question)
        for term in synonym_terms:
            if term and term not in metrics:
                metrics.append(term)
        entities = extract_entities(search_question, metrics)
        is_complex = _looks_complex(question, refs)
        question_type = _question_type(question, refs)
        queries = _build_rule_queries(
            normalized_question=normalized_question,
            refs=refs,
            metrics=metrics,
            entities=entities,
            max_queries=self.settings.QUERY_AGENT_MAX_QUERIES,
        )
        sub_questions = _build_sub_questions(
            refs=refs,
            metrics=metrics,
            entities=entities,
            max_items=self.settings.QUERY_AGENT_MAX_SUB_QUESTIONS,
        )
        return QueryPlan(
            original_question=question,
            normalized_question=normalized_question,
            needs_rewrite=is_complex or normalized_question != question.strip(),
            question_type=question_type,
            source="rule",
            reason=_rule_reason(question, refs, metrics, is_complex),
            standard_refs=refs,
            entities=entities,
            metrics=metrics,
            sub_questions=sub_questions if is_complex else [],
            rewritten_queries=queries,
            evidence_requirements=_build_evidence_requirements(refs, metrics, entities),
            synonym_expansions=synonym_expansions_to_dicts(synonym_expansions),
            confidence=0.72 if is_complex else 0.95,
        )

    def _llm_plan(self, question: str, fallback: QueryPlan) -> QueryPlan:
        payload = OpenAICompatibleLLM().complete_json(
            QUERY_PLANNER_PROMPT,
            (
                f"用户问题：{question}\n\n"
                f"规则检测结果：{fallback.to_dict()}\n\n"
                "同义词转写小样本：\n"
                "1. 用户问题：冷鲜肉的 TVBN 限量是多少？\n"
                "   normalized_question：冷鲜肉的挥发性盐基氮(TVB-N)限量是多少？\n"
                "   metrics：['挥发性盐基氮', 'TVB-N', '限量']\n"
                "   rewritten_queries：['冷鲜肉 挥发性盐基氮 TVB-N 限量', '冷鲜肉 tvbn 限量']\n"
                "2. 用户问题：GB 2707 里面 tvb-n 怎么规定？\n"
                "   normalized_question：GB 2707 里面挥发性盐基氮(TVB-N)怎么规定？\n"
                "   metrics：['挥发性盐基氮', 'TVB-N']\n\n"
                "如果规则检测结果中包含 synonym_expansions，必须把 canonical 和 aliases 同时放入 metrics 或 rewritten_queries，避免只按缩写检索。\n\n"
                "请输出查询规划 JSON。"
            ),
        )
        normalized_question = _clean_str(payload.get("normalized_question")) or fallback.normalized_question
        rewritten_queries = _clean_list(payload.get("rewritten_queries"))
        if not rewritten_queries:
            rewritten_queries = fallback.rewritten_queries
        plan = QueryPlan(
            original_question=question,
            normalized_question=normalized_question,
            needs_rewrite=bool(payload.get("needs_rewrite", fallback.needs_rewrite)),
            question_type=_clean_str(payload.get("question_type")) or fallback.question_type,
            source="llm",
            reason=_clean_str(payload.get("reason")) or fallback.reason,
            standard_refs=_clean_list(payload.get("standard_refs")) or fallback.standard_refs,
            entities=_clean_list(payload.get("entities")) or fallback.entities,
            metrics=_clean_list(payload.get("metrics")) or fallback.metrics,
            sub_questions=_clean_list(payload.get("sub_questions"))[: self.settings.QUERY_AGENT_MAX_SUB_QUESTIONS],
            rewritten_queries=_unique_queries(
                [normalized_question, *rewritten_queries],
                limit=self.settings.QUERY_AGENT_MAX_QUERIES,
            ),
            evidence_requirements=_clean_list(payload.get("evidence_requirements"))
            or fallback.evidence_requirements,
            synonym_expansions=_clean_expansion_list(payload.get("synonym_expansions"))
            or fallback.synonym_expansions,
            confidence=_clean_float(payload.get("confidence"), fallback.confidence),
            llm_used=True,
        )
        return _repair_plan(plan, fallback)


def normalize_question(question: str) -> str:
    text = unicodedata.normalize("NFKC", question or "")
    text = re.sub(r"[\u2010-\u2014\u2212]", "-", text)
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\s+", " ", text).strip()
    text = STANDARD_REF_PATTERN.sub(lambda match: _normalize_standard_ref(match.group(0)), text)
    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"\bμ\s*g\b", "μg", text, flags=re.I)
    text = re.sub(r"\bu\s*g\b", "μg", text, flags=re.I)
    text = re.sub(r"\bm\s*g\b", "mg", text, flags=re.I)
    text, _ = apply_query_synonyms(text)
    return text


def extract_standard_refs(question: str) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for match in STANDARD_REF_PATTERN.finditer(question or ""):
        ref = _normalize_standard_ref(match.group(0))
        key = normalize_for_search(ref).replace(" ", "")
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
    return refs


def extract_metric_terms(question: str) -> list[str]:
    terms = [term for term in METRIC_TERMS if term in question]
    for term in synonym_search_terms(detect_query_synonyms(question)):
        if term and term not in terms:
            terms.append(term)
    return terms


def extract_entities(question: str, metrics: list[str]) -> list[str]:
    entities: list[str] = []
    for metric in metrics:
        pattern = rf"([\u4e00-\u9fffA-Za-z0-9()/\-·]+?)的{re.escape(metric)}"
        for match in re.finditer(pattern, question):
            entity = _clean_entity(match.group(1))
            _append_entity_variants(entities, entity)
        pattern = rf"([\u4e00-\u9fffA-Za-z0-9()/\-·]+?)在([\u4e00-\u9fffA-Za-z0-9()/\-·]+?)(?:中|里|上)?的?{re.escape(metric)}"
        for match in re.finditer(pattern, question):
            _append_entity_variants(entities, _clean_entity(match.group(1)))
            _append_entity_variants(entities, _clean_entity(match.group(2)))
    return entities[:5]


def _normalize_standard_ref(value: str) -> str:
    text = value.upper().replace(" ", "")
    text = re.sub(r"[\u2010-\u2014\u2212]", "-", text)
    return text.replace("GB/T", "GB/T ")


def _looks_complex(question: str, refs: list[str]) -> bool:
    if len(refs) >= 2:
        return True
    if any(marker in question for marker in COMPLEX_MARKERS):
        return True
    if len(question) >= 42 and ("，" in question or "、" in question or "," in question):
        return True
    return False


def _question_type(question: str, refs: list[str]) -> str:
    if len(refs) >= 2:
        return "cross_document"
    if "对比" in question or "比较" in question or "不同" in question:
        return "comparison"
    if "分别" in question or "同时" in question:
        return "multi_hop"
    if "什么是" in question or "定义" in question:
        return "definition"
    return "single_lookup"


def _rule_reason(question: str, refs: list[str], metrics: list[str], is_complex: bool) -> str:
    if not is_complex:
        return "simple question; normalized only"
    reasons: list[str] = []
    if refs:
        reasons.append("contains standard reference")
    if metrics:
        reasons.append("contains regulated metric")
    if any(marker in question for marker in COMPLEX_MARKERS):
        reasons.append("contains complex retrieval marker")
    return "; ".join(reasons) or "complex question"


def _build_rule_queries(
    *,
    normalized_question: str,
    refs: list[str],
    metrics: list[str],
    entities: list[str],
    max_queries: int,
) -> list[str]:
    queries = [normalized_question]
    core_terms = [*entities, *metrics]
    for ref in refs:
        if core_terms:
            queries.append(f"{ref} {' '.join(core_terms)}")
        queries.append(ref)
    if core_terms:
        queries.append(" ".join(core_terms))
    for entity in entities:
        for metric in metrics[:3]:
            queries.append(f"{entity} {metric}")
    return _unique_queries(queries, limit=max_queries)


def _build_sub_questions(
    *,
    refs: list[str],
    metrics: list[str],
    entities: list[str],
    max_items: int,
) -> list[str]:
    sub_questions: list[str] = []
    core = " ".join([*entities, *metrics]).strip()
    for ref in refs:
        if core:
            sub_questions.append(f"{ref} 中 {core} 的规定是什么")
        else:
            sub_questions.append(f"{ref} 的相关规定是什么")
    if len(refs) >= 2:
        sub_questions.append(f"{refs[0]} 与 {refs[-1]} 的引用或适用关系是什么")
    leaf_entities = _leaf_entities(entities)
    primary_metrics = _primary_metric_terms(metrics)
    if len(leaf_entities) >= 2:
        metric_text = " ".join(primary_metrics[:2]).strip()
        for entity in leaf_entities:
            sub_questions.append(
                f"{entity} {metric_text} 的规定是什么"
                if metric_text
                else f"{entity} 的相关规定是什么"
            )
    elif len(leaf_entities) == 1 and len(primary_metrics) >= 2:
        for metric in primary_metrics:
            sub_questions.append(
                f"{leaf_entities[0]} {metric} 的规定是什么"
            )
    return _unique_queries(sub_questions, limit=max_items)


def _build_evidence_requirements(
    refs: list[str],
    metrics: list[str],
    entities: list[str],
) -> list[str]:
    requirements: list[str] = []
    requirements.extend(refs)
    requirements.extend(entities)
    requirements.extend(metrics)
    return _unique_queries(requirements, limit=12)


def _repair_plan(plan: QueryPlan, fallback: QueryPlan) -> QueryPlan:
    if not plan.normalized_question:
        plan.normalized_question = fallback.normalized_question
    if not plan.rewritten_queries:
        plan.rewritten_queries = fallback.rewritten_queries
    if not plan.synonym_expansions:
        plan.synonym_expansions = fallback.synonym_expansions
    if plan.normalized_question not in plan.rewritten_queries:
        plan.rewritten_queries.insert(0, plan.normalized_question)
    for query in fallback.rewritten_queries:
        if query not in plan.rewritten_queries:
            plan.rewritten_queries.append(query)
    plan.rewritten_queries = _unique_queries(
        plan.rewritten_queries,
        limit=get_settings().QUERY_AGENT_MAX_QUERIES,
    )
    return plan


def _clean_entity(value: str) -> str:
    text = STANDARD_REF_PATTERN.sub("", value)
    text = re.sub(
        r"^(根据|按照|现行|标准|比较|对比|中|和|及|以及|,|，|、)+",
        "",
        text,
    )
    text = text.strip(" ,，。？?；;：:的")
    return text[-28:] if len(text) > 28 else text


def _append_entity_variants(entities: list[str], entity: str) -> None:
    if not entity:
        return
    variants = [entity]
    match = re.match(r"(.+?)在(.+?)(?:中|里|上)?$", entity)
    if match:
        variants.extend([_clean_entity(match.group(1)), _clean_entity(match.group(2))])
    if re.search(r"[、和与]", entity):
        variants.extend(
            _clean_entity(item)
            for item in re.split(r"[、和与]", entity)
        )
    for variant in variants:
        if variant and variant not in entities:
            entities.append(variant)


def _leaf_entities(entities: list[str]) -> list[str]:
    leaves = [
        entity
        for entity in entities
        if entity and not re.search(r"[、和与]", entity)
    ]
    return _unique_queries(leaves, limit=5)


def _primary_metric_terms(metrics: list[str]) -> list[str]:
    generic = {"限量", "最大残留限量", "残留限量", "添加量"}
    candidates = [
        metric
        for metric in metrics
        if metric not in generic and re.search(r"[\u4e00-\u9fff]", metric)
    ]
    if not candidates:
        candidates = [metric for metric in metrics if metric]
    selected: list[str] = []
    for candidate in candidates:
        compact = normalize_for_search(candidate).replace(" ", "")
        if not compact:
            continue
        if any(
            compact in normalize_for_search(existing).replace(" ", "")
            or normalize_for_search(existing).replace(" ", "") in compact
            for existing in selected
        ):
            continue
        selected.append(candidate)
        if len(selected) >= 3:
            break
    return selected


def _clean_str(value: object) -> str:
    return str(value or "").strip()


def _clean_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        text = _clean_str(item)
        if text:
            cleaned.append(text)
    return _unique_queries(cleaned, limit=20)


def _clean_expansion_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        canonical = _clean_str(item.get("canonical"))
        if not canonical:
            continue
        aliases = _clean_list(item.get("aliases"))
        matched = _clean_list(item.get("matched"))
        cleaned.append(
            {
                "canonical": canonical,
                "aliases": aliases,
                "matched": matched,
                "category": _clean_str(item.get("category")) or "metric",
            }
        )
    return cleaned[:20]


def _clean_float(value: object, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _unique_queries(queries: list[str], *, limit: int) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for query in queries:
        text = _clean_str(query)
        key = normalize_for_search(text).replace(" ", "")
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(text)
        if len(unique) >= limit:
            break
    return unique
