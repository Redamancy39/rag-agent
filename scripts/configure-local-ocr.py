"""Write a separate OCR-only profile without opening credential configuration."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
profile = root / "backend/.env.ocr"
values = """PREPROCESS_OCR_FALLBACK_ENABLED=true
OCR_DETECTION_MODEL_DIR=../data/models/ocr/paddleocr/PP-OCRv5_mobile_det
OCR_RECOGNITION_MODEL_DIR=../data/models/ocr/paddleocr/PP-OCRv5_mobile_rec
OCR_TEXTLINE_ORIENTATION_MODEL_DIR=
PADDLEOCR_DEVICE=cpu
PADDLEOCR_USE_TEXTLINE_ORIENTATION=false
PADDLEOCR_USE_SUBPROCESS=true
"""
if profile.exists():
    raise SystemExit("Existing backend/.env.ocr preserved. Review its OCR settings before changing it.")
for model in ("PP-OCRv5_mobile_det", "PP-OCRv5_mobile_rec"):
    directory = root / "data/models/ocr/paddleocr" / model
    if not all((directory / name).is_file() for name in ("inference.json", "inference.pdiparams", "inference.yml")):
        raise SystemExit(f"Model files not ready: {model}")
with profile.open("x", encoding="utf-8") as stream:
    stream.write(values)
print("Created backend/.env.ocr. Existing backend/.env was not read or changed.")
