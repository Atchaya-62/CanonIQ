from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .education import EducationRecord
from .experience import ExperienceRecord


@dataclass(slots=True)
class ProvenanceEntry:
    source: str
    method: str
    timestamp: str
    confidence: float
    reason: str
    source_path: str | None = None


@dataclass(slots=True)
class ValueRecord:
    value: Any
    source: str
    method: str
    timestamp: str
    confidence: float
    reason: str
    raw_value: Any | None = None
    sources: list[str] = field(default_factory=list)
    source_path: str | None = None


@dataclass(slots=True)
class CandidateProfile:
    candidate_id: str | None = None
    name: ValueRecord | None = None
    years_experience: int | None = None
    emails: list[ValueRecord] = field(default_factory=list)
    phones: list[ValueRecord] = field(default_factory=list)
    links: dict[str, ValueRecord] = field(default_factory=dict)
    locations: list[ValueRecord] = field(default_factory=list)
    country: ValueRecord | None = None
    skills: list[ValueRecord] = field(default_factory=list)
    experience: list[ExperienceRecord] = field(default_factory=list)
    education: list[EducationRecord] = field(default_factory=list)
    summary: ValueRecord | None = None
    notes: list[ValueRecord] = field(default_factory=list)
    source_types: list[str] = field(default_factory=list)
    provenance: list[ProvenanceEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.0
    explanation: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def add_provenance(self, source: str, method: str, confidence: float, reason: str) -> None:
        self.provenance.append(
            ProvenanceEntry(
                source=source,
                method=method,
                timestamp="1970-01-01T00:00:00Z",
                confidence=confidence,
                reason=reason,
                source_path=source,
            )
        )

    def identity_components(self) -> set[str]:
        components: set[str] = set()
        if self.name and self.name.value:
            components.add("name")
        if any(record.value for record in self.emails):
            components.add("email")
        if any(record.value for record in self.phones):
            components.add("phone")
        if any(key in {"github", "linkedin"} and record.value for key, record in self.links.items()):
            components.update(key for key, record in self.links.items() if key in {"github", "linkedin"} and record.value)
        if any(source.startswith("resume") for source in self.source_types):
            components.add("resume")
        return components

    def has_minimum_identity(self) -> bool:
        components = self.identity_components()
        direct_identity = components & {"email", "phone", "github", "linkedin", "resume"}
        if direct_identity:
            return True
        return "name" in components and len(components) > 1
