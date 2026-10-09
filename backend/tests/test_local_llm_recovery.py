from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.models import Base, Document, User
from app.models.document_job import DocumentProcessingJob

from app.services.local_llm_recovery import _run, _source_matches, _validate_manifest


class ApprovedNormalizationTests(unittest.TestCase):
    def test_requires_explicit_approval_and_matching_project(self):
        root = Path('project')
        entry = {'id': 25}
        with self.assertRaises(ValueError):
            _validate_manifest({'project_root': str(root), 'documents': [entry]}, root)
        with self.assertRaises(ValueError):
            _validate_manifest({'project_root': 'another', 'approval': 'explicit_user_approval',
                                'documents': [entry]}, root)

    def test_rejects_duplicate_or_empty_scope(self):
        root = Path('project')
        for entries in ([], [{'id': 25}, {'id': 25}]):
            with self.assertRaises(ValueError):
                _validate_manifest({'project_root': str(root), 'approval': 'explicit_user_approval',
                                    'documents': entries}, root)

    def test_accepts_exact_approved_scope(self):
        root = Path('project')
        _validate_manifest({'project_root': str(root), 'approval': 'explicit_user_approval',
                            'documents': [{'id': 25}, {'id': 26}]}, root)

    def test_completed_records_are_not_submitted_again(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'manifest.json'
            path.write_text(json.dumps({'project_root': str(root),
                'approval': 'explicit_user_approval', 'state': 'running',
                'documents': [{'id': 25}], 'results': {'25': {'status': 'indexed'}}}), encoding='utf-8')
            settings = SimpleNamespace(CHUNK_LLM_NORMALIZATION_ENABLED=True, OPENAI_API_KEY='synthetic',
                CHUNK_LLM_MIN_CHUNKS_PER_DOCUMENT=20, CHUNK_LLM_MAX_CHUNKS_PER_DOCUMENT=120)
            with patch('app.services.local_llm_recovery.get_settings', return_value=settings), \
                 patch('app.services.local_llm_recovery.SessionLocal') as db, \
                 patch('app.services.document_service.normalize_document_chunks_by_id') as normalize:
                _run(path, root)
                _run(path, root)
                normalize.assert_not_called()
                db.assert_not_called()
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['state'], 'done')

    def test_rejects_candidate_limit_beyond_approved_cap(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'manifest.json'
            path.write_text(json.dumps({'project_root': str(root),
                'approval': 'explicit_user_approval', 'documents': [{'id': 25}]}), encoding='utf-8')
            settings = SimpleNamespace(CHUNK_LLM_NORMALIZATION_ENABLED=True, OPENAI_API_KEY='synthetic',
                CHUNK_LLM_MIN_CHUNKS_PER_DOCUMENT=20, CHUNK_LLM_MAX_CHUNKS_PER_DOCUMENT=121)
            with patch('app.services.local_llm_recovery.get_settings', return_value=settings), \
                 patch('app.services.document_service.normalize_document_chunks_by_id') as normalize:
                with self.assertRaises(RuntimeError):
                    _run(path, root)
                normalize.assert_not_called()

    def test_source_guard_detects_replacement_owner_and_external_paths(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            upload = root / 'data/uploads/a.pdf'
            upload.parent.mkdir(parents=True)
            upload.write_bytes(b'pdf')
            doc = SimpleNamespace(storage_path=str(upload), filename='a.pdf',
                                  owner_id=1, collection_id=None)
            entry = {'filename': 'a.pdf', 'owner_id': 1, 'collection_id': None, 'file_size': 3}
            self.assertTrue(_source_matches(doc, entry, root))
            doc.owner_id = 2
            self.assertFalse(_source_matches(doc, entry, root))
            doc.owner_id = 1
            upload.write_bytes(b'replaced')
            self.assertFalse(_source_matches(doc, entry, root))
            outside = root / 'outside.pdf'
            outside.write_bytes(b'pdf')
            doc.storage_path = str(outside)
            self.assertFalse(_source_matches(doc, entry, root))

    def test_approved_workflow_reuses_queue_and_records_one_terminal_job(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'data/uploads/synthetic.pdf'
            source.parent.mkdir(parents=True)
            source.write_bytes(b'pdf')
            engine = create_engine('sqlite://', poolclass=StaticPool)
            Base.metadata.create_all(engine)
            sessions = sessionmaker(bind=engine)
            with sessions() as db:
                owner = User(username='synthetic', hashed_password='test', is_active=True, is_admin=True)
                db.add(owner)
                db.flush()
                doc = Document(filename='synthetic.pdf', file_type='pdf', storage_path=str(source),
                    file_size=3, owner_id=owner.id, status='indexed', chunk_count=1)
                db.add(doc)
                db.commit()
                entry = {'id': doc.id, 'filename': doc.filename, 'owner_id': owner.id,
                         'collection_id': None, 'file_size': 3}
            path = root / 'manifest.json'
            path.write_text(json.dumps({'project_root': str(root), 'approval': 'explicit_user_approval',
                                       'state': 'pending', 'documents': [entry]}), encoding='utf-8')
            def complete_synthetic_job(document_id):
                with sessions() as db:
                    doc = db.get(Document, document_id)
                    self.assertEqual(doc.status, 'llm_preprocessing_queued')
                    job = db.scalar(select(DocumentProcessingJob).where(DocumentProcessingJob.document_id == document_id))
                    self.assertEqual(json.loads(job.options_json)['action'], 'manual_llm_chunk_normalization')
                    doc.status = job.status = 'indexed'
                    job.trace_json = json.dumps([{'node': 'LlmNormalize', 'state': 'done',
                        'summary': {'enabled': True, 'candidate_count': 0, 'attempted_count': 0}}])
                    db.commit()
            settings = SimpleNamespace(CHUNK_LLM_NORMALIZATION_ENABLED=True, OPENAI_API_KEY='synthetic',
                CHUNK_LLM_MIN_CHUNKS_PER_DOCUMENT=20, CHUNK_LLM_MAX_CHUNKS_PER_DOCUMENT=120)
            with patch('app.services.local_llm_recovery.get_settings', return_value=settings), \
                 patch('app.services.local_llm_recovery.SessionLocal', sessions), \
                 patch('app.services.document_service.normalize_document_chunks_by_id', side_effect=complete_synthetic_job) as run:
                _run(path, root)
                _run(path, root)
                run.assert_called_once_with(entry['id'])
            manifest = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(manifest['results'][str(entry['id'])]['llm']['normalization_status'], 'not_needed')
            with sessions() as db:
                self.assertEqual(db.scalar(select(func.count()).select_from(DocumentProcessingJob)), 1)
            engine.dispose()
