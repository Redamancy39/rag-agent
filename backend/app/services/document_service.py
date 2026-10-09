import importlib.util
import gc
import json
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.agent.ingestion_agent import plan_to_dict, probe_to_dict
from app.agent.graph import LangGraphUnavailableError, run_ingestion_graph
from app.agent.ingestion_nodes import (
    IngestionCallbacks,
    IngestionContext,
    IngestionPipeline,
)
from app.core.config import get_settings
from app.core.logger import get_logger
from app.db.session import SessionLocal
from app.models.document import Document
from app.models.document_collection import (
    CollectionGroupPermission,
    CollectionUserPermission,
    DocumentCollection,
)
from app.models.document_job import DocumentProcessingJob
from app.models.group import GroupPermission, UserGroup
from app.models.permission import Permission
from app.models.user import User
from app.rag.chunk_quality import annotate_chunk_quality
from app.rag.embeddings import BgeEmbeddingModel
from app.rag.llm_budget import IngestionLlmBudget, LIMIT_MESSAGES
from app.rag.file_types import detect_file_type, sanitize_filename, validate_upload_source
from app.services.document_dedup import DuplicateUpload, file_sha256, find_duplicate

_upload_record_lock = threading.RLock()
from app.rag.normalizers.llm_normalizer import (
    count_llm_normalized_chunks,
    dedupe_llm_normalized_chunks,
    merge_llm_normalized_chunks,
    normalize_chunks_with_llm,
    select_llm_normalization_candidates,
)
from app.rag.schemas import DocumentChunk, SourceLocator
from app.rag.vector_store import ChromaVectorStore

logger = get_logger(__name__)
_INGESTION_SEMAPHORE: threading.BoundedSemaphore | None = None
_INGESTION_SEMAPHORE_LOCK = threading.Lock()


class DocumentIngestionError(RuntimeError):
    pass


def list_accessible_documents(db: Session, user: User) -> list[Document]:
    if user.is_admin:
        return list(
            db.scalars(
                select(Document)
                .options(
                    selectinload(Document.owner),
                    selectinload(Document.collection),
                )
                .order_by(Document.id.desc())
            )
        )

    direct_document_ids = (
        select(Permission.document_id)
        .where(Permission.user_id == user.id, Permission.can_read.is_(True))
    )
    group_ids = select(UserGroup.group_id).where(UserGroup.user_id == user.id)
    group_document_ids = (
        select(GroupPermission.document_id)
        .where(
            GroupPermission.group_id.in_(group_ids),
            GroupPermission.can_read.is_(True),
        )
    )
    owned_collection_ids = select(DocumentCollection.id).where(
        DocumentCollection.owner_id == user.id
    )
    direct_collection_ids = select(CollectionUserPermission.collection_id).where(
        CollectionUserPermission.user_id == user.id,
        CollectionUserPermission.can_read.is_(True),
    )
    group_collection_ids = select(CollectionGroupPermission.collection_id).where(
        CollectionGroupPermission.group_id.in_(group_ids),
        CollectionGroupPermission.can_read.is_(True),
    )
    statement = (
        select(Document)
        .options(
            selectinload(Document.owner),
            selectinload(Document.collection),
        )
        .where(
            or_(
                Document.owner_id == user.id,
                Document.id.in_(direct_document_ids),
                Document.id.in_(group_document_ids),
                Document.collection_id.in_(owned_collection_ids),
                Document.collection_id.in_(direct_collection_ids),
                Document.collection_id.in_(group_collection_ids),
            )
        )
        .distinct()
        .order_by(Document.id.desc())
    )
    return list(db.scalars(statement))


def get_accessible_document(db: Session, document_id: int, user: User) -> Document | None:
    document = db.get(Document, document_id)
    if not document:
        return None
    if user.is_admin or document.owner_id == user.id:
        return document

    permission = db.scalar(
        select(Permission).where(
            Permission.document_id == document_id,
            Permission.user_id == user.id,
            Permission.can_read.is_(True),
        )
    )
    if permission:
        return document

    group_ids = select(UserGroup.group_id).where(UserGroup.user_id == user.id)
    group_permission = db.scalar(
        select(GroupPermission).where(
            GroupPermission.document_id == document_id,
            GroupPermission.group_id.in_(group_ids),
            GroupPermission.can_read.is_(True),
        )
    )
    if group_permission:
        return document
    return document if _has_collection_access(db, document, user, write=False) else None


def get_writable_document(db: Session, document_id: int, user: User) -> Document | None:
    document = db.get(Document, document_id)
    if not document:
        return None
    if user.is_admin or document.owner_id == user.id:
        return document

    permission = db.scalar(
        select(Permission).where(
            Permission.document_id == document_id,
            Permission.user_id == user.id,
            Permission.can_write.is_(True),
        )
    )
    if permission:
        return document

    group_ids = select(UserGroup.group_id).where(UserGroup.user_id == user.id)
    group_permission = db.scalar(
        select(GroupPermission).where(
            GroupPermission.document_id == document_id,
            GroupPermission.group_id.in_(group_ids),
            GroupPermission.can_write.is_(True),
        )
    )
    if group_permission:
        return document
    return document if _has_collection_access(db, document, user, write=True) else None


