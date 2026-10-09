import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from app.services.document_llm_status import summarize_document_llm, NO_CANDIDATES
from app.rag.normalizers.llm_normalizer import (
    normalize_chunks_with_llm, normalize_with_llm, ChunkTextNormalizer,
    StructuredFactNormalizer, LlmNormalizationSelection,
)
from app.rag.schemas import DocumentChunk, DocumentBlock

def job(summary=None, *, status='indexed', state='done', message=None):
    trace = [] if summary is None else [{'node':'LlmNormalize','state':state,'summary':summary}]
    return SimpleNamespace(id=7,status=status,stage='llm_preprocessing',message=message,
                           trace_json=json.dumps(trace),finished_at=None)

class LlmStatusTests(unittest.TestCase):
    def test_enabled_switch_is_not_execution(self):
        record=summarize_document_llm(job({'enabled':True,'candidate_count':0,'generated_count':0}))
        self.assertEqual((record.check_status,record.normalization_status),('not_run','not_needed'))

    def test_disabled_with_candidates_does_not_claim_detection(self):
        record=summarize_document_llm(job({'enabled':False,'candidate_count':5,'generated_count':0}))
        self.assertEqual(record.check_status,'not_run')

    def test_legacy_without_response_counts_stays_unknown(self):
        record=summarize_document_llm(job({'enabled':True,'candidate_count':2,'generated_count':0}))
        self.assertEqual(record.check_status,'unknown')

    def test_model_responded_but_no_rewrite(self):
        record=summarize_document_llm(job({'attempted_count':2,'succeeded_count':2,'failed_count':0,'generated_count':0}))
        self.assertEqual((record.check_status,record.normalization_status),('completed','not_generated'))

    def test_all_model_failures_are_not_completed(self):
        record=summarize_document_llm(job({'attempted_count':2,'succeeded_count':0,'failed_count':2,'generated_count':0}))
        self.assertEqual((record.check_status,record.normalization_status),('failed','failed'))

    def test_partial_success_with_indexed_result(self):
        record=summarize_document_llm(job({'attempted_count':2,'succeeded_count':1,'failed_count':1,'generated_count':1,'stored_count':1}))
        self.assertEqual((record.check_status,record.normalization_status),('partial','indexed'))

    def test_index_failure_does_not_claim_persisted_result(self):
        record=summarize_document_llm(job({'succeeded_count':1,'generated_count':1,'stored_count':1},status='failed'))
        self.assertEqual((record.check_status,record.normalization_status),('completed','index_failed'))

    def test_existing_stored_result_with_no_new_candidates(self):
        record=summarize_document_llm(job({'enabled':True,'candidate_count':0,'attempted_count':0,'stored_count':4,'generated_count':0}))
        self.assertEqual(record.normalization_status,'indexed')
        self.assertEqual(record.stored_count,4)

    def test_old_rule_only_manual_job(self):
        record=summarize_document_llm(job(message=NO_CANDIDATES))
        self.assertEqual((record.check_status,record.normalization_status),('not_run','not_needed'))

    def test_running_job_is_not_completed(self):
        record=summarize_document_llm(job({'enabled':True,'candidate_count':2,'attempted_count':0},status='llm_preprocessing',state='running'))
        self.assertEqual(record.check_status,'running')

    def test_corrupt_trace_stays_unknown(self):
        old=job()
        old.trace_json='invalid-json'
        self.assertEqual(summarize_document_llm(old).check_status,'unknown')

class NormalizationAccountingTests(unittest.TestCase):
    def test_preprocessing_response_without_facts_is_recorded(self):
        stats={}
        block=DocumentBlock(text='synthetic table facts',metadata={'chunk_type':'table_row_fact'})
        settings=SimpleNamespace(PREPROCESS_LLM_ENABLED=True,PREPROCESS_FACT_LLM_ENABLED=True,PREPROCESS_LLM_TARGET_CHUNK_TYPES=['table_row_fact'],PREPROCESS_LLM_MAX_INPUT_CHARS=4000)
        fake=SimpleNamespace(complete_json=Mock(return_value={'facts':[]}))
        with patch('app.rag.normalizers.llm_normalizer.get_settings',return_value=settings), \
             patch.object(StructuredFactNormalizer,'_get_llm',return_value=fake):
            self.assertEqual(normalize_with_llm([block],stats=stats),[])
        fake.complete_json.assert_called_once()
        self.assertEqual({key: stats[key] for key in ('attempted_count','succeeded_count','failed_count')},
                         {'attempted_count':1,'succeeded_count':1,'failed_count':0})

    def test_partial_response_counts_without_live_api(self):
        chunks=[DocumentChunk(text='synthetic candidate content long enough',metadata={}) for _ in range(3)]
        stats={}
        settings=SimpleNamespace(PREPROCESS_LLM_ENABLED=True,CHUNK_LLM_NORMALIZATION_ENABLED=True,
                                 CHUNK_LLM_MIN_INPUT_CHARS=20,PREPROCESS_LLM_MAX_INPUT_CHARS=4000,OPENAI_MODEL_NAME='synthetic')
        fake=SimpleNamespace(complete_json=Mock(side_effect=[{'normalized_text':'synthetic normalized content long enough'}, {'should_use':False}, RuntimeError('synthetic failure')]))
        with patch('app.rag.normalizers.llm_normalizer.get_settings',return_value=settings), \
             patch('app.rag.normalizers.llm_normalizer.select_llm_normalization_candidates',return_value=LlmNormalizationSelection(chunks,3,0,3)), \
             patch.object(ChunkTextNormalizer,'_get_llm',return_value=fake):
            normalized=normalize_chunks_with_llm(chunks,stats=stats)
        self.assertEqual(len(normalized),1)
        self.assertTrue(normalized[0].metadata['llm_normalized'])
        self.assertEqual({key: stats[key] for key in ('attempted_count','succeeded_count','failed_count')},
                         {'attempted_count':3,'succeeded_count':2,'failed_count':1})

    def test_short_candidate_is_not_a_model_response(self):
        chunk=DocumentChunk(text='tiny',metadata={})
        stats={}
        settings=SimpleNamespace(PREPROCESS_LLM_ENABLED=True,CHUNK_LLM_NORMALIZATION_ENABLED=True,CHUNK_LLM_MIN_INPUT_CHARS=20)
        with patch('app.rag.normalizers.llm_normalizer.get_settings',return_value=settings), \
             patch('app.rag.normalizers.llm_normalizer.select_llm_normalization_candidates',return_value=LlmNormalizationSelection([chunk],1,0,1)), \
             patch.object(ChunkTextNormalizer,'_get_llm') as model:
            self.assertEqual(normalize_chunks_with_llm([chunk],stats=stats),[])
            model.assert_not_called()
        self.assertEqual({key: stats[key] for key in ('attempted_count','succeeded_count','failed_count')},
                         {'attempted_count':0,'succeeded_count':0,'failed_count':0})

    def test_no_candidates_do_not_call_model(self):
        stats={}
        settings=SimpleNamespace(PREPROCESS_LLM_ENABLED=True,CHUNK_LLM_NORMALIZATION_ENABLED=True)
        with patch('app.rag.normalizers.llm_normalizer.get_settings',return_value=settings), \
             patch('app.rag.normalizers.llm_normalizer.select_llm_normalization_candidates',return_value=LlmNormalizationSelection([],0,0,0)), \
             patch.object(ChunkTextNormalizer,'normalize') as model:
            self.assertEqual(normalize_chunks_with_llm([],stats=stats),[])
            model.assert_not_called()
        self.assertEqual(stats['attempted_count'],0)
