import unittest

from app.schemas.chat import Citation
from app.services.rag_service import _parse_answer_payload


def _citations() -> list[Citation]:
    return [
        Citation(
            document_id=1,
            filename="A.pdf",
            page=3,
            table="T1",
            chunk_id="a",
            score=0.9,
            text="evidence A",
        ),
        Citation(
            document_id=2,
            filename="B.pdf",
            page=8,
            table="T2",
            chunk_id="b",
            score=0.8,
            text="evidence B",
        ),
    ]


class CitationValidationTests(unittest.TestCase):
    def test_remaps_selected_citations_to_contiguous_ids(self) -> None:
        response = _parse_answer_payload(
            {
                "found": True,
                "classification": "matched",
                "conclusion": "claim from source two[2].",
                "basis": "numeric basis[2], condition[1].",
                "evidence_indices": [1, 2],
                "evidence_keywords": [
                    {"index": 1, "keywords": "condition"},
                    {"index": 2, "keywords": "numeric"},
                ],
            },
            _citations(),
        )

        self.assertTrue(response.citation_validation.valid)
        self.assertEqual(
            [item.filename for item in response.citations],
            ["B.pdf", "A.pdf"],
        )
        self.assertEqual(
            [item.citation_id for item in response.citations],
            [1, 2],
        )
        self.assertIn("[1]", response.sections.conclusion)
        self.assertIn("[1]", response.sections.basis)
        self.assertIn("[2]", response.sections.basis)
        self.assertEqual(response.evidence_rows[0].keywords, "numeric")

    def test_rejects_unknown_citation_id(self) -> None:
        response = _parse_answer_payload(
            {
                "found": True,
                "classification": "matched",
                "conclusion": "invalid claim[9].",
                "basis": "invalid basis[9].",
                "evidence_indices": [9],
            },
            _citations(),
        )

        self.assertFalse(response.citation_validation.valid)
        self.assertEqual(response.citation_validation.invalid_indices, [9])
        self.assertEqual(response.sections.classification, "未找到")

    def test_rejects_uncited_basis(self) -> None:
        response = _parse_answer_payload(
            {
                "found": True,
                "classification": "matched",
                "conclusion": "valid claim[1].",
                "basis": "basis without a marker.",
                "evidence_indices": [1],
            },
            _citations(),
        )

        self.assertFalse(response.citation_validation.valid)
        self.assertEqual(
            response.citation_validation.uncited_sections,
            ["basis"],
        )
        self.assertEqual(response.sections.classification, "未找到")


if __name__ == "__main__":
    unittest.main()
