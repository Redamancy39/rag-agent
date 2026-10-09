import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
from openai import APIStatusError, APITimeoutError
from app.core.config import Settings
from app.rag.llm_budget import IngestionLlmBudget, LLMLimitReached
from app.rag.llm_client import OpenAICompatibleLLM
from app.rag.normalizers.llm_normalizer import normalize_with_llm, normalize_chunks_with_llm
from app.rag.schemas import DocumentBlock, DocumentChunk
from app.services.document_llm_status import summarize_document_llm


def settings(**kwargs):
    return Settings(_env_file=None, OPENAI_API_KEY='synthetic-only', OPENAI_MODEL_NAME='synthetic',
                    PREPROCESS_LLM_ENABLED=True, CHUNK_LLM_NORMALIZATION_ENABLED=True, **kwargs)


def response(**payload):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])


def chunk(index):
    return DocumentChunk(text=f'Synthetic table candidate {index} with sufficient readable content',
                         metadata={'needs_llm_normalization': True, 'local_chunk_index': index})


class IngestionLlmLimitTests(unittest.TestCase):
    def setUp(self):
        self.settings = settings()
        self.sdk = Mock()
        self.sdk.chat.completions.create.return_value = response(should_use=False)
        self.patches = [patch('app.rag.llm_client.get_settings', return_value=self.settings),
                        patch('app.rag.normalizers.llm_normalizer.get_settings', return_value=self.settings),
                        patch('openai.OpenAI', return_value=self.sdk)]
        for item in self.patches: item.start()
        self.addCleanup(lambda: [item.stop() for item in reversed(self.patches)])

    def test_default_fact_stage_makes_zero_requests_for_548_rows(self):
        stats = {}
        parts = [DocumentBlock(text='Synthetic row fact', metadata={'chunk_type': 'table_row_fact'}) for _ in range(548)]
        self.assertEqual(normalize_with_llm(parts, stats=stats), [])
        self.sdk.chat.completions.create.assert_not_called()
        self.assertFalse(stats['fact_preprocessing_enabled'])

    def test_large_candidate_set_is_capped_at_120(self):
        stats = {}
        normalize_chunks_with_llm([chunk(i) for i in range(548)], stats=stats)
        self.assertEqual(self.sdk.chat.completions.create.call_count, 120)
        self.assertEqual(stats['request_attempted_count'], 120)
        self.assertEqual(stats['processed_count'], 120)
        self.assertEqual(stats['skipped_count'], 428)

    def test_enabled_fact_and_chunk_stages_share_budget(self):
        self.settings.PREPROCESS_FACT_LLM_ENABLED = True
        self.settings.INGESTION_LLM_MAX_CALLS = 3
        budget = IngestionLlmBudget(self.settings)
        parts = [DocumentBlock(text='Synthetic fact', metadata={'chunk_type': 'table_row_fact'}) for _ in range(2)]
        normalize_with_llm(parts, budget=budget)
        stats = {}
        normalize_chunks_with_llm([chunk(i) for i in range(4)], budget=budget, stats=stats)
        self.assertEqual(self.sdk.chat.completions.create.call_count, 3)
        self.assertEqual(stats['limit_reason'], 'call_limit')
        self.assertEqual(stats['processed_count'], 1)
        self.assertEqual(stats['skipped_count'], 3)

    def test_retry_consumes_budget_and_sdk_retries_are_disabled(self):
        self.settings.INGESTION_LLM_MAX_CALLS = 2
        self.sdk.chat.completions.create.side_effect = [APITimeoutError(request=httpx.Request('POST', 'https://synthetic.invalid')), response(should_use=False)]
        stats = {}
        normalize_chunks_with_llm([chunk(0), chunk(1)], stats=stats)
        self.assertEqual(self.sdk.chat.completions.create.call_count, 2)
        self.assertEqual(stats['retry_count'], 1)
        self.assertEqual(stats['request_failed_count'], 1)
        self.assertEqual(stats['processed_count'], 1)
        self.assertEqual(stats['attempted_count'], 1)
        self.assertEqual(stats['limit_reason'], 'call_limit')
        import openai
        self.assertEqual(openai.OpenAI.call_args.kwargs['max_retries'], 0)
        self.assertEqual(self.sdk.chat.completions.create.call_args.kwargs['max_tokens'], 2048)

    def test_exhausted_retry_budget_does_not_send_another_request(self):
        self.settings.INGESTION_LLM_MAX_CALLS = 1
        self.sdk.chat.completions.create.side_effect = APITimeoutError(request=httpx.Request('POST', 'https://synthetic.invalid'))
        stats = {}
        normalize_chunks_with_llm([chunk(0)], stats=stats)
        self.assertEqual(self.sdk.chat.completions.create.call_count, 1)
        self.assertEqual(stats['request_attempted_count'], 1)
        self.assertEqual(stats['failed_count'], 1)
        self.assertEqual(stats['limit_reason'], 'call_limit')

    def test_deadline_preserves_returned_results_and_shortens_request_timeout(self):
        self.settings.INGESTION_LLM_MAX_SECONDS = 2
        time = [0.0]
        budget = IngestionLlmBudget(self.settings, clock=lambda: time[0])
        def complete(**kwargs):
            self.assertLessEqual(kwargs['timeout'], 2)
            time[0] = 2.1
            return response(normalized_text='Synthetic normalized text returned before later work is skipped')
        self.sdk.chat.completions.create.side_effect = complete
        stats = {}
        result = normalize_chunks_with_llm([chunk(0), chunk(1)], budget=budget, stats=stats)
        self.assertEqual(len(result), 1)
        self.assertEqual(stats['limit_reason'], 'time_limit')
        self.assertEqual(stats['processed_count'], 1)
        self.assertEqual(self.sdk.chat.completions.create.call_count, 1)

    def test_three_consecutive_failures_stop_without_failing_all_candidates(self):
        self.sdk.chat.completions.create.side_effect = APITimeoutError(request=httpx.Request('POST', 'https://synthetic.invalid'))
        stats = {}
        normalize_chunks_with_llm([chunk(i) for i in range(20)], stats=stats)
        self.assertEqual(self.sdk.chat.completions.create.call_count, 6)
        self.assertEqual(stats['limit_reason'], 'api_failures')
        self.assertEqual(stats['processed_count'], 3)

    def test_non_retryable_auth_error_stops_after_one_request(self):
        error = APIStatusError('synthetic unauthorized', response=httpx.Response(401, request=httpx.Request('POST', 'https://synthetic.invalid')), body=None)
        self.sdk.chat.completions.create.side_effect = error
        stats = {}
        normalize_chunks_with_llm([chunk(0), chunk(1)], stats=stats)
        self.assertEqual(self.sdk.chat.completions.create.call_count, 1)
        self.assertEqual(stats['limit_reason'], 'api_failures')

    def test_progress_updates_on_request_retry_and_failure_without_false_completion(self):
        self.settings.INGESTION_LLM_MAX_CALLS = 2
        self.sdk.chat.completions.create.side_effect = [APITimeoutError(request=httpx.Request('POST', 'https://synthetic.invalid')), response(should_use=False)]
        updates, traces = [], []
        stats = {}
        normalize_chunks_with_llm([chunk(0), chunk(1)], stats=stats,
            progress_callback=lambda current, total, message: updates.append((current, total, message)),
            trace_callback=lambda summary: traces.append(summary))
        self.assertEqual([u[0] for u in updates], sorted(u[0] for u in updates))
        self.assertTrue(any('API 重试' in u[2] for u in updates))
        self.assertEqual(updates[-1][:2], (1, 2))
        self.assertEqual(traces[-1]['request_attempted_count'], 2)
        self.assertEqual(traces[-1]['limit_reason'], 'call_limit')

    def test_limit_record_is_partial_and_shows_request_counts(self):
        job = SimpleNamespace(id=1, finished_at=None, stage='indexed', status='indexed', message='',
            trace_json=json.dumps([{'node': 'LlmNormalize', 'state': 'done', 'summary': dict(enabled=True,
                candidate_count=20, attempted_count=3, succeeded_count=3, failed_count=0, generated_count=2,
                stored_count=2, processed_count=3, skipped_count=17, request_attempted_count=4,
                request_max_calls=4, retry_count=1, limit_reason='call_limit')}]))
        result = summarize_document_llm(job)
        self.assertEqual(result.check_status, 'partial')
        self.assertEqual(result.normalization_status, 'indexed')
        self.assertIn('4/4', result.detail)
        self.assertIn('保留原文', result.detail)

    def test_parse_and_normalize_limit_still_index_all_unprocessed_source_chunks(self):
        from app.agent.ingestion_nodes import IngestionCallbacks, IngestionContext, ParseOcrNode, NormalizeNode, IndexNode, ReportNode
        from app.agent.ingestion_agent import IngestionPlan, IngestionProbe
        self.settings.INGESTION_LLM_MAX_CALLS = 1
        parts = [DocumentBlock(text=f'Synthetic long table row {i} for deterministic ingestion testing',
            metadata={'chunk_type': 'table_row_fact', 'table_index': i + 1,
                      'preprocess_repair_flags': 'microbe_power_hint'}) for i in range(4)]
        statuses, traces = [], []
        doc = SimpleNamespace(id=1, filename='synthetic.docx', file_type='docx', storage_path='synthetic.docx', chunk_count=0, error_message=None)
        callbacks = IngestionCallbacks(set_status=lambda status, message: statuses.append((status,message)),
            update_progress=lambda *args: None, update_trace=lambda event: traces.append(event),
            store_plan=lambda plan: None, should_normalize_chunks=lambda plan: True,
            attach_metadata=lambda chunks: chunks, parser_status_message=lambda _: 'synthetic parse')
        ctx = IngestionContext(db=None, document=doc, callbacks=callbacks, settings=self.settings)
        ctx.plan = IngestionPlan('docx_loader',False,False,True,'synthetic',IngestionProbe('docx',100))
        with patch('app.agent.ingestion_nodes.get_loader') as loader, \
             patch('app.rag.preprocessor.get_settings', return_value=self.settings):
            loader.return_value.load.return_value = parts
            ParseOcrNode().run(ctx)
        self.sdk.chat.completions.create.assert_not_called()
        with patch('app.rag.chunk_quality.get_settings', return_value=self.settings):
            NormalizeNode().run(ctx)
        self.assertEqual(len(ctx.chunks), 4)
        self.assertEqual(ctx.report['normalization']['limit_reason'], 'call_limit')
        with patch('app.agent.ingestion_nodes.BgeEmbeddingModel') as model, \
             patch('app.agent.ingestion_nodes.ChromaVectorStore') as store:
            model.return_value.embed_texts.side_effect = lambda texts: [[0.1,0.2] for _ in texts]
            IndexNode().run(ctx)
            self.assertEqual(len(store.return_value.add_documents.call_args.args[1]), 4)
        ReportNode().run(ctx)
        self.assertEqual(doc.chunk_count, 4)
        self.assertEqual(statuses[-1][0], 'indexed')
        self.assertIn('保留', statuses[-1][1])
        self.assertTrue(any(e['node']=='LlmNormalize' and e['state']=='done' for e in traces))

    def test_progress_stage_is_persisted_and_cleared_for_embedding(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.models import Base, Document, User
        from app.services.document_service import _create_processing_job, _update_job_progress, _set_document_status
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            owner = User(username='synthetic', hashed_password='test')
            db.add(owner); db.flush()
            doc = Document(filename='synthetic.txt', storage_path='synthetic.txt', file_type='txt', file_size=100,
                           owner_id=owner.id, status='normalize')
            db.add(doc); db.commit()
            job = _create_processing_job(db, doc)
            _update_job_progress(db, doc, current=2, total=5, detail='synthetic request in flight')
            self.assertEqual(job.stage, 'llm_preprocessing')
            self.assertEqual(job.status, 'llm_preprocessing')
            self.assertEqual(job.progress_percent, 40)
            self.assertIsNotNone(job.updated_at)
            _set_document_status(db, doc, 'embedding', 'synthetic embedding')
            self.assertEqual(job.progress_total, 0)
            self.assertIsNone(job.progress_detail)
        engine.dispose()
