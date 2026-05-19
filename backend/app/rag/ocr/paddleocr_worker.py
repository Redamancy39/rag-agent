import json
import os
import sys

from app.rag.ocr.paddleocr_engine import OCR_WORKER_JSON_MARKER, PaddleOcrEngine


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m app.rag.ocr.paddleocr_worker <pdf_path>", file=sys.stderr)
        return 2
    os.environ["PADDLEOCR_FORCE_IN_PROCESS"] = "1"
    parts = PaddleOcrEngine().extract_pdf(sys.argv[1])
    payload = [
        {
            "text": part.text,
            "metadata": part.metadata,
        }
        for part in parts
    ]
    print(OCR_WORKER_JSON_MARKER)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
