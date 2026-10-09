import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Base, Document, User, ChatJob
from app.rag.retrieval_options import RetrievalOptions, resolve_retrieval_options
from app.rag.retriever import PermissionAwareRetriever
from app.schemas.chat import ChatRequest, ChatResponse, Citation, RetrievalUsageRead, RetrievalScopeRead
from app.services.chat_job_service import create_chat_job
from app.services.log_service import chat_log_to_read, create_chat_log
from app.services.rag_service import RagService, _prepare_context, _select_context


def settings():
    return Settings(_env_file=None, OPENAI_API_KEY='', RERANKER_ENABLED=True, RERANKER_MODEL_NAME='synthetic',
                    QUERY_AGENT_LLM_ENABLED=False, QUERY_AGENT_EVIDENCE_LLM_ENABLED=False)


def citation(text, name='synthetic.txt'):
    return Citation(document_id=1, filename=name, text=text, score=.9, chunk_type='text')


class RetrievalSettingsTests(unittest.TestCase):
    def test_request_limits_and_input_cannot_override_window_reservation(self):
        for value in (4,41):
            with self.assertRaises(ValidationError): ChatRequest(question='synthetic', top_k=value)
        with self.assertRaises(ValidationError): ChatRequest(question='synthetic', context_max_chars=64001)
        options=resolve_retrieval_options(ChatRequest(question='synthetic', top_k=40, output_reserve_ratio=0),settings())
        self.assertEqual(options.output_reserve_ratio,.30)
        self.assertEqual(options.candidate_top_k,80)
        self.assertEqual(options.context_max_chars,48000)

    def test_manual_candidate_is_at_least_top_k_and_snapshot_is_immutable(self):
        options=resolve_retrieval_options(RetrievalOptions(top_k=40,candidate_top_k=16,context_auto=False,context_max_chars=64000),settings())
        self.assertEqual(options.candidate_top_k,40); self.assertEqual(options.context_max_chars,64000)
        with self.assertRaises(ValidationError): options.top_k=5

    def test_oversized_first_block_does_not_hide_later_complete_evidence(self):
        a,b=citation('大'*10000,'large.txt'),citation('small complete evidence','small.txt')
        context,selected=_select_context([a,b],8000)
        self.assertEqual(selected,[b]); self.assertIn('[1]',context); self.assertNotIn('large.txt',context)
        self.assertLessEqual(len(context),8000)

    def test_context_counts_separators_and_never_truncates_a_source(self):
        source=citation('complete source')
        full,_=_select_context([source],1000)
        context,chosen=_select_context([source,source],len(full)*2+1)
        self.assertEqual(len(chosen),1); self.assertEqual(context,full)

    def test_token_guard_drops_complete_blocks_and_includes_question_and_system(self):
        items=[citation('证据'*1500),citation('Another complete source')]
        context,prompt,chosen,bound=_prepare_context('synthetic question',items,max_chars=64000,input_token_limit=6000)
        self.assertLessEqual(bound,6000); self.assertEqual(len(chosen),1)
        self.assertIn('synthetic question',prompt); self.assertNotIn('证据',context)
        _,_,chosen,bound=_prepare_context('长'*5000,items,max_chars=64000,input_token_limit=1000)
        self.assertEqual(chosen,[]); self.assertGreater(bound,1000)

    def test_vector_lexical_candidates_use_request_budget_without_mutating_config(self):
        retriever=object.__new__(PermissionAwareRetriever); retriever.settings=settings()
        retriever.embedding_model=Mock(); retriever.vector_store=Mock()
        retriever.vector_store.search_by_embedding.return_value=[]
        retriever.keyword_retriever=Mock(); retriever.keyword_retriever.retrieve.return_value=[]
        retriever.bm25_retriever=Mock(); retriever.bm25_retriever.retrieve.return_value=[]
        retriever._retrieve_single_query('synthetic',allowed_document_ids=[1],top_k=80,lexical_chunks=[],candidate_top_k=80)
        for client in (retriever.vector_store.search_by_embedding,retriever.keyword_retriever.retrieve,retriever.bm25_retriever.retrieve):
            self.assertEqual(client.call_args.kwargs['top_k'],80)
        self.assertEqual(retriever.settings.RERANKER_CANDIDATE_TOP_K,32)

    def test_no_rerank_does_not_load_model_and_query_merge_can_exceed_old_48_cap(self):
        retriever=object.__new__(PermissionAwareRetriever); retriever.settings=settings()
        retriever._load_lexical_chunks=Mock(return_value=[])
        retriever._retrieve_single_query=Mock(return_value=[{'id':str(i),'score':.9,'text':'synthetic'} for i in range(80)])
        options=resolve_retrieval_options(RetrievalOptions(top_k=40,rerank_enabled=False),retriever.settings)
        with patch('app.rag.retriever.get_optional_reranker') as load:
            hits,trace=retriever._retrieve_with_optional_trace('synthetic',allowed_document_ids=[1],top_k=40,
                query_plan=None,retrieval_queries=[('one','normalized'),('two','sub_question')],retrieval_options=options)
        load.assert_not_called(); self.assertEqual(len(hits),40)
        merged=next(step for step in trace if step['source']=='decomposition_merged')
        self.assertEqual(merged['hit_count'],80)

    def test_task_snapshot_and_history_keep_params_after_other_settings_change(self):
        engine=create_engine('sqlite://'); Base.metadata.create_all(engine)
        with Session(engine) as db:
            user=User(username='synthetic',hashed_password='test',is_admin=False); db.add(user); db.commit()
            original=resolve_retrieval_options(RetrievalOptions(top_k=40),settings())
            job=create_chat_job(db,user=user,question='synthetic',document_ids=[1],top_k=40,retrieval_options=original)
            other=resolve_retrieval_options(RetrievalOptions(top_k=5),settings())
            self.assertEqual(json.loads(job.retrieval_options_json)['top_k'],40)
            self.assertEqual(other.top_k,5)
            log=create_chat_log(db,user=user,question='synthetic',response=ChatResponse(answer='synthetic',
                retrieval_scope=RetrievalScopeRead(top_k=40,options=original,usage=RetrievalUsageRead(context_chars=40000))))
            restored=chat_log_to_read(log).response
            self.assertEqual(restored.retrieval_scope.options.top_k,40)
            self.assertEqual(restored.retrieval_scope.options.context_max_chars,48000)
            self.assertEqual(restored.retrieval_scope.usage.context_chars,40000)
        engine.dispose()

    def test_permission_filter_blocks_unowned_doc_even_with_large_top_k(self):
        engine=create_engine('sqlite://'); Base.metadata.create_all(engine)
        with Session(engine) as db,patch('app.services.rag_service.get_settings',return_value=settings()):
            a=User(username='a',hashed_password='test'); b=User(username='b',hashed_password='test')
            db.add_all([a,b]);db.flush()
            db.add(Document(filename='private.txt',storage_path='synthetic',file_type='txt',owner_id=b.id,status='indexed'))
            db.commit()
            with patch('app.services.rag_service.PermissionAwareRetriever') as retrieve:
                response=RagService().answer(db,user=a,question='synthetic',requested_document_ids=[1],top_k=40)
            retrieve.assert_not_called(); self.assertEqual(response.retrieval_scope.allowed_document_ids,[])
        engine.dispose()

    def test_generation_uses_only_prepared_sources_and_records_actual_usage(self):
        config=settings(); config.OPENAI_API_KEY='synthetic-no-network'
        with patch('app.services.rag_service.get_settings',return_value=config),patch('app.services.rag_service.OpenAICompatibleLLM') as factory:
            client=factory.return_value
            client.last_usage=SimpleNamespace(prompt_tokens=77,completion_tokens=19,completion_tokens_details=SimpleNamespace(reasoning_tokens=4))
            client.last_finish_reason='stop'
            client.complete_json.return_value={'found':True,'classification':'匹配','conclusion':'synthetic [1]', 'basis':'source [1]', 'evidence_indices':[1]}
            usage=RetrievalUsageRead()
            response=RagService()._generate_answer('synthetic',[citation('source')],generation_prompt='only prepared source',usage=usage,max_output_tokens=4096)
            self.assertEqual(client.complete_json.call_args.args[1],'only prepared source')
            factory.assert_called_once_with(max_output_tokens=4096)
            self.assertEqual(usage.input_tokens,77);self.assertEqual(usage.output_tokens,19);self.assertEqual(usage.reasoning_tokens,4)
            self.assertTrue(usage.generation_requested);self.assertTrue(response.citation_validation.valid)

    def test_full_answer_budget_omission_only_exposes_selected_citation(self):
        from app.agent.evidence_judge import EvidenceDecision
        engine=create_engine('sqlite://'); Base.metadata.create_all(engine)
        config=settings();config.OPENAI_API_KEY='synthetic-no-network'
        with Session(engine) as db,patch('app.services.rag_service.get_settings',return_value=config):
            user=User(username='synthetic',hashed_password='test');db.add(user);db.flush()
            doc=Document(filename='synthetic.txt',storage_path='synthetic',file_type='txt',owner_id=user.id,status='indexed');db.add(doc);db.commit()
            hits=[{'id':'large','score':.9,'text':'large complete source '*1000,'metadata':{'document_id':doc.id,'filename':'large.txt','chunk_type':'text'}},
                  {'id':'small','score':.9,'text':'Small complete source with synthetic evidence sufficient for a test answer.','metadata':{'document_id':doc.id,'filename':'small.txt','chunk_type':'text'}}]
            with patch('app.services.rag_service.PermissionAwareRetriever') as retrieval,patch('app.services.rag_service.EvidenceJudge') as judge,patch('app.services.rag_service.OpenAICompatibleLLM') as llm:
                retrieval.return_value.retrieve_with_plan.return_value=(hits,[],None)
                judge.return_value.judge.return_value=EvidenceDecision(sufficient=True,reason='synthetic',confidence=1)
                llm.return_value.complete_json.return_value={'found':True,'classification':'匹配','conclusion':'answer [1]','basis':'source [1]','evidence_indices':[1]}
                llm.return_value.last_usage=None;llm.return_value.last_finish_reason='stop'
                response=RagService().answer(db,user=user,question='synthetic',retrieval_options=resolve_retrieval_options(RetrievalOptions(context_auto=False,context_max_chars=8000),config))
                prompt=llm.return_value.complete_json.call_args.args[1]
                self.assertIn('small.txt',prompt);self.assertNotIn('large.txt',prompt)
                self.assertEqual(judge.return_value.judge.call_args.kwargs['citations'][0].chunk_id,'small')
                self.assertEqual(response.citations[0].chunk_id,'small')
                self.assertTrue(response.citation_validation.valid)
                self.assertEqual(response.retrieval_scope.usage.omitted_count,1)
                self.assertEqual(response.retrieval_scope.usage.context_evidence_count,1)
                self.assertIsNone(response.retrieval_scope.usage.input_tokens)
        engine.dispose()

    def test_input_budget_cannot_fit_system_prompt_returns_without_api(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        config=settings();config.QA_MODEL_CONTEXT_TOKENS=1024
        with Session(engine) as db,patch('app.services.rag_service.get_settings',return_value=config):
            user=User(username='synthetic',hashed_password='test');db.add(user);db.flush()
            doc=Document(filename='synthetic.txt',storage_path='synthetic',file_type='txt',owner_id=user.id,status='indexed');db.add(doc);db.commit()
            with patch('app.services.rag_service.PermissionAwareRetriever') as retrieval,patch('app.services.rag_service.OpenAICompatibleLLM') as api:
                retrieval.return_value.retrieve_with_plan.return_value=([{'id':'one','score':.9,'text':'Complete synthetic source with enough readable characters for validation.','metadata':{'document_id':doc.id,'filename':'synthetic.txt'}}],[],None)
                response=RagService().answer(db,user=user,question='synthetic')
                api.assert_not_called()
                self.assertEqual(response.retrieval_scope.usage.context_evidence_count,0)
                self.assertFalse(response.retrieval_scope.usage.generation_requested)
                self.assertTrue(response.retrieval_scope.usage.budget_message)
        engine.dispose()


if __name__=='__main__': unittest.main()
