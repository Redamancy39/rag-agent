import json
import os
import site
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from typing import Any

from app.core.config import get_settings
from app.rag.schemas import LoadedDocumentPart

_DLL_DIRECTORY_HANDLES: list[Any] = []
OCR_WORKER_JSON_MARKER = "__RAG_OCR_JSON_START__"


@dataclass(slots=True)
class OcrLine:
    text: str
    score: float | None = None
    bbox: tuple[float, float, float, float] | None = None


class PaddleOcrEngine:
    def __init__(self) -> None:
        settings = get_settings()
        self.use_textline_orientation = settings.PADDLEOCR_USE_TEXTLINE_ORIENTATION
        self.use_subprocess = _should_use_subprocess(settings)
        self.ocr = None
        if not self.use_subprocess:
            _prepare_windows_paddle_dll_dirs()
            _preload_paddle()
            self.ocr = _get_paddleocr_instance(
                detection_model_dir=_as_str(settings.OCR_DETECTION_MODEL_DIR),
                recognition_model_dir=_as_str(settings.OCR_RECOGNITION_MODEL_DIR),
                textline_orientation_model_dir=_as_str(
                    settings.OCR_TEXTLINE_ORIENTATION_MODEL_DIR
                ),
                device=settings.PADDLEOCR_DEVICE,
                use_textline_orientation=settings.PADDLEOCR_USE_TEXTLINE_ORIENTATION,
            )

    def extract_pdf(
        self,
        path: str | Path,
        page_numbers: set[int] | None = None,
    ) -> list[LoadedDocumentPart]:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError(
                "OCR fallback for PDF requires PyMuPDF. Install: pip install -r requirements-rag.txt"
            ) from exc

        settings = get_settings()
        file_path = Path(path)
        if self.use_subprocess:
            return _extract_pdf_via_subprocess(
                file_path,
                settings.OCR_MAX_PAGES,
                page_numbers=page_numbers,
            )

        parts: list[LoadedDocumentPart] = []
        page_filter = set(page_numbers or set())
        with TemporaryDirectory(prefix="rag_ocr_") as temp_dir:
            with fitz.open(str(file_path)) as pdf:
                max_pages = settings.OCR_MAX_PAGES or len(pdf)
                for page_index, page in enumerate(pdf, start=1):
                    if page_index > max_pages:
                        break
                    if page_filter and page_index not in page_filter:
                        continue
                    image_path = Path(temp_dir) / f"page_{page_index}.png"
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    pixmap.save(str(image_path))
                    lines = self.extract_image_lines(image_path)
                    text = _render_ocr_text(lines)
                    if text.strip():
                        metadata = {
                            "source": file_path.name,
                            "page": page_index,
                            "chunk_type": "ocr_page_text",
                            "extraction_method": "paddleocr",
                        }
                        metadata.update(_ocr_metadata(lines))
                        parts.append(
                            LoadedDocumentPart(
                                text=text,
                                metadata=metadata,
                            )
                        )
        return parts

    def extract_image(self, path: str | Path) -> str:
        return _render_ocr_text(self.extract_image_lines(path))

    def extract_image_lines(self, path: str | Path) -> list[OcrLine]:
        if self.ocr is None:
            raise RuntimeError("In-process PaddleOCR is not initialized")
        predictor = getattr(self.ocr, "predict", None)
        if callable(predictor):
            result = predictor(str(path))
        else:
            result = self.ocr.ocr(str(path), cls=self.use_textline_orientation)
        lines = _collect_ocr_lines(result)
        if lines:
            return lines
        return [OcrLine(text=text) for text in _collect_texts(result)]


