from __future__ import annotations

from dataclasses import dataclass, field
from ..models.candidate import CandidateProfile
from .validation_engine import ValidationEngine


@dataclass(slots=True)
class ValidationReport:
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.warnings


class CandidateValidator:
    def __init__(self) -> None:
        self.engine = ValidationEngine()

    def validate(self, profile: CandidateProfile) -> ValidationReport:
        report = ValidationReport()
        result = self.engine.validate_profile(profile)
        report.warnings.extend(result.warnings)
        profile.warnings.extend(report.warnings)
        return report
