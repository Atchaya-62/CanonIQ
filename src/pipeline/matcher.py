from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from functools import lru_cache

from ..models.candidate import CandidateProfile
from ..pipeline.config_store import load_config
from ..utils.email_utils import normalize_email
from ..utils.location_utils import normalize_location
from ..utils.phone_utils import normalize_phone
from ..utils.skill_utils import canonicalize_skills
from ..utils.string_similarity import normalized_similarity, token_sort_similarity
from ..utils.text_utils import clean_text, remove_accents


@dataclass(slots=True)
class MatchDecision:
    left_index: int
    right_index: int
    score: float
    reasons: list[str] = field(default_factory=list)
    evidence: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class MatchWeights:
    threshold: float = 0.85
    email: float = 1.0
    phone: float = 0.9
    github: float = 0.85
    linkedin: float = 0.85
    name: float = 0.75
    location: float = 0.3
    company: float = 0.4
    skill: float = 0.25
    education: float = 0.3
    notes: float = 0.1
    headline: float = 0.35
    experience: float = 0.3


class CandidateMatcher:
    def __init__(self, threshold: float = 0.85, weights_path: str | Path | None = None) -> None:
        self.weights = self._load_weights(weights_path)
        self.weights.threshold = threshold
        self.source_weights = self._load_source_weights()
        self._name_variant_groups = (
            {"sara", "sarah"},
            {"jon", "john"},
            {"bob", "robert"},
            {"mike", "michael"},
            {"liz", "elizabeth"},
            {"alex", "alexander"},
        )

    def cluster(self, profiles: list[CandidateProfile]) -> tuple[list[list[CandidateProfile]], list[MatchDecision]]:
        ordered = sorted(profiles, key=self._profile_key)
        parent = list(range(len(ordered)))
        decisions: list[MatchDecision] = []
        for left_index in range(len(ordered)):
            for right_index in range(left_index + 1, len(ordered)):
                left = ordered[left_index]
                right = ordered[right_index]
                score, reasons = self.score(left, right)
                if score >= self.weights.threshold:
                    self._union(parent, left_index, right_index)
                    decisions.append(MatchDecision(left_index, right_index, score, reasons, self._explain(left, right)))
        clusters: dict[int, list[CandidateProfile]] = {}
        for index, profile in enumerate(ordered):
            root = self._find(parent, index)
            clusters.setdefault(root, []).append(profile)
        ordered_clusters = [clusters[key] for key in sorted(clusters)]
        return ordered_clusters, decisions

    def _load_weights(self, weights_path: str | Path | None) -> MatchWeights:
        path = Path(weights_path) if weights_path else Path(__file__).resolve().parents[1] / "config" / "matching_weights.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            allowed = set(MatchWeights.__dataclass_fields__)
            filtered = {key: float(value) for key, value in data.items() if key in allowed}
            return MatchWeights(**filtered)
        return MatchWeights()

    def _load_source_weights(self) -> dict[str, float]:
        data = load_config("source_weights.json") or {}
        if isinstance(data, dict) and data:
            return {str(key).lower(): float(value) for key, value in data.items()}
        weights = load_config("confidence_weights.json") or {}
        source_weights = weights.get("source_reliability") if isinstance(weights, dict) else {}
        if isinstance(source_weights, dict):
            return {str(key).lower(): float(value) for key, value in source_weights.items()}
        return {"resume": 0.95, "linkedin": 0.93, "ats": 0.92, "github": 0.88, "csv": 0.90, "json": 0.86, "notes": 0.60}

    def _find(self, parent: list[int], index: int) -> int:
        if parent[index] != index:
            parent[index] = self._find(parent, parent[index])
        return parent[index]

    def _union(self, parent: list[int], left: int, right: int) -> None:
        left_root = self._find(parent, left)
        right_root = self._find(parent, right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    def score(self, left: CandidateProfile, right: CandidateProfile) -> tuple[float, list[str]]:
        signals = self._signals(left, right)
        score = round(min(1.0, sum(score for score, matched, _reason in signals if matched and score > 0.0)), 4)
        reasons = [reason for _score, matched, reason in signals if matched]
        return score, reasons

    def _signals(self, left: CandidateProfile, right: CandidateProfile):
        left_emails = set(self._normalized_emails(left))
        right_emails = set(self._normalized_emails(right))
        left_phones = set(self._normalized_phones(left))
        right_phones = set(self._normalized_phones(right))
        left_links = {record.value for record in left.links.values()}
        right_links = {record.value for record in right.links.values()}
        left_skills = set(self._normalized_skills(left))
        right_skills = set(self._normalized_skills(right))
        left_company = self._normalized_experience_fields(left.experience, "company")
        right_company = self._normalized_experience_fields(right.experience, "company")
        left_school = self._normalized_experience_fields(left.education, "institution")
        right_school = self._normalized_experience_fields(right.education, "institution")
        left_city = self._city(left)
        right_city = self._city(right)
        left_name = self._normalized_name(self._name(left))
        right_name = self._normalized_name(self._name(right))
        left_notes = self._notes(left)
        right_notes = self._notes(right)
        left_headline = self._normalized_name(self._headline(left))
        right_headline = self._normalized_name(self._headline(right))
        enrichment_bonus = self._enrichment_bonus(left, right, left_name, right_name)
        name_similarity = self._name_similarity(left_name, right_name)
        return [
            (self.weights.email * self._set_similarity(left_emails, right_emails), bool(left_emails & right_emails), "matched email"),
            (self.weights.phone * self._set_similarity(left_phones, right_phones), bool(left_phones & right_phones), "matched phone"),
            (self.weights.github * self._url_match(left_links, right_links, "github.com"), self._url_match(left_links, right_links, "github.com"), "matched github"),
            (self.weights.linkedin * self._url_match(left_links, right_links, "linkedin.com"), self._url_match(left_links, right_links, "linkedin.com"), "matched linkedin"),
            (self.weights.name * name_similarity + (0.1 if name_similarity >= 0.95 else 0.0), bool(left_name and right_name), "matched name"),
            (enrichment_bonus, enrichment_bonus > 0.0, "matched profile enrichment"),
            (self.weights.location * self._set_similarity({left_city}, {right_city}, minimum=0.8), bool(left_city and right_city), "matched location"),
            (self.weights.company * self._set_similarity(left_company, right_company, minimum=0.85), bool(left_company and right_company), "matched company"),
            (self.weights.education * self._set_similarity(left_school, right_school, minimum=0.85), bool(left_school and right_school), "matched education"),
            (self.weights.skill * self._set_similarity(left_skills, right_skills, minimum=0.85), bool(left_skills and right_skills), "matched skills"),
            (self.weights.notes * self._set_similarity(left_notes, right_notes, minimum=0.75), bool(left_notes and right_notes), "matched notes"),
            (self.weights.headline * self._set_similarity({left_headline}, {right_headline}, minimum=0.85), bool(left_headline and right_headline), "matched headline"),
            (self.weights.experience * self._set_similarity(self._normalized_experience(left.experience), self._normalized_experience(right.experience), minimum=0.85), bool(left.experience and right.experience), "matched experience"),
        ]

    def _set_similarity(self, left: set[str], right: set[str], minimum: float = 0.0) -> float:
        if not left or not right:
            return 0.0
        best = 0.0
        for left_value in left:
            for right_value in right:
                best = max(best, normalized_similarity(left_value, right_value))
        return best if best >= minimum else 0.0

    def _enrichment_bonus(self, left: CandidateProfile, right: CandidateProfile, left_name: str, right_name: str) -> float:
        if self._name_similarity(left_name, right_name) < 0.95:
            return 0.0
        left_identity = bool(left.emails or left.phones)
        right_identity = bool(right.emails or right.phones)
        left_enrichment = bool(left.summary or left.locations or left.skills or left.experience or left.education)
        right_enrichment = bool(right.summary or right.locations or right.skills or right.experience or right.education)
        if left_identity and right_enrichment and not right_identity:
            return 0.25
        if right_identity and left_enrichment and not left_identity:
            return 0.25
        return 0.0

    def _normalized_experience_fields(self, records, attribute: str) -> set[str]:
        values = set()
        for record in records:
            value = getattr(record, attribute, None)
            if not value:
                continue
            normalized = self._normalized_name(str(value))
            if normalized:
                values.add(normalized)
        return values

    def _normalized_experience(self, records) -> set[str]:
        values = set()
        for record in records:
            company = self._normalized_name(getattr(record, "company", "") or "")
            title = self._normalized_name(getattr(record, "title", "") or "")
            location = self._city_like(getattr(record, "location", "") or "")
            key = " | ".join(part for part in (company, title, location) if part)
            if key:
                values.add(key)
        return values

    def _url_match(self, left_links: set[str], right_links: set[str], token: str) -> bool:
        for left in left_links:
            for right in right_links:
                if token in left and token in right and normalized_similarity(left, right) >= 0.9:
                    return True
        return False

    def _name(self, profile: CandidateProfile) -> str:
        return str(profile.name.value if profile.name else "")

    def _headline(self, profile: CandidateProfile) -> str:
        return str(profile.summary.value if profile.summary else "")

    def _normalized_name(self, value: str) -> str:
        cleaned = clean_text(remove_accents(value))
        if not cleaned:
            return ""
        return " ".join(part for part in cleaned.lower().replace("-", " ").split() if part)

    def _name_similarity(self, left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        similarity = max(normalized_similarity(left, right), token_sort_similarity(left, right))
        if self._name_variant_match(left, right):
            similarity = max(similarity, 0.92)
        if self._family_name_match(left, right) and self._first_name_match(left, right):
            similarity = max(similarity, 0.96)
        return min(1.0, similarity)

    def _first_name_match(self, left: str, right: str) -> bool:
        left_tokens = left.split()
        right_tokens = right.split()
        if not left_tokens or not right_tokens:
            return False
        return self._variant_or_exact(left_tokens[0], right_tokens[0])

    def _family_name_match(self, left: str, right: str) -> bool:
        left_tokens = left.split()
        right_tokens = right.split()
        if len(left_tokens) < 2 or len(right_tokens) < 2:
            return False
        return left_tokens[-1] == right_tokens[-1]

    def _variant_or_exact(self, left: str, right: str) -> bool:
        if left == right:
            return True
        for group in self._name_variant_groups:
            if left in group and right in group:
                return True
        return False

    def _name_variant_match(self, left: str, right: str) -> bool:
        return self._variant_or_exact(left.split()[0] if left else "", right.split()[0] if right else "")

    def _notes(self, profile: CandidateProfile) -> set[str]:
        values = set()
        for record in profile.notes:
            normalized = self._normalized_name(str(record.value))
            if normalized:
                values.add(normalized)
        if profile.summary and profile.summary.value:
            normalized = self._normalized_name(str(profile.summary.value))
            if normalized:
                values.add(normalized)
        return values

    def _profile_key(self, profile: CandidateProfile) -> str:
        name = self._normalized_name(self._name(profile))
        email = sorted(record.value for record in profile.emails)[0] if profile.emails else ""
        return f"{name}|{email}"

    def _normalized_emails(self, profile: CandidateProfile) -> list[str]:
        values = []
        for record in profile.emails:
            normalized = normalize_email(str(record.value))
            if normalized:
                values.append(normalized)
        return sorted(set(values))

    def _normalized_phones(self, profile: CandidateProfile) -> list[str]:
        values = []
        default_country = self._infer_country(profile)
        location = self._best_location(profile)
        for record in profile.phones:
            normalized = normalize_phone(str(record.value), default_country=default_country, location=location)
            if normalized:
                values.append(normalized)
        return sorted(set(values))

    def _normalized_skills(self, profile: CandidateProfile) -> set[str]:
        values = set()
        for record in profile.skills:
            canonical = canonicalize_skills([record.value])
            if canonical:
                values.update(self._normalized_name(skill) for skill in canonical if skill)
        return {value for value in values if value}

    def _shared_normalized_email(self, left: CandidateProfile, right: CandidateProfile) -> bool:
        return bool(set(self._normalized_emails(left)) & set(self._normalized_emails(right)))

    def _shared_normalized_phone(self, left: CandidateProfile, right: CandidateProfile) -> bool:
        return bool(set(self._normalized_phones(left)) & set(self._normalized_phones(right)))

    def _city(self, profile: CandidateProfile) -> str:
        location = self._best_location(profile)
        if not location:
            return ""
        normalized = normalize_location(remove_accents(str(location)))
        if not normalized:
            return ""
        return normalized.split(",")[0].strip().lower()

    def _best_location(self, profile: CandidateProfile) -> str | None:
        if profile.locations:
            return str(profile.locations[0].value) if profile.locations[0].value else None
        if profile.experience:
            return next((record.location for record in profile.experience if record.location), None)
        return None

    def _infer_country(self, profile: CandidateProfile) -> str | None:
        if profile.country and profile.country.value:
            return str(profile.country.value)
        location = self._best_location(profile)
        if not location:
            return None
        normalized = normalize_location(remove_accents(str(location)))
        if not normalized:
            return None
        parts = [part.strip() for part in normalized.split(",") if part.strip()]
        if not parts:
            return None
        tail = parts[-1].upper()
        if tail in {"IN", "US", "GB"}:
            return tail
        return None

    def _city_like(self, value: str) -> str:
        if not value:
            return ""
        normalized = normalize_location(remove_accents(value))
        if not normalized:
            return ""
        return normalized.split(",")[0].strip().lower()

    def _explain(self, left: CandidateProfile, right: CandidateProfile) -> dict[str, float]:
        signals = self._signals(left, right)
        return {reason.replace("matched ", ""): round(score, 4) for score, matched, reason in signals if matched and score > 0.0}
