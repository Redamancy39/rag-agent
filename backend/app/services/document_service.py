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

from app.agent.ingestion_agent import plan_ingestion, plan_to_dict, probe_to_dict
from app.core.config import get_settings
from app.core.logger import get_logger
from app.db.session import SessionLocal
from app.models.document import Document
from app.models.document_job import DocumentProcessingJob
from app.models.group import GroupPermission, UserGroup
from app.models.permission import Permission
from app.models.user import User
from app.rag.chunkers.rule_chunker import RuleChunker
from app.rag.chunk_quality import annotate_chunk_quality
from app.rag.embeddings import BgeEmbeddingModel
from app.rag.file_types import detect_file_type, sanitize_filename
from app.rag.loaders.factory import get_loader
from app.rag.normalizers.llm_normalizer import normalize_chunks_with_llm
from app.rag.preprocessor import DocumentPreprocessor
from app.rag.schemas import DocumentChunk
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
                .options(selectinload(Document.owner))
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
    statement = (
        select(Document)
        .options(selectinload(Document.owner))
        .where(
            or_(
                Document.owner_id == user.id,
                Document.id.in_(direct_document_ids),
                Document.id.in_(group_document_ids),
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
    return document if group_permission else None


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
    return document if group_permission else None


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
    pages = {
        int(page)
        for page in (_safe_int(metadata.get("page")) for metadata in metadata_items)
        if page is not None
    }
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
        "unique_pages": len(pages),
        "chunk_type_counts": dict(chunk_type_counts),
        "quality_counts": dict(quality_counts),
        "average_quality_score": _average(quality_scores),
        "low_quality_count": quality_counts.get("low", 0),
        "ocr_chunk_count": sum(1 for metadata in metadata_items if _is_ocr_chunk(metadata)),
        "ocr_average_score": _average(ocr_scores),
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
    }
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
    enable_llm_chunk_normalization: bool | None = None,
) -> Document:
    settings = get_settings()
    original_filename = sanitize_filename(upload_file.filename or "uploaded_file")
    file_type = detect_file_type(original_filename)
    suffix = Path(original_filename).suffix.lower()
    if suffix not in settings.ALLOWED_FILE_EXTENSIONS:
        raise ValueError(f"File extension is not allowed: {suffix}")

    user_upload_dir = settings.UPLOAD_DIR / str(user.id)
    user_upload_dir.mkdir(parents=True, exist_ok=True)
    storage_filename = f"{uuid4().hex}{suffix}"
    storage_path = user_upload_dir / storage_filename

    file_size = await _save_upload_file(upload_file, storage_path)

    document = Document(
        filename=original_filename,
        file_type=file_type,
        content_type=upload_file.content_type,
        storage_path=str(storage_path),
        file_size=file_size,
        status="queued",
        status_message="文件已保存，等待后台入库",
        owner_id=user.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    _create_processing_job(
        db,
        document,
        options={
            "enable_llm_chunk_normalization": enable_llm_chunk_normalization,
        },
    )
    return document


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
            "enable_llm_chunk_normalization": True,
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
    settings = get_settings()
    ingestion_plan = None
    if settings.INGESTION_AGENT_ENABLED:
        _set_document_status(db, document, "agent_planning", "入库 Agent 正在探测文件并选择解析工具")
        ingestion_plan = plan_ingestion(document.storage_path, document.file_type)
        _store_ingestion_plan(db, document, ingestion_plan)
        _set_document_status(db, document, "agent_planning", ingestion_plan.status_message)

    parts = []
    if not ingestion_plan or ingestion_plan.primary_reader != "paddleocr":
        _set_document_status(db, document, "parsing", _parser_status_message(document.file_type))
        loader = get_loader(document.file_type)
        try:
            parts = loader.load(document.storage_path)
        except Exception as exc:
            _set_document_status(
                db,
                document,
                "failed",
                "文件无法读取，PDF 可能加密、损坏或缺少对应解析依赖",
                error_message=str(exc)[:2000],
            )
            raise

    parts = DocumentPreprocessor().preprocess(
        file_type=document.file_type,
        path=document.storage_path,
        parts=parts,
        stage_callback=lambda status, message: _set_document_status(
            db,
            document,
            status,
            message,
        ),
        force_ocr=bool(ingestion_plan and ingestion_plan.use_ocr),
        use_llm_preprocessing=(
            ingestion_plan.use_llm_preprocessing if ingestion_plan else None
        ),
    )
    if not parts:
        raise ValueError("No text content extracted from document")

    _set_document_status(db, document, "chunking", "正在按规则切块并保留页码、表格等来源信息")
    chunker = RuleChunker(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )
    chunks = chunker.split_documents(parts)
    if not chunks:
        raise ValueError("No chunks generated from document")

    chunks = annotate_chunk_quality(chunks)
    enable_chunk_llm = _is_chunk_llm_enabled_for_document(
        db,
        document,
        ingestion_plan_use_llm=(
            ingestion_plan.use_llm_preprocessing if ingestion_plan else None
        ),
    )
    if enable_chunk_llm:
        _set_document_status(
            db,
            document,
            "llm_preprocessing",
            "正在对低质量 OCR / 表格型切块进行 LLM 结构化归一化",
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
        )
        if normalized_chunks:
            chunks = annotate_chunk_quality([*chunks, *normalized_chunks])

    indexed_chunks = _attach_document_metadata(document, chunks)

    _set_document_status(db, document, "embedding", "正在调用 BGE Embedding 生成向量")

    embeddings = BgeEmbeddingModel().embed_texts([chunk.text for chunk in indexed_chunks])

    _set_document_status(db, document, "indexing", "正在写入 ChromaDB 向量库")

    vector_store = ChromaVectorStore()
    vector_store.delete_document(document.id)
    chunk_ids = [f"doc:{document.id}:chunk:{index}" for index in range(len(indexed_chunks))]
    vector_store.add_documents(chunk_ids, indexed_chunks, embeddings)

    document.status = "indexed"
    document.status_message = "入库完成，可以进行检索问答"
    document.chunk_count = len(indexed_chunks)
    document.error_message = None
    db.add(document)
    db.commit()
    db.refresh(document)


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
    candidate_count = sum(
        1 for chunk in chunks if bool(chunk.metadata.get("needs_llm_normalization"))
    )
    if candidate_count == 0:
        document.status = "indexed"
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
        return

    _set_document_status(
        db,
        document,
        "llm_preprocessing",
        f"正在对 {min(candidate_count, settings.CHUNK_LLM_MAX_CHUNKS_PER_DOCUMENT)} 个候选切块进行 LLM 结构化归一化",
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
    )
    if not normalized_chunks:
        document.status = "indexed"
        document.status_message = "LLM 整理完成，但未生成新的归一化切块"
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
        return

    merged_chunks = annotate_chunk_quality([*chunks, *normalized_chunks])
    indexed_chunks = _attach_document_metadata(document, merged_chunks)
    _set_document_status(db, document, "embedding", "正在为 LLM 整理后的切块重新生成向量")
    embeddings = BgeEmbeddingModel().embed_texts([chunk.text for chunk in indexed_chunks])
    _set_document_status(db, document, "indexing", "正在重写 ChromaDB 中该文档的向量切块")
    vector_store.delete_document(document.id)
    chunk_ids = [f"doc:{document.id}:chunk:{index}" for index in range(len(indexed_chunks))]
    vector_store.add_documents(chunk_ids, indexed_chunks, embeddings)

    document.status = "indexed"
    document.status_message = f"LLM 整理完成，新增 {len(normalized_chunks)} 个归一化切块"
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
    user_choice = options.get("enable_llm_chunk_normalization")
    if user_choice is not None:
        return bool(user_choice)
    if ingestion_plan_use_llm is not None:
        return bool(ingestion_plan_use_llm)
    return bool(settings.CHUNK_LLM_NORMALIZATION_ENABLED)


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
    return "正在读取文件内容"


def _attach_document_metadata(
    document: Document,
    chunks: list[DocumentChunk],
) -> list[DocumentChunk]:
    indexed_chunks: list[DocumentChunk] = []
    for chunk_index, chunk in enumerate(chunks):
        metadata = dict(chunk.metadata)
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
    page = metadata.get("page")
    if page:
        parts.append(f"页码：第{page}页")
    chunk_type = metadata.get("chunk_type")
    if chunk_type:
        parts.append(f"内容类型：{chunk_type}")
    table_index = metadata.get("table_index")
    if table_index:
        parts.append(f"表格：{table_index}")
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
    if table_chunk_count and llm_normalized_count == 0:
        recommendations.append("检测到表格型内容但没有 LLM 归一化结果，建议对表格多的标准文档开启整理开关。")
    if not recommendations:
        recommendations.append("当前文档处理质量未发现明显异常，可进入问答阶段验证引用准确率。")
    return recommendations
