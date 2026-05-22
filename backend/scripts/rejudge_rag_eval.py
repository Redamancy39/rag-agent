import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.evaluation import RagEvalCase  # noqa: E402
from app.services.evaluation_service import (  # noqa: E402
    _actual_found,
    _case_passed,
    _missing_keywords,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rejudge an existing RAG eval result without calling the LLM.",
    )
    parser.add_argument("--testset", required=True, help="Path to the JSON testset.")
    parser.add_argument("--result", required=True, help="Path to an existing eval result JSON.")
    parser.add_argument(
        "--output",
        default="",
        help="Optional output JSON path. Defaults to overwriting neither file and only prints a summary.",
    )
    args = parser.parse_args()

    testset = json.loads(Path(args.testset).read_text(encoding="utf-8"))
    result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    cases = {item["id"]: RagEvalCase.model_validate(item) for item in testset["cases"]}

    changed: list[dict] = []
    passed_count = 0
    for row in result.get("results", []):
        case = cases.get(row.get("id"))
        if not case:
            continue
        response = row.get("response") or {}
        sections = response.get("sections") or {}
        answer = response.get("answer") or _section_text(sections)
        actual_found = _actual_found(answer)
        answer_text = _section_text(sections)
        citation_text = _citation_text(sections, response.get("evidence_rows") or [])
        missing_answer = _missing_keywords(answer_text, case.expected_answer_keywords)
        missing_citation = _missing_keywords(citation_text, case.expected_citation_keywords)
        passed = _case_passed(
            case,
            actual_found=actual_found,
            missing_answer_keywords=missing_answer,
            missing_citation_keywords=missing_citation,
        )
        if passed != row.get("passed"):
            changed.append({"id": row.get("id"), "old_passed": row.get("passed"), "new_passed": passed})
        row["passed"] = passed
        row["actual_found"] = actual_found
        row["missing_answer_keywords"] = missing_answer
        row["missing_citation_keywords"] = missing_citation
        passed_count += int(passed)

    total = len(result.get("results", []))
    result["passed"] = passed_count
    result["failed"] = total - passed_count
    result["pass_rate"] = round(passed_count / total, 4) if total else 0.0
    result["rejudge_changed"] = changed

    print(f"Rejudged eval: {passed_count}/{total} passed ({result['pass_rate']:.2%}).")
    if changed:
        print("Changed cases:", ", ".join(item["id"] for item in changed))
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Result saved to: {output_path}")


def _section_text(sections: dict) -> str:
    return "\n".join(str(sections.get(key) or "") for key in ("classification", "conclusion", "basis", "citation"))


def _citation_text(sections: dict, evidence_rows: list[dict]) -> str:
    return "\n".join(
        [
            str(sections.get("citation") or ""),
            *[
                f"{row.get('filename', '')} {row.get('page') or ''} "
                f"{row.get('table') or ''} {row.get('keywords') or ''}"
                for row in evidence_rows
            ],
        ]
    )


if __name__ == "__main__":
    main()