@lru_cache(maxsize=1)
def _get_paddleocr_instance(
    *,
    detection_model_dir: str | None,
    recognition_model_dir: str | None,
    textline_orientation_model_dir: str | None,
    device: str,
    use_textline_orientation: bool,
) -> Any:
    _prepare_windows_paddle_dll_dirs()
    _preload_paddle()
    try:
        PaddleOCR = _import_paddleocr_without_torch_probe()
    except ImportError as exc:
        raise RuntimeError(
            "OCR fallback requires paddleocr. Install optional OCR dependencies first."
        ) from exc

    normalized_device = (device or "cpu").strip().lower()
    v3_kwargs = {
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "device": normalized_device,
        "enable_mkldnn": normalized_device == "cpu",
        "text_detection_model_name": _path_name(detection_model_dir),
        "text_detection_model_dir": detection_model_dir,
        "text_recognition_model_name": _path_name(recognition_model_dir),
        "text_recognition_model_dir": recognition_model_dir,
        "textline_orientation_model_name": _path_name(textline_orientation_model_dir),
        "textline_orientation_model_dir": textline_orientation_model_dir,
        "use_textline_orientation": use_textline_orientation,
    }
    v3_kwargs = {key: value for key, value in v3_kwargs.items() if value not in {None, ""}}
    try:
        return PaddleOCR(**v3_kwargs)
    except TypeError:
        v2_kwargs = {
            "det_model_dir": detection_model_dir,
            "rec_model_dir": recognition_model_dir,
            "cls_model_dir": textline_orientation_model_dir,
            "use_gpu": normalized_device.startswith("gpu"),
            "use_angle_cls": use_textline_orientation,
            "lang": "ch",
        }
        v2_kwargs = {key: value for key, value in v2_kwargs.items() if value not in {None, ""}}
        return PaddleOCR(**v2_kwargs)


def _as_str(value: Any) -> str | None:
    return str(value) if value else None


def _path_name(value: Any) -> str | None:
    return Path(value).name if value else None


def _collect_texts(value: Any) -> list[str]:
    texts: list[str] = []
    _walk_ocr_result(value, texts)
    return [text for text in texts if text]


def _collect_ocr_lines(value: Any) -> list[OcrLine]:
    lines: list[OcrLine] = []
    _walk_ocr_lines(value, lines)
    return [line for line in lines if line.text]


def _walk_ocr_lines(value: Any, lines: list[OcrLine]) -> None:
    if value is None:
        return
    if hasattr(value, "res"):
        _walk_ocr_lines(getattr(value, "res"), lines)
        return
    if isinstance(value, dict):
        extracted = _lines_from_mapping(value)
        if extracted:
            lines.extend(extracted)
            return
        for child in value.values():
            _walk_ocr_lines(child, lines)
        return
    if _is_v2_line(value):
        line = _line_from_v2(value)
        if line:
            lines.append(line)
        return
    if hasattr(value, "rec_texts"):
        extracted = _lines_from_object(value)
        if extracted:
            lines.extend(extracted)
            return
    if isinstance(value, (list, tuple)):
        for child in value:
            _walk_ocr_lines(child, lines)


