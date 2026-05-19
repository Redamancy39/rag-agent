# Reranker, RAG Evaluation, and Processing Jobs

## 1. Reranker

The retrieval pipeline now works in two stages:

1. ChromaDB vector recall gets `RERANKER_CANDIDATE_TOP_K` candidates.
2. BGE reranker reorders candidates and returns the final `top_k`.

Configuration is in `backend/.env`:

```env
RERANKER_MODEL_NAME=E:/rag_project/rag-agent-kb-system/data/models/rerankers/bge-reranker-v2-m3
RERANKER_ENABLED=true
RERANKER_DEVICE=auto
RERANKER_CANDIDATE_TOP_K=20
```

`FlagEmbedding` is recommended for `bge-reranker-v2-m3`. If it is not installed, the app tries `sentence-transformers` CrossEncoder. If reranker loading fails, retrieval falls back to vector search and logs a warning.

## 2. Document Processing Jobs

Each uploaded document now creates a row in `document_processing_jobs`.

The document table still stores the latest user-facing state:

- `documents.status`
- `documents.status_message`

The job table stores task history and timing:

- `document_id`
- `status`
- `stage`
- `message`
- `error_message`
- `started_at`
- `finished_at`

API:

```http
GET /api/v1/documents/{document_id}/jobs
```

The endpoint returns the processing jobs for a document if the current user has access.

## 3. RAG Test Set

Example test set:

```text
data/eval/rag_testset.example.json
```

Run locally:

```powershell
cd E:\rag_project\rag-agent-kb-system\backend
D:\Anaconda\envs\rag-agent\python.exe scripts\run_rag_eval.py --username admin
```

Run a custom test set:

```powershell
D:\Anaconda\envs\rag-agent\python.exe scripts\run_rag_eval.py --username admin --testset E:\path\to\rag_testset.json
```

API:

```http
POST /api/v1/evaluations/rag
```

Request shape:

```json
{
  "name": "gb-standard-test",
  "cases": [
    {
      "id": "case-001",
      "question": "某指标的限量是多少？",
      "expected_found": true,
      "expected_answer_keywords": ["限量", "mg/kg"],
      "expected_citation_keywords": ["GB", "页"],
      "document_ids": null,
      "top_k": 5
    }
  ]
}
```

The first version checks:

- whether the system should find an answer;
- whether required answer keywords appear;
- whether required citation keywords appear.

This is intentionally simple and deterministic. A later stage can add LLM-as-judge scoring.
