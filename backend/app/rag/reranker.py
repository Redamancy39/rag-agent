from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class RerankerUnavailable(RuntimeError):
    pass


class BgeReranker:
    def __init__(self, model_name: str | None = None) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.RERANKER_MODEL_NAME
        if not self.model_name:
            raise RerankerUnavailable("RERANKER_MODEL_NAME is not configured")
        self.device = _resolve_device(settings.RERANKER_DEVICE)
        self.backend, self.model = _load_reranker(self.model_name, self.device)

    def rerank(self, query: str, hits: list[dict], top_k: int) -> list[dict]:
        if not hits:
            return []

        pairs = [[query, str(hit.get("text") or "")] for hit in hits]
        scores = self._predict(pairs)
        reranked_hits: list[dict] = []
        for hit, rerank_score in zip(hits, scores, strict=False):
            updated_hit = dict(hit)
            updated_hit["vector_score"] = hit.get("score")
            updated_hit["rerank_score"] = float(rerank_score)
            updated_hit["score"] = float(rerank_score)
            reranked_hits.append(updated_hit)
        reranked_hits.sort(key=lambda item: float(item.get("rerank_score") or 0.0), reverse=True)
        return reranked_hits[:top_k]

    def _predict(self, pairs: list[list[str]]) -> list[float]:
        if self.backend == "flag_embedding":
            scores = self.model.compute_score(pairs, normalize=True)
            if isinstance(scores, (int, float)):
                return [float(scores)]
            return [float(score) for score in scores]

        scores = self.model.predict(pairs)
        return [float(score) for score in scores]


@lru_cache(maxsize=1)
def get_optional_reranker() -> BgeReranker | None:
    try:
        return BgeReranker()
    except RerankerUnavailable as exc:
        logger.warning("Reranker unavailable: %s", exc)
    except Exception as exc:
        logger.warning("Reranker disabled after load failure: %s", exc)
    return None


@lru_cache(maxsize=2)
def _load_reranker(model_name: str, device: str) -> tuple[str, Any]:
    try:
        from FlagEmbedding import FlagReranker

        return "flag_embedding", FlagReranker(model_name, use_fp16=device == "cuda")
    except ImportError:
        logger.info("FlagEmbedding is not installed; trying sentence-transformers CrossEncoder")
    except Exception as exc:
        logger.warning("Failed to load reranker with FlagEmbedding: %s", exc)

    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        raise RerankerUnavailable(
            "Reranker requires FlagEmbedding or sentence-transformers. "
            "Install: pip install -r requirements-rag.txt"
        ) from exc

    try:
        return "cross_encoder", CrossEncoder(model_name, device=device)
    except Exception as exc:
        raise RerankerUnavailable(f"Failed to load reranker model: {exc}") from exc


def _resolve_device(configured_device: str) -> str:
    if configured_device != "auto":
        return configured_device
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"
