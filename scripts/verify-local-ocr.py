"""Verify actual local OCR and scanned-PDF preprocessing with synthetic text."""
import importlib.metadata
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
os.chdir(ROOT / "backend")
os.environ["OPENAI_API_KEY"] = ""
os.environ["PREPROCESS_OCR_FALLBACK_ENABLED"] = "true"
os.environ["OCR_DETECTION_MODEL_DIR"] = str(ROOT / "data/models/ocr/paddleocr/PP-OCRv5_mobile_det")
os.environ["OCR_RECOGNITION_MODEL_DIR"] = str(ROOT / "data/models/ocr/paddleocr/PP-OCRv5_mobile_rec")
os.environ["OCR_TEXTLINE_ORIENTATION_MODEL_DIR"] = ""
os.environ["PADDLEOCR_DEVICE"] = "cpu"
os.environ["PADDLEOCR_USE_TEXTLINE_ORIENTATION"] = "false"
os.environ["PREPROCESS_LLM_ENABLED"] = "false"
os.environ["CHUNK_LLM_NORMALIZATION_ENABLED"] = "false"
os.environ["INGESTION_AGENT_LLM_ENABLED"] = "false"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

def main():
    from PIL import Image, ImageDraw, ImageFont
    import fitz
    import paddle
    from app.agent.ingestion_agent import probe_document, plan_from_probe
    from app.rag.preprocessor import DocumentPreprocessor
    from app.rag.ocr.paddleocr_engine import PaddleOcrEngine
    from app.rag.chunkers.rule_chunker import RuleChunker
    from app.rag.chunk_quality import annotate_chunk_quality

    folder = ROOT / "backend/.codex_smoke/ocr_local"
    folder.mkdir(parents=True, exist_ok=True)
    image_path = folder / "synthetic-scan.png"
    pdf_path = folder / "synthetic-scan.pdf"
    image = Image.new("RGB", (1600, 1000), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 48)
    lines = ["OCR 本地识别测试", "测试数据，不代表真实标准", "食品名称：测试样品", "检测数值：12.50 mg/kg", "批次编号：TEST-2026", "权限感知企业知识库", "English OCR TEST DOCUMENT"]
    for index, line in enumerate(lines):
        draw.text((80, 60 + index * 115), line, font=font, fill="black")
    image.save(image_path)
    doc = fitz.open()
    page = doc.new_page(width=800, height=500)
    page.insert_image(page.rect, filename=str(image_path))
    doc.save(str(pdf_path))
    doc.close()
    with fitz.open(pdf_path) as check:
        assert not check[0].get_text().strip(), "Fixture must have no text layer"
    probe = probe_document(pdf_path, "pdf")
    plan = plan_from_probe(probe)
    assert plan.use_ocr and plan.primary_reader == "paddleocr"
    parts = DocumentPreprocessor().preprocess(file_type="pdf", path=pdf_path, parts=[], force_ocr=plan.use_ocr, use_llm_preprocessing=False)
    text = "\n".join(part.text for part in parts)
    compact = "".join(text.split()).lower()
    required = ["本地识别测试", "测试样品", "12.50", "mg/kg", "test-2026"]
    matches = {item: item in compact for item in required}
    assert all(matches.values()), matches
    assert parts[0].locator.page == 1
    assert parts[0].extraction_method == "paddleocr"
    chunks = annotate_chunk_quality(RuleChunker().split_documents(parts))
    assert chunks
    result = {
        "packages": {name: importlib.metadata.version(name) for name in ("paddleocr", "paddlepaddle", "paddlex", "PyMuPDF", "numpy")},
        "device": "cpu", "paddle_cuda_build": paddle.is_compiled_with_cuda(),
        "fixture_has_no_text_layer": True, "probe_reader": plan.primary_reader,
        "matched_markers": matches, "ocr_blocks": len(parts), "chunk_count": len(chunks),
        "extraction_method": parts[0].extraction_method, "page": parts[0].locator.page,
        "recognized_text": text, "external_llm_called": False,
        "embedding_or_reranker_loaded": False,
        "image": str(image_path), "pdf": str(pdf_path),
    }
    report = ROOT / "backend/.runtime_reports/ocr-verification.json"
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
