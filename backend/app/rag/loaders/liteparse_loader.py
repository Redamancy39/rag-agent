from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logger import get_logger
from app.rag.loaders.base import BaseLoader
from app.rag.schemas import DocumentBlock, SourceLocator

logger = get_logger(__name__)


class LiteParseUnavailableError(RuntimeError):
    pass


class LiteParseLoader(BaseLoader):
    """Parse documents through the local LiteParse CLI.

    LiteParse converts Office formats to PDF when LibreOffice is available,
    then emits layout-aware JSON. The adapter keeps page-level provenance and
    maps the result into the project's DocumentBlock representation.
    """

    def __init__(self, *, use_ocr: bool | None = None) -> None:
        self.settings = get_settings()
        self.use_ocr = (
            self.settings.LITEPARSE_OCR_ENABLED
            if use_ocr is None
            else bool(use_ocr)
        )

    def load(self, path: str | Path) -> list[DocumentBlock]:
        file_path = Path(path)
        if not self.settings.LITEPARSE_ENABLED:
            raise LiteParseUnavailableError(
                "LiteParse processing is disabled. Set LITEPARSE_ENABLED=true "
                "to parse legacy Office or image-heavy documents."
            )
        command = resolve_liteparse_command(self.settings.LITEPARSE_COMMAND)
        if command is None:
            raise LiteParseUnavailableError(
                "LiteParse is not installed or the 'lit' command is not on PATH. "
                "Install backend/requirements-rag.txt and LibreOffice for legacy "
                "Office formats."
            )

        with tempfile.TemporaryDirectory(prefix="rag-liteparse-") as temp_dir:
            output_path = Path(temp_dir) / "result.json"
            args = [
                command,
                "parse",
                str(file_path),
                "--format",
                "json",
                "-o",
                str(output_path),
                "--max-pages",
                str(max(1, self.settings.LITEPARSE_MAX_PAGES)),
                "--dpi",
                str(max(72, self.settings.LITEPARSE_DPI)),
                "--num-workers",
                str(max(1, self.settings.LITEPARSE_NUM_WORKERS)),
                "--quiet",
            ]
            if self.use_ocr:
                args.extend(
                    [
                        "--ocr-language",
                        self.settings.LITEPARSE_OCR_LANGUAGE,
                    ]
                )
            else:
                args.append("--no-ocr")

            logger.info(
                "Running LiteParse path=%s use_ocr=%s command=%s",
                file_path,
                self.use_ocr,
                command,
            )
            completed = self._run_command(args, command)
            ocr_fallback_reason = ""
            if completed.returncode != 0 and self.use_ocr:
                ocr_fallback_reason = (
                    completed.stderr or completed.stdout or ""
                ).strip()[:1000]
                logger.warning(
                    "LiteParse OCR failed; retrying without OCR path=%s error=%s",
                    file_path,
                    ocr_fallback_reason,
                )
                output_path.unlink(missing_ok=True)
                retry_args = _without_ocr_args(args)
                completed = self._run_command(retry_args, command)

            if completed.returncode != 0:
                error = (completed.stderr or completed.stdout or "").strip()
                if ocr_fallback_reason:
                    error = (
                        f"OCR attempt: {ocr_fallback_reason}; "
                        f"no-OCR retry: {error}"
                    )
                raise RuntimeError(
                    "LiteParse parsing failed. "
                    f"exit_code={completed.returncode}; error={error[:1500]}"
                )
            payload = _load_liteparse_payload(output_path, completed.stdout)
            if ocr_fallback_reason:
                payload["_adapter_ocr_requested"] = True
                payload["_adapter_ocr_fallback_reason"] = ocr_fallback_reason
            blocks = blocks_from_liteparse_payload(
                payload,
                source=file_path.name,
                document_format=file_path.suffix.lower().lstrip("."),
            )
            if (
                not blocks
                and not self.use_ocr
                and self.settings.LITEPARSE_OCR_ENABLED
            ):
                logger.info(
                    "LiteParse returned no native text; retrying with OCR path=%s",
                    file_path,
                )
                output_path.unlink(missing_ok=True)
                ocr_args = _with_ocr_args(
                    args,
                    self.settings.LITEPARSE_OCR_LANGUAGE,
                )
                completed = self._run_command(ocr_args, command)
                if completed.returncode != 0:
                    error = (completed.stderr or completed.stdout or "").strip()
                    raise RuntimeError(
                        "LiteParse OCR fallback failed. "
                        f"exit_code={completed.returncode}; error={error[:1500]}"
                    )
                payload = _load_liteparse_payload(output_path, completed.stdout)
                payload["_adapter_ocr_requested"] = True
                blocks = blocks_from_liteparse_payload(
                    payload,
                    source=file_path.name,
                    document_format=file_path.suffix.lower().lstrip("."),
                )
        if not blocks:
            raise RuntimeError("LiteParse returned no readable text")
        return blocks

    def _run_command(
        self,
        args: list[str],
        command: str,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                args,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(1.0, self.settings.LITEPARSE_TIMEOUT_SECONDS),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"LiteParse timed out after "
                f"{self.settings.LITEPARSE_TIMEOUT_SECONDS:g} seconds"
            ) from exc
        except OSError as exc:
            raise LiteParseUnavailableError(
                f"Failed to launch LiteParse command: {command}"
            ) from exc


