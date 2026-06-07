import unittest

from app.agent.query_agent import QueryPlan
from app.rag.retriever import (
    _merge_decomposed_hits,
    _retrieval_queries_from_plan,
)


class QueryDecompositionTests(unittest.TestCase):
    def test_simple_lookup_uses_one_query(self) -> None:
        plan = QueryPlan(
            original_question="What is the limit?",
            normalized_question="What is the limit?",
            needs_rewrite=True,
            question_type="single_lookup",
            entities=["pork"],
            metrics=["TVBN", "TVB-N", "volatile basic nitrogen", "limit"],
            rewritten_queries=["What is the limit?", "limit"],
        )

        queries = _retrieval_queries_from_plan(
            plan,
            enabled=True,
            max_queries=3,
        )

        self.assertEqual(queries, [("What is the limit?", "normalized")])

    def test_cross_document_question_is_bounded(self) -> None:
        plan = QueryPlan(
            original_question="Compare standard A and B.",
            normalized_question="Compare standard A and B.",
            needs_rewrite=True,
            question_type="cross_document",
            standard_refs=["A", "B"],
            sub_questions=[
                "What does standard A require?",
                "What does standard B require?",
                "How do A and B relate?",
            ],
            rewritten_queries=[
                "Compare standard A and B.",
                "A requirement",
                "B requirement",
            ],
        )

        queries = _retrieval_queries_from_plan(
            plan,
            enabled=True,
            max_queries=3,
        )

        self.assertEqual(len(queries), 3)
        self.assertEqual(queries[0][1], "normalized")
        self.assertEqual(queries[1][1], "decomposed")
        self.assertEqual(queries[2][1], "decomposed")

    def test_merge_keeps_best_score_and_query_provenance(self) -> None:
        hits = [
            {
                "id": "chunk-1",
                "score": 0.71,
                "retrieval_query": "primary",
                "retrieval_query_source": "normalized",
                "retrieval_sources": ["vector"],
                "matched_terms": ["a"],
            },
            {
                "id": "chunk-1",
                "score": 0.83,
                "retrieval_query": "sub query",
                "retrieval_query_source": "decomposed",
                "retrieval_sources": ["bm25"],
                "matched_terms": ["b"],
            },
        ]

        merged = _merge_decomposed_hits(hits)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["score"], 0.83)
        self.assertEqual(
            merged[0]["retrieval_queries"],
            ["primary", "sub query"],
        )
        self.assertEqual(
            merged[0]["retrieval_query_sources"],
            ["normalized", "decomposed"],
        )
        self.assertEqual(merged[0]["retrieval_sources"], ["vector", "bm25"])
        self.assertEqual(merged[0]["matched_terms"], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
