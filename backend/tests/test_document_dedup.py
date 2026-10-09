import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import BackgroundTasks, Response, UploadFile
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.api.documents import upload_document
from app.db.init_db import _ensure_sqlite_schema
from app.models import Base, Document, DocumentCollection, DocumentProcessingJob, User
from app.services.document_dedup import DuplicateUpload
from app.services.document_service import create_document_record


class DocumentDedupTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = create_engine('sqlite:///' + (self.root / 'test.db').as_posix())
        Base.metadata.create_all(self.engine)
        self.settings = SimpleNamespace(UPLOAD_DIR=self.root / 'uploads', ALLOWED_FILE_EXTENSIONS=['.txt'], MAX_UPLOAD_SIZE_MB=50)
        self.settings_patch = patch('app.services.document_service.get_settings', return_value=self.settings)
        self.settings_patch.start()
        self.db = Session(self.engine)
        self.owner = User(username='synthetic', hashed_password='test', is_active=True, is_admin=True)
        self.other = User(username='other', hashed_password='test', is_active=True, is_admin=False)
        self.db.add_all([self.owner, self.other]); self.db.commit()

    def tearDown(self):
        self.db.close(); self.settings_patch.stop(); self.engine.dispose(); self.temp.cleanup()

    def upload(self, name='a.txt', content=b'synthetic text', **kwargs):
        return asyncio.run(create_document_record(self.db, self.owner,
            UploadFile(filename=name, file=BytesIO(content)), **kwargs))

    def test_renamed_identical_bytes_skip_queued_document_and_remove_extra_file(self):
        first = self.upload()
        with self.assertRaises(DuplicateUpload) as caught:
            self.upload('different.txt')
        self.assertEqual(caught.exception.document.id, first.id)
        self.assertEqual(self.db.scalar(select(func.count(Document.id))), 1)
        self.assertEqual(self.db.scalar(select(func.count(DocumentProcessingJob.id))), 1)
        self.assertEqual(len(list(self.settings.UPLOAD_DIR.rglob('*.txt'))), 1)

    def test_same_name_and_size_with_different_content_is_not_duplicate(self):
        first = self.upload(content=b'abc')
        second = self.upload(content=b'xyz')
        self.assertNotEqual(first.id, second.id)

    def test_legacy_indexed_document_is_hashed_without_reprocessing(self):
        first = self.upload()
        first.status = 'indexed'; first.chunk_count = 42; first.content_sha256 = None
        self.db.commit()
        with self.assertRaises(DuplicateUpload): self.upload('renamed.txt')
        self.db.refresh(first)
        self.assertEqual(len(first.content_sha256), 64)
        self.assertEqual(first.chunk_count, 42)
        self.assertEqual(self.db.scalar(select(func.count(DocumentProcessingJob.id))), 1)

    def test_failed_document_allows_a_new_upload(self):
        first = self.upload(); first.status = 'failed'; self.db.commit()
        self.assertNotEqual(first.id, self.upload().id)

    def test_missing_old_source_does_not_block_new_upload(self):
        first = self.upload(); Path(first.storage_path).unlink()
        self.assertNotEqual(first.id, self.upload().id)

    def test_different_collection_and_owner_are_separate(self):
        first = self.upload()
        collection = DocumentCollection(name='other scope', owner_id=self.owner.id)
        self.db.add(collection); self.db.commit()
        second = self.upload(collection_id=collection.id)
        third = asyncio.run(create_document_record(self.db, self.other, UploadFile(filename='a.txt', file=BytesIO(b'synthetic text'))))
        self.assertEqual(len({first.id, second.id, third.id}), 3)

    def test_unwritable_collection_rejected_before_saving_or_duplicate_lookup(self):
        collection = DocumentCollection(name='private', owner_id=self.owner.id)
        self.db.add(collection); self.db.commit()
        with self.assertRaises(PermissionError):
            asyncio.run(create_document_record(self.db, self.other,
                UploadFile(filename='a.txt', file=BytesIO(b'synthetic text')), collection_id=collection.id))
        self.assertFalse((self.settings.UPLOAD_DIR / str(self.other.id)).exists())

    def test_duplicate_route_returns_existing_document_without_background_task(self):
        first = self.upload()
        tasks, response = BackgroundTasks(), Response()
        result = asyncio.run(upload_document(tasks, response,
            file=UploadFile(filename='copy.txt', file=BytesIO(b'synthetic text')),
            current_user=self.owner, db=self.db, llm_chunk_normalization_mode='disabled',
            enable_llm_chunk_normalization=None, collection_id=None, source_relative_path=None))
        self.assertTrue(result.duplicate)
        self.assertEqual(result.id, first.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tasks.tasks, [])

    def test_parallel_identical_uploads_create_one_document_and_job(self):
        owner_id = self.owner.id
        self.db.rollback()
        barrier = threading.Barrier(2)
        def worker():
            with Session(self.engine) as db:
                owner = db.get(User, owner_id)
                barrier.wait(timeout=5)
                try:
                    document = asyncio.run(create_document_record(db, owner, UploadFile(filename='a.txt', file=BytesIO(b'parallel synthetic'))))
                    return document.id, False
                except DuplicateUpload as exc:
                    return exc.document.id, True
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: worker(), range(2)))
        self.assertEqual(len({result[0] for result in results}), 1)
        self.assertEqual(sorted(result[1] for result in results), [False, True])
        self.assertEqual(self.db.scalar(select(func.count(DocumentProcessingJob.id))), 1)

    def test_sqlite_legacy_schema_upgrade_is_additive_and_idempotent(self):
        first = self.upload()
        self.db.close()
        with self.engine.begin() as connection:
            connection.exec_driver_sql('DROP INDEX ix_documents_content_sha256')
            connection.exec_driver_sql('ALTER TABLE documents DROP COLUMN content_sha256')
        with patch('app.db.init_db.engine', self.engine), patch('app.db.init_db.get_settings', return_value=SimpleNamespace(DATABASE_URL='sqlite:///test.db')):
            _ensure_sqlite_schema(); _ensure_sqlite_schema()
        with Session(self.engine) as db:
            restored = db.get(Document, first.id)
            self.assertEqual(restored.filename, 'a.txt')
            self.assertIsNone(restored.content_sha256)


if __name__ == '__main__': unittest.main()
