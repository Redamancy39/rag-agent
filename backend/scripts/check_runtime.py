from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import PROJECT_ROOT, get_settings


def main() -> int:
    settings = get_settings()
    checks = [
        ("python", sys.executable),
        ("ingestion_executor", settings.INGESTION_EXECUTOR),
        ("langgraph", _module_status("langgraph")),
        (
            "log_dir",
            _first_writable_dir_status(
                [settings.LOG_DIR, PROJECT_ROOT / "backend" / ".runtime_logs"]
            ),
        ),
        ("database", _sqlite_writable_status(settings.DATABASE_URL)),
        ("chroma_dir", _writable_dir_status(settings.CHROMA_DIR)),
    ]
    failed = False
    for name, value in checks:
        status = "OK"
        if isinstance(value, str) and value.startswith("FAIL"):
            status = "FAIL"
            failed = True
        print(f"[{status}] {name}: {value}")
    return 1 if failed else 0


def _module_status(module_name: str) -> str:
    if importlib.util.find_spec(module_name) is None:
        return "FAIL not installed"
    return "installed"


def _writable_dir_status(directory: Path) -> str:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        test_file = directory / ".runtime_write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
    except OSError as exc:
        return f"FAIL {exc}"
    return str(directory)


def _first_writable_dir_status(candidate_dirs: list[Path]) -> str:
    failures: list[str] = []
    for directory in candidate_dirs:
        status = _writable_dir_status(directory)
        if not status.startswith("FAIL"):
            if failures:
                return f"{directory} (fallback; primary failed: {failures[0]})"
            return status
        failures.append(status)
    return "FAIL " + " | ".join(failures)


def _sqlite_writable_status(database_url: str) -> str:
    if not database_url.startswith("sqlite:///"):
        return "not sqlite"
    db_path = Path(database_url.replace("sqlite:///", "", 1))
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(db_path)) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS runtime_check (id INTEGER)")
            connection.execute("INSERT INTO runtime_check (id) VALUES (1)")
            connection.execute("DELETE FROM runtime_check")
            connection.commit()
    except sqlite3.Error as exc:
        return f"FAIL {exc}"
    except OSError as exc:
        return f"FAIL {exc}"
    return str(db_path)


if __name__ == "__main__":
    raise SystemExit(main())