def _has_collection_access(
    db: Session,
    document: Document,
    user: User,
    *,
    write: bool,
) -> bool:
    if document.collection_id is None:
        return False
    collection = db.get(DocumentCollection, document.collection_id)
    if not collection:
        return False
    if user.is_admin or collection.owner_id == user.id:
        return True
    user_flag = (
        CollectionUserPermission.can_write
        if write
        else CollectionUserPermission.can_read
    )
    direct = db.scalar(
        select(CollectionUserPermission.id).where(
            CollectionUserPermission.collection_id == collection.id,
            CollectionUserPermission.user_id == user.id,
            user_flag.is_(True),
        )
    )
    if direct:
        return True
    group_ids = select(UserGroup.group_id).where(UserGroup.user_id == user.id)
    group_flag = (
        CollectionGroupPermission.can_write
        if write
        else CollectionGroupPermission.can_read
    )
    inherited = db.scalar(
        select(CollectionGroupPermission.id).where(
            CollectionGroupPermission.collection_id == collection.id,
            CollectionGroupPermission.group_id.in_(group_ids),
            group_flag.is_(True),
        )
    )
    return inherited is not None


def list_document_chunks(
    db: Session,
    document_id: int,
    user: User,
    limit: int = 100,
) -> list[dict] | None:
    document = get_accessible_document(db, document_id, user)
    if not document:
        return None
    if document.status != "indexed":
        return []
    return ChromaVectorStore().get_document_chunks(document_id=document_id, limit=limit)


def list_document_jobs(
    db: Session,
    document_id: int,
    user: User,
) -> list[DocumentProcessingJob] | None:
    document = get_accessible_document(db, document_id, user)
    if not document:
        return None
    statement = (
        select(DocumentProcessingJob)
        .where(DocumentProcessingJob.document_id == document_id)
        .order_by(DocumentProcessingJob.id.desc())
    )
    return list(db.scalars(statement))


def get_document_quality_report(db: Session, document_id: int, user: User) -> dict | None:
    document = get_accessible_document(db, document_id, user)
    if not document:
        return None

    jobs = list_document_jobs(db, document_id, user) or []
    latest_job = jobs[0] if jobs else None
    chunks = []
    if document.status == "indexed":
        chunks = ChromaVectorStore().get_document_chunks(
            document_id=document.id,
            limit=max(document.chunk_count or 0, 10000),
        )

    metadata_items = [chunk.get("metadata") or {} for chunk in chunks]
    chunk_type_counts = Counter(str(metadata.get("chunk_type") or "unknown") for metadata in metadata_items)
    quality_scores = [
        _safe_float(metadata.get("chunk_quality_score"))
        for metadata in metadata_items
        if _safe_float(metadata.get("chunk_quality_score")) is not None
    ]
    quality_counts = Counter(
        _quality_label(_safe_float(metadata.get("chunk_quality_score")))
        for metadata in metadata_items
    )
    locations: set[str] = set()
    for metadata in metadata_items:
        locator = SourceLocator.from_metadata(metadata)
        if locator.kind != "document":
            locations.add(locator.canonical_key())
    ocr_scores = [
        _safe_float(metadata.get("ocr_avg_score"))
        for metadata in metadata_items
        if _is_ocr_chunk(metadata) and _safe_float(metadata.get("ocr_avg_score")) is not None
    ]
    report = {
        "document_id": document.id,
        "filename": document.filename,
        "status": document.status,
        "status_message": document.status_message,
        "total_chunks": len(chunks),
        "unique_pages": len(locations),
        "unique_locations": len(locations),
        "chunk_type_counts": dict(chunk_type_counts),
        "quality_counts": dict(quality_counts),
        "average_quality_score": _average(quality_scores),
        "low_quality_count": quality_counts.get("low", 0),
        "ocr_chunk_count": sum(1 for metadata in metadata_items if _is_ocr_chunk(metadata)),
        "ocr_average_score": _average(ocr_scores),
        "bad_text_layer_count": sum(
            1 for metadata in metadata_items if bool(metadata.get("bad_text_layer"))
        ),
        "ocr_replaced_bad_text_layer_count": sum(
            1
            for metadata in metadata_items
            if bool(metadata.get("ocr_replaced_bad_text_layer"))
        ),
        "preprocess_repair_count": sum(
            1 for metadata in metadata_items if bool(metadata.get("preprocess_repair_flags"))
        ),
        "suspicious_power_notation_count": sum(
            1
            for metadata in metadata_items
            if "suspicious_power_notation"
            in str(metadata.get("chunk_quality_flags") or "")
        ),
        "table_chunk_count": sum(1 for metadata in metadata_items if _is_table_chunk(metadata)),
        "llm_normalized_count": sum(1 for metadata in metadata_items if _is_llm_normalized(metadata)),
        "llm_candidate_count": sum(
            1 for metadata in metadata_items if bool(metadata.get("needs_llm_normalization"))
        ),
        "latest_job_stage": latest_job.stage if latest_job else None,
        "latest_job_message": (
            latest_job.progress_detail or latest_job.message
            if latest_job
            else None
        ),
        "latest_job_progress_current": latest_job.progress_current if latest_job else 0,
        "latest_job_progress_total": latest_job.progress_total if latest_job else 0,
        "latest_job_progress_percent": latest_job.progress_percent if latest_job else 0,
        "latest_job_trace": (
            _load_trace_json(latest_job.trace_json)
            if latest_job and latest_job.trace_json
            else []
        ),
    }
    report["health_score"] = _quality_health_score(document, report)
    report["risk_level"] = _quality_risk_level(document, report)
    report["risk_items"] = _quality_risk_items(document, report)
    report["stage_overview"] = _quality_stage_overview(document, report)
    report["recommendations"] = _quality_recommendations(document, report)
    return report


