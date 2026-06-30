from __future__ import annotations

import re

from ..models.candidate import CandidateProfile, ValueRecord
from ..models.education import EducationRecord
from ..models.experience import ExperienceRecord
from ..utils.date_utils import normalize_date
from ..utils.email_utils import normalize_email
from ..utils.location_utils import normalize_location
from ..utils.phone_utils import normalize_phone
from ..utils.skill_utils import canonicalize_skills, skill_alias_map
from ..utils.text_utils import clean_text, normalize_url, title_case_name

EMAIL_PATTERN = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])")
PHONE_PATTERN = re.compile(r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d[\d\s().-]{7,}\d")
URL_PATTERN = re.compile(r"https?://[^\s)>\]]+|www\.[^\s)>\]]+")
SKILL_SPLIT_PATTERN = re.compile(r"[,;/|]\s*")
DEFAULT_TIMESTAMP = "1970-01-01T00:00:00Z"


def make_value_record(
    value: str | None,
    source: str,
    method: str,
    confidence: float,
    reason: str,
    timestamp: str = DEFAULT_TIMESTAMP,
    source_path: str | None = None,
) -> ValueRecord | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None
    return ValueRecord(cleaned, source, method, timestamp, confidence, reason, raw_value=value, source_path=source_path)


def collect_emails(text: str | None) -> list[str]:
    if not text:
        return []
    return list(dict.fromkeys(normalize_email(match.group(0)) for match in EMAIL_PATTERN.finditer(text) if normalize_email(match.group(0))))


def collect_phones(text: str | None) -> list[str]:
    if not text:
        return []
    return list(dict.fromkeys(normalize_phone(match.group(0)) for match in PHONE_PATTERN.finditer(text) if normalize_phone(match.group(0))))


def collect_urls(text: str | None) -> list[str]:
    if not text:
        return []
    return list(dict.fromkeys(normalize_url(match.group(0)) for match in URL_PATTERN.finditer(text) if normalize_url(match.group(0))))


def extract_skills(raw: list[str] | str | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        values = [clean_text(item) for item in raw if clean_text(item)]
        return canonicalize_skills(values)
    if not isinstance(raw, str):
        return []
    text = clean_text(raw) or ""
    lowered = text.lower()
    aliases = sorted(skill_alias_map().items(), key=lambda item: len(item[0]), reverse=True)
    discovered: list[str] = []
    seen: set[str] = set()
    for alias, canonical in aliases:
        if alias and alias in lowered and canonical not in seen:
            discovered.append(canonical)
            seen.add(canonical)
    if discovered:
        return discovered
    values = SKILL_SPLIT_PATTERN.split(text)
    return canonicalize_skills([clean_text(item) for item in values if clean_text(item)])


def parse_month(value: str | None) -> str | None:
    normalized = normalize_date(value)
    return normalized


def parse_years_experience(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        years = int(value)
        return years if years >= 0 else None
    if isinstance(value, str):
        cleaned = clean_text(value)
        if cleaned is None:
            return None
        try:
            years = int(float(cleaned))
        except ValueError:
            return None
        return years if years >= 0 else None
    return None


def calculate_years_experience(experiences) -> int | None:
    if not experiences:
        return None
    intervals: list[tuple[int, int]] = []
    for exp in experiences:
        if not getattr(exp, "start_date", None):
            continue
        start = _month_index(exp.start_date)
        end = _month_index(exp.end_date or exp.start_date)
        if start is not None and end is not None and end >= start:
            intervals.append((start, end))
    if not intervals:
        return None
    intervals.sort()
    merged: list[tuple[int, int]] = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 1:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    months = 0
    for start, end in merged:
        start_year, start_month = divmod(start, 100)
        end_year, end_month = divmod(end, 100)
        months += (end_year - start_year) * 12 + (end_month - start_month) + 1
    return max(0, round(months / 12))


def _month_index(value: str | None) -> int | None:
    if not value or len(value) < 7:
        return None
    try:
        return int(value[:4]) * 100 + int(value[5:7])
    except ValueError:
        return None


def build_experience(
    company: str | None,
    title: str | None,
    location: str | None,
    start: str | None,
    end: str | None,
    current: bool,
    description: str | None,
    source: str,
    source_path: str | None = None,
) -> ExperienceRecord:
    return ExperienceRecord(
        company=title_case_name(company),
        title=title_case_name(title),
        location=normalize_location(location),
        start_date=parse_month(start),
        end_date=parse_month(end),
        is_current=current,
        description=clean_text(description),
        source=source,
        source_path=source_path,
    )


def build_education(
    institution: str | None,
    degree: str | None,
    field_of_study: str | None,
    start: str | None,
    end: str | None,
    source: str,
    source_path: str | None = None,
) -> EducationRecord:
    return EducationRecord(
        institution=title_case_name(institution),
        degree=title_case_name(degree),
        field_of_study=title_case_name(field_of_study),
        start_date=parse_month(start),
        end_date=parse_month(end),
        source=source,
        source_path=source_path,
    )


def fragment_profile(source_type: str, source: str, timestamp: str = DEFAULT_TIMESTAMP) -> CandidateProfile:
    profile = CandidateProfile(source_types=[source_type])
    profile.add_provenance(source, "parse", 0.5, f"parsed from {source_type}")
    if profile.provenance:
        profile.provenance[-1].timestamp = timestamp
    return profile
