from __future__ import annotations

from typing import Any

STATE_SCHEMA_VERSION = "ingestion_state_v1"


def build_ingestion_state_snapshot(
    context: Any,
    *,
    current_node: str | None = None,
) -> dict[str, Any]:
    document = context.document
    probe = getattr(context, "probe", None)
    plan = getattr(context, "plan", None)
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "current_node": current_node,
        "document": {
            "id": document.id,
            "filename": document.filename,
            "file_type": document.file_type,
            "status": document.status,
            "chunk_count": document.chunk_count,
        },
        "probe": _probe_snapshot(probe),
        "plan": _plan_snapshot(plan),
        "counts": {
            "parts": len(getattr(context, "parts", []) or []),
            "chunks": len(getattr(context, "chunks", []) or []),
            "indexed_chunks": len(getattr(context, "indexed_chunks", []) or []),
            "embeddings": len(getattr(context, "embeddings", []) or []),
        },
        "quality": _safe_dict((getattr(context, "report", {}) or {}).get("quality")),
        "node_results": _safe_dict(getattr(context, "node_results", {})),
    }


def build_node_contract(node_name: str) -> dict[str, list[str]]:
    return NODE_CONTRACTS.get(
        node_name,
        {
            "reads": [],
            "writes": [],
            "side_effects": [],
        },
    )


NODE_CONTRACTS: dict[str, dict[str, list[str]]] = {
    "FileProbe": {
        "reads": ["document.storage_path", "document.file_type", "settings"],
        "writes": ["context.probe", "report.probe"],
        "side_effects": [],
    },
    "StrategyPlanner": {
        "reads": ["context.probe", "settings"],
        "writes": ["context.plan", "report.plan", "document_processing_jobs.plan_json"],
        "side_effects": ["optional LLM planner call"],
    },
    "RouteTextFirst": {
        "reads": ["context.plan"],
        "writes": ["trace.route"],
        "side_effects": [],
    },
    "RouteOcrFirst": {
        "reads": ["context.plan"],
        "writes": ["trace.route"],
        "side_effects": [],
    },
    "RouteLlmNormalize": {
        "reads": ["context.plan"],
        "writes": ["trace.route"],
        "side_effects": [],
    },
    "RouteSkipLlmNormalize": {
        "reads": ["context.plan"],
        "writes": ["trace.route"],
        "side_effects": [],
    },
    "Parse/OCR": {
        "reads": ["context.plan", "document.storage_path", "document.file_type"],
        "writes": ["context.parts", "report.parsed_part_count"],
        "side_effects": ["optional PaddleOCR inference", "optional LLM part preprocessing"],
    },
    "Normalize": {
        "reads": ["context.parts", "context.plan", "settings"],
        "writes": ["context.chunks", "report.normalization"],
        "side_effects": ["optional LLM chunk normalization"],
    },
    "ChunkQuality": {
        "reads": ["context.chunks"],
        "writes": ["context.chunks.metadata", "report.quality"],
        "side_effects": [],
    },
    "Index": {
        "reads": ["context.chunks", "document metadata", "settings"],
        "writes": ["context.indexed_chunks", "context.embeddings", "report.indexed_chunk_count"],
        "side_effects": ["BGE embedding inference", "ChromaDB rewrite"],
    },
    "Report": {
        "reads": ["context.indexed_chunks", "context.report"],
        "writes": ["document.chunk_count", "document.status", "report.document"],
        "side_effects": ["database status update"],
    },
}


def _probe_snapshot(probe: Any | None) -> dict[str, Any] | None:
    if probe is None:
        return None
    return {
        "file_type": probe.file_type,
        "file_size": probe.file_size,
        "page_count": probe.page_count,
        "sampled_pages": probe.sampled_pages,
        "text_chars": probe.text_chars,
        "table_count": probe.table_count,
        "readable": probe.readable,
        "probe_error": probe.probe_error,
    }


def _plan_snapshot(plan: Any | None) -> dict[str, Any] | None:
    if plan is None:
        return None
    return {
        "primary_reader": plan.primary_reader,
        "use_ocr": plan.use_ocr,
        "use_llm_preprocessing": plan.use_llm_preprocessing,
        "source": plan.source,
        "reason": plan.reason,
    }


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