def delete_document_as_admin(db: Session, document_id: int, user: User) -> bool:
    if not user.is_admin:
        raise PermissionError("Only admin users can delete documents")

    document = db.get(Document, document_id)
    if not document:
        return False

    try:
        ChromaVectorStore().delete_document(document.id)
    except Exception as exc:
        logger.warning("Failed to delete vectors for document id=%s: %s", document.id, exc)

    storage_path = Path(document.storage_path)
    try:
        storage_path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Failed to delete source file for document id=%s: %s", document.id, exc)

    db.delete(document)
    db.commit()
    return True


async def create_document_record(
    db: Session,
    user: User,
    upload_file: UploadFile,
    *,
    llm_chunk_normalization_mode: str | bool | None = "auto",
    collection_id: int | None = None,
    source_relative_path: str | None = None,
) -> Document:
    settings = get_settings()
    normalization_mode = _parse_llm_chunk_normalization_mode(
        llm_chunk_normalization_mode
    )
    source_relative_path = validate_upload_source(upload_file.filename or 'uploaded_file', source_relative_path)
    original_filename = sanitize_filename(upload_file.filename or "uploaded_file")
    file_type = detect_file_type(original_filename)
    suffix = Path(original_filename).suffix.lower()
    if suffix not in settings.ALLOWED_FILE_EXTENSIONS:
        raise ValueError(f"File extension is not allowed: {suffix}")
    collection = None
    if collection_id is not None:
        collection = db.get(DocumentCollection, collection_id)
        if not collection:
            raise ValueError("Document collection not found")
        if not _can_write_collection(db, collection, user):
            raise PermissionError("No write permission for this document collection")

    owner_id = user.id
    target_collection_id = collection.id if collection else None
    user_upload_dir = settings.UPLOAD_DIR / str(owner_id)
    user_upload_dir.mkdir(parents=True, exist_ok=True)
    storage_filename = f"{uuid4().hex}{suffix}"
    storage_path = user_upload_dir / storage_filename

    committed = False
    try:
        file_size = await _save_upload_file(upload_file, storage_path)
        digest = file_sha256(storage_path)
        with _upload_record_lock:
            # SQLite's write reservation serializes check + creation across processes too.
            # End the read-only permission-check transaction before reserving the writer.
            db.rollback()
            if db.get_bind().dialect.name == 'sqlite':
                db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            if target_collection_id is not None:
                collection = db.get(DocumentCollection, target_collection_id)
                if collection is None or not _can_write_collection(db, collection, user):
                    raise PermissionError('No write permission for this document collection')
            duplicate = find_duplicate(db, owner_id=owner_id, collection_id=target_collection_id,
                                       size=file_size, digest=digest)
            if duplicate:
                db.commit()  # Persist any legacy fingerprints; never create a new job.
                raise DuplicateUpload(duplicate)
            document = Document(
                filename=original_filename, file_type=file_type,
                content_type=upload_file.content_type, storage_path=str(storage_path),
                file_size=file_size, content_sha256=digest, status='queued',
                status_message='文件已保存，等待后台入库', owner_id=owner_id,
                collection_id=target_collection_id,
            )
            db.add(document)
            db.flush()
            # This commits the new document and its job together while holding the reservation.
            _create_processing_job(db, document, options={
                'llm_chunk_normalization_mode': normalization_mode,
                **({'source_relative_path': source_relative_path} if source_relative_path else {}),
            })
            committed = True
            db.refresh(document)
            return document
    except DuplicateUpload:
        storage_path.unlink(missing_ok=True)
        raise
    except Exception:
        db.rollback()
        if not committed:
            storage_path.unlink(missing_ok=True)
        raise


def _can_write_collection(
    db: Session,
    collection: DocumentCollection,
    user: User,
) -> bool:
    if user.is_admin or collection.owner_id == user.id:
        return True
    direct = db.scalar(
        select(CollectionUserPermission.id).where(
            CollectionUserPermission.collection_id == collection.id,
            CollectionUserPermission.user_id == user.id,
            CollectionUserPermission.can_write.is_(True),
        )
    )
    if direct:
        return True
    group_ids = select(UserGroup.group_id).where(UserGroup.user_id == user.id)
    inherited = db.scalar(
        select(CollectionGroupPermission.id).where(
            CollectionGroupPermission.collection_id == collection.id,
            CollectionGroupPermission.group_id.in_(group_ids),
            CollectionGroupPermission.can_write.is_(True),
        )
    )
    return inherited is not None


async def create_and_index_document(
    db: Session,
    user: User,
    upload_file: UploadFile,
) -> Document:
    document = await create_document_record(db, user, upload_file)
    try:
        index_document_by_id(document.id)
        db.refresh(document)
        return document
    except Exception as exc:
        raise DocumentIngestionError(str(exc)) from exc


def index_document_by_id(document_id: int) -> None:
    _run_document_gpu_task(
        document_id=document_id,
        waiting_status="queued",
        waiting_message="文档正在入库队列中等待 OCR / Embedding / LLM 资源",
        runner=_index_document_by_id_locked,
    )


def _index_document_by_id_locked(document_id: int) -> None:
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if not document:
            logger.warning("Skip indexing missing document id=%s", document_id)
            return
        try:
            _index_document(db, document)
            logger.info(
                "Indexed document id=%s filename=%s chunks=%s",
                document.id,
                document.filename,
                document.chunk_count,
            )
        except Exception as exc:
            _set_document_status(
                db,
                document,
                "failed",
                "文件无法读取或入库失败，请查看错误信息",
                error_message=str(exc)[:2000],
            )
            logger.exception("Failed to index document id=%s", document.id)


