from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ExperienceRecord:
    company: str | None = None
    title: str | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool = False
    description: str | None = None
    source: str | None = None
    source_path: str | None = None
    confidence: float = 0.0
    provenance: list[dict[str, Any]] = field(default_factory=list)

    def key(self) -> tuple[str | None, str | None, str | None]:
        return (self.company, self.title, self.start_date)
