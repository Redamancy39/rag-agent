"""Create only the local RAG model profile; preserve credential configuration."""
from pathlib import Path
import importlib.util

root = Path(__file__).resolve().parents[1]
profile = root / 'backend/.env.rag'
if profile.exists():
    raise SystemExit('Existing backend/.env.rag preserved. Review before changing it.')
models = [('embeddings/bge-m3', 'pytorch_model.bin'), ('rerankers/bge-reranker-v2-m3', 'model.safetensors')]
for name, weights in models:
    folder = root / 'data/models' / name
    if not (folder / weights).is_file() or not (folder / 'config.json').is_file():
        raise SystemExit(f'Model files not ready: {name}')
if any(importlib.util.find_spec(name) is None for name in ('torch', 'sentence_transformers', 'chromadb', 'FlagEmbedding')):
    raise SystemExit('Local RAG dependencies are not installed.')
values = '''EMBEDDING_MODEL_NAME=../data/models/embeddings/bge-m3
EMBEDDING_DEVICE=auto
EMBEDDING_BATCH_SIZE=4
RERANKER_MODEL_NAME=../data/models/rerankers/bge-reranker-v2-m3
RERANKER_ENABLED=true
RERANKER_DEVICE=auto
RERANKER_CANDIDATE_TOP_K=32
'''
with profile.open('x', encoding='utf-8') as stream:
    stream.write(values)
print('Created backend/.env.rag; credential configuration preserved.')
