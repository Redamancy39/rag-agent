"""Summarize recorded LLM execution without loading models or document text."""
import json
from sqlalchemy import func, select
from sqlalchemy.orm import load_only
from app.models.document_job import DocumentProcessingJob
from app.schemas.document import DocumentLlmStatusRead, DocumentRead
from app.rag.llm_budget import LIMIT_MESSAGES

NO_CANDIDATES = '未发现需要 LLM 整理的低质量 OCR / 表格切块'
EXISTING_RESULTS = '可疑切块已存在 LLM 归一化结果，本次无需重复整理'

def _count(summary, key):
    value = summary.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

def summarize_document_llm(job):
    if job is None:
        return DocumentLlmStatusRead(screening_status='not_run', check_status='not_run',
                                     normalization_status='not_run', detail='尚无文档处理任务。')
    result = DocumentLlmStatusRead(job_id=job.id, checked_at=job.finished_at)
    try:
        trace = json.loads(job.trace_json or '[]')
    except (TypeError, ValueError):
        trace = []
    events = [e for e in trace if isinstance(e, dict)] if isinstance(trace, list) else []
    node = next((e for e in reversed(events) if e.get('node') in ('Normalize', 'LlmNormalize')), None)
    if node is None:
        if job.stage == 'llm_preprocessing' and job.message == NO_CANDIDATES:
            return result.model_copy(update=dict(screening_status='completed', check_status='not_run',
                normalization_status='not_needed', candidate_count=0, attempted_count=0,
                generated_count=0, detail='规则筛查未发现候选分块，没有调用 LLM。'))
        if job.stage == 'llm_preprocessing' and job.message == EXISTING_RESULTS:
            return result.model_copy(update=dict(screening_status='completed', check_status='completed',
                normalization_status='recorded', detail='任务记录表明已有 LLM 整理块，本次未重复调用；数量可查看质量报告。'))
        if job.stage == 'llm_preprocessing' and job.status not in ('indexed', 'failed'):
            return result.model_copy(update=dict(check_status='running', normalization_status='running',
                detail='整理任务正在处理，尚无完成结果。'))
        if job.status in ('uploaded', 'queued', 'probing', 'planning', 'parsing', 'ocr'):
            return result.model_copy(update=dict(check_status='not_run', normalization_status='not_run',
                detail='任务尚未记录 LLM 检测结果。'))
        result.detail = '历史任务缺少实际调用统计，不能确认是否完成 LLM 检测；可查看任务或质量报告。'
        return result
    summary = node.get('summary') if isinstance(node.get('summary'), dict) else {}
    for key in ('candidate_count', 'attempted_count', 'succeeded_count', 'failed_count', 'generated_count', 'stored_count',
                'processed_count', 'skipped_count', 'request_attempted_count', 'request_succeeded_count',
                'request_failed_count', 'retry_count', 'request_max_calls'):
        setattr(result, key, _count(summary, key))
    result.limit_reason = summary.get('limit_reason') if summary.get('limit_reason') in LIMIT_MESSAGES else None
    elapsed = summary.get('elapsed_seconds')
    result.elapsed_seconds = float(elapsed) if isinstance(elapsed, (int, float)) and elapsed >= 0 else None
    result.screening_status = 'completed' if node.get('state') == 'done' or result.candidate_count is not None else 'unknown'
    if result.succeeded_count and result.succeeded_count > 0:
        result.check_status = 'partial' if result.failed_count or result.limit_reason else 'completed'
    elif result.failed_count and result.failed_count > 0:
        result.check_status = 'failed'
    elif (result.generated_count and result.generated_count > 0) or (result.stored_count and result.stored_count > 0):
        result.check_status = 'completed'
    elif node.get('state') == 'running' and job.status != 'failed' and summary.get('enabled') is True and result.candidate_count:
        result.check_status = 'running'
    elif result.attempted_count == 0 or (summary.get('enabled') is False) or result.candidate_count == 0:
        result.check_status = 'not_run'
    if result.stored_count and job.status == 'indexed':
        result.normalization_status = 'indexed'
    elif result.generated_count and result.generated_count > 0:
        result.normalization_status = 'indexed' if job.status == 'indexed' else 'index_failed' if job.status == 'failed' else 'pending'
    elif result.check_status == 'failed':
        result.normalization_status = 'failed'
    elif result.candidate_count == 0 and summary.get('enabled') is True:
        result.normalization_status = 'not_needed'
    elif result.check_status in ('completed', 'partial'):
        result.normalization_status = 'not_generated'
    elif result.check_status == 'not_run':
        result.normalization_status = 'not_run'
    elif result.check_status == 'running':
        result.normalization_status = 'running'
    result.detail = '最近任务的候选分块执行记录；规则筛查与开关启用不代表实际调用 LLM。'
    if result.succeeded_count:
        result.detail = f'收到 {result.succeeded_count} 次模型响应，处理失败 {result.failed_count or 0} 次；仅针对筛选出的候选内容。'
    elif result.failed_count:
        result.detail = f'LLM 流程处理失败 {result.failed_count} 次，尚无成功模型响应。'
    elif result.check_status == 'not_run':
        result.detail = '该次任务没有实际调用 LLM；规则筛查与启用开关不代表已完成大模型检测。'
    if result.stored_count and result.attempted_count == 0:
        result.detail = f'已有 {result.stored_count} 个大模型整理块；最近任务没有重复调用 LLM。'
    if result.check_status == 'unknown':
        result.detail = '该历史任务缺少调用结果计数，不能根据“整理完成”确认 LLM 检测成功。'
    if result.request_attempted_count is not None:
        result.detail += f' 实际 API 请求 {result.request_attempted_count}/{result.request_max_calls}，重试 {result.retry_count or 0}。'
    if result.limit_reason:
        result.detail += ' ' + LIMIT_MESSAGES[result.limit_reason] + '。'
    return result

def documents_with_llm_status(db, documents):
    """One metadata query for already permission-filtered document IDs."""
    if not documents:
        return []
    latest = (select(DocumentProcessingJob.document_id, func.max(DocumentProcessingJob.id).label('job_id'))
              .where(DocumentProcessingJob.document_id.in_([d.id for d in documents]))
              .group_by(DocumentProcessingJob.document_id).subquery())
    statement = select(DocumentProcessingJob).options(load_only(
        DocumentProcessingJob.id, DocumentProcessingJob.document_id,
        DocumentProcessingJob.status, DocumentProcessingJob.stage,
        DocumentProcessingJob.message, DocumentProcessingJob.trace_json,
        DocumentProcessingJob.finished_at,
    )).join(latest, DocumentProcessingJob.id == latest.c.job_id)
    jobs = {j.document_id: j for j in db.scalars(statement)}
    return [DocumentRead.model_validate(d).model_copy(update={'llm_processing': summarize_document_llm(jobs.get(d.id))}) for d in documents]
