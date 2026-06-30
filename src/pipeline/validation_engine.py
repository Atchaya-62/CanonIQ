from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

from ..models.candidate import CandidateProfile
from ..utils.date_utils import current_month
from ..utils.email_utils import is_valid_email
from ..utils.phone_utils import is_valid_phone


@dataclass(slots=True)
class ValidationResult:
    valid: bool
    warnings: list[str] = field(default_factory=list)
    confidence_impact: float = 0.0


class BaseValidator:
    field_name = ""

    def validate(self, value) -> ValidationResult:
        return ValidationResult(True, [], 0.0)


class EmailValidator(BaseValidator):
    field_name = "email"

    def validate(self, value) -> ValidationResult:
        valid = is_valid_email(value)
        return ValidationResult(valid, [] if valid else [f"invalid email: {value}"], -0.10 if not valid else 0.05)


class PhoneValidator(BaseValidator):
    field_name = "phone"

    def validate(self, value) -> ValidationResult:
        valid = is_valid_phone(value)
        return ValidationResult(valid, [] if valid else [f"invalid phone: {value}"], -0.10 if not valid else 0.05)


class URLValidator(BaseValidator):
    field_name = "url"

    def validate(self, value) -> ValidationResult:
        parsed = urlparse(value or "")
        valid = bool(parsed.scheme and parsed.netloc)
        return ValidationResult(valid, [] if valid else [f"malformed url: {value}"], -0.08 if not valid else 0.03)


class DateValidator(BaseValidator):
    field_name = "date"

    def validate(self, value) -> ValidationResult:
        if not value:
            return ValidationResult(True, [], 0.0)
        try:
            datetime.strptime(str(value)[:7], "%Y-%m")
            return ValidationResult(True, [], 0.02)
        except ValueError:
            return ValidationResult(False, [f"invalid date: {value}"], -0.08)


class LocationValidator(BaseValidator):
    field_name = "location"

    def validate(self, value) -> ValidationResult:
        return ValidationResult(bool(value), [] if value else ["invalid location: empty"], 0.0)


class SkillValidator(BaseValidator):
    field_name = "skill"

    def validate(self, value) -> ValidationResult:
        return ValidationResult(bool(value), [] if value else ["invalid skill: empty"], 0.0)


class ValidationEngine:
    def __init__(self) -> None:
        self.email_validator = EmailValidator()
        self.phone_validator = PhoneValidator()
        self.url_validator = URLValidator()
        self.date_validator = DateValidator()
        self.location_validator = LocationValidator()
        self.skill_validator = SkillValidator()

    def validate_profile(self, profile: CandidateProfile) -> ValidationResult:
        warnings: list[str] = []
        confidence_impact = 0.0
        if not profile.has_minimum_identity():
            warnings.append(f"{profile.candidate_id or 'candidate'} missing candidate identity")
            confidence_impact -= 0.15
        for record in profile.emails:
            result = self.email_validator.validate(record.value)
            warnings.extend(result.warnings)
            confidence_impact += result.confidence_impact
        for record in profile.phones:
            result = self.phone_validator.validate(record.value)
            warnings.extend(result.warnings)
            confidence_impact += result.confidence_impact
        for key, record in profile.links.items():
            result = self.url_validator.validate(record.value)
            warnings.extend(result.warnings)
            confidence_impact += result.confidence_impact
            if key == "github" and "github.com" not in (record.value or ""):
                warnings.append(f"invalid github url: {record.value}")
                confidence_impact -= 0.05
            if key == "linkedin" and "linkedin.com" not in (record.value or ""):
                warnings.append(f"linkedin mismatch: {record.value}")
                confidence_impact -= 0.05
        current_year = datetime.now(timezone.utc).year
        for experience in profile.experience:
            if experience.start_date and self._year(experience.start_date) > current_year:
                warnings.append(f"future employment start date: {experience.start_date}")
                confidence_impact -= 0.06
            if experience.end_date and self._year(experience.end_date) > current_year + 1:
                warnings.append(f"future employment end date: {experience.end_date}")
                confidence_impact -= 0.06
        self._add_duplicate_warnings(profile, warnings)
        return ValidationResult(not warnings, warnings, confidence_impact)

    def _add_duplicate_warnings(self, profile: CandidateProfile, warnings: list[str]) -> None:
        if len({record.value for record in profile.emails}) != len(profile.emails):
            warnings.append("duplicate emails detected")
        if len({record.value for record in profile.phones}) != len(profile.phones):
            warnings.append("duplicate phones detected")
        if len({record.value for record in profile.skills}) != len(profile.skills):
            warnings.append("duplicate skills detected")
        if len({record.key() for record in profile.experience}) != len(profile.experience):
            warnings.append("duplicate experiences detected")
        if len({record.key() for record in profile.education}) != len(profile.education):
            warnings.append("duplicate education detected")
        if self._has_overlapping_jobs(profile):
            warnings.append("overlapping jobs detected")

    def _has_overlapping_jobs(self, profile: CandidateProfile) -> bool:
        intervals = []
        for record in profile.experience:
            start = self._year_month(record.start_date)
            end_value = current_month() if record.is_current and not record.end_date else record.end_date
            end = self._year_month(end_value)
            if start and end:
                intervals.append((start, end))
        intervals.sort()
        for index in range(1, len(intervals)):
            if intervals[index][0] <= intervals[index - 1][1]:
                return True
        return False

    def _year(self, value: str) -> int:
        try:
            return int(value[:4])
        except (TypeError, ValueError):
            return 0

    def _year_month(self, value: str | None) -> int:
        if not value or len(value) < 7:
            return 0
        try:
            return int(value[:4]) * 100 + int(value[5:7])
        except ValueError:
            return 0