def resolve_liteparse_command(configured_command: str | None = None) -> str | None:
    command = str(configured_command or "lit").strip()
    if not command:
        return None
    command_path = Path(command)
    if command_path.is_file():
        return str(command_path)
    return shutil.which(command)


def blocks_from_liteparse_payload(
    payload: dict[str, Any],
    *,
    source: str,
    document_format: str,
) -> list[DocumentBlock]:
    ocr_fallback_reason = _clean_text(
        payload.get("_adapter_ocr_fallback_reason")
    )
    pages = payload.get("pages")
    blocks: list[DocumentBlock] = []
    if isinstance(pages, list):
        for fallback_page, page in enumerate(pages, start=1):
            if not isinstance(page, dict):
                continue
            page_number = _page_number(page, fallback_page)
            items = _page_items(page)
            text = _page_text(page, items)
            if not text:
                continue
            ocr_items = [item for item in items if _item_is_ocr(item)]
            ocr_confidences = [
                confidence
                for item in ocr_items
                for confidence in [_safe_float(item.get("confidence"))]
                if confidence is not None
            ]
            ocr_used = _page_used_ocr(page, items, ocr_confidences)
            metadata: dict[str, Any] = {
                "parser_family": "liteparse",
                "layout_aware": True,
                "liteparse_item_count": len(items),
                "liteparse_has_bbox": any(_item_bbox(item) is not None for item in items),
                "liteparse_ocr_used": ocr_used,
            }
            if payload.get("_adapter_ocr_requested") is True:
                metadata["liteparse_ocr_requested"] = True
            if ocr_fallback_reason:
                metadata["liteparse_ocr_fallback_reason"] = (
                    ocr_fallback_reason[:500]
                )
            if ocr_confidences:
                metadata["ocr_avg_score"] = round(
                    sum(ocr_confidences) / len(ocr_confidences),
                    4,
                )
            blocks.append(
                DocumentBlock(
                    text=text,
                    metadata=metadata,
                    block_type=(
                        "liteparse_ocr_page_text"
                        if ocr_used
                        else "liteparse_page_text"
                    ),
                    source=source,
                    document_format=document_format,
                    extraction_method=(
                        "liteparse_ocr" if ocr_used else "liteparse_layout_text"
                    ),
                    locator=SourceLocator(page=page_number),
                )
            )

    if blocks:
        return blocks

    text = _clean_text(payload.get("text") or payload.get("content"))
    if not text:
        return []
    return [
        DocumentBlock(
            text=text,
            metadata={
                "parser_family": "liteparse",
                "layout_aware": False,
                "liteparse_ocr_used": bool(payload.get("ocr_used")),
                "liteparse_ocr_requested": bool(
                    payload.get("_adapter_ocr_requested")
                ),
                "liteparse_ocr_fallback_reason": ocr_fallback_reason[:500],
            },
            block_type="liteparse_document_text",
            source=source,
            document_format=document_format,
            extraction_method="liteparse_text",
        )
    ]


