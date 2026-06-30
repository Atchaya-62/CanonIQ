from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path

from ..models.candidate import CandidateProfile
from ..models.schemas import ProjectionConfig
from ..utils.date_utils import current_month
from ..utils.location_utils import normalize_country, normalize_location
from ..utils.text_utils import clean_text


class ProjectionEngine:
    def __init__(self, config: ProjectionConfig | None = None):
        self.config = config or ProjectionConfig(fields={})

    @classmethod
    def from_file(cls, path: str | Path) -> "ProjectionEngine":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(ProjectionConfig.model_validate(data))

    def project(self, profile: CandidateProfile) -> dict:
        if self.config.format == "canonical":
            return self._canonical_project(profile)
        payload = self._to_dict(profile)
        if not self.config.fields:
            return payload
        projected = {}
        for path, field_config in self.config.fields.items():
            if field_config.remove:
                continue
            try:
                value = self._get_path(payload, path)
                if value is None:
                    value = self._missing_value(field_config)
                if field_config.normalize and isinstance(value, str):
                    value = clean_text(value)
                if value is _ProjectionSkip:
                    continue
                if value is _ProjectionError:
                    raise ValueError(f"Projection failed for field '{path}'")
            except Exception as exc:  # pragma: no cover - defensive fallback
                value = self._error_value(field_config, path, exc)
                if value is _ProjectionSkip:
                    continue
                if value is _ProjectionError:
                    raise
            target = field_config.rename or path
            self._set_path(projected, target, value)
        return projected

    def _canonical_project(self, profile: CandidateProfile) -> dict:
        name_record = self._selected_record(profile.name)
        email_record = self._selected_record(profile.emails)
        phone_record = self._selected_record(profile.phones)
        location, location_provenance = self._location_payload(profile)
        experience = profile.years_experience if profile.years_experience is not None else self._years_experience(profile)
        return {
            "name": str(name_record.value) if name_record and name_record.value is not None else None,
            "primary_email": str(email_record.value) if email_record and email_record.value is not None else None,
            "primary_phone": str(phone_record.value) if phone_record and phone_record.value is not None else None,
            "experience": experience,
            "location": location,
            "all_skills": self._alphabetical_values(profile.skills),
            "overall_confidence": profile.confidence,
            "provenance": self._compact_provenance(profile, location_provenance),
        }

    def _selected_record(self, records):
        if records is None:
            return None
        if not isinstance(records, (list, tuple)):
            records = [records]
        selected = None
        for record in records or []:
            if record is None or getattr(record, "value", None) in (None, ""):
                continue
            if selected is None:
                selected = record
                continue
            if self._record_rank(record) > self._record_rank(selected):
                selected = record
            elif self._record_rank(record) == self._record_rank(selected) and str(record.value).lower() < str(selected.value).lower():
                selected = record
        return selected

    def _record_rank(self, record) -> tuple[float, str]:
        return (float(getattr(record, "confidence", 0.0)), str(getattr(record, "value", "")).lower())

    def _missing_value(self, field_config) -> object:
        return self._fallback_value(field_config, field_config.on_missing)

    def _error_value(self, field_config, path: str, exc: Exception):
        fallback = self._fallback_value(field_config, field_config.on_error)
        if fallback is _ProjectionSkip:
            return _ProjectionSkip
        if fallback is _ProjectionError:
            raise ValueError(f"Projection failed for field '{path}'") from exc
        return fallback

    def _fallback_value(self, field_config, mode: str):
        if mode == "omit":
            return _ProjectionSkip
        if mode == "null":
            return None
        if mode == "empty":
            return []
        if mode == "default":
            return field_config.default
        if mode == "error":
            return _ProjectionError
        return None

    def _string_values(self, records) -> list[str]:
        ranked = sorted(
            (
                (float(getattr(record, "confidence", 0.0)), str(getattr(record, "value", "")))
                for record in records
                if getattr(record, "value", None)
            ),
            key=lambda item: (-item[0], item[1].lower()),
        )
        values: list[str] = []
        seen: set[str] = set()
        for _confidence, value in ranked:
            if value not in seen:
                seen.add(value)
                values.append(value)
        return values

    def _alphabetical_values(self, records) -> list[str]:
        values = sorted({str(record.value) for record in records if getattr(record, "value", None)}, key=lambda item: item.lower())
        return values

    def _location_payload(self, profile: CandidateProfile) -> tuple[dict[str, str | None], dict[str, object] | None]:
        city = None
        country = profile.country.value if profile.country and profile.country.value else None
        options: list[tuple[float, str]] = []
        for record in profile.locations:
            if record.value:
                options.append((float(getattr(record, "confidence", 0.0)), str(record.value)))
        for record in profile.experience:
            if record.location:
                options.append((0.65, str(record.location)))
        source_location = None
        if options:
            def location_score(item: tuple[float, str]) -> tuple[int, float]:
                confidence, value = item
                return (1 if "," in value else 0, confidence)

            source_location = sorted(options, key=location_score, reverse=True)[0][1]
        if source_location:
            normalized = normalize_location(str(source_location))
            if normalized:
                parts = [part.strip() for part in normalized.split(",") if part.strip()]
                if parts:
                    city = parts[0]
                    if len(parts) > 1 and not country:
                        country = normalize_country(parts[-1])
        provenance = None
        if source_location:
            provenance = {
                "value": source_location,
                "source": self._first_source(profile.locations, source_location) or self._first_source_from_experience(profile, source_location),
                "seen_in": self._seen_in(profile.locations, source_location) or self._seen_in_experience(profile, source_location),
                "confidence": self._first_confidence(profile.locations, source_location, default=0.65),
                "selected_from": len(options),
                "reason": "Highest-confidence location evidence",
            }
        return {"city": city, "country": country}, provenance

    def _headline(self, profile: CandidateProfile) -> tuple[str | None, dict[str, object] | None]:
        if profile.summary and profile.summary.value:
            return str(profile.summary.value), self._record_provenance(profile.summary, "headline")
        if profile.experience:
            titles = [record.title for record in profile.experience if record.title]
            if titles:
                record = next((record for record in profile.experience if record.title), None)
                return titles[0], self._nested_provenance(record, "headline") if record else None
        return None, None

    def _years_experience(self, profile: CandidateProfile) -> int | None:
        intervals: list[tuple[int, int]] = []
        seen: set[tuple[str | None, str | None, str | None]] = set()
        for record in profile.experience:
            key = record.key()
            if key in seen:
                continue
            seen.add(key)
            interval = self._interval_months(record.start_date, record.end_date, record.is_current)
            if interval:
                intervals.append(interval)
        months = self._merged_months(intervals)
        if months <= 0:
            return None
        return max(0, round(months / 12))

    def _interval_months(self, start_date: str | None, end_date: str | None, is_current: bool) -> tuple[int, int] | None:
        start = self._ym(start_date)
        end = self._ym(end_date if end_date else current_month()) if is_current or end_date is None else self._ym(end_date)
        if start is None or end is None or end < start:
            return None
        return start, end

    def _merged_months(self, intervals: list[tuple[int, int]]) -> int:
        if not intervals:
            return 0
        ordered = sorted(intervals)
        merged: list[tuple[int, int]] = [ordered[0]]
        for start, end in ordered[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end + 1:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        total = 0
        for start, end in merged:
            start_year, start_month = divmod(start, 100)
            end_year, end_month = divmod(end, 100)
            total += (end_year - start_year) * 12 + (end_month - start_month) + 1
        return total

    def _ym(self, value: str | None) -> int | None:
        if not value or len(value) < 7:
            return None
        try:
            return int(value[:4]) * 100 + int(value[5:7])
        except ValueError:
            return None

    def _to_dict(self, value):
        if is_dataclass(value):
            return {key: self._to_dict(item) for key, item in asdict(value).items()}
        if isinstance(value, list):
            return [self._to_dict(item) for item in value]
        if isinstance(value, dict):
            return {key: self._to_dict(item) for key, item in value.items()}
        return value

    def _get_path(self, payload: dict, path: str):
        current = payload
        for part in path.split("."):
            if isinstance(current, list):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    return None
            elif isinstance(current, dict):
                current = current.get(part)
            else:
                return None
            if current is None:
                return None
        return current

    def _set_path(self, payload: dict, path: str, value) -> None:
        parts = path.split(".")
        current = payload
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value

    def _field_provenance(self, profile: CandidateProfile, location_provenance: dict[str, object] | None, headline_provenance: dict[str, object] | None) -> dict[str, object]:
        return {
            "full_name": self._record_provenance(profile.name, "full_name"),
            "emails": [self._record_provenance(record, "emails") for record in profile.emails],
            "phones": [self._record_provenance(record, "phones") for record in profile.phones],
            "location": location_provenance,
            "headline": headline_provenance,
            "skills": [self._record_provenance(record, "skills") for record in profile.skills],
            "experience": [self._nested_provenance(record, "experience") for record in profile.experience],
            "education": [self._nested_provenance(record, "education") for record in profile.education],
            "notes": [self._record_provenance(record, "notes") for record in profile.notes],
        }

    def _compact_provenance(self, profile: CandidateProfile, location_provenance: dict[str, object] | None = None) -> list[dict[str, str]]:
        provenance: list[dict[str, str]] = []
        if profile.name:
            provenance.extend(self._provenance_entries(profile.name, "name", "priority_merge"))
        email_record = self._selected_record(profile.emails)
        if email_record:
            provenance.extend(self._provenance_entries(email_record, "primary_email", "exact_match"))
        phone_record = self._selected_record(profile.phones)
        if phone_record:
            provenance.extend(self._provenance_entries(phone_record, "primary_phone", "exact_match"))
        experience_record = self._selected_record(profile.experience)
        if experience_record:
            provenance.extend(self._provenance_entries(experience_record, "experience", "priority_merge"))
        if location_provenance and location_provenance.get("source"):
            provenance.append(
                {
                    "field": "location",
                    "source": self._label_source(str(location_provenance.get("source"))),
                    "method": "highest_confidence",
                }
            )
        skill_record = self._selected_record(profile.skills)
        if skill_record:
            provenance.extend(self._provenance_entries(skill_record, "all_skills", "priority_merge"))
        return provenance

    def _provenance_entries(self, record, field: str, method: str) -> list[dict[str, str]]:
        if record is None or getattr(record, "value", None) in (None, ""):
            return []
        sources = list(getattr(record, "sources", []) or [])
        if field == "emails" and sources:
            return [{"field": field, "source": self._label_source(source), "method": method} for source in dict.fromkeys(source for source in sources if source)]
        source = getattr(record, "source_path", None) or getattr(record, "source", None)
        if not source and sources:
            source = sources[0]
        if not source:
            return []
        return [{"field": field, "source": self._label_source(source), "method": method}]

    def _record_provenance(self, record, field_name: str) -> dict[str, object] | None:
        if record is None or getattr(record, "value", None) is None:
            return None
        sources = list(getattr(record, "sources", []) or ([getattr(record, "source_path", None) or getattr(record, "source", None)] if getattr(record, "source_path", None) or getattr(record, "source", None) else []))
        return {
            "value": self._to_dict(getattr(record, "value", None)),
            "source": getattr(record, "source_path", None) or getattr(record, "source", None),
            "confidence": float(getattr(record, "confidence", 0.0)),
            "selected_from": len(set(source for source in sources if source)) or 1,
            "seen_in": [source for source in dict.fromkeys(source for source in sources if source)],
            "reason": getattr(record, "reason", f"selected {field_name}"),
        }

    def _nested_provenance(self, record, field_name: str) -> dict[str, object] | None:
        if record is None:
            return None
        payload = self._to_dict(record)
        payload["provenance"] = list(getattr(record, "provenance", []) or [])
        payload["field"] = field_name
        if getattr(record, "source_path", None):
            payload["source"] = record.source_path
        return payload

    def _first_source(self, records, value: str) -> str | None:
        for record in records:
            if str(getattr(record, "value", "")) == value:
                return getattr(record, "source_path", None) or getattr(record, "source", None)
        return None

    def _first_source_from_experience(self, profile: CandidateProfile, value: str) -> str | None:
        for record in profile.experience:
            if str(record.location or "") == value:
                return record.source_path or record.source
        return None

    def _seen_in(self, records, value: str) -> list[str]:
        return [source for source in dict.fromkeys(
            (getattr(record, "source_path", None) or getattr(record, "source", None))
            for record in records
            if str(getattr(record, "value", "")) == value and (getattr(record, "source_path", None) or getattr(record, "source", None))
        )]

    def _seen_in_experience(self, profile: CandidateProfile, value: str) -> list[str]:
        return [source for source in dict.fromkeys(
            (record.source_path or record.source)
            for record in profile.experience
            if str(record.location or "") == value and (record.source_path or record.source)
        )]

    def _first_confidence(self, records, value: str, default: float = 0.0) -> float:
        for record in records:
            if str(getattr(record, "value", "")) == value:
                return float(getattr(record, "confidence", default))
        return default

    def _label_source(self, value: str | None) -> str:
        if not value:
            return "unknown"
        text = str(value).replace("\\", "/")
        basename = text.rsplit("/", 1)[-1]
        mapping = {
            "candidate.csv": "Recruiter CSV",
            "recruiter.csv": "Recruiter CSV",
            "ats.json": "ATS JSON",
            "linkedin.json": "LinkedIn Profile",
            "github.json": "GitHub Profile",
            "resume.pdf": "Resume",
            "resume.txt": "Resume",
            "notes.txt": "Recruiter Notes",
            "recruiter_notes.txt": "Recruiter Notes",
            "linkedin": "LinkedIn Profile",
            "github": "GitHub Profile",
            "resume": "Resume",
            "ats_json": "ATS JSON",
            "csv": "CSV",
            "json": "JSON",
            "notes": "Recruiter Notes",
        }
        return mapping.get(basename.lower(), basename)


class _ProjectionSentinel:
    pass


_ProjectionSkip = _ProjectionSentinel()
_ProjectionError = _ProjectionSentinel()
