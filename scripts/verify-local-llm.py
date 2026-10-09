"""One explicitly authorized API call using synthetic data, never existing documents."""
from pathlib import Path
from functools import partial
import json
import os
import runpy
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

def main():
    if '--allow-api-call' not in sys.argv:
        raise SystemExit('Explicit API validation opt-in required: --allow-api-call')
    os.environ['LOCAL_LLM_MODE'] = 'chat_and_normalization'
    runpy.run_path(str(ROOT / 'scripts/run-local-backend.py'), run_name='verify_llm_profile')
    from app.core.config import get_settings
    from app.rag.llm_client import OpenAICompatibleLLM
    from app.rag.normalizers.llm_normalizer import ChunkTextNormalizer
    from app.rag.schemas import DocumentChunk

    settings = get_settings()
    if urlsplit(settings.OPENAI_BASE_URL or '').hostname != 'api.deepseek.com':
        raise SystemExit('This validation is limited to the configured official DeepSeek endpoint.')
    report = {'provider': 'DeepSeek', 'requested_model': settings.OPENAI_MODEL_NAME,
              'api_key_present': bool(settings.OPENAI_API_KEY), 'data': 'synthetic only',
              'existing_documents_sent': False, 'preprocess_llm_enabled': settings.PREPROCESS_LLM_ENABLED,
              'chunk_llm_normalization_enabled': settings.CHUNK_LLM_NORMALIZATION_ENABLED,
              'request_count': 0}
    started = time.monotonic()
    try:
        llm = OpenAICompatibleLLM()
        llm.client = llm.client.with_options(max_retries=0, timeout=60.0)
        # Keep this validation bounded to a single non-thinking JSON response.
        create = llm.client.chat.completions.create
        llm.client.chat.completions.create = partial(
            create, max_tokens=1024, extra_body={'thinking': {'type': 'disabled'}}
        )
        normalizer = ChunkTextNormalizer()
        normalizer._llm = llm
        raw = ('合成测试资料，非真实食品标准。\n'
               '模拟项目 | 模拟限值 | 单位\n测试指标 | 3 | mg/kg\n'
               '适用条件：仅用于 API 联通测试，不具有业务含义。')
        chunk = DocumentChunk(text=raw, metadata={'filename': 'synthetic-api-check.txt',
                              'page': 1, 'chunk_type': 'table_row_fact',
                              'needs_llm_normalization': True, 'local_chunk_index': 0})
        report['request_count'] = 1
        normalized = normalizer.normalize(chunk)
        report['api_status'] = 'passed'
        report['normalized_chunk_generated'] = normalized is not None
        if normalized is not None:
            report['source_page_preserved'] = normalized.metadata.get('page') == 1
            report['normalized_text_length'] = len(normalized.text)
            report['llm_normalized'] = normalized.metadata.get('llm_normalized') is True
    except Exception as exc:
        # Never print exception bodies/headers: provider errors can contain input.
        report['api_status'] = 'failed'
        report['error_type'] = type(exc).__name__
        report['http_status'] = getattr(exc, 'status_code', None)
    report['elapsed_seconds'] = round(time.monotonic() - started, 2)
    output = ROOT / 'backend/.runtime_reports/deepseek-api-verification.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['api_status'] == 'passed' else 1

if __name__ == '__main__':
    raise SystemExit(main())
