from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.logger import get_logger
from app.rag.llm_client import OpenAICompatibleLLM

logger = get_logger(__name__)

CITATION_MARK = re.compile(r"[\[【]\d+[\]】]")
NOT_FOUND_MARK = "未找到相关答案"

DECISION_PROMPT = """你只判断用户问题要不要查询企业知识库，并在不需要查询时给出直接回答。不要读取文档，不要假设任何文档内容。

需要查询：问题在询问可能写在已上传文档中的事实、条款、数值、步骤、定义、规定或材料内容。不确定时也要查询。
不需要查询：问候、系统使用方式、与文档无关的文字整理，或不依赖文档的计算。

不需要查询时，answer 只回答问题本身，不能编造文件名、标准号、限量、条款或任何文档内容。
需要查询时，answer 使用空字符串。

只输出 JSON：
{"search": true, "reason": "简短原因", "answer": ""}
"""


@dataclass(slots=True)
class RetrievalGateDecision:
    search: bool
    reason: str
    answer: str = ""


def decide_knowledge_search(question: str) -> RetrievalGateDecision:
    try:
        payload = OpenAICompatibleLLM(max_output_tokens=512).complete_json(
            DECISION_PROMPT,
            f"用户问题：{question}",
        )
    except Exception as exc:
        logger.warning("Knowledge search decision failed: %s", exc)
        return RetrievalGateDecision(True, "判断失败，继续查询知识库")

    search = payload.get("search")
    if not isinstance(search, bool):
        return RetrievalGateDecision(True, "判断结果无效，继续查询知识库")
    reason = _clean(payload.get("reason"))[:300]
    answer = _clean(payload.get("answer"))[:2000]
    if search:
        return RetrievalGateDecision(True, reason or "问题需要查询知识库")
    if not answer or CITATION_MARK.search(answer) or NOT_FOUND_MARK in answer:
        return RetrievalGateDecision(True, "直接回答不适合跳过检索，继续查询知识库")
    return RetrievalGateDecision(False, reason or "问题不需要查询知识库", answer)


def _clean(value: object) -> str:
    return str(value or "").strip()
