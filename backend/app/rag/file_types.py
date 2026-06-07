from pathlib import Path

SUPPORTED_FILE_TYPES = {
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
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
