import logging
from logging.handlers import RotatingFileHandler

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_file = settings.LOG_DIR / "backend.log"
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    handlers: list[logging.Handler] = [stream_handler]

    try:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        handlers.insert(0, file_handler)
    except OSError as exc:
        stream_handler.handle(
            logging.LogRecord(
                name=__name__,
                level=logging.WARNING,
                pathname=__file__,
                lineno=0,
                msg="File logging disabled: %s",
                args=(exc,),
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
