"""Start the API with independent local model and explicitly enabled LLM profiles."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.chdir(root / "backend")
sys.path.insert(0, str(root / "backend"))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

def configure_local_llm():
    """Keep credentials in .env and default to offline without an opt-in profile."""
    from dotenv import dotenv_values

    profile = root / 'backend/.env.llm'
    values = dotenv_values(profile) if profile.is_file() else {}
    mode = os.environ.get('LOCAL_LLM_MODE') or values.get('LOCAL_LLM_MODE') or 'offline'
    if mode not in {'offline', 'chat', 'chat_and_normalization'}:
        raise RuntimeError('LOCAL_LLM_MODE must be offline, chat, or chat_and_normalization.')
    os.environ['LOCAL_LLM_MODE'] = mode
    normalize = mode == 'chat_and_normalization'
    for key in ('PREPROCESS_LLM_ENABLED', 'CHUNK_LLM_NORMALIZATION_ENABLED'):
        os.environ[key] = 'true' if normalize else 'false'
    for key in ('INGESTION_AGENT_LLM_ENABLED', 'QUERY_AGENT_LLM_ENABLED', 'QUERY_AGENT_EVIDENCE_LLM_ENABLED'):
        os.environ[key] = 'false'
    if mode == 'offline':
        # Set an explicit empty value in Python: PowerShell 5.1 removes it.
        os.environ['OPENAI_API_KEY'] = ''
    else:
        from app.core.config import Settings
        settings = Settings()
        if not (settings.OPENAI_API_KEY or '').strip() or not settings.OPENAI_MODEL_NAME:
            raise RuntimeError('LLM profile is enabled but API key/model is missing. Check backend/.env without sharing the key.')
        import importlib.util
        if importlib.util.find_spec('openai') is None:
            raise RuntimeError('LLM profile requires the openai package from backend/requirements-rag-local.txt.')
    return mode

llm_mode = configure_local_llm()

def configure_local_ocr():
    """Read only the separate OCR profile; never rewrite credential settings."""
    profile = root / "backend/.env.ocr"
    if not profile.is_file():
        return False
    from dotenv import dotenv_values

    permitted = {
        "PREPROCESS_OCR_FALLBACK_ENABLED", "OCR_DETECTION_MODEL_DIR",
        "OCR_RECOGNITION_MODEL_DIR", "OCR_TEXTLINE_ORIENTATION_MODEL_DIR",
        "PADDLEOCR_DEVICE", "PADDLEOCR_USE_TEXTLINE_ORIENTATION",
        "PADDLEOCR_USE_SUBPROCESS",
    }
    values = dotenv_values(profile)
    for key in permitted:
        if key in values:
            os.environ[key] = values[key] or ""
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    if os.environ.get("PREPROCESS_OCR_FALLBACK_ENABLED", "").lower() != "true":
        return False
    for key in ("OCR_DETECTION_MODEL_DIR", "OCR_RECOGNITION_MODEL_DIR"):
        directory = Path(os.environ.get(key, ""))
        if not all((directory / name).is_file() for name in ("inference.json", "inference.pdiparams", "inference.yml")):
            raise RuntimeError(f"Local OCR model is missing: {directory}")
    import importlib.util
    if any(importlib.util.find_spec(name) is None for name in ("paddle", "paddleocr", "fitz")):
        raise RuntimeError("OCR profile exists but dependencies are missing. Install backend/requirements-ocr-local.txt.")
    return True

ocr_enabled = configure_local_ocr()

def configure_local_rag():
    """Load only the separately validated local vectorization/reranking profile."""
    profile = root / 'backend/.env.rag'
    if not profile.is_file():
        return False
    from dotenv import dotenv_values
    import importlib.util
    permitted = {
        'EMBEDDING_MODEL_NAME', 'EMBEDDING_DEVICE', 'EMBEDDING_BATCH_SIZE',
        'RERANKER_MODEL_NAME', 'RERANKER_ENABLED', 'RERANKER_DEVICE',
        'RERANKER_CANDIDATE_TOP_K',
    }
    values = dotenv_values(profile)
    for key in permitted:
        if key in values:
            os.environ[key] = values[key] or ''
    for key in ('EMBEDDING_MODEL_NAME', 'RERANKER_MODEL_NAME'):
        folder = Path(os.environ.get(key, ''))
        if not (folder / 'config.json').is_file() or not any((folder / name).is_file() for name in ('pytorch_model.bin', 'model.safetensors')):
            raise RuntimeError(f'Local RAG model is missing: {folder}')
    if any(importlib.util.find_spec(name) is None for name in ('torch', 'sentence_transformers', 'chromadb', 'FlagEmbedding')):
        raise RuntimeError('Local RAG profile dependencies are missing. Install backend/requirements-rag-local.txt.')
    os.environ['ANONYMIZED_TELEMETRY'] = 'False'
    return True

rag_enabled = configure_local_rag()
if rag_enabled:
    from app.core.native_runtime import prepare_torch_runtime
    prepare_torch_runtime()

import uvicorn

if __name__ == "__main__":
    print("Local OCR: enabled (CPU)" if ocr_enabled else "Local OCR: disabled", flush=True)
    print('Local RAG: BGE-M3 + bge-reranker-v2-m3 enabled' if rag_enabled else 'Local RAG: not configured', flush=True)
    print('External LLM mode: ' + llm_mode, flush=True)
    from app.core.config import get_settings
    ingestion_settings = get_settings()
    print(f'Ingestion LLM: fact_stage={ingestion_settings.PREPROCESS_FACT_LLM_ENABLED}; '
          f'request_cap={ingestion_settings.INGESTION_LLM_MAX_CALLS}; '
          f'time_budget={ingestion_settings.INGESTION_LLM_MAX_SECONDS}s; '
          f'max_retries={ingestion_settings.INGESTION_LLM_MAX_RETRIES}', flush=True)
    from app.main import app
    from app.services.local_ingestion_recovery import register_local_recovery
    register_local_recovery(app, root)
    from app.services.local_llm_recovery import register_local_llm_recovery
    register_local_llm_recovery(app, root)
    uvicorn.run(app, host="127.0.0.1", port=8000)
