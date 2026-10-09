"""Verify real local GPU embedding/reranking, Chroma and OCR with isolated data."""
from pathlib import Path
import importlib.metadata
import json
import os
import runpy
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
os.environ['LOCAL_LLM_MODE'] = 'offline'
runpy.run_path(str(ROOT / 'scripts/run-local-backend.py'), run_name='local_rag_check')
folder = ROOT / 'backend/.codex_smoke' / ('real-rag-' + uuid.uuid4().hex)
folder.mkdir(parents=True)
from app.core import config
settings = config.Settings(
    _env_file=None,
    DATABASE_URL='sqlite:///' + (folder / 'app.db').as_posix(),
    UPLOAD_DIR=folder / 'uploads', CHROMA_DIR=folder / 'chroma', LOG_DIR=folder / 'logs',
    FIRST_SUPERUSER_USERNAME=None, FIRST_SUPERUSER_PASSWORD=None,
    OPENAI_API_KEY='', INGESTION_AGENT_LLM_ENABLED=False,
    PREPROCESS_LLM_ENABLED=False, CHUNK_LLM_NORMALIZATION_ENABLED=False,
    QUERY_AGENT_LLM_ENABLED=False, QUERY_AGENT_EVIDENCE_LLM_ENABLED=False,
)
config.get_settings = lambda: settings

def main():
    import numpy as np
    import torch
    from app.db.init_db import init_db
    from app.db.session import SessionLocal
    from app.models.user import User
    from app.models.document import Document
    from app.rag.preprocessor import DocumentPreprocessor
    from app.rag.embeddings import BgeEmbeddingModel
    from app.rag.reranker import BgeReranker
    from app.rag.vector_store import ChromaVectorStore
    from app.rag.schemas import DocumentChunk
    from app.services.rag_service import RagService

    assert torch.cuda.is_available(), 'Expected RTX 5060 GPU support'
    print('GPU:', torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0), flush=True)
    assert float((torch.ones(2, device='cuda') * 3).sum().cpu()) == 6.0
    fixture = ROOT / 'backend/.codex_smoke/ocr_local/synthetic-scan.pdf'
    parts = DocumentPreprocessor().preprocess(file_type='pdf', path=fixture, parts=[], force_ocr=True, use_llm_preprocessing=False)
    assert '测试样品' in ''.join(part.text for part in parts)
    print('Mixed Torch + local OCR verified.', flush=True)
    texts = [
        '食品添加剂应当按照国家食品安全标准规定的使用范围和最大使用量使用。',
        '北京今天有雨，明天晴天。',
        '系统管理员可以管理文档访问权限。',
    ]
    model = BgeEmbeddingModel()
    embeddings = model.embed_texts(texts)
    vectors = np.asarray(embeddings)
    assert vectors.shape == (3, 1024) and np.isfinite(vectors).all()
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=0.001)
    init_db()
    with SessionLocal() as db:
        user = User(username='synthetic_rag_user', hashed_password='not-a-login-account', is_active=True, is_admin=False)
        db.add(user); db.flush()
        db.add(Document(id=90001, filename='synthetic-rag.txt', file_type='txt', storage_path=str(folder / 'synthetic-rag.txt'), owner_id=user.id, status='indexed', chunk_count=3, file_size=100))
        db.commit(); db.refresh(user)
        chunks = [DocumentChunk(text=text, metadata={'document_id':90001,'filename':'synthetic-rag.txt','chunk_index':index,'chunk_type':'text'}) for index,text in enumerate(texts)]
        store = ChromaVectorStore()
        store.add_documents([f'synthetic-{index}' for index in range(3)], chunks, embeddings)
        query = '食品添加剂的使用量应当遵守什么标准？'
        hits = store.search_by_embedding(model.embed_query(query), allowed_document_ids=[90001], top_k=3)
        assert len(hits) == 3
        reranker = BgeReranker()
        ranked = reranker.rerank(query, hits, top_k=3)
        assert len(ranked) == 3 and all(np.isfinite(hit['rerank_score']) for hit in ranked)
        assert '食品添加剂' in ranked[0]['text']
        assert next(model.model.parameters()).device.type == 'cuda'
        if reranker.backend == 'flag_embedding':
            assert next(reranker.model.model.parameters()).device.type == 'cuda'
        print('Real BGE-M3 -> Chroma -> Reranker verified.', flush=True)
        response = RagService().answer(db, user=user, question=query, requested_document_ids=[90001], top_k=3)
        assert response.citations and response.retrieval_scope.allowed_document_ids == [90001]
        assert any(step.source == 'reranked_with_preserved_recall' for step in response.retrieval_trace)
        assert response.retrieval_only, 'External LLM must remain disabled during this verification'
        result = {
            'packages':{name:importlib.metadata.version(name) for name in ('torch','sentence-transformers','transformers','chromadb','FlagEmbedding')},
            'gpu':torch.cuda.get_device_name(0), 'gpu_capability':torch.cuda.get_device_capability(0),
            'embedding_device':model.device, 'embedding_dimension':1024,
            'reranker_backend':reranker.backend, 'reranker_device':reranker.device,
            'rerank_scores':[float(hit['rerank_score']) for hit in ranked],
            'chroma_vectors':store.collection.count(), 'ocr_with_torch':True,
            'retrieval_only':response.retrieval_only, 'citations':len(response.citations),
            'external_llm_called':False, 'real_user_data_changed':False,
        }
        target = ROOT / 'backend/.runtime_reports/rag-verification.json'
        target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False,indent=2), flush=True)

if __name__ == '__main__':
    main()
