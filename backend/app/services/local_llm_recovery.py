"""Run candidate-only normalization for an explicitly approved local manifest."""
import json
from pathlib import Path
import threading

from sqlalchemy import select
from sqlalchemy.orm import load_only

from app.core.config import get_settings
from app.core.logger import get_logger
from app.db.session import SessionLocal
from app.models.document import Document
from app.models.document_job import DocumentProcessingJob
from app.models.user import User
from app.services.local_ingestion_recovery import _save

logger = get_logger(__name__)


def _validate_manifest(manifest, project_root):
    if manifest.get('project_root') != str(project_root):
        raise ValueError('Normalization manifest project mismatch')
    if manifest.get('approval') != 'explicit_user_approval':
        raise ValueError('Normalization manifest requires explicit user approval')
    entries = manifest.get('documents', [])
    ids = [entry['id'] for entry in entries]
    if not entries or len(ids) != len(set(ids)):
        raise ValueError('Normalization manifest requires unique document IDs')


def _source_matches(document, entry, project_root):
    source = Path(document.storage_path).resolve()
    return (document.filename == entry['filename']
            and document.owner_id == entry['owner_id']
            and document.collection_id == entry['collection_id']
            and source.is_relative_to((project_root / 'data/uploads').resolve())
            and source.is_file() and source.stat().st_size == entry['file_size'])


def _run(path, project_root):
    from app.services.document_service import (
        normalize_document_chunks_by_id, queue_document_chunk_normalization,
    )
    from app.services.document_llm_status import summarize_document_llm

    manifest = json.loads(path.read_text(encoding='utf-8'))
    _validate_manifest(manifest, project_root)
    if manifest.get('state') == 'done':
        return
    settings = get_settings()
    if not settings.CHUNK_LLM_NORMALIZATION_ENABLED or not settings.OPENAI_API_KEY:
        raise RuntimeError('Approved normalization requires the enabled local LLM profile')
    if max(settings.CHUNK_LLM_MIN_CHUNKS_PER_DOCUMENT,
           settings.CHUNK_LLM_MAX_CHUNKS_PER_DOCUMENT) > 120:
        raise RuntimeError('Approved normalization candidate limit exceeds 120')
    results = manifest.setdefault('results', {})
    manifest['state'] = 'running'
    _save(path, manifest)
    for entry in manifest['documents']:
        key = str(entry['id'])
        if key in results:
            continue
        with SessionLocal() as db:
            document = db.get(Document, entry['id'])
            if not document or not _source_matches(document, entry, project_root):
                results[key] = {'status': 'skipped_identity_or_source_change'}
                _save(path, manifest)
                continue
            latest = db.scalar(select(DocumentProcessingJob)
                .where(DocumentProcessingJob.document_id == document.id)
                .order_by(DocumentProcessingJob.id.desc()))
            if entry.get('normalization_job_id'):
                if not latest or latest.id != entry['normalization_job_id']:
                    results[key] = {'status': 'skipped_job_change'}
                    _save(path, manifest)
                    continue
                if latest.status in ('indexed', 'failed'):
                    results[key] = {'status': document.status, 'job_id': latest.id,
                                    'llm': summarize_document_llm(latest).model_dump(mode='json')}
                    _save(path, manifest)
                    continue
            elif document.status == 'indexed':
                owner = db.scalar(select(User).options(load_only(
                    User.id, User.is_active, User.is_admin)).where(User.id == entry['owner_id']))
                if not owner or not owner.is_active:
                    results[key] = {'status': 'skipped_inactive_owner'}
                    _save(path, manifest)
                    continue
                queue_document_chunk_normalization(db, document.id, owner)
                db.flush()
                entry['normalization_job_id'] = db.scalar(select(DocumentProcessingJob.id)
                    .where(DocumentProcessingJob.document_id == document.id)
                    .order_by(DocumentProcessingJob.id.desc()))
                _save(path, manifest)
            else:
                results[key] = {'status': 'skipped_not_indexed'}
                _save(path, manifest)
                continue
        logger.info('Approved candidate normalization: document id=%s', entry['id'])
        normalize_document_chunks_by_id(entry['id'])
        with SessionLocal() as db:
            document = db.get(Document, entry['id'])
            job = db.get(DocumentProcessingJob, entry['normalization_job_id'])
            results[key] = {'status': document.status, 'job_id': job.id,
                            'chunk_count': document.chunk_count,
                            'llm': summarize_document_llm(job).model_dump(mode='json')}
        _save(path, manifest)
    manifest['state'] = 'done'
    _save(path, manifest)
    logger.info('Approved normalization finished: documents=%s', len(results))


def register_local_llm_recovery(app, project_root):
    path = project_root / 'backend/.runtime_reports/local-llm-normalization.json'
    if not path.is_file():
        return
    manifest = json.loads(path.read_text(encoding='utf-8'))
    _validate_manifest(manifest, project_root)
    if manifest.get('state') == 'done':
        return
    def start():
        def run_after_ingestion():
            ingestion = getattr(app.state, 'local_recovery_worker', None)
            if ingestion:
                ingestion.join()
            try:
                _run(path, project_root)
            except Exception:
                logger.exception('Approved local normalization stopped; checkpoint retained')
        worker = threading.Thread(target=run_after_ingestion,
                                  name='local-llm-normalization', daemon=True)
        app.state.local_llm_recovery_worker = worker
        worker.start()
    app.add_event_handler('startup', start)
