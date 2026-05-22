import json
import os
import sys

from app.rag.ocr.paddleocr_engine import OCR_WORKER_JSON_MARKER, PaddleOcrEngine


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m app.rag.ocr.paddleocr_worker <pdf_path>", file=sys.stderr)
        return 2
    os.environ["PADDLEOCR_FORCE_IN_PROCESS"] = "1"
    page_numbers = _parse_page_numbers(os.environ.get("OCR_PAGE_NUMBERS"))
    parts = PaddleOcrEngine().extract_pdf(sys.argv[1], page_numbers=page_numbers)
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


def _parse_page_numbers(value: str | None) -> set[int] | None:
    if not value:
        return None
    pages: set[int] = set()
    for item in value.split(","):
        try:
            page = int(item.strip())
        except ValueError:
            continue
        if page > 0:
            pages.add(page)
    return pages or None


if __name__ == "__main__":
    raise SystemExit(main())
