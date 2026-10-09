"""Resume an explicit local restart checkpoint in the API's own worker process."""
from datetime import datetime, timezone
import json
from pathlib import Path
import threading

from app.core.logger import get_logger
from app.db.session import SessionLocal
from app.models.document import Document
from app.models.document_job import DocumentProcessingJob

logger = get_logger(__name__)


def _save(path: Path, checkpoint: dict) -> None:
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def _run(path: Path, project_root: Path) -> None:
    from app.services.document_service import (
        _create_processing_job, _get_processing_options,
        index_document_by_id, normalize_document_chunks_by_id,
    )
    checkpoint = json.loads(path.read_text(encoding='utf-8'))
    if checkpoint.get('project_root') != str(project_root) or checkpoint.get('state') == 'done':
        return
    results = checkpoint.setdefault('results', {})
    checkpoint['state'] = 'running'
    _save(path, checkpoint)
    for entry in checkpoint.get('documents', []):
        key = str(entry['id'])
        if key in results:
            continue
        with SessionLocal() as db:
            document = db.get(Document, entry['id'])
            if not document or document.filename != entry['filename']:
                results[key] = {'status': 'skipped_identity_change'}
                _save(path, checkpoint)
                continue
            if document.status == 'indexed':
                results[key] = {'status': 'indexed', 'already_complete': True}
                _save(path, checkpoint)
                continue
            if entry.get('operation') == 'normalize' and not checkpoint.get('allow_llm_normalization', False):
                results[key] = {'status': 'skipped_requires_llm_approval'}
                _save(path, checkpoint)
                continue
            source = Path(document.storage_path).resolve()
            if (not source.is_relative_to((project_root / 'data/uploads').resolve())
                or not source.is_file() or source.stat().st_size != entry['file_size']
                or document.owner_id != entry['owner_id']
                or document.collection_id != entry['collection_id']):
                results[key] = {'status': 'skipped_source_or_ownership_change'}
                _save(path, checkpoint)
                continue
            if document.status == 'failed' and 'shm.dll' not in (document.error_message or ''):
                results[key] = {'status': 'failed', 'preserved_unrelated_failure': True}
                _save(path, checkpoint)
                continue
            options = _get_processing_options(db, document)
            if not checkpoint.get('allow_llm_normalization', False):
                options = {**options, 'llm_chunk_normalization_mode': 'disabled'}
            previous = db.get(DocumentProcessingJob, entry['job_id'])
            if previous and previous.status not in ('indexed', 'failed'):
                previous.status = 'failed'
                previous.stage = 'failed'
                previous.message = '运行环境修复重启，旧任务中断并保留记录'
                previous.error_message = 'Interrupted for native runtime recovery'
                previous.finished_at = datetime.now(timezone.utc)
            document.status = 'queued'
            document.status_message = '运行环境修复后恢复原入库队列'
            document.error_message = None
            new_job = _create_processing_job(db, document, options=options)
            job_id = new_job.id
        logger.info('Recovering local document id=%s job=%s', entry['id'], job_id)
        try:
            if entry.get('operation') == 'normalize':
                normalize_document_chunks_by_id(entry['id'])
            else:
                index_document_by_id(entry['id'])
            with SessionLocal() as db:
                document = db.get(Document, entry['id'])
                results[key] = {'status': document.status, 'chunk_count': document.chunk_count, 'job_id': job_id}
        except Exception as exc:
            results[key] = {'status': 'recovery_exception', 'error_type': type(exc).__name__, 'job_id': job_id}
            logger.exception('Local recovery failed for document id=%s', entry['id'])
        _save(path, checkpoint)
    checkpoint['state'] = 'done'
    _save(path, checkpoint)
    logger.info('Local checkpoint recovery finished: documents=%s', len(results))


def register_local_recovery(app, project_root: Path) -> None:
    path = project_root / 'backend/.runtime_reports/local-ingestion-recovery.json'
    if not path.is_file():
        return
    checkpoint = json.loads(path.read_text(encoding='utf-8'))
    if checkpoint.get('state') == 'done':
        return
    def start():
        worker = threading.Thread(target=_run, args=(path, project_root), name='local-ingestion-recovery', daemon=True)
        app.state.local_recovery_worker = worker
        worker.start()
    app.add_event_handler('startup', start)
