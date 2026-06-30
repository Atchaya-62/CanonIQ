from __future__ import annotations

from collections import defaultdict
from hashlib import sha1
from pathlib import Path
import json

from ..models.candidate import CandidateProfile, ValueRecord
from ..models.education import EducationRecord
from ..models.experience import ExperienceRecord
from ..pipeline.config_store import load_config


class CandidateMerger:
    def __init__(self, source_weights_path: str | Path | None = None) -> None:
        self.source_weights = self._load_source_weights(source_weights_path)

    def merge(self, cluster: list[CandidateProfile]) -> CandidateProfile:
        merged = CandidateProfile()
        merged.candidate_id = self._candidate_id(cluster)
        merged.name = self._best_scalar([profile.name for profile in cluster if profile.name])
        merged.years_experience = self._best_years_experience(cluster)
        merged.summary = self._best_scalar([profile.summary for profile in cluster if profile.summary])
        merged.country = self._best_scalar([profile.country for profile in cluster if profile.country])
        merged.emails = self._merge_values(cluster, "emails")
        merged.phones = self._merge_values(cluster, "phones")
        merged.skills = self._merge_values(cluster, "skills")
        merged.locations = self._merge_values(cluster, "locations")
        merged.links = self._merge_links(cluster)
        merged.experience = self._merge_experience(cluster)
        merged.education = self._merge_education(cluster)
        merged.notes = self._merge_notes(cluster)
        merged.source_types = sorted({source for profile in cluster for source in profile.source_types})
        merged.explanation = self._merge_explanations(cluster, merged)
        merged.warnings = sorted({warning for profile in cluster for warning in profile.warnings})
        merged.extra["aliases"] = self._merge_aliases(cluster, merged)
        merged.extra["merge_score"] = round(sum(self._profile_merge_score(profile) for profile in cluster), 4)
        merged.extra["merge_threshold"] = 1.0
        merged.extra["merge_decision"] = "merged" if len(cluster) > 1 else "singleton"
        merged.extra["field_conflicts"] = self._field_conflicts(cluster, merged)
        merged.extra["field_resolvers"] = self._resolver_summary(merged)
        return merged

    def _candidate_id(self, cluster: list[CandidateProfile]) -> str:
        seed_parts = []
        for profile in cluster:
            if profile.emails:
                seed_parts.append(sorted(record.value for record in profile.emails)[0])
            elif profile.name and profile.name.value:
                seed_parts.append(profile.name.value)
        seed = "|".join(sorted(seed_parts)) or "unknown"
        return "cand_" + sha1(seed.encode("utf-8")).hexdigest()[:16]

    def _best_scalar(self, records: list[ValueRecord]) -> ValueRecord | None:
        if not records:
            return None
        selected = sorted(records, key=lambda record: (-self._record_score(record), str(record.value).lower()))[0]
        selected.sources = sorted({record.source_path or record.source for record in records if record.source_path or record.source})
        if not selected.source_path:
            selected.source_path = next((record.source_path for record in records if record.source_path), None)
        selected.reason = "Highest weighted confidence across sources"
        return selected

    def _best_years_experience(self, cluster: list[CandidateProfile]) -> int | None:
        values = [profile.years_experience for profile in cluster if profile.years_experience is not None]
        return max(values) if values else None

    def _merge_values(self, cluster: list[CandidateProfile], field_name: str) -> list[ValueRecord]:
        grouped: dict[str, list[ValueRecord]] = defaultdict(list)
        for profile in cluster:
            for record in getattr(profile, field_name):
                grouped[str(record.value).lower()].append(record)
        merged = []
        for key, records in grouped.items():
            best = sorted(records, key=lambda record: (-self._record_score(record), record.source))[0]
            best.reason = f"merged from {len(records)} source(s)"
            best.sources = sorted({record.source_path or record.source for record in records if record.source_path or record.source})
            merged.append(best)
        return sorted(merged, key=lambda record: (-record.confidence, str(record.value).lower()))

    def _merge_links(self, cluster: list[CandidateProfile]) -> dict[str, ValueRecord]:
        merged: dict[str, ValueRecord] = {}
        for profile in cluster:
            for key, record in profile.links.items():
                if key not in merged or record.confidence > merged[key].confidence:
                    merged[key] = record
        return dict(sorted(merged.items()))

    def _merge_experience(self, cluster: list[CandidateProfile]) -> list[ExperienceRecord]:
        grouped: dict[tuple[str | None, str | None, str | None], list[ExperienceRecord]] = defaultdict(list)
        for profile in cluster:
            for record in profile.experience:
                grouped[record.key()].append(record)
        result = []
        for key, records in grouped.items():
            result.append(sorted(records, key=lambda record: (record.start_date or "", record.end_date or "", record.source or ""))[0])
            result[-1].provenance = [{"source": record.source, "confidence": record.confidence, "reason": "merged experience"} for record in records if record.source]
        return sorted(result, key=lambda record: ((record.company or ""), (record.title or ""), (record.start_date or "")))

    def _merge_education(self, cluster: list[CandidateProfile]) -> list[EducationRecord]:
        grouped: dict[tuple[str | None, str | None, str | None], list[EducationRecord]] = defaultdict(list)
        for profile in cluster:
            for record in profile.education:
                grouped[record.key()].append(record)
        result = []
        for key, records in grouped.items():
            result.append(sorted(records, key=lambda record: (record.start_date or "", record.end_date or "", record.source or ""))[0])
            result[-1].provenance = [{"source": record.source, "confidence": record.confidence, "reason": "merged education"} for record in records if record.source]
        return sorted(result, key=lambda record: ((record.institution or ""), (record.degree or ""), (record.field_of_study or "")))

    def _merge_notes(self, cluster: list[CandidateProfile]) -> list[ValueRecord]:
        notes: list[ValueRecord] = []
        for profile in cluster:
            notes.extend(profile.notes)
        unique = {}
        for record in notes:
            key = str(record.value).strip().lower()
            if key and key not in unique:
                unique[key] = record
        return sorted(unique.values(), key=lambda record: str(record.value).lower())

    def _merge_explanations(self, cluster: list[CandidateProfile], merged: CandidateProfile) -> list[str]:
        explanations = [f"Merged {len(cluster)} data sources"]
        if merged.name:
            explanations.append(f"Name ← {self._source_label(merged.name)}")
        if merged.emails:
            explanations.append(f"Email ← {self._source_label(merged.emails[0])}")
        if merged.phones:
            explanations.append(f"Phone ← {self._source_label(merged.phones[0])}")
        if merged.summary:
            explanations.append(f"Headline ← {self._source_label(merged.summary)}")
        if merged.links:
            explanations.append("Links merged from available profiles")
        if merged.notes:
            explanations.append(f"Attached {len(merged.notes)} note(s)")
        return explanations

    def _merge_aliases(self, cluster: list[CandidateProfile], merged: CandidateProfile) -> list[str]:
        aliases = []
        selected = str(merged.name.value).strip().lower() if merged.name and merged.name.value else ""
        for profile in cluster:
            if profile.name and profile.name.value:
                value = str(profile.name.value).strip()
                if value and value.lower() != selected:
                    aliases.append(value)
        return sorted(set(aliases), key=str.lower)

    def _field_conflicts(self, cluster: list[CandidateProfile], merged: CandidateProfile) -> dict[str, object]:
        conflicts: dict[str, object] = {}
        for field_name in ("emails", "phones"):
            records = [record for profile in cluster for record in getattr(profile, field_name) if record.value]
            values = sorted({str(record.value) for record in records})
            if len(values) > 1:
                primary_record = sorted(records, key=lambda record: (-self._record_score(record), str(record.value).lower()))[0]
                conflicts[field_name] = {
                    "status": "conflict",
                    "primary": str(primary_record.value),
                    "alternate": [value for value in values if value != str(primary_record.value)],
                    "reason": "Different values across sources.",
                }
        return conflicts

    def _resolver_summary(self, merged: CandidateProfile) -> dict[str, str]:
        return {
            "name": self._source_label(merged.name) if merged.name else "n/a",
            "email": self._source_label(merged.emails[0]) if merged.emails else "n/a",
            "phone": self._source_label(merged.phones[0]) if merged.phones else "n/a",
            "headline": self._source_label(merged.summary) if merged.summary else "n/a",
            "location": self._source_label(merged.locations[0]) if merged.locations else "n/a",
            "skills": self._source_label(merged.skills[0]) if merged.skills else "n/a",
        }

    def _source_label(self, record: ValueRecord) -> str:
        label = record.source_path or record.source or "unknown"
        return self._friendly_source_label(label)

    def _friendly_source_label(self, value: str) -> str:
        name = value.replace("\\", "/").rsplit("/", 1)[-1].lower()
        mapping = {
            "recruiter.csv": "Recruiter CSV",
            "candidate.csv": "Recruiter CSV",
            "ats.json": "ATS JSON",
            "linkedin.json": "LinkedIn Profile",
            "github.json": "GitHub Profile",
            "resume.pdf": "Resume",
            "resume.txt": "Resume",
            "notes.txt": "Recruiter Notes",
            "recruiter_notes.txt": "Recruiter Notes",
        }
        return mapping.get(name, value)

    def _profile_merge_score(self, profile: CandidateProfile) -> float:
        evidence = 0.0
        if profile.name and profile.name.value:
            evidence = max(evidence, self._record_score(profile.name))
        for collection in (profile.emails, profile.phones, profile.skills, profile.locations, profile.notes):
            if collection:
                evidence = max(evidence, max(self._record_score(record) for record in collection if record.value))
        for record in profile.links.values():
            if record and record.value:
                evidence = max(evidence, self._record_score(record))
        if profile.summary and profile.summary.value:
            evidence = max(evidence, self._record_score(profile.summary))
        if profile.experience or profile.education:
            evidence = max(evidence, 0.6)
        return max(0.0, min(1.0, evidence))

    def _record_score(self, record: ValueRecord) -> float:
        source = (record.source_path or record.source or "").split("/")[-1].split("\\")[-1].lower()
        reliability = self._source_reliability(source)
        support = len(set(record.sources or [record.source_path or record.source]))
        return round(min(1.0, float(record.confidence) * 0.7 + reliability * 0.25 + min(0.05, support * 0.01)), 4)

    def _source_reliability(self, source: str | None) -> float:
        if not source:
            return 0.8
        source = source.lower()
        for key, value in self.source_weights.items():
            if key and key.lower() in source:
                return float(value)
        if source.startswith("linkedin"):
            return 0.9
        if source.startswith("github"):
            return 0.85
        if source.startswith("resume"):
            return 0.92
        if source.startswith("ats"):
            return 0.95
        if source.startswith("notes"):
            return 0.6
        if source.startswith("csv"):
            return 0.9
        return 0.8

    def _load_source_weights(self, source_weights_path: str | Path | None) -> dict[str, float]:
        if source_weights_path:
            path = Path(source_weights_path)
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    return {str(key).lower(): float(value) for key, value in data.items()}
                except json.JSONDecodeError:
                    return {}
        data = load_config("source_weights.json") or {}
        if isinstance(data, dict) and data:
            return {str(key).lower(): float(value) for key, value in data.items()}
        return {}
