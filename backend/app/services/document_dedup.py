"""Exact-byte deduplication within the uploader's target collection."""
import hashlib
from pathlib import Path

from sqlalchemy import select

from app.models.document import Document


class DuplicateUpload(Exception):
    def __init__(self, document):
        self.document = document
        super().__init__('相同内容已存在，已跳过重复入库')


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def find_duplicate(db, *, owner_id, collection_id, size, digest):
    # Only inspect this uploader's documents: never disclose another account's files.
    candidates = db.scalars(select(Document).where(
        Document.owner_id == owner_id, Document.collection_id == collection_id,
        Document.file_size == size, Document.status != 'failed',
    ).order_by(Document.id))
    for document in candidates:
        source = Path(document.storage_path)
        try:
            if not source.is_file() or source.stat().st_size != size:
                continue
        except OSError:
            continue
        if not document.content_sha256:
            # Legacy documents are fingerprinted lazily; no OCR/LLM/indexing is run.
            try:
                document.content_sha256 = file_sha256(source)
            except OSError:
                continue
        if document.content_sha256 == digest:
            return document
    return None
