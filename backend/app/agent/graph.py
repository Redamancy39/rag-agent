from __future__ import annotations

from typing import Any, TypedDict

from app.agent.ingestion_nodes import (
    ChunkQualityNode,
    FileProbeNode,
    IngestionContext,
    IngestionNode,
    IndexNode,
    NodeOutcome,
    NormalizeNode,
    ParseOcrNode,
    ReportNode,
    StrategyPlannerNode,
    run_ingestion_node,
)
from app.agent.ingestion_state import build_ingestion_state_snapshot


class LangGraphUnavailableError(RuntimeError):
    pass


class IngestionGraphState(TypedDict, total=False):
    context: IngestionContext
    current_node: str | None
    completed_nodes: list[str]
    state_snapshot: dict[str, Any]


class RouteDecisionNode:
    def __init__(self, name: str, message: str, detail_key: str) -> None:
        self.name = name
        self.message = message
        self.detail_key = detail_key

    def run(self, context: IngestionContext) -> NodeOutcome:
        return NodeOutcome(
            message=self.message,
            details={
                "route": self.detail_key,
                "primary_reader": (
                    context.plan.primary_reader if context.plan is not None else None
                ),
                "use_ocr": context.plan.use_ocr if context.plan is not None else None,
                "use_liteparse": (
                    bool(getattr(context.plan, "use_liteparse", False))
                    if context.plan is not None
                    else None
                ),
                "use_llm_preprocessing": (
                    context.plan.use_llm_preprocessing if context.plan is not None else None
                ),
            },
        )


def run_ingestion_graph(
    context: IngestionContext,
    *,
    nodes: list[IngestionNode] | None = None,
) -> IngestionContext:
    graph = build_ingestion_graph(nodes)
    final_state = graph.invoke(
        {
            "context": context,
            "current_node": None,
            "completed_nodes": [],
            "state_snapshot": build_ingestion_state_snapshot(context),
        }
    )
    return final_state["context"]


def build_ingestion_graph(nodes: list[IngestionNode] | None = None) -> Any:
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:
        raise LangGraphUnavailableError(
            "LangGraph is not installed. Install requirements-rag.txt or set "
            "INGESTION_EXECUTOR=pipeline."
        ) from exc
    try:
        from langgraph.graph import START
    except ImportError:
        START = None

    if nodes is None:
        return _build_default_ingestion_graph(StateGraph, START, END)

    graph_nodes = nodes
    workflow = StateGraph(IngestionGraphState)
    node_ids: list[str] = []
    for node in graph_nodes:
        node_id = _graph_node_id(node.name)
        node_ids.append(node_id)
        workflow.add_node(node_id, _make_graph_node(node))

    if not node_ids:
        raise ValueError("No ingestion graph nodes configured")

    if START is not None:
        try:
            workflow.add_edge(START, node_ids[0])
        except Exception:
            workflow.set_entry_point(node_ids[0])
    else:
        workflow.set_entry_point(node_ids[0])
    for previous, current in zip(node_ids, node_ids[1:], strict=False):
        workflow.add_edge(previous, current)
    workflow.add_edge(node_ids[-1], END)
    return workflow.compile()


def build_graph() -> Any:
    return build_ingestion_graph()


def _build_default_ingestion_graph(StateGraph: Any, START: Any, END: Any) -> Any:
    workflow = StateGraph(IngestionGraphState)
    nodes: dict[str, IngestionNode] = {
        "file_probe": FileProbeNode(),
        "strategy_planner": StrategyPlannerNode(),
        "route_text_first": RouteDecisionNode(
            "RouteTextFirst",
            "文本层可用，按文本优先路径继续",
            "text_first",
        ),
        "route_ocr_first": RouteDecisionNode(
            "RouteOcrFirst",
            "策略要求 OCR，按 OCR 优先路径继续",
            "ocr_first",
        ),
        "route_liteparse": RouteDecisionNode(
            "RouteLiteParse",
            "策略要求 LiteParse，按格式转换与版面解析路径继续",
            "liteparse",
        ),
        "parse_ocr": ParseOcrNode(),
        "route_llm_normalize": RouteDecisionNode(
            "RouteLlmNormalize",
            "策略建议启用 LLM 表格/低质量切块整理",
            "llm_normalize",
        ),
        "route_skip_llm_normalize": RouteDecisionNode(
            "RouteSkipLlmNormalize",
            "策略未要求 LLM 切块整理，直接进入规则归一化",
            "skip_llm_normalize",
        ),
        "normalize": NormalizeNode(),
        "chunk_quality": ChunkQualityNode(),
        "index": IndexNode(),
        "report": ReportNode(),
    }
    for node_id, node in nodes.items():
        workflow.add_node(node_id, _make_graph_node(node))

    _add_start_edge(workflow, START, "file_probe")
    workflow.add_edge("file_probe", "strategy_planner")
    workflow.add_conditional_edges(
        "strategy_planner",
        _parse_route,
        {
            "text_first": "route_text_first",
            "ocr_first": "route_ocr_first",
            "liteparse": "route_liteparse",
        },
    )
    workflow.add_edge("route_text_first", "parse_ocr")
    workflow.add_edge("route_ocr_first", "parse_ocr")
    workflow.add_edge("route_liteparse", "parse_ocr")
    workflow.add_conditional_edges(
        "parse_ocr",
        _llm_route,
        {
            "llm_normalize": "route_llm_normalize",
            "skip_llm_normalize": "route_skip_llm_normalize",
        },
    )
    workflow.add_edge("route_llm_normalize", "normalize")
    workflow.add_edge("route_skip_llm_normalize", "normalize")
    workflow.add_edge("normalize", "chunk_quality")
    workflow.add_edge("chunk_quality", "index")
    workflow.add_edge("index", "report")
    workflow.add_edge("report", END)
    return workflow.compile()


def _make_graph_node(node: IngestionNode):
    def _run(state: IngestionGraphState) -> IngestionGraphState:
        context = state["context"]
        run_ingestion_node(node, context)
        completed_nodes = [*(state.get("completed_nodes") or []), node.name]
        return {
            "context": context,
            "current_node": node.name,
            "completed_nodes": completed_nodes,
            "state_snapshot": build_ingestion_state_snapshot(
                context,
                current_node=node.name,
            ),
        }

    return _run


def _parse_route(state: IngestionGraphState) -> str:
    plan = state["context"].plan
    if plan is not None and (
        bool(getattr(plan, "use_liteparse", False))
        or plan.primary_reader == "liteparse"
    ):
        return "liteparse"
    if plan is not None and (plan.use_ocr or plan.primary_reader == "paddleocr"):
        return "ocr_first"
    return "text_first"


def _llm_route(state: IngestionGraphState) -> str:
    context = state["context"]
    if context.callbacks.should_normalize_chunks(context.plan):
        return "llm_normalize"
    return "skip_llm_normalize"


def _add_start_edge(workflow: Any, START: Any, first_node: str) -> None:
    if START is not None:
        try:
            workflow.add_edge(START, first_node)
            return
        except Exception:
            pass
    workflow.set_entry_point(first_node)


def _graph_node_id(node_name: str) -> str:
    return (
        node_name.lower()
        .replace("/", "_")
        .replace(" ", "_")
        .replace("-", "_")
    )