def _load_liteparse_payload(output_path: Path, stdout: str) -> dict[str, Any]:
    raw = ""
    if output_path.exists():
        raw = output_path.read_text(encoding="utf-8-sig", errors="replace")
    if not raw.strip():
        raw = stdout
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("LiteParse returned invalid JSON output") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("LiteParse JSON root must be an object")
    return payload


def _without_ocr_args(args: list[str]) -> list[str]:
    filtered: list[str] = []
    skip_next = False
    for item in args:
        if skip_next:
            skip_next = False
            continue
        if item == "--ocr-language":
            skip_next = True
            continue
        if item == "--no-ocr":
            continue
        filtered.append(item)
    filtered.append("--no-ocr")
    return filtered


def _with_ocr_args(args: list[str], language: str) -> list[str]:
    filtered = _without_ocr_args(args)
    filtered = [item for item in filtered if item != "--no-ocr"]
    filtered.extend(["--ocr-language", language])
    return filtered


def _page_items(page: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("text_items", "items", "blocks"):
        value = page.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _page_text(page: dict[str, Any], items: list[dict[str, Any]]) -> str:
    direct_text = _clean_text(page.get("text") or page.get("content"))
    if direct_text:
        return direct_text

    ordered_items = sorted(items, key=_item_order)
    texts = [
        _clean_text(item.get("text") or item.get("content"))
        for item in ordered_items
    ]
    return "\n".join(text for text in texts if text)


def _page_number(page: dict[str, Any], fallback: int) -> int:
    for key in ("page_number", "page", "number", "index"):
        value = page.get(key)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        return parsed + 1 if key == "index" and parsed == fallback - 1 else max(1, parsed)
    return fallback


def _page_used_ocr(
    page: dict[str, Any],
    items: list[dict[str, Any]],
    confidences: list[float],
) -> bool:
    if page.get("ocr_used") is True or page.get("is_ocr") is True:
        return True
    return bool(confidences or any(_item_is_ocr(item) for item in items))


def _item_is_ocr(item: dict[str, Any]) -> bool:
    if item.get("is_ocr") is True:
        return True
    method = str(item.get("source") or item.get("method") or "").lower()
    if "ocr" in method:
        return True
    # LiteParse native PDFium items include font metadata. OCR-only items
    # normally have confidence but no native font information.
    return (
        _safe_float(item.get("confidence")) is not None
        and not item.get("font_name")
        and item.get("font_size") is None
    )


def _item_order(item: dict[str, Any]) -> tuple[float, float]:
    bbox = _item_bbox(item)
    if bbox is None:
        return (float("inf"), float("inf"))
    return (bbox[1], bbox[0])


def _item_bbox(item: dict[str, Any]) -> tuple[float, float, float, float] | None:
    value = item.get("bbox") or item.get("box")
    if value is None and all(
        item.get(key) is not None
        for key in ("x", "y", "width", "height")
    ):
        try:
            x = float(item["x"])
            y = float(item["y"])
            return (
                x,
                y,
                x + float(item["width"]),
                y + float(item["height"]),
            )
        except (TypeError, ValueError):
            return None
    if isinstance(value, dict):
        value = [
            value.get("x1", value.get("left")),
            value.get("y1", value.get("top")),
            value.get("x2", value.get("right")),
            value.get("y2", value.get("bottom")),
        ]
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    try:
        return tuple(float(value[index]) for index in range(4))
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    lines = [" ".join(line.split()) for line in str(value).splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
