from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze failed RAG eval cases.")
    parser.add_argument("--input", required=True, help="Path to rag_eval_*.json")
    parser.add_argument("--output", default="", help="Optional markdown report path")
    args = parser.parse_args()

    input_path = Path(args.input)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    failures = [
        result
        for result in payload.get("results", [])
        if isinstance(result, dict) and not result.get("passed")
    ]
    summary = _summarize_failures(failures)
    report = _render_markdown(input_path, payload, summary)

    output_path = (
        Path(args.output)
        if args.output
        else input_path.with_name(f"{input_path.stem}_failure_analysis.md")
    )
    output_path = _write_report(output_path, report)
    print(f"Analyzed {len(failures)} failed cases.")
    print(f"Report saved to: {output_path}")


def _summarize_failures(failures: list[dict[str, Any]]) -> dict[str, Any]:
    reason_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    examples_by_reason: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for item in failures:
        reason = _classify_failure(item)
        reason_counts[reason] += 1
        for tag in item.get("tags") or []:
            tag_counts[str(tag)] += 1
        if len(examples_by_reason[reason]) < 8:
            examples_by_reason[reason].append(_compact_case(item))

    return {
        "reason_counts": dict(reason_counts.most_common()),
        "tag_counts": dict(tag_counts.most_common(30)),
        "examples_by_reason": dict(examples_by_reason),
    }


def _write_report(output_path: Path, report: str) -> Path:
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        return output_path
    except OSError:
        fallback_dir = BACKEND_ROOT / ".runtime_reports"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        fallback_path = fallback_dir / output_path.name
        fallback_path.write_text(report, encoding="utf-8")
        return fallback_path


def _classify_failure(item: dict[str, Any]) -> str:
    expected_found = bool(item.get("expected_found"))
    actual_found = bool(item.get("actual_found"))
    missing_answer = item.get("missing_answer_keywords") or []
    missing_citation = item.get("missing_citation_keywords") or []
    response = item.get("response") or {}
    evidence_rows = response.get("evidence_rows") or []
    citations = response.get("citations") or []
    trace = response.get("retrieval_trace") or []

    if expected_found and not actual_found:
        if _trace_has_no_hits(trace) or (not evidence_rows and not citations):
            return "retrieval_miss_or_permission_scope"
        return "llm_false_negative_or_evidence_rejected"
    if not expected_found and actual_found:
        return "false_positive_should_refuse"
    if missing_citation:
        if not evidence_rows and not citations:
            return "citation_missing_due_to_no_evidence"
        return "citation_mismatch_or_source_not_returned"
    if missing_answer:
        if not evidence_rows and not citations:
            return "answer_missing_due_to_no_evidence"
        if _all_top_hits_low_score(trace):
            return "weak_retrieval_low_score"
        return "answer_keyword_missing_or_eval_needs_review"
    return "unknown_failure"


def _trace_has_no_hits(trace: list[Any]) -> bool:
    if not trace:
        return False
    return all(int((step or {}).get("hit_count") or 0) == 0 for step in trace if isinstance(step, dict))


def _all_top_hits_low_score(trace: list[Any], threshold: float = 0.35) -> bool:
    scores: list[float] = []
    for step in trace:
        if not isinstance(step, dict):
            continue
        for hit in step.get("top_hits") or []:
            if not isinstance(hit, dict):
                continue
            score = hit.get("score")
            if isinstance(score, (int, float)):
                scores.append(float(score))
    return bool(scores) and max(scores) < threshold


def _compact_case(item: dict[str, Any]) -> dict[str, Any]:
    response = item.get("response") or {}
    sections = response.get("sections") or {}
    evidence_rows = response.get("evidence_rows") or []
    return {
        "id": item.get("id"),
        "question": item.get("question"),
        "expected_found": item.get("expected_found"),
        "actual_found": item.get("actual_found"),
        "missing_answer_keywords": item.get("missing_answer_keywords") or [],
        "missing_citation_keywords": item.get("missing_citation_keywords") or [],
        "classification": sections.get("classification"),
        "conclusion": sections.get("conclusion"),
        "top_evidence": [
            {
                "filename": row.get("filename"),
                "page": row.get("page"),
                "table": row.get("table"),
                "score": row.get("score"),
                "keywords": row.get("keywords"),
            }
            for row in evidence_rows[:3]
            if isinstance(row, dict)
        ],
    }


def _render_markdown(
    input_path: Path,
    payload: dict[str, Any],
    summary: dict[str, Any],
) -> str:
    lines = [
        "# RAG Eval Failure Analysis",
        "",
        f"- Source: `{input_path}`",
        f"- Name: {payload.get('name', '-')}",
        f"- Pass rate: {payload.get('pass_rate', 0):.2%}",
        f"- Failed: {payload.get('failed', 0)} / {payload.get('total', 0)}",
        "",
        "## Failure Reasons",
        "",
        "| Reason | Count |",
        "| --- | ---: |",
    ]
    for reason, count in summary["reason_counts"].items():
        lines.append(f"| {reason} | {count} |")

    lines.extend(["", "## Tag Distribution", "", "| Tag | Count |", "| --- | ---: |"])
    for tag, count in summary["tag_counts"].items():
        lines.append(f"| {tag} | {count} |")

    lines.extend(["", "## Examples", ""])
    for reason, examples in summary["examples_by_reason"].items():
        lines.extend([f"### {reason}", ""])
        for example in examples:
            lines.append(f"- `{example['id']}` {example['question']}")
            lines.append(f"  - missing_answer: {example['missing_answer_keywords']}")
            lines.append(f"  - missing_citation: {example['missing_citation_keywords']}")
            lines.append(f"  - conclusion: {example['conclusion']}")
            if example["top_evidence"]:
                top = example["top_evidence"][0]
                lines.append(
                    "  - top_evidence: "
                    f"{top.get('filename')} / p{top.get('page')} / "
                    f"{top.get('table')} / score={top.get('score')}"
                )
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
