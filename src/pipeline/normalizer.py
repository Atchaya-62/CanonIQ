from __future__ import annotations

from collections import defaultdict

from ..models.candidate import CandidateProfile, ValueRecord
from ..models.education import EducationRecord
from ..models.experience import ExperienceRecord
from ..pipeline.normalization_engine import NormalizationContext, default_normalization_engine
from ..utils.email_utils import normalize_email
from ..utils.location_utils import normalize_country, normalize_location
from ..utils.phone_utils import normalize_phone
from ..utils.skill_utils import canonicalize_skills
from ..utils.string_similarity import string_similarity
from ..utils.text_utils import clean_text, normalize_url, title_case_name


class CandidateNormalizer:
    def __init__(self) -> None:
        self.engine = default_normalization_engine()

    def normalize(self, profile: CandidateProfile) -> CandidateProfile:
        self._normalize_scalar_fields(profile)
        profile.emails = self._normalize_values(profile.emails, normalize_email, "email")
        profile.phones = self._normalize_phones(profile)
        profile.skills = self._normalize_skills(profile.skills)
        profile.locations = self._normalize_locations(profile.locations)
        profile.links = self._normalize_links(profile.links)
        profile.experience = self._normalize_experience(profile.experience)
        profile.education = self._normalize_education(profile.education)
        profile.source_types = sorted(set(profile.source_types))
        profile.warnings = sorted(set(filter(None, profile.warnings)))
        profile.explanation = list(dict.fromkeys(profile.explanation))
        return profile

    def _normalize_scalar_fields(self, profile: CandidateProfile) -> None:
        if profile.name and profile.name.value:
            profile.name.value = title_case_name(profile.name.value)
            profile.extra["normalized_name"] = self.engine.normalize_name_value(profile.name.value)
        if profile.summary and profile.summary.value:
            profile.summary.value = clean_text(profile.summary.value)
        if profile.country and profile.country.value:
            profile.country.value = normalize_country(profile.country.value)
            profile.extra["normalized_country"] = profile.country.value

    def _normalize_values(self, records: list[ValueRecord], normalizer, field_name: str) -> list[ValueRecord]:
        indexed: dict[str, ValueRecord] = {}
        for record in records:
            normalized = normalizer(record.value)
            if not normalized:
                continue
            record.value = normalized
            record.confidence = max(record.confidence, 0.5)
            indexed[normalized] = self._choose_better(indexed.get(normalized), record)
        return self._sort_records(indexed.values())

    def _normalize_skills(self, records: list[ValueRecord]) -> list[ValueRecord]:
        grouped: dict[str, ValueRecord] = {}
        for record in records:
            canonical = canonicalize_skills([record.value])
            skill = canonical[0] if canonical else None
            if not skill:
                continue
            record.value = skill
            grouped[skill] = self._choose_better(grouped.get(skill), record)
        return [grouped[key] for key in sorted(grouped.keys(), key=str.lower)]

    def _normalize_locations(self, records: list[ValueRecord]) -> list[ValueRecord]:
        normalized: dict[str, ValueRecord] = {}
        for record in records:
            value = normalize_location(record.value)
            if not value:
                continue
            record.value = value
            normalized[value] = self._choose_better(normalized.get(value), record)
        return self._sort_records(normalized.values())

    def _normalize_links(self, links: dict[str, ValueRecord]) -> dict[str, ValueRecord]:
        result: dict[str, ValueRecord] = {}
        for key, record in links.items():
            if record and record.value:
                value = normalize_url(record.value)
                if value:
                    record.value = value
                    result[key] = record
        return dict(sorted(result.items()))

    def _normalize_phones(self, profile: CandidateProfile) -> list[ValueRecord]:
        default_country = self._infer_country(profile)
        location = self._best_location(profile)
        return self._normalize_values(
            profile.phones,
            lambda value: normalize_phone(value, default_country=default_country, location=location),
            "phone",
        )

    def _normalize_experience(self, records: list[ExperienceRecord]) -> list[ExperienceRecord]:
        deduped: dict[tuple[str | None, str | None, str | None], ExperienceRecord] = {}
        for record in records:
            record.company = title_case_name(record.company)
            record.title = title_case_name(record.title)
            record.location = normalize_location(record.location)
            record.start_date = clean_text(record.start_date)
            record.end_date = clean_text(record.end_date)
            deduped[record.key()] = record
        return sorted(deduped.values(), key=lambda item: ((item.company or ""), (item.title or ""), (item.start_date or "")))

    def _normalize_education(self, records: list[EducationRecord]) -> list[EducationRecord]:
        deduped: dict[tuple[str | None, str | None, str | None], EducationRecord] = {}
        for record in records:
            record.institution = title_case_name(record.institution)
            record.degree = title_case_name(record.degree)
            record.field_of_study = title_case_name(record.field_of_study)
            record.start_date = clean_text(record.start_date)
            record.end_date = clean_text(record.end_date)
            deduped[record.key()] = record
        return sorted(deduped.values(), key=lambda item: ((item.institution or ""), (item.degree or ""), (item.field_of_study or "")))

    def _choose_better(self, current: ValueRecord | None, candidate: ValueRecord) -> ValueRecord:
        if current is None:
            return candidate
        if candidate.confidence > current.confidence:
            return candidate
        if candidate.confidence == current.confidence and string_similarity(str(candidate.value), str(current.value)) >= 1.0:
            return candidate
        return current

    def _sort_records(self, records) -> list[ValueRecord]:
        return sorted(records, key=lambda item: (-item.confidence, str(item.value).lower()))

    def _infer_country(self, profile: CandidateProfile) -> str | None:
        if profile.country and profile.country.value:
            return str(profile.country.value)
        location = self._best_location(profile)
        if location:
            parts = [part.strip() for part in str(location).split(",") if part.strip()]
            if parts:
                return parts[-1]
        return None

    def _best_location(self, profile: CandidateProfile) -> str | None:
        for record in profile.locations:
            if record.value:
                return str(record.value)
        for record in profile.experience:
            if record.location:
                return str(record.location)
        return None