def _walk_ocr_result(value: Any, texts: list[str]) -> None:
    if value is None:
        return
    if isinstance(value, dict):
        for key in ("rec_texts", "texts"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                texts.extend(_clean_text(item) for item in candidate if _clean_text(item))
        for child in value.values():
            _walk_ocr_result(child, texts)
        return
    if hasattr(value, "rec_texts"):
        candidate = getattr(value, "rec_texts")
        if isinstance(candidate, list):
            texts.extend(_clean_text(item) for item in candidate if _clean_text(item))
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and isinstance(value[1], (list, tuple)) and value[1]:
            text = _clean_text(value[1][0])
            if text:
                texts.append(text)
        for child in value:
            _walk_ocr_result(child, texts)


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _lines_from_mapping(value: dict[str, Any]) -> list[OcrLine]:
    texts = _first_list(value, ("rec_texts", "texts"))
    if not texts:
        return []
    scores = _first_list(value, ("rec_scores", "scores", "text_scores"))
    boxes = _first_list(
        value,
        (
            "rec_polys",
            "rec_boxes",
            "dt_polys",
            "dt_boxes",
            "boxes",
            "polys",
            "text_boxes",
        ),
    )
    return _lines_from_parallel_values(texts, scores, boxes)


def _lines_from_object(value: Any) -> list[OcrLine]:
    texts = _as_list(getattr(value, "rec_texts", None))
    if not texts:
        return []
    scores = _as_list(getattr(value, "rec_scores", None))
    boxes = None
    for attr in ("rec_polys", "rec_boxes", "dt_polys", "dt_boxes", "boxes", "polys"):
        boxes = _as_list(getattr(value, attr, None))
        if boxes:
            break
    return _lines_from_parallel_values(texts, scores, boxes)


def _lines_from_parallel_values(
    texts: list[Any],
    scores: list[Any] | None,
    boxes: list[Any] | None,
) -> list[OcrLine]:
    lines: list[OcrLine] = []
    for index, value in enumerate(texts):
        text = _clean_text(value)
        if not text:
            continue
        score = _as_float(scores[index]) if scores and index < len(scores) else None
        bbox = _bbox_from_any(boxes[index]) if boxes and index < len(boxes) else None
        lines.append(OcrLine(text=text, score=score, bbox=bbox))
    return lines


def _is_v2_line(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return False
    candidate = value[1]
    return (
        isinstance(candidate, (list, tuple))
        and len(candidate) >= 1
        and isinstance(candidate[0], str)
    )


def _line_from_v2(value: Any) -> OcrLine | None:
    candidate = value[1]
    text = _clean_text(candidate[0])
    if not text:
        return None
    score = _as_float(candidate[1]) if len(candidate) > 1 else None
    return OcrLine(text=text, score=score, bbox=_bbox_from_any(value[0]))


def _first_list(value: dict[str, Any], keys: tuple[str, ...]) -> list[Any] | None:
    for key in keys:
        items = _as_list(value.get(key))
        if items:
            return items
    return None


def _as_list(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bbox_from_any(value: Any) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, dict):
        for keys in (("x1", "y1", "x2", "y2"), ("left", "top", "right", "bottom")):
            if all(key in value for key in keys):
                return tuple(float(value[key]) for key in keys)  # type: ignore[return-value]
        return None
    if not isinstance(value, (list, tuple)):
        return None
    if len(value) == 4 and all(isinstance(item, (int, float)) for item in value):
        x1, y1, x2, y2 = (float(item) for item in value)
        return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    points: list[tuple[float, float]] = []
    for point in value:
        if hasattr(point, "tolist"):
            point = point.tolist()
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            try:
                points.append((float(point[0]), float(point[1])))
            except (TypeError, ValueError):
                continue
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _render_ocr_text(lines: list[OcrLine]) -> str:
    positioned = [line for line in lines if line.bbox]
    if len(positioned) < max(4, len(lines) // 2):
        return "\n".join(line.text for line in lines)

    rows = _group_lines_into_rows(positioned)
    multi_cell_rows = sum(1 for row in rows if len(row) > 1)
    separator = " | " if multi_cell_rows >= 2 else " "
    rendered_rows = []
    for row in rows:
        row.sort(key=lambda line: line.bbox[0] if line.bbox else 0)
        rendered_rows.append(separator.join(line.text for line in row))
    return "\n".join(rendered_rows)


def _group_lines_into_rows(lines: list[OcrLine]) -> list[list[OcrLine]]:
    heights = [
        max(1.0, line.bbox[3] - line.bbox[1])
        for line in lines
        if line.bbox is not None
    ]
    tolerance = max(8.0, median(heights) * 0.65) if heights else 10.0
    rows: list[list[OcrLine]] = []
    row_centers: list[float] = []
    for line in sorted(lines, key=lambda item: _bbox_center_y(item.bbox)):
        center = _bbox_center_y(line.bbox)
        target_index = None
        for index, row_center in enumerate(row_centers):
            if abs(center - row_center) <= tolerance:
                target_index = index
                break
        if target_index is None:
            rows.append([line])
            row_centers.append(center)
            continue
        rows[target_index].append(line)
        row_centers[target_index] = (
            row_centers[target_index] * (len(rows[target_index]) - 1) + center
        ) / len(rows[target_index])
    return rows


def _bbox_center_y(bbox: tuple[float, float, float, float] | None) -> float:
    if bbox is None:
        return 0.0
    return (bbox[1] + bbox[3]) / 2


def _ocr_metadata(lines: list[OcrLine]) -> dict[str, Any]:
    scores = [line.score for line in lines if line.score is not None]
    avg_score = sum(scores) / len(scores) if scores else None
    min_score = min(scores) if scores else None
    low_confidence_count = sum(1 for score in scores if score < 0.8)
    preview = [
        {
            "text": line.text[:120],
            "score": round(line.score, 4) if line.score is not None else None,
            "bbox": [round(value, 2) for value in line.bbox] if line.bbox else None,
        }
        for line in lines[:80]
    ]
    return {
        "ocr_line_count": len(lines),
        "ocr_avg_score": round(avg_score, 4) if avg_score is not None else 0.0,
        "ocr_min_score": round(min_score, 4) if min_score is not None else 0.0,
        "ocr_low_confidence_count": low_confidence_count,
        "ocr_table_like": _ocr_lines_look_table_like(lines),
        "ocr_lines_json": json.dumps(preview, ensure_ascii=False),
    }


def _ocr_lines_look_table_like(lines: list[OcrLine]) -> bool:
    text = "\n".join(line.text for line in lines)
    keywords = ("表", "限量", "μg/kg", "mg/kg", "动物种类", "靶组织", "残留标志物")
    keyword_hits = sum(1 for keyword in keywords if keyword in text)
    positioned = [line for line in lines if line.bbox]
    if len(positioned) >= 4:
        rows = _group_lines_into_rows(positioned)
        multi_cell_rows = sum(1 for row in rows if len(row) > 1)
        if multi_cell_rows >= 3 and keyword_hits >= 1:
            return True
    return keyword_hits >= 2


def _prepare_windows_paddle_dll_dirs() -> None:
    if os.name != "nt":
        return
    candidate_roots = [Path(prefix) / "Lib" / "site-packages" for prefix in [sys.prefix]]
    candidate_roots.extend(Path(path) for path in site.getsitepackages())
    seen: set[Path] = set()
    for root in candidate_roots:
        nvidia_root = root / "nvidia"
        if not nvidia_root.exists():
            continue
        for bin_dir in nvidia_root.glob("*/bin"):
            resolved = bin_dir.resolve()
            if resolved in seen or not resolved.exists():
                continue
            seen.add(resolved)
            _add_windows_dll_dir(resolved)


def _add_windows_dll_dir(path: Path) -> None:
    path_text = str(path)
    if path_text not in os.environ.get("PATH", ""):
        os.environ["PATH"] = path_text + os.pathsep + os.environ.get("PATH", "")
    add_dll_directory = getattr(os, "add_dll_directory", None)
    if callable(add_dll_directory):
        try:
            _DLL_DIRECTORY_HANDLES.append(add_dll_directory(path_text))
        except OSError:
            return


def _preload_paddle() -> None:
    try:
        import paddle  # noqa: F401
    except ImportError:
        return


def _should_use_subprocess(settings: Any) -> bool:
    if os.environ.get("PADDLEOCR_FORCE_IN_PROCESS") == "1":
        return False
    device = str(getattr(settings, "PADDLEOCR_DEVICE", "cpu") or "cpu").lower()
    return bool(
        getattr(settings, "PADDLEOCR_USE_SUBPROCESS", True)
        and os.name == "nt"
        and device.startswith("gpu")
    )


def _extract_pdf_via_subprocess(
    path: Path,
    max_pages: int | None,
    *,
    page_numbers: set[int] | None = None,
) -> list[LoadedDocumentPart]:
    env = os.environ.copy()
    env["PADDLEOCR_FORCE_IN_PROCESS"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if max_pages is not None:
        env["OCR_MAX_PAGES"] = str(max_pages)
    if page_numbers:
        env["OCR_PAGE_NUMBERS"] = ",".join(str(page) for page in sorted(page_numbers))
    backend_dir = Path(__file__).resolve().parents[3]
    command = [
        sys.executable,
        "-m",
        "app.rag.ocr.paddleocr_worker",
        str(path),
    ]
    completed = subprocess.run(
        command,
        cwd=str(backend_dir),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=None,
        check=False,
    )
    if completed.returncode != 0:
        output = (completed.stderr or completed.stdout)[-4000:]
        raise RuntimeError(f"PaddleOCR subprocess failed: {output}")
    payload = _parse_worker_payload(completed.stdout)
    return [
        LoadedDocumentPart(
            text=str(item.get("text") or ""),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in payload
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]


def _parse_worker_payload(stdout: str) -> list[dict[str, Any]]:
    marker_index = stdout.rfind(OCR_WORKER_JSON_MARKER)
    if marker_index < 0:
        raise RuntimeError("PaddleOCR subprocess did not return OCR JSON payload")
    payload_text = stdout[marker_index + len(OCR_WORKER_JSON_MARKER) :].strip()
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("PaddleOCR subprocess returned invalid JSON") from exc
    return payload if isinstance(payload, list) else []


def _import_paddleocr_without_torch_probe() -> Any:
    import importlib.util

    original_find_spec = importlib.util.find_spec

    def find_spec_without_torch(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "torch" or name.startswith("torch."):
            return None
        return original_find_spec(name, *args, **kwargs)

    importlib.util.find_spec = find_spec_without_torch
    try:
        from paddleocr import PaddleOCR
    finally:
        importlib.util.find_spec = original_find_spec
    return PaddleOCR
