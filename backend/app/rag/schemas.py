from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LoadedDocumentPart:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DocumentChunk:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
