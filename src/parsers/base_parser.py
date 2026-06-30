from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..models.candidate import CandidateProfile

if TYPE_CHECKING:
    from ..pipeline.loader import SourceDocument


class BaseParser(ABC):
    source_types: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.warnings: list[str] = []

    @abstractmethod
    def parse(self, document: SourceDocument) -> list[CandidateProfile]:
        raise NotImplementedError

    def _reset_warnings(self) -> None:
        self.warnings = []

    def _warn(self, document: SourceDocument, message: str) -> None:
        self.warnings.append(f"{document.path}: {message}")