def queue_document_chunk_normalization(
    db: Session,
    document_id: int,
    user: User,
) -> Document:
    document = get_writable_document(db, document_id, user)
    if not document:
        raise PermissionError("Document not found or not writable")
    if document.status not in {"indexed", "llm_preprocessing", "llm_preprocessing_queued"}:
        raise ValueError("Only indexed documents can be normalized")
    _create_processing_job(
        db,
        document,
        options={
            "action": "manual_llm_chunk_normalization",
            "llm_chunk_normalization_mode": "enabled",
        },
    )
    _set_document_status(
        db,
        document,
        "llm_preprocessing_queued",
        "已加入 LLM 切块整理队列，等待 GPU / API 资源",
    )
    return document


def normalize_document_chunks_by_id(document_id: int) -> None:
    _run_document_gpu_task(
        document_id=document_id,
        waiting_status="llm_preprocessing_queued",
        waiting_message="LLM 切块整理正在队列中等待 GPU / API 资源",
        runner=_normalize_document_chunks_by_id_locked,
    )


def _normalize_document_chunks_by_id_locked(document_id: int) -> None:
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if not document:
            logger.warning("Skip LLM normalization for missing document id=%s", document_id)
            return
        try:
            _normalize_indexed_document_chunks(db, document)
        except Exception as exc:
            _set_document_status(
                db,
                document,
                "failed",
                "LLM 切块整理失败，请查看错误信息",
                error_message=str(exc)[:2000],
            )
            logger.exception("Failed to normalize chunks for document id=%s", document.id)


async def _save_upload_file(upload_file: UploadFile, destination: Path) -> int:
    settings = get_settings()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    total_size = 0

    with destination.open("wb") as output:
        while True:
            chunk = await upload_file.read(1024 * 1024)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > max_bytes:
                output.close()
                destination.unlink(missing_ok=True)
                raise ValueError(
                    f"File is too large. Max size: {settings.MAX_UPLOAD_SIZE_MB} MB"
                )
            output.write(chunk)

    if total_size == 0:
        destination.unlink(missing_ok=True)
        raise ValueError("Uploaded file is empty")
    return total_size


def _index_document(db: Session, document: Document) -> None:
    callbacks = IngestionCallbacks(
        set_status=lambda status, message: _set_document_status(
            db,
            document,
            status,
            message,
        ),
        update_progress=lambda current, total, message: _update_job_progress(
            db,
            document,
            current=current,
            total=total,
            detail=message,
        ),
        update_trace=lambda event: _upsert_processing_trace(db, document, event),
        store_plan=lambda plan: _store_ingestion_plan(db, document, plan),
        should_normalize_chunks=lambda plan: _is_chunk_llm_enabled_for_document(
            db,
            document,
            ingestion_plan_use_llm=(
                plan.use_llm_preprocessing if plan is not None else None
            ),
        ),
        attach_metadata=lambda chunks: _attach_document_metadata(document, chunks,
            source_relative_path=_get_processing_options(db, document).get('source_relative_path')),
        parser_status_message=_parser_status_message,
    )
    context = IngestionContext(db=db, document=document, callbacks=callbacks)
    settings = get_settings()
    if settings.INGESTION_EXECUTOR == "langgraph":
        try:
            run_ingestion_graph(context)
            return
        except LangGraphUnavailableError as exc:
            logger.warning("LangGraph ingestion unavailable, falling back to pipeline: %s", exc)
            _upsert_processing_trace(
                db,
                document,
                {
                    "node": "LangGraphAdapter",
                    "label": "LangGraph 适配器",
                    "state": "skipped",
                    "message": "LangGraph 未安装，已回退到原生节点执行器",
                    "summary": {
                        "executor": settings.INGESTION_EXECUTOR,
                        "fallback": "pipeline",
                    },
                },
            )
    IngestionPipeline().run(context)


