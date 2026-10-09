import asyncio
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import UploadFile
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, Document, User
from app.models.document_job import DocumentProcessingJob
from app.rag.file_types import validate_upload_source
from app.rag.schemas import DocumentChunk
from app.services.document_service import _attach_document_metadata, create_document_record


class FolderSourceTests(unittest.TestCase):
    def test_filters_disguised_metadata_and_os_artifacts(self):
        for path in ['资料/.DS_Store', '资料/__MACOSX/._报告.pdf', '资料/._报告.pdf',
                     '资料/~$报告.docx', '资料/Thumbs.db', '资料/.git/报告.txt']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_upload_source(path.split('/')[-1], path)

    def test_rejects_absolute_traversal_and_mismatched_provenance(self):
        for path in ['../报告.pdf', '/资料/报告.pdf', 'C:\\资料\\报告.pdf', '资料/another.pdf', '资料//报告.pdf']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_upload_source('报告.pdf', path)
        self.assertEqual(validate_upload_source('报告.pdf', '资料\\子目录\\报告.pdf'), '资料/子目录/报告.pdf')
        self.assertIsNone(validate_upload_source('报告.pdf'))

    def test_manual_upload_cannot_bypass_metadata_guard(self):
        upload = UploadFile(filename='._报告.pdf', file=BytesIO(b'synthetic metadata'))
        with self.assertRaises(ValueError):
            asyncio.run(create_document_record(None, None, upload))
        self.assertEqual(upload.file.tell(), 0)

    def test_same_names_store_separately_with_folder_provenance_and_disabled_llm(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            engine = create_engine('sqlite://')
            Base.metadata.create_all(engine)
            settings = SimpleNamespace(UPLOAD_DIR=root / 'uploads', ALLOWED_FILE_EXTENSIONS=['.txt'], MAX_UPLOAD_SIZE_MB=50)
            with Session(engine) as db, patch('app.services.document_service.get_settings', return_value=settings):
                owner = User(username='synthetic', hashed_password='test', is_active=True, is_admin=False)
                db.add(owner); db.commit()
                documents = []
                for path in ['资料/食品/说明.txt', '资料/材料/说明.txt']:
                    upload = UploadFile(filename='说明.txt', file=BytesIO(path.encode('utf-8')))
                    documents.append(asyncio.run(create_document_record(db, owner, upload,
                        llm_chunk_normalization_mode='disabled', source_relative_path=path)))
                self.assertNotEqual(documents[0].id, documents[1].id)
                self.assertNotEqual(documents[0].storage_path, documents[1].storage_path)
                self.assertTrue(all(Path(d.storage_path).is_relative_to(root / 'uploads') for d in documents))
                jobs = list(db.scalars(select(DocumentProcessingJob).order_by(DocumentProcessingJob.id)))
                self.assertEqual([json.loads(j.options_json)['source_relative_path'] for j in jobs], ['资料/食品/说明.txt', '资料/材料/说明.txt'])
                chunks = _attach_document_metadata(documents[0], [DocumentChunk(text='test', metadata={})], source_relative_path='资料/食品/说明.txt')
                self.assertEqual(chunks[0].metadata['source_relative_path'], '资料/食品/说明.txt')
                rewritten = _attach_document_metadata(documents[0], chunks)
                self.assertEqual(rewritten[0].metadata['source_relative_path'], '资料/食品/说明.txt')
            engine.dispose()
