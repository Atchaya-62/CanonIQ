from __future__ import annotations

from dataclasses import dataclass, field

from ..models.candidate import CandidateProfile
from ..parsers import CSVParser, GitHubParser, JSONParser, LinkedInParser, NotesParser, ResumeParser
from .loader import SourceDocument


@dataclass(slots=True)
class ExtractResult:
    profiles: list[CandidateProfile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SourceExtractor:
    def __init__(self) -> None:
        self.parsers = [CSVParser(), JSONParser(), LinkedInParser(), GitHubParser(), ResumeParser(), NotesParser()]

    def extract(self, documents: list[SourceDocument]) -> ExtractResult:
        result = ExtractResult()
        for document in documents:
            parser = self._select_parser(document.source_type)
            if parser is None:
                result.warnings.append(f"unsupported source: {document.path}")
                continue
            try:
                result.profiles.extend(parser.parse(document))
                result.warnings.extend(parser.warnings)
            except Exception as exc:  # pragma: no cover - defensive guard
                result.warnings.append(f"parse failure for {document.path}: {exc}")
        return result

    def _select_parser(self, source_type: str):
        for parser in self.parsers:
            if source_type in parser.source_types or source_type.startswith(tuple(parser.source_types)):
                return parser
        return None