def _normalize_indexed_document_chunks(db: Session, document: Document) -> None:
    settings = get_settings()
    if not document.chunk_count:
        raise ValueError("Document has no indexed chunks")

    _set_document_status(
        db,
        document,
        "llm_preprocessing",
        "正在读取已入库切块，筛选需要 LLM 整理的低质量 OCR / 表格切块",
    )
    vector_store = ChromaVectorStore()
    raw_chunks = vector_store.get_document_chunks(
        document_id=document.id,
        limit=max(document.chunk_count or 0, 10000),
    )
    if not raw_chunks:
        raise ValueError("No indexed chunks found in vector store")

    chunks = annotate_chunk_quality(
        [
            DocumentChunk(
                text=str(item.get("text") or ""),
                metadata=dict(item.get("metadata") or {}),
            )
            for item in raw_chunks
        ]
    )
    original_chunk_count = len(chunks)
    chunks = dedupe_llm_normalized_chunks(chunks)
    deduped_count = original_chunk_count - len(chunks)
    selection = select_llm_normalization_candidates(chunks)
    normalization_report = {
        'enabled': True, 'candidate_count': len(selection.candidates),
        'eligible_count': selection.eligible_count, 'attempted_count': 0,
        'succeeded_count': 0, 'failed_count': 0, 'generated_count': 0,
        'stored_count': count_llm_normalized_chunks(chunks),
    }
    def record_normalization(state):
        _upsert_processing_trace(db, document, {
            'node': 'LlmNormalize', 'state': state,
            'summary': dict(normalization_report),
        })

    record_normalization('running')
    if selection.eligible_count == 0:
        if deduped_count > 0:
            _rewrite_document_vectors(
                db,
                document,
                chunks,
                status_message=f"LLM 整理完成，已清理 {deduped_count} 个重复归一化切块",
            )
            record_normalization('done')
            return
        document.status = "indexed"
        if selection.skipped_existing_count:
            document.status_message = (
                "可疑切块已存在 LLM 归一化结果，本次无需重复整理"
            )
        else:
            document.status_message = "未发现需要 LLM 整理的低质量 OCR / 表格切块"
        document.error_message = None
        db.add(document)
        _update_processing_job(
            db,
            document,
            status="indexed",
            stage="llm_preprocessing",
            message=document.status_message,
            error_message=None,
        )
        db.commit()
        db.refresh(document)
        record_normalization('done')
        return

    _set_document_status(
        db,
        document,
        "llm_preprocessing",
        (
            f"正在对 {len(selection.candidates)} 个候选切块进行 LLM 结构化归一化"
            f"（可补充候选 {selection.eligible_count} 个，"
            f"已跳过已整理 {selection.skipped_existing_count} 个）"
        ),
    )
    normalized_chunks = normalize_chunks_with_llm(
        chunks,
        progress_callback=lambda current, total, message: _update_job_progress(
            db,
            document,
            current=current,
            total=total,
            detail=message,
        ),
        force=True,
        stats=normalization_report,
        budget=IngestionLlmBudget(settings),
        trace_callback=lambda summary: record_normalization('running'),
    )
    normalization_report['generated_count'] = len(normalized_chunks)
    record_normalization('running')
    if not normalized_chunks:
        document.status = "indexed"
        reason = normalization_report.get('limit_reason')
        document.status_message = LIMIT_MESSAGES[reason] if reason else "LLM 整理完成，但未生成新的归一化切块"
        document.error_message = None
        db.add(document)
        _update_processing_job(
            db,
            document,
            status="indexed",
            stage="llm_preprocessing",
            message=document.status_message,
            error_message=None,
        )
        db.commit()
        db.refresh(document)
        record_normalization('done')
        return

    merged_chunks = annotate_chunk_quality(
        merge_llm_normalized_chunks(chunks, normalized_chunks)
    )
    replaced_count = max(0, len(chunks) + len(normalized_chunks) - len(merged_chunks))
    _rewrite_document_vectors(
        db,
        document,
        merged_chunks,
        status_message=(
            f"LLM 整理完成，生成 {len(normalized_chunks)} 个归一化切块"
            + ('；' + LIMIT_MESSAGES[normalization_report['limit_reason']] if normalization_report.get('limit_reason') else '')
            + (f"，替换 {replaced_count} 个原始切块" if replaced_count else "")
            + (f"，清理 {deduped_count} 个重复归一化切块" if deduped_count else "")
        ),
    )
    normalization_report['stored_count'] = count_llm_normalized_chunks(merged_chunks)
    record_normalization('done')


def _rewrite_document_vectors(
    db: Session,
    document: Document,
    chunks: list[DocumentChunk],
    *,
    status_message: str,
) -> None:
    indexed_chunks = _attach_document_metadata(document, chunks)

    _set_document_status(
        db,
        document,
        "embedding",
        "正在为 LLM 整理后的切块重新生成向量",
    )
    embeddings = BgeEmbeddingModel().embed_texts([chunk.text for chunk in indexed_chunks])

    _set_document_status(
        db,
        document,
        "indexing",
        "正在重写 ChromaDB 中该文档的向量切块",
    )
    vector_store = ChromaVectorStore()
    vector_store.delete_document(document.id)
    chunk_ids = [f"doc:{document.id}:chunk:{index}" for index in range(len(indexed_chunks))]
    vector_store.add_documents(chunk_ids, indexed_chunks, embeddings)

    document.status = "indexed"
    document.status_message = status_message
    document.chunk_count = len(indexed_chunks)
    document.error_message = None
    db.add(document)
    _update_processing_job(
        db,
        document,
        status="indexed",
        stage="llm_preprocessing",
        message=document.status_message,
        error_message=None,
    )
    db.commit()
    db.refresh(document)


def _run_document_gpu_task(
    *,
    document_id: int,
    waiting_status: str,
    waiting_message: str,
    runner,
) -> None:
    semaphore = _get_ingestion_semaphore()
    acquired = semaphore.acquire(blocking=False)
    if not acquired:
        _mark_document_waiting(document_id, waiting_status, waiting_message)
        semaphore.acquire()
    try:
        runner(document_id)
    finally:
        _release_accelerator_memory()
        semaphore.release()


def _get_ingestion_semaphore() -> threading.BoundedSemaphore:
    global _INGESTION_SEMAPHORE
    if _INGESTION_SEMAPHORE is None:
        with _INGESTION_SEMAPHORE_LOCK:
            if _INGESTION_SEMAPHORE is None:
                max_workers = max(1, int(get_settings().INGESTION_MAX_CONCURRENT_JOBS))
                _INGESTION_SEMAPHORE = threading.BoundedSemaphore(max_workers)
                logger.info("Ingestion queue concurrency set to %s", max_workers)
    return _INGESTION_SEMAPHORE


def _mark_document_waiting(document_id: int, status: str, message: str) -> None:
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if not document:
            return
        _set_document_status(db, document, status, message)


def _release_accelerator_memory() -> None:
    if not get_settings().RELEASE_GPU_CACHE_AFTER_INGESTION:
        return
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    try:
        import paddle

        empty_cache = getattr(getattr(paddle, "device", None), "cuda", None)
        if empty_cache and hasattr(empty_cache, "empty_cache"):
            empty_cache.empty_cache()
    except Exception:
        pass


