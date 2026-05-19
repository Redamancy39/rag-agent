from typing import TypedDict


class AgentState(TypedDict, total=False):
    question: str
    answer: str
    citations: list[dict]
