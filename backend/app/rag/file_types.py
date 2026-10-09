from pathlib import Path
import re

SUPPORTED_FILE_TYPES = {
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
    ".pdf": "pdf",
    ".doc": "doc",
    ".docx": "docx",
    ".ppt": "ppt",
    ".pptx": "pptx",
    ".xls": "xls",
    ".xlsx": "xlsx",
}


def detect_file_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    try:
        return SUPPORTED_FILE_TYPES[suffix]
    except KeyError as exc:
        raise ValueError(f"Unsupported file type: {suffix or 'unknown'}") from exc


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    if not name:
        raise ValueError("Filename is empty")
    return "".join(char if char.isalnum() or char in "._- " else "_" for char in name)


def validate_upload_source(filename: str, relative_path: str | None = None) -> str | None:
    """Validate display provenance only; never use it as a filesystem destination."""
    basename = filename.replace('\\', '/').split('/')[-1]
    value = relative_path.replace('\\', '/') if relative_path is not None else basename
    parts = value.split('/')
    if (not value or len(value) > 4096 or value.startswith('/') or re.match(r'^[a-z]:', value, re.I)
        or any(not part or part in ('.', '..') or any(ord(c) < 32 for c in part) for part in parts)):
        raise ValueError('Invalid source relative path')
    if relative_path is not None and parts[-1] != basename:
        raise ValueError('Source relative path does not match the uploaded filename')
    for part in parts:
        lower = part.lower()
        if (lower in {'__macosx', 'thumbs.db', 'desktop.ini', '$recycle.bin', 'system volume information'}
            or lower.startswith('.')):
            raise ValueError('System metadata, hidden, or temporary files are not documents')
    if (basename.startswith('~$') or basename.endswith('~')
        or re.search(r'\.(tmp|temp|swp|swo|bak)$', basename, re.I)):
        raise ValueError('Temporary or backup files are not documents')
    if any(part.lower() == 'node_modules' for part in parts[:-1]):
        raise ValueError('Dependency directories are excluded from document import')
    return value if relative_path is not None else None