def _set_document_status(
    db: Session,
    document: Document,
    status: str,
    message: str,
    *,
    error_message: str | None = None,
) -> None:
    document.status = status
    document.status_message = message
    if error_message is not None:
        document.error_message = error_message
    db.add(document)
    _update_processing_job(
        db,
        document,
        status=status,
        stage=status,
        message=message,
        error_message=error_message,
    )
    db.commit()
    db.refresh(document)


def _create_processing_job(
    db: Session,
    document: Document,
    *,
    options: dict | None = None,
) -> DocumentProcessingJob:
    now = datetime.now(timezone.utc)
    job = DocumentProcessingJob(
        document_id=document.id,
        status=document.status,
        stage=document.status,
        message=document.status_message,
        started_at=None,
        finished_at=None,
        created_at=now,
        updated_at=now,
        options_json=json.dumps(options or {}, ensure_ascii=False),
        trace_json="[]",
        progress_total=0,
        progress_current=0,
        progress_percent=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _get_latest_processing_job(
    db: Session,
    document: Document,
) -> DocumentProcessingJob:
    job = db.scalar(
        select(DocumentProcessingJob)
        .where(DocumentProcessingJob.document_id == document.id)
        .order_by(DocumentProcessingJob.id.desc())
    )
    if job:
        return job
    return _create_processing_job(db, document)


def _update_processing_job(
    db: Session,
    document: Document,
    *,
    status: str,
    stage: str,
    message: str,
    error_message: str | None,
) -> None:
    job = _get_latest_processing_job(db, document)
    now = datetime.now(timezone.utc)
    job.status = status
    job.stage = stage
    job.message = message
    if stage != 'llm_preprocessing':
        job.progress_current = job.progress_total = job.progress_percent = 0
        job.progress_detail = None
    job.updated_at = now
    if job.started_at is None and status != "queued":
        job.started_at = now
    if status in {"indexed", "failed"}:
        job.finished_at = now
    if error_message is not None:
        job.error_message = error_message
    db.add(job)


def _update_job_progress(
    db: Session,
    document: Document,
    *,
    current: int,
    total: int,
    detail: str,
) -> None:
    job = _get_latest_processing_job(db, document)
    job.status = job.stage = 'llm_preprocessing'
    job.progress_current = max(0, current)
    job.progress_total = max(0, total)
    job.progress_percent = (
        min(100, int((job.progress_current / job.progress_total) * 100))
        if job.progress_total
        else 0
    )
    job.progress_detail = detail[:512]
    job.message = detail[:512]
    job.updated_at = datetime.now(timezone.utc)
    document.status = "llm_preprocessing"
    document.status_message = detail[:512]
    db.add(document)
    db.add(job)
    db.commit()


def _upsert_processing_trace(
    db: Session,
    document: Document,
    event: dict,
) -> None:
    job = _get_latest_processing_job(db, document)
    trace = _load_trace_json(job.trace_json)
    node = str(event.get("node") or "")
    merged = False
    if node:
        for index in range(len(trace) - 1, -1, -1):
            item = trace[index]
            if item.get("node") == node and item.get("state") == "running":
                trace[index] = {**item, **event}
                merged = True
                break
    if not merged:
        trace.append(event)
    job.trace_json = json.dumps(trace, ensure_ascii=False)
    job.updated_at = datetime.now(timezone.utc)
    db.add(job)
    db.commit()


def _load_trace_json(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _is_chunk_llm_enabled_for_document(
    db: Session,
    document: Document,
    *,
    ingestion_plan_use_llm: bool | None,
) -> bool:
    settings = get_settings()
    if not (settings.PREPROCESS_LLM_ENABLED and settings.CHUNK_LLM_NORMALIZATION_ENABLED):
        return False

    options = _get_processing_options(db, document)
    mode = _processing_llm_normalization_mode(options)
    if mode == "enabled":
        return True
    if mode == "disabled":
        return False
    if ingestion_plan_use_llm is not None:
        return bool(ingestion_plan_use_llm)
    return bool(settings.CHUNK_LLM_NORMALIZATION_ENABLED)


def _parse_llm_chunk_normalization_mode(value: str | bool | None) -> str:
    if isinstance(value, bool):
        return "enabled" if value else "disabled"
    normalized = str(value or "auto").strip().lower()
    aliases = {
        "true": "enabled",
        "false": "disabled",
        "on": "enabled",
        "off": "disabled",
        "force": "enabled",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"auto", "enabled", "disabled"}:
        raise ValueError(
            "Invalid LLM chunk normalization mode. "
            "Expected: auto, enabled, or disabled."
        )
    return normalized


def _processing_llm_normalization_mode(options: dict) -> str:
    if "llm_chunk_normalization_mode" in options:
        return _parse_llm_chunk_normalization_mode(
            options.get("llm_chunk_normalization_mode")
        )
    if "enable_llm_chunk_normalization" in options:
        return _parse_llm_chunk_normalization_mode(
            options.get("enable_llm_chunk_normalization")
        )
    return "auto"


def _get_processing_options(db: Session, document: Document) -> dict:
    job = _get_latest_processing_job(db, document)
    if not job.options_json:
        return {}
    try:
        parsed = json.loads(job.options_json)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _store_ingestion_plan(
    db: Session,
    document: Document,
    ingestion_plan,
) -> None:
    job = _get_latest_processing_job(db, document)
    job.probe_json = json.dumps(
        probe_to_dict(ingestion_plan.probe),
        ensure_ascii=False,
    )
    job.plan_json = json.dumps(
        plan_to_dict(ingestion_plan),
        ensure_ascii=False,
    )
    job.updated_at = datetime.now(timezone.utc)
    db.add(job)
    db.commit()


def _parser_status_message(file_type: str) -> str:
    if file_type == "pdf":
        if importlib.util.find_spec("fitz") is not None:
            return "正在使用 PyMuPDF 读取 PDF 文本、页码和表格"
        return "未检测到 PyMuPDF，正在使用 pypdf 读取 PDF 文本"
    if file_type in {"markdown", "md"}:
        return "正在读取 Markdown 文本"
    if file_type == "txt":
        return "正在读取 TXT 文本"
    if file_type == "docx":
        return "正在使用 python-docx 读取标题、段落和表格"
    if file_type == "doc":
        return "正在使用 LiteParse / LibreOffice 转换并解析旧版 DOC"
    if file_type == "pptx":
        return "正在使用 python-pptx 读取幻灯片文本、表格和演讲者备注"
    if file_type == "ppt":
        return "正在使用 LiteParse / LibreOffice 转换并解析旧版 PPT"
    if file_type == "xlsx":
        return "正在使用 openpyxl 识别工作表、数据区域、表头和单元格范围"
    if file_type == "xls":
        return "正在使用 LiteParse / LibreOffice 转换并解析旧版 XLS"
    return "正在读取文件内容"


def _attach_document_metadata(
    document: Document,
    chunks: list[DocumentChunk],
    *, source_relative_path: str | None = None,
) -> list[DocumentChunk]:
    indexed_chunks: list[DocumentChunk] = []
    for chunk_index, chunk in enumerate(chunks):
        metadata = dict(chunk.metadata)
        if source_relative_path:
            metadata['source_relative_path'] = source_relative_path
        metadata.update(
            {
                "document_id": document.id,
                "owner_id": document.owner_id,
                "filename": document.filename,
                "file_type": document.file_type,
                "chunk_index": chunk_index,
                "status": document.status,
            }
        )
        indexed_chunks.append(
            DocumentChunk(
                text=_add_provenance_to_chunk_text(document, chunk.text, metadata),
                metadata=metadata,
            )
        )
    return indexed_chunks


def _add_provenance_to_chunk_text(
    document: Document,
    text: str,
    metadata: dict,
) -> str:
    parts = [f"来源文件：{document.filename}"]
    locator = SourceLocator.from_metadata(metadata)
    parts.extend(locator.provenance_parts())
    chunk_type = metadata.get("chunk_type")
    if chunk_type:
        parts.append(f"内容类型：{chunk_type}")
    table_title = metadata.get("table_title")
    if table_title:
        parts.append(f"表题：{table_title}")
    return "；".join(parts) + "。\n" + text


def _safe_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _quality_label(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 0.85:
        return "high"
    if score >= 0.65:
        return "medium"
    return "low"


def _is_ocr_chunk(metadata: dict) -> bool:
    chunk_type = str(metadata.get("chunk_type") or "")
    extraction_method = str(metadata.get("extraction_method") or "")
    return (
        "ocr" in chunk_type
        or "ocr" in extraction_method
        or metadata.get("ocr_line_count") is not None
    )


def _is_table_chunk(metadata: dict) -> bool:
    chunk_type = str(metadata.get("chunk_type") or "")
    return (
        "table" in chunk_type
        or metadata.get("table_index") is not None
        or metadata.get("table_title") is not None
    )


def _is_llm_normalized(metadata: dict) -> bool:
    chunk_type = str(metadata.get("chunk_type") or "")
    extraction_method = str(metadata.get("extraction_method") or "")
    return (
        bool(metadata.get("llm_normalized"))
        or chunk_type in {"llm_normalized_chunk", "llm_structured_fact"}
        or "llm" in extraction_method
    )


def _quality_recommendations(document: Document, report: dict) -> list[str]:
    recommendations: list[str] = []
    total_chunks = int(report.get("total_chunks") or 0)
    low_quality_count = int(report.get("low_quality_count") or 0)
    table_chunk_count = int(report.get("table_chunk_count") or 0)
    llm_normalized_count = int(report.get("llm_normalized_count") or 0)
    bad_text_layer_count = int(report.get("bad_text_layer_count") or 0)
    preprocess_repair_count = int(report.get("preprocess_repair_count") or 0)
    suspicious_power_count = int(report.get("suspicious_power_notation_count") or 0)
    ocr_average_score = report.get("ocr_average_score")

    if document.status == "failed":
        recommendations.append("文档入库失败，优先查看处理任务中的错误信息。")
    if document.status != "indexed":
        recommendations.append("文档尚未完成入库，报告只包含当前阶段已记录的信息。")
    if total_chunks == 0 and document.status == "indexed":
        recommendations.append("文档已入库但没有可见分块，建议重新入库并检查解析器。")
    if total_chunks and low_quality_count / total_chunks >= 0.25:
        recommendations.append("低质量切块占比较高，建议开启 LLM 切块整理或检查 OCR 输出。")
    if isinstance(ocr_average_score, (int, float)) and ocr_average_score < 0.85:
        recommendations.append("OCR 平均置信度偏低，建议检查扫描清晰度、版面方向和 OCR 模型。")
    if bad_text_layer_count:
        recommendations.append("检测到 PDF 文本层异常页，建议确认是否已启用 OCR fallback 并重新入库受影响文档。")
    if preprocess_repair_count:
        recommendations.append("检测到单位或 OCR 形态修复提示，建议查看引用页确认 μg/kg、10 的上标等关键值。")
    if suspicious_power_count:
        recommendations.append("检测到疑似微生物表格上标丢失，建议优先使用 LLM 整理并人工抽查该页。")
    if table_chunk_count and llm_normalized_count == 0:
        recommendations.append("检测到表格型内容但没有 LLM 归一化结果，建议对表格多的标准文档开启整理开关。")
    if not recommendations:
        recommendations.append("当前文档处理质量未发现明显异常，可进入问答阶段验证引用准确率。")
    return recommendations


def _quality_health_score(document: Document, report: dict) -> int:
    if document.status == "failed":
        return 0

    total_chunks = int(report.get("total_chunks") or 0)
    low_quality_count = int(report.get("low_quality_count") or 0)
    suspicious_power_count = int(report.get("suspicious_power_notation_count") or 0)
    bad_text_layer_count = int(report.get("bad_text_layer_count") or 0)
    preprocess_repair_count = int(report.get("preprocess_repair_count") or 0)
    table_chunk_count = int(report.get("table_chunk_count") or 0)
    llm_normalized_count = int(report.get("llm_normalized_count") or 0)
    average_quality_score = report.get("average_quality_score")
    ocr_average_score = report.get("ocr_average_score")

    if isinstance(average_quality_score, (int, float)):
        score = float(average_quality_score) * 100
    elif document.status == "indexed" and total_chunks:
        score = 76.0
    else:
        score = 45.0

    if document.status != "indexed":
        score -= 18
    if total_chunks:
        score -= min(35.0, (low_quality_count / total_chunks) * 70)
    if isinstance(ocr_average_score, (int, float)) and ocr_average_score < 0.9:
        score -= min(18.0, (0.9 - float(ocr_average_score)) * 100)
    score -= min(14.0, bad_text_layer_count * 2.0)
    score -= min(12.0, suspicious_power_count * 4.0)
    score -= min(8.0, preprocess_repair_count * 0.7)

    if table_chunk_count and llm_normalized_count:
        score += 5

    return max(0, min(100, round(score)))


def _quality_risk_level(document: Document, report: dict) -> str:
    score = int(report.get("health_score") or 0)
    total_chunks = int(report.get("total_chunks") or 0)
    low_quality_count = int(report.get("low_quality_count") or 0)
    suspicious_power_count = int(report.get("suspicious_power_notation_count") or 0)

    if document.status == "failed" or score < 60:
        return "high"
    if document.status != "indexed":
        return "medium"
    if total_chunks and low_quality_count / total_chunks >= 0.2:
        return "medium"
    if suspicious_power_count:
        return "medium"
    return "low"


def _quality_risk_items(document: Document, report: dict) -> list[str]:
    items: list[str] = []
    total_chunks = int(report.get("total_chunks") or 0)
    low_quality_count = int(report.get("low_quality_count") or 0)
    bad_text_layer_count = int(report.get("bad_text_layer_count") or 0)
    preprocess_repair_count = int(report.get("preprocess_repair_count") or 0)
    suspicious_power_count = int(report.get("suspicious_power_notation_count") or 0)
    table_chunk_count = int(report.get("table_chunk_count") or 0)
    llm_normalized_count = int(report.get("llm_normalized_count") or 0)
    ocr_average_score = report.get("ocr_average_score")

    if document.status == "failed":
        items.append("入库失败")
    elif document.status != "indexed":
        items.append("仍在处理中")
    if total_chunks and low_quality_count / total_chunks >= 0.2:
        items.append("低质量切块占比较高")
    if isinstance(ocr_average_score, (int, float)) and ocr_average_score < 0.85:
        items.append("OCR 平均置信度偏低")
    if bad_text_layer_count:
        items.append("PDF 文本层存在异常页")
    if preprocess_repair_count:
        items.append("存在单位或 OCR 形态修复提示")
    if suspicious_power_count:
        items.append("疑似存在 10 的上标或微生物限量表误读")
    if table_chunk_count and llm_normalized_count == 0:
        items.append("表格内容尚未 LLM 归一化")
    return items or ["未发现明显风险"]


def _quality_stage_overview(document: Document, report: dict) -> list[dict[str, object]]:
    status = document.status
    latest_stage = str(report.get("latest_job_stage") or status or "")
    latest_message = str(report.get("latest_job_message") or document.status_message or "")
    total_chunks = int(report.get("total_chunks") or 0)
    ocr_chunk_count = int(report.get("ocr_chunk_count") or 0)
    table_chunk_count = int(report.get("table_chunk_count") or 0)
    llm_normalized_count = int(report.get("llm_normalized_count") or 0)

    def item(name: str, state: str, detail: str, metric: str = "") -> dict[str, object]:
        return {
            "name": name,
            "state": state,
            "detail": detail,
            "metric": metric,
        }

    return [
        item(
            "Agent 探测",
            "done" if latest_stage else "pending",
            "识别文件类型、可读性、OCR 与 LLM 整理需求",
            latest_message if latest_stage == "agent_planning" else "",
        ),
        item(
            "解析 / OCR",
            "done" if total_chunks or status in {"chunking", "embedding", "indexing", "indexed"} else "running",
            "优先文本层与表格解析，必要时进入 PaddleOCR",
            f"OCR 块 {ocr_chunk_count}",
        ),
        item(
            "表格归一化",
            "done" if llm_normalized_count else ("running" if status == "llm_preprocessing" else "optional"),
            "将表格行转为可检索事实，低质量块可调用 LLM 整理",
            f"表格块 {table_chunk_count} / LLM {llm_normalized_count}",
        ),
        item(
            "分块与入库",
            "done" if status == "indexed" else ("failed" if status == "failed" else "running"),
            "写入来源页码、质量评分和 ChromaDB 向量索引",
            f"切块 {total_chunks}",
        ),
    ]
