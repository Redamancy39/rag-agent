from abc import ABC, abstractmethod
from pathlib import Path

from app.rag.schemas import LoadedDocumentPart


class BaseLoader(ABC):
    @abstractmethod
    def load(self, path: str | Path) -> list[LoadedDocumentPart]:
        raise NotImplementedError
