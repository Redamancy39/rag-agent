import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, ChatLog, User
from app.schemas.chat import (
    AnswerSections,
    ChatResponse,
    Citation,
    CitationValidationRead,
    EvidenceDecisionRead,
    QueryPlanRead,
    RetrievalScopeRead,
    RetrievalTraceHit,
    RetrievalTraceStep,
)
from app.services.log_service import chat_log_to_read, create_chat_log
from app.services.rag_service import _mark_selected_trace_hits


class ChatLogTraceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(
            username="trace-user",
            email=None,
            hashed_password="test",
            is_active=True,
            is_admin=False,
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_full_trace_snapshot_round_trip(self) -> None:
        response = _sample_response()
        _mark_selected_trace_hits(response)

        chat_log = create_chat_log(
            self.db,
            user=self.user,
            question="测试问题",
            response=response,
        )

        self.assertIsNotNone(chat_log)
        restored = chat_log_to_read(chat_log)
        self.assertIsNotNone(restored.response)
        self.assertEqual(restored.response.retrieval_scope.allowed_document_ids, [7])
        self.assertEqual(restored.response.query_plan.normalized_question, "测试问题")
        self.assertEqual(restored.response.retrieval_trace[0].duration_ms, 18)
        hit = restored.response.retrieval_trace[0].top_hits[0]
        self.assertTrue(hit.selected_for_answer)
        self.assertEqual(hit.citation_id, 1)
        self.assertEqual(hit.vector_score, 0.82)
        self.assertEqual(hit.bm25_score, 0.61)

    def test_legacy_log_is_returned_with_default_trace(self) -> None:
        legacy = ChatLog(
            user_id=self.user.id,
            question="旧问题",
            answer="旧答案",
            citations_json="[]",
        )
        self.db.add(legacy)
        self.db.commit()
        self.db.refresh(legacy)

        restored = chat_log_to_read(legacy)

        self.assertEqual(restored.answer, "旧答案")
        self.assertIsNotNone(restored.response)
        self.assertEqual(restored.response.retrieval_trace, [])
        self.assertEqual(restored.response.log_id, legacy.id)


def _sample_response() -> ChatResponse:
    citation = Citation(
        citation_id=1,
        document_id=7,
        filename="sample.pdf",
        chunk_id="doc:7:chunk:3",
        page=2,
        score=0.91,
        text="测试证据",
    )
    trace_hit = RetrievalTraceHit(
        rank=1,
        score=0.91,
        vector_score=0.82,
        keyword_score=0.44,
        bm25_score=0.61,
        rerank_score=0.91,
        filename="sample.pdf",
        page=2,
        chunk_id="doc:7:chunk:3",
        retrieval_source="hybrid",
        matched_terms=["测试"],
        text_preview="测试证据",
    )
    return ChatResponse(
        answer="结论为测试结果[1]",
        sections=AnswerSections(
            classification="证据匹配",
            conclusion="结论为测试结果[1]",
            basis="测试证据[1]",
            citation="[1]",
        ),
        citations=[citation],
        retrieval_trace=[
            RetrievalTraceStep(
                query_index=0,
                query="测试问题",
                source="reranked_with_preserved_recall",
                hit_count=1,
                duration_ms=18,
                top_hits=[trace_hit],
            )
        ],
        query_plan=QueryPlanRead(
            original_question="测试问题",
            normalized_question="测试问题",
            needs_rewrite=False,
            question_type="fact",
            source="rule",
            reason="无需改写",
        ),
        evidence_decision=EvidenceDecisionRead(
            sufficient=True,
            source="rule",
            reason="证据充分",
            confidence=0.95,
        ),
        citation_validation=CitationValidationRead(
            valid=True,
            cited_indices=[1],
        ),
        retrieval_scope=RetrievalScopeRead(
            requested_document_ids=[7],
            allowed_document_ids=[7],
            top_k=5,
        ),
    )


if __name__ == "__main__":
    unittest.main()
