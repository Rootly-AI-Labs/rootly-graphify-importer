from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Confidence(str, Enum):
    EXTRACTED = "EXTRACTED"
    INFERRED = "INFERRED"
    AMBIGUOUS = "AMBIGUOUS"


class FileType(str, Enum):
    CODE = "code"
    DOCUMENT = "document"
    PAPER = "paper"


@dataclass
class GraphNode:
    id: str
    label: str
    file_type: FileType
    source_file: str
    source_location: Optional[str] = None
    community: Optional[int] = None


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str
    confidence: Confidence
    source_file: str
    source_location: Optional[str] = None
    weight: float = 1.0


@dataclass
class ExtractionResult:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
