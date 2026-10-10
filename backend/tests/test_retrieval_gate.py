import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agent.retrieval_gate import RetrievalGateDecision, decide_knowledge_search
from app.core.config import Settings
from app.models import Base, Document, User
from app.services.rag_service import NOT_FOUND_ANSWER, RagService


def _settings(**overrides) -> Settings:
    values = dict(OPENAI_API_KEY='test-key', OPENAI_MODEL_NAME='test-model', AGENTIC_RAG_ENABLED=True)
    values.update(overrides)
    return Settings(_env_file=None, **values)


class RetrievalGateDecisionTests(unittest.TestCase):
    def test_invalid_payload_continues_search(self) -> None:
        with patch('app.agent.retrieval_gate.OpenAICompatibleLLM') as llm:
            llm.return_value.complete_json.return_value = {'search': 'yes'}
            decision = decide_knowledge_search('你好')
        self.assertTrue(decision.search)
        self.assertIn('无效', decision.reason)

    def test_failure_continues_search(self) -> None:
        with patch('app.agent.retrieval_gate.OpenAICompatibleLLM', side_effect=RuntimeError('offline')):
            decision = decide_knowledge_search('铅的限量是多少')
        self.assertTrue(decision.search)

    def test_direct_answer_with_citation_mark_continues_search(self) -> None:
        with patch('app.agent.retrieval_gate.OpenAICompatibleLLM') as llm:
            llm.return_value.complete_json.return_value = {
                'search': False,
                'reason': '闲聊',
                'answer': '限量是 0.05 mg/kg[1]',
            }
            decision = decide_knowledge_search('你好')
        self.assertTrue(decision.search)

    def test_direct_answer_is_accepted_without_document_facts(self) -> None:
        with patch('app.agent.retrieval_gate.OpenAICompatibleLLM') as llm:
            llm.return_value.complete_json.return_value = {
                'search': False,
                'reason': '问候不需要文档',
                'answer': '你好，我可以帮你查询已上传文档。',
            }
            decision = decide_knowledge_search('你好')
        self.assertFalse(decision.search)
        self.assertEqual(decision.answer, '你好，我可以帮你查询已上传文档。')


class RetrievalGateAnswerTests(unittest.TestCase):
    def test_disabled_gate_still_retrieves(self) -> None:
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        settings = _settings(AGENTIC_RAG_ENABLED=False, OPENAI_API_KEY='')
        try:
            with Session(engine) as db, patch('app.services.rag_service.get_settings', return_value=settings):
                user = User(username='synthetic', hashed_password='test')
                db.add(user)
                db.flush()
                doc = Document(filename='synthetic.txt', storage_path='synthetic', file_type='txt', owner_id=user.id, status='indexed')
                db.add(doc)
                db.commit()
                with patch('app.services.rag_service.decide_knowledge_search', side_effect=AssertionError('gate')), patch('app.services.rag_service.PermissionAwareRetriever') as retriever:
                    retriever.return_value.retrieve_with_plan.return_value = ([], [], None)
                    response = RagService().answer(db, user=user, question='铅的限量是多少')
        finally:
            engine.dispose()
        self.assertTrue(response.knowledge_search)
        self.assertEqual(response.sections.classification, '未找到')
        self.assertEqual(response.sections.conclusion, NOT_FOUND_ANSWER)
        retriever.return_value.retrieve_with_plan.assert_called_once()

    def test_skipped_search_does_not_read_documents(self) -> None:
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        settings = _settings()
        decision = RetrievalGateDecision(False, '问候不需要文档', '你好，我可以帮你查询已上传文档。')
        try:
            with Session(engine) as db, patch('app.services.rag_service.get_settings', return_value=settings):
                user = User(username='synthetic', hashed_password='test')
                db.add(user)
                db.commit()
                with patch('app.services.rag_service.decide_knowledge_search', return_value=decision), patch('app.services.rag_service.PermissionAwareRetriever', side_effect=AssertionError('retriever')), patch('app.services.rag_service.document_service.list_accessible_documents', side_effect=AssertionError('permissions')):
                    response = RagService().answer(db, user=user, question='你好')
        finally:
            engine.dispose()
        self.assertFalse(response.knowledge_search)
        self.assertEqual(response.sections.classification, '未查询知识库')
        self.assertEqual(response.sections.conclusion, decision.answer)
        self.assertEqual(response.citations, [])
        self.assertEqual(response.knowledge_search_reason, decision.reason)

    def test_search_decision_uses_existing_not_found_result(self) -> None:
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        settings = _settings()
        try:
            with Session(engine) as db, patch('app.services.rag_service.get_settings', return_value=settings):
                user = User(username='synthetic', hashed_password='test')
                db.add(user)
                db.flush()
                doc = Document(filename='synthetic.txt', storage_path='synthetic', file_type='txt', owner_id=user.id, status='indexed')
                db.add(doc)
                db.commit()
                decision = RetrievalGateDecision(True, '问题需要查询知识库')
                with patch('app.services.rag_service.decide_knowledge_search', return_value=decision), patch('app.services.rag_service.PermissionAwareRetriever') as retriever:
                    retriever.return_value.retrieve_with_plan.return_value = ([], [], None)
                    response = RagService().answer(db, user=user, question='这份手册里的保养步骤是什么')
        finally:
            engine.dispose()
        self.assertTrue(response.knowledge_search)
        self.assertEqual(response.sections.conclusion, NOT_FOUND_ANSWER)
        self.assertEqual(response.knowledge_search_reason, decision.reason)
        retriever.return_value.retrieve_with_plan.assert_called_once()

    def test_selected_documents_skip_the_gate(self) -> None:
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        settings = _settings()
        try:
            with Session(engine) as db, patch('app.services.rag_service.get_settings', return_value=settings):
                user = User(username='synthetic', hashed_password='test')
                db.add(user)
                db.flush()
                doc = Document(filename='synthetic.txt', storage_path='synthetic', file_type='txt', owner_id=user.id, status='indexed')
                db.add(doc)
                db.commit()
                with patch('app.services.rag_service.decide_knowledge_search', side_effect=AssertionError('gate')), patch('app.services.rag_service.PermissionAwareRetriever') as retriever:
                    retriever.return_value.retrieve_with_plan.return_value = ([], [], None)
                    response = RagService().answer(db, user=user, question='你好', requested_document_ids=[doc.id])
        finally:
            engine.dispose()
        self.assertTrue(response.knowledge_search)
        self.assertEqual(response.sections.conclusion, NOT_FOUND_ANSWER)

    def test_force_retrieval_skips_the_gate(self) -> None:
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        settings = _settings()
        try:
            with Session(engine) as db, patch('app.services.rag_service.get_settings', return_value=settings):
                user = User(username='synthetic', hashed_password='test')
                db.add(user)
                db.flush()
                doc = Document(filename='synthetic.txt', storage_path='synthetic', file_type='txt', owner_id=user.id, status='indexed')
                db.add(doc)
                db.commit()
                with patch('app.services.rag_service.decide_knowledge_search', side_effect=AssertionError('gate')), patch('app.services.rag_service.PermissionAwareRetriever') as retriever:
                    retriever.return_value.retrieve_with_plan.return_value = ([], [], None)
                    response = RagService().answer(db, user=user, question='你好', force_retrieval=True)
        finally:
            engine.dispose()
        self.assertTrue(response.knowledge_search)
        self.assertEqual(response.sections.conclusion, NOT_FOUND_ANSWER)


if __name__ == '__main__':
    unittest.main()
