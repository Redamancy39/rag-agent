import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.evaluation import RagEvalRunRequest  # noqa: E402
from app.services.evaluation_service import run_rag_evaluation  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local RAG evaluation testset.")
    parser.add_argument(
        "--testset",
        default=str(PROJECT_ROOT / "data" / "eval" / "rag_testset.example.json"),
        help="Path to a JSON testset file.",
    )
    parser.add_argument(
        "--username",
        default="admin",
        help="Username whose document permissions are used for evaluation.",
    )
    parser.add_argument(
        "--password",
        default="",
        help="Accepted for CLI compatibility; local evaluation uses database permissions directly.",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Accepted for CLI compatibility; local evaluation does not call the HTTP API.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output JSON path. Defaults to data/eval/results/rag_eval_<timestamp>.json.",
    )
    args = parser.parse_args()

    testset_path = Path(args.testset)
    payload = json.loads(testset_path.read_text(encoding="utf-8"))
    request = RagEvalRunRequest.model_validate(payload)

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == args.username))
        if not user:
            raise SystemExit(f"User not found: {args.username}")
        result = run_rag_evaluation(db, user=user, request=request)

    output_path = Path(args.output) if args.output else _default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"RAG eval finished: {result.passed}/{result.total} passed "
        f"({result.pass_rate:.2%})."
    )
    print(f"Result saved to: {output_path}")


def _default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return PROJECT_ROOT / "data" / "eval" / "results" / f"rag_eval_{timestamp}.json"


if __name__ == "__main__":
    main()
