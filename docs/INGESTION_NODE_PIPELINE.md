# Ingestion Node Pipeline

This document records the first step of the Agent-oriented refactor for the
document ingestion flow. The current implementation is still a lightweight
service pipeline, not a full LangGraph workflow, but the stages are now explicit
and can be migrated to graph nodes later.

## Node Order

```text
FileProbe
  -> StrategyPlanner
  -> Parse/OCR
  -> Normalize
  -> ChunkQuality
  -> Index
  -> Report
```

## Code Locations

- Pipeline and node definitions:
  `backend/app/agent/ingestion_nodes.py`
- Optional LangGraph adapter:
  `backend/app/agent/graph.py`
- Serializable graph-state snapshot:
  `backend/app/agent/ingestion_state.py`
- Probe and planning dataclasses:
  `backend/app/agent/ingestion_agent.py`
- Service integration:
  `backend/app/services/document_service.py`

## Node Responsibilities

| Node | Responsibility | Main output |
| --- | --- | --- |
| `FileProbe` | Samples the file and records file type, text readability, table count, page count, probe errors and OCR need. | `IngestionProbe` |
| `StrategyPlanner` | Converts probe data into a parser/OCR/LLM strategy. Rules remain the safety baseline; optional LLM planning can adjust the strategy. | `IngestionPlan` |
| `Parse/OCR` | Runs the selected file loader and `DocumentPreprocessor`, including OCR fallback and page-level text repair when needed. | loaded document parts |
| `Normalize` | Splits parsed parts into chunks and optionally runs LLM normalization for low-quality OCR/table chunks. | normalized chunks |
| `ChunkQuality` | Scores final chunks for readability, OCR noise and table structure signals. | quality metadata |
| `Index` | Attaches document metadata, generates BGE embeddings and rewrites the document's ChromaDB vectors. | indexed chunks |
| `Report` | Finalizes document status, chunk count and ingestion report logging. | indexed document |

## Design Notes

- `document_service._index_document()` now delegates orchestration to
  `IngestionPipeline`.
- Database updates remain in `document_service` through callback functions. This
  keeps the nodes independent from persistence details and makes a future
  LangGraph migration simpler.
- Existing manual LLM chunk normalization is unchanged.
- Existing `document_processing_jobs.probe_json` and `plan_json` are still
  written by the strategy stage when the ingestion agent is enabled.
- The pipeline intentionally keeps deterministic rules as a safety gate. LLM
  planning cannot disable OCR when the rule probe detects unusable text.
- Each node now emits a small contract (`reads`, `writes`, `side_effects`) and a
  serializable `state_snapshot`. This is the migration boundary for a future
  LangGraph `StateGraph`: node inputs and outputs are explicit rather than
  inferred from service code.
- Node trace items can be `running`, `done`, `skipped` or `failed`. Skipped nodes
  are used for configuration-driven branches, for example when the ingestion
  agent is disabled or LLM chunk normalization has no eligible candidates.
- The `Normalize` node records LLM normalization selection details, including
  eligible chunk count, selected candidate count, already-normalized skip count,
  generated normalized chunk count and merge mode.

## LangGraph Migration Readiness

The current pre-migration state is:

| Requirement | Current status |
| --- | --- |
| Explicit nodes | Done. Seven service nodes match the target graph stages. |
| Serializable state | Done. `build_ingestion_state_snapshot()` emits `ingestion_state_v1`. |
| Node contracts | Done. `build_node_contract()` records reads/writes/side effects. |
| Observable transitions | Done. Trace JSON stores state, duration, summary, contract and snapshot. |
| Branch visibility | Partial. Configuration branches and LLM-normalization skip reasons are visible; retry branches are still future work. |
| Retry / fallback policy | Not implemented as graph edges yet. Current fallback remains inside loaders/preprocessor. |
| LangGraph runtime | Optional adapter added. The default executor remains `pipeline`; `INGESTION_EXECUTOR=langgraph` enables the sequential graph when the dependency is installed. |

## Optional LangGraph Executor

The project now has an optional LangGraph adapter for the ingestion workflow.
It reuses the same node classes and `run_ingestion_node()` execution function as
the stable pipeline, so trace output, state snapshots and error handling remain
consistent.

Configuration:

```env
INGESTION_EXECUTOR=pipeline
```

Supported values:

- `pipeline`: default stable executor. No LangGraph dependency required.
- `langgraph`: build and invoke a sequential `StateGraph` using the same nodes.
  If `langgraph` is not installed, the service records a skipped
  `LangGraphAdapter` trace event and falls back to `pipeline`.

Install the optional dependency through `backend/requirements-rag.txt`:

```powershell
pip install -r requirements-rag.txt
```

This adapter is intentionally conservative. It does not yet add conditional
retry or human-in-the-loop review; those should be added after the graph has
been exercised on the current PDF test set.

The default LangGraph adapter now exposes two lightweight branch points:

```text
StrategyPlanner
  -> RouteTextFirst / RouteOcrFirst
  -> Parse/OCR
  -> RouteLlmNormalize / RouteSkipLlmNormalize
  -> Normalize
```

These route nodes do not duplicate parser logic. They make the existing
strategy decision visible in the graph trace, while the actual parsing and
fallback logic remains in `Parse/OCR` and `DocumentPreprocessor`.

Failure fallback currently works at the parser/preprocessor level:

- `PdfLoader` tries PyMuPDF first and falls back to pypdf when PyMuPDF parsing
  raises an exception.
- If PDF text parsing or text-layer validation fails and
  `PREPROCESS_OCR_FALLBACK_ENABLED=true`, `Parse/OCR` records
  `report.parse_fallback` and retries with PaddleOCR.
- Chunk-level LLM normalization is best-effort. A failed chunk is skipped and
  the original chunk remains available for indexing.

## Current Boundary

This is an Agent-oriented structure, not yet an autonomous multi-step agent.
The next step is to convert these service nodes into observable LangGraph nodes
with explicit state transitions, retry policies and failure branches.
