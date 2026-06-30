from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from ..models.candidate import CandidateProfile, ValueRecord
from ..pipeline.config_store import load_config
from ..utils.email_utils import is_valid_email
from ..utils.phone_utils import is_valid_phone


@dataclass(slots=True)
class ConfidenceWeights:
    record_floor: float = 0.55
    name_only: float = 0.35
    name_email: float = 0.60
    name_email_phone: float = 0.80
    direct_contact_only: float = 0.55
    github: float = 0.70
    linkedin: float = 0.70
    resume: float = 0.75
    multi_source: float = 0.95
    source_reliability: dict[str, float] = field(default_factory=lambda: {
        "resume": 0.95,
        "linkedin": 0.93,
        "ats": 0.92,
        "github": 0.88,
        "csv": 0.90,
        "json": 0.86,
        "notes": 0.60,
    })


class ConfidenceScorer:
    def __init__(self, weights_path: str | Path | None = None) -> None:
        self.weights = self._load_weights(weights_path)

    def score(self, profile: CandidateProfile) -> CandidateProfile:
        value_scores = []
        if profile.name:
            profile.name.confidence = self._name_score(profile)
            value_scores.append(profile.name.confidence)
        for collection in (profile.emails, profile.phones, profile.skills, profile.locations):
            for record in collection:
                record.confidence = self._score_record(record, collection)
                value_scores.append(record.confidence)
        for record in profile.links.values():
            record.confidence = self._score_record(record, list(profile.links.values()))
            value_scores.append(record.confidence)
        if profile.summary:
            profile.summary.confidence = self._summary_score(profile)
            value_scores.append(profile.summary.confidence)
        profile.confidence = self._overall_score(profile, value_scores)
        profile.extra["confidence_explanation"] = self._explanation(profile, value_scores)
        profile.explanation.append(f"overall confidence {profile.confidence:.2f}")
        return profile

    def _score_record(self, record: ValueRecord, collection: list[ValueRecord]) -> float:
        support = self._support_count(record, collection)
        base = max(record.confidence, self.weights.record_floor)
        reliability = self._source_reliability(record.source)
        support_bonus = min(0.18, max(0, support - 1) * 0.06)
        validity_bonus = 0.0
        value = str(record.value)
        if "@" in value and is_valid_email(value):
            validity_bonus += 0.08
        if value.startswith("+") and is_valid_phone(value):
            validity_bonus += 0.08
        confidence = base * 0.55 + reliability * 0.25 + support_bonus + validity_bonus
        return round(min(0.99, confidence), 4)

    def _support_count(self, record: ValueRecord, collection: list[ValueRecord]) -> int:
        sources = set(record.sources or [record.source])
        for item in collection:
            if item.value == record.value:
                sources.update(item.sources or [item.source])
        return len(sources)

    def _name_score(self, profile: CandidateProfile) -> float:
        if not profile.name or not profile.name.value:
            return 0.0
        support = 0
        if profile.emails:
            support += 1
        if profile.phones:
            support += 1
        if any(key in {"github", "linkedin"} for key in profile.links):
            support += 1
        if profile.experience or profile.education:
            support += 1
        if support == 0:
            return min(self.weights.name_only, 0.24)
        if support == 1 and profile.emails:
            return min(self.weights.name_email, 0.24 + support * 0.12)
        if support >= 2 and profile.emails and profile.phones:
            return min(self.weights.name_email_phone, 0.24 + support * 0.16)
        return min(self.weights.name_only, 0.24 + support * 0.03)

    def _summary_score(self, profile: CandidateProfile) -> float:
        if not profile.summary or not profile.summary.value:
            return 0.0
        support = 1 + int(bool(profile.experience)) + int(bool(profile.skills))
        return min(0.99, 0.78 + min(0.16, support * 0.04))

    def _overall_score(self, profile: CandidateProfile, value_scores: list[float]) -> float:
        if not profile.has_minimum_identity():
            return 0.0
        score = 0.3
        if profile.name and profile.name.value:
            score += min(0.14, self._name_score(profile))
        if profile.emails:
            score += 0.16
        if profile.phones:
            score += 0.12
        if "github" in profile.links:
            score += 0.08 * self._source_reliability("github")
        if "linkedin" in profile.links:
            score += 0.08 * self._source_reliability("linkedin")
        if any(source.startswith("resume") for source in profile.source_types):
            score += 0.10 * self._highest_reliability(profile.source_types)
        distinct_sources = len({source for source in profile.source_types if source})
        identity_types = len(profile.identity_components() & {"email", "phone", "github", "linkedin", "resume"})
        if distinct_sources > 1 or identity_types > 2:
            score += 0.10
        if profile.experience or profile.education:
            score += 0.05
        if value_scores:
            score += min(0.12, sum(value_scores) / len(value_scores) * 0.12)
        if profile.extra.get("field_conflicts"):
            score -= 0.08
        if profile.warnings:
            score -= min(0.05, len(profile.warnings) * 0.01)
        return round(min(0.99, max(0.0, score)), 4)

    def _load_weights(self, weights_path: str | Path | None) -> ConfidenceWeights:
        path = Path(weights_path) if weights_path else Path(__file__).resolve().parents[1] / "config" / "confidence_weights.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            allowed = set(ConfidenceWeights.__dataclass_fields__)
            filtered = {key: float(value) for key, value in data.items() if key in allowed and key != "source_reliability"}
            if "source_reliability" in data and isinstance(data["source_reliability"], dict):
                filtered["source_reliability"] = {str(key): float(value) for key, value in data["source_reliability"].items()}
            weights = ConfidenceWeights(**filtered)
        else:
            weights = ConfidenceWeights()
        source_weights = load_config("source_weights.json") or {}
        if isinstance(source_weights, dict) and source_weights:
            weights.source_reliability.update({str(key).lower(): float(value) for key, value in source_weights.items()})
        return weights

    def _source_reliability(self, source: str | None) -> float:
        if not source:
            return 0.8
        for key, value in self.weights.source_reliability.items():
            if source.startswith(key):
                return float(value)
        return 0.8

    def _highest_reliability(self, source_types: list[str]) -> float:
        if not source_types:
            return 0.8
        return max(self._source_reliability(source) for source in source_types)

    def _explanation(self, profile: CandidateProfile, value_scores: list[float]) -> dict[str, object]:
        source_reliability = max((self._source_reliability(source) for source in profile.source_types), default=0.8)
        return {
            "validation": "passed" if not profile.warnings else "warnings present",
            "agreement": round(sum(value_scores) / len(value_scores), 4) if value_scores else 0.0,
            "sources": len({source for source in profile.source_types if source}),
            "source_reliability": round(source_reliability, 4),
            "conflicts": bool(profile.extra.get("field_conflicts")),
            "missing_values": not profile.has_minimum_identity(),
        }
