from functools import lru_cache

from app.core.config import get_settings


class EmbeddingModel:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("BGE embedding will be implemented in stage 2")

    def embed_query(self, query: str) -> list[float]:
        raise NotImplementedError("BGE embedding will be implemented in stage 2")


class BgeEmbeddingModel(EmbeddingModel):
    def __init__(self, model_name: str | None = None) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self.batch_size = settings.EMBEDDING_BATCH_SIZE
        self.device = _resolve_embedding_device(settings.EMBEDDING_DEVICE)
        self.model = _load_sentence_transformer(self.model_name, self.device)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=self.batch_size,
        )
        return vectors.tolist()

    def embed_query(self, query: str) -> list[float]:
        vectors = self.embed_texts([query])
        return vectors[0] if vectors else []


@lru_cache(maxsize=2)
def _load_sentence_transformer(model_name: str, device: str):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Embedding requires sentence-transformers. "
            "Install: pip install -r requirements-rag.txt"
        ) from exc

    return SentenceTransformer(model_name, device=device)


def _resolve_embedding_device(configured_device: str) -> str:
    if configured_device != "auto":
        return configured_device
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"
