import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import PROJECT_ROOT, get_settings


def configure_logging() -> None:
    settings = get_settings()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    handlers: list[logging.Handler] = [stream_handler]

    file_handler, file_warning = _build_file_handler(
        [settings.LOG_DIR, PROJECT_ROOT / "backend" / ".runtime_logs"],
        formatter,
    )
    if file_handler:
        handlers.insert(0, file_handler)
    elif file_warning:
        stream_handler.handle(
            logging.LogRecord(
                name=__name__,
                level=logging.WARNING,
                pathname=__file__,
                lineno=0,
                msg="File logging disabled: %s",
                args=(file_warning,),
                exc_info=None,
            )
        )

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        handlers=handlers,
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def _build_file_handler(
    candidate_dirs: list[Path],
    formatter: logging.Formatter,
) -> tuple[logging.Handler | None, str | None]:
    errors: list[str] = []
    for directory in candidate_dirs:
        log_file = directory / "backend.log"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                log_file,
                maxBytes=5 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            handler.setFormatter(formatter)
            return handler, None
        except OSError as exc:
            errors.append(f"{log_file}: {exc}")
    return None, " | ".join(errors) if errors else None
