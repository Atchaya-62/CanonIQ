from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
import logging
from os import getenv
from time import perf_counter

from ..models.candidate import CandidateProfile
from .confidence import ConfidenceScorer
from .extractor import SourceExtractor
from .loader import InputLoader
from .matcher import CandidateMatcher
from .merger import CandidateMerger
from .normalizer import CandidateNormalizer
from .projector import ProjectionEngine
from .validator import CandidateValidator
from .writer import OutputWriter


@dataclass(slots=True)
class TransformResult:
    candidates: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, object] = field(default_factory=dict)
    explanations: dict[str, dict[str, object]] = field(default_factory=dict)
    validation_report: dict[str, object] = field(default_factory=dict)


class CandidateTransformer:
    def __init__(self, projection: ProjectionEngine | None = None) -> None:
        self.loader = InputLoader()
        self.extractor = SourceExtractor()
        self.normalizer = CandidateNormalizer()
        self.matcher = CandidateMatcher(threshold=0.85)
        self.merger = CandidateMerger()
        self.scorer = ConfidenceScorer()
        self.validator = CandidateValidator()
        self.projector = projection or ProjectionEngine()
        self.writer = OutputWriter()
        self._logger = logging.getLogger(__name__)
        self._debug_flow = getenv("EIGHTFOLD_DEBUG_FLOW", "").strip().lower() in {"1", "true", "yes", "on"}

    def run(self, input_path: str, dry_run: bool = False, explain: bool = False) -> TransformResult:
        started = perf_counter()
        documents = self.loader.load(input_path)
        self._trace("Loaded", documents=len(documents))
        loaded = perf_counter()
        extraction = self.extractor.extract(documents)
        self._trace("Parsed", profiles=len(extraction.profiles), warnings=len(extraction.warnings))
        extracted = perf_counter()
        normalized = []
        for profile in extraction.profiles:
            normalized_profile = self.normalizer.normalize(profile)
            if not (normalized_profile.has_minimum_identity() or self._is_enrichment_profile(normalized_profile)):
                source = normalized_profile.provenance[0].source if normalized_profile.provenance else "candidate"
                extraction.warnings.append(f"{source}: discarded because no candidate identity exists.")
                continue
            normalized.append(normalized_profile)
        self._trace("Normalized", profiles=len(normalized), warnings=len(extraction.warnings))
        normalized_at = perf_counter()
        note_profiles = [profile for profile in normalized if self._is_note_profile(profile)]
        regular_profiles = [profile for profile in normalized if not self._is_note_profile(profile)]
        clusters, decisions = self.matcher.cluster(regular_profiles)
        self._trace("Merged", clusters=len(clusters), decisions=len(decisions))
        matched = perf_counter()
        if not clusters and note_profiles and any(self._has_explicit_identity(profile) for profile in note_profiles):
            clusters = [[profile] for profile in note_profiles if self._has_explicit_identity(profile)]
        merged = []
        for cluster in clusters:
            merged_profile = self.scorer.score(self.merger.merge(cluster))
            if len(cluster) == 1 and not merged_profile.has_minimum_identity():
                source = merged_profile.source_types[0] if merged_profile.source_types else "candidate"
                extraction.warnings.append(f"{source}: discarded because no candidate identity exists.")
                continue
            merged.append(merged_profile)
        merged_at = perf_counter()
        if note_profiles:
            merged = self._attach_notes(merged, note_profiles)
            merged = [self.scorer.score(profile) for profile in merged]
        validated: list[CandidateProfile] = []
        validation_warnings: list[str] = []
        validation_started = perf_counter()
        for profile in merged:
            profile_warnings = self.validator.validate(profile).warnings
            validation_warnings.extend(profile_warnings)
            validated.append(self.scorer.score(profile))
        self._trace("Validated", profiles=len(validated), warnings=len(validation_warnings))
        validation_finished = perf_counter()
        projected_started = perf_counter()
        projected = [self.projector.project(profile) for profile in validated]
        self._trace("Final Candidate", candidates=len(projected))
        projected_finished = perf_counter()
        warnings = extraction.warnings[:]
        explanations = {
            profile.candidate_id or f"candidate_{index}": self._build_explanation(profile, cluster if index < len(clusters) else [])
            for index, (profile, cluster) in enumerate(zip(merged, clusters, strict=False))
        }
        for profile in merged:
            warnings.extend(profile.warnings)
        warnings.extend(validation_warnings)
        runtime = round(perf_counter() - started, 4)
        parse_seconds = round(extracted - loaded, 4)
        normalize_seconds = round(normalized_at - extracted, 4)
        matching_seconds = round(matched - normalized_at, 4)
        merge_seconds = round(merged_at - matched, 4)
        validation_seconds = round(validation_finished - validation_started, 4)
        projection_seconds = round(projected_finished - projected_started, 4)
        stats = {
            "records_processed": len(documents),
            "duplicates_merged": sum(max(0, len(cluster) - 1) for cluster in clusters),
            "sources": sorted({document.source_type for document in documents}),
            "warnings": len(warnings),
            "average_confidence": round(sum(profile.confidence for profile in merged) / len(merged), 4) if merged else 0.0,
            "average_merge_score": round(sum(decision.score for decision in decisions) / len(decisions), 4) if decisions else 0.0,
            "average_parsing_time": round(parse_seconds / len(documents), 4) if documents else 0.0,
            "parse_seconds": parse_seconds,
            "normalization_seconds": normalize_seconds,
            "matching_seconds": matching_seconds,
            "merge_seconds": merge_seconds,
            "validation_seconds": validation_seconds,
            "projection_seconds": projection_seconds,
            "runtime_seconds": runtime,
        }
        validation_report = self._validation_report(warnings, validation_warnings, extraction.warnings, merged)
        if explain:
            explanations.update({f"{decision.left_index}:{decision.right_index}": decision.reasons for decision in decisions})
        return TransformResult(projected, warnings, stats, explanations, validation_report)

    def _trace(self, stage: str, **details) -> None:
        if not self._debug_flow:
            return
        summary = ", ".join(f"{key}={value}" for key, value in details.items()) if details else ""
        self._logger.debug("%s%s%s", stage, ": " if summary else "", summary)

    def _is_note_profile(self, profile: CandidateProfile) -> bool:
        return any(source.startswith("notes") for source in profile.source_types)

    def _has_explicit_identity(self, profile: CandidateProfile) -> bool:
        return profile.has_minimum_identity()

    def _is_enrichment_profile(self, profile: CandidateProfile) -> bool:
        if not any(source.startswith("linkedin") for source in profile.source_types):
            return False
        if not profile.name or not profile.name.value:
            return False
        return bool(profile.summary or profile.locations or profile.skills or profile.experience or profile.education)

    def _attach_notes(self, candidates: list[CandidateProfile], notes: list[CandidateProfile]) -> list[CandidateProfile]:
        if not candidates:
            return candidates
        ordered_candidates = sorted(candidates, key=lambda item: item.candidate_id or "")
        for note_profile in sorted(notes, key=lambda item: item.candidate_id or (item.name.value if item.name else "")):
            best_index = self._best_candidate_index(ordered_candidates, note_profile)
            if best_index is None:
                continue
            ordered_candidates[best_index].notes.extend(note_profile.notes or self._notes_from_profile(note_profile))
        return ordered_candidates

    def _best_candidate_index(self, candidates: list[CandidateProfile], note_profile: CandidateProfile) -> int | None:
        if len(candidates) == 1:
            return 0
        scores = []
        for index, candidate in enumerate(candidates):
            score, reasons = self.matcher.score(candidate, note_profile)
            scores.append((score, -index, index, reasons))
        if not scores:
            return None
        scores.sort(reverse=True)
        return scores[0][2]

    def _notes_from_profile(self, profile: CandidateProfile):
        if profile.notes:
            return profile.notes
        if profile.summary and profile.summary.value:
            return [profile.summary]
        return []

    def _validation_report(self, warnings: list[str], validation_warnings: list[str], extraction_warnings: list[str], merged: list[CandidateProfile]) -> dict[str, object]:
        discarded = [warning for warning in extraction_warnings if "discarded because no candidate identity exists" in warning]
        parser_failures = [warning for warning in extraction_warnings if "parse failure" in warning or "Malformed JSON skipped" in warning]
        invalid_emails = [warning for warning in validation_warnings if "invalid email" in warning]
        invalid_phones = [warning for warning in validation_warnings if "invalid phone" in warning]
        duplicate_records = [warning for warning in validation_warnings if "duplicate" in warning]
        confidence_issues = [warning for warning in validation_warnings if "confidence" in warning.lower()]
        return {
            "warnings": warnings,
            "discarded_records": discarded,
            "duplicate_records": duplicate_records,
            "invalid_emails": invalid_emails,
            "invalid_phones": invalid_phones,
            "parser_failures": parser_failures,
            "confidence_issues": confidence_issues,
            "candidates_validated": len(merged),
        }

    def _build_explanation(self, profile: CandidateProfile, cluster: list[CandidateProfile]) -> dict[str, object]:
        field_selection = self._field_selection(profile)
        field_details = self._field_details(profile)
        return {
            "candidate": profile.name.value if profile.name and profile.name.value else profile.candidate_id,
            "merge_summary": self._merge_summary(profile, cluster),
            "merge_details": list(profile.explanation or []),
            "merge_decision": profile.extra.get("merge_decision", "merged"),
            "merge_score": profile.extra.get("merge_score", 0.0),
            "merge_threshold": profile.extra.get("merge_threshold", 0.0),
            "cluster_size": len(cluster) or 1,
            "sources_merged": self._cluster_sources(cluster or [profile]),
            "matched_on": self._matched_on(profile),
            "matching_details": self._matching_details(profile),
            "field_selection": field_selection,
            "field_details": field_details,
            "field_conflicts": profile.extra.get("field_conflicts", {}),
            "field_resolvers": profile.extra.get("field_resolvers", {}),
            "warnings": [self._friendly_message(warning) for warning in profile.warnings],
            "overall_confidence": profile.confidence,
            "confidence_evidence": profile.extra.get("confidence_explanation", {}),
        }

    def _merge_summary(self, profile: CandidateProfile, cluster: list[CandidateProfile]) -> str:
        lines = [f"Merged {len(cluster) or 1} data sources"]
        sources = self._cluster_sources(cluster or [profile])
        if sources:
            lines.append("Sources: " + ", ".join(sources))
        matched_on = self._matched_on(profile)
        if matched_on:
            lines.append("Matched on: " + "; ".join(matched_on))
        field_selection = self._field_selection(profile)
        field_lines = []
        for field_name in ("name", "email", "phone", "headline", "location", "skills", "experience", "github", "linkedin", "country"):
            value = field_selection.get(field_name)
            if value:
                field_lines.append(f"{field_name}: {value}")
        if field_lines:
            lines.append("Field resolution: " + "; ".join(field_lines))
        confidence = profile.confidence
        lines.append(f"Overall confidence: {confidence:.0%}")
        warnings = [self._friendly_message(warning) for warning in profile.warnings]
        if warnings:
            lines.append("Warnings: " + "; ".join(warnings))
        return "\n".join(lines)

    def _source_label(self, record) -> str | None:
        if record is None:
            return None
        label = getattr(record, "source_path", None) or getattr(record, "source", None)
        return self._friendly_source_label(label) if label else None

    def _field_selection(self, profile: CandidateProfile) -> dict[str, object]:
        return {
            "name": self._source_label(profile.name),
            "email": self._best_source_label(profile.emails),
            "phone": self._best_source_label(profile.phones),
            "headline": self._source_label(profile.summary),
            "country": self._source_label(profile.country),
            "github": self._source_label(profile.links.get("github")) if profile.links.get("github") else None,
            "linkedin": self._source_label(profile.links.get("linkedin")) if profile.links.get("linkedin") else None,
            "experience": self._best_sources_label(profile.experience),
            "skills": self._best_sources_label(profile.skills),
            "location": self._best_sources_label(profile.locations),
        }

    def _field_details(self, profile: CandidateProfile) -> dict[str, object]:
        details: dict[str, object] = {}
        for field_name, record in (
            ("name", profile.name),
            ("headline", profile.summary),
            ("country", profile.country),
            ("github", profile.links.get("github")),
            ("linkedin", profile.links.get("linkedin")),
        ):
            detail = self._record_detail(record, field_name) if record else None
            if detail:
                details[field_name] = detail
        for field_name, records in (
            ("email", profile.emails),
            ("phone", profile.phones),
            ("location", profile.locations),
            ("skills", profile.skills),
            ("experience", profile.experience),
            ("education", profile.education),
            ("notes", profile.notes),
        ):
            detail = self._collection_detail(records, field_name)
            if detail:
                details[field_name] = detail
        return details

    def _best_source_label(self, records) -> str | None:
        if not records:
            return None
        first = records[0]
        return self._source_label(first)

    def _best_sources_label(self, records) -> str | None:
        labels = self._unique_labels(self._source_label(record) for record in records if record)
        if not labels:
            return None
        return " + ".join(labels)

    def _cluster_sources(self, cluster: list[CandidateProfile]) -> list[str]:
        labels = []
        for profile in cluster:
            labels.extend(self._profile_sources(profile))
        return self._unique_labels(labels)

    def _profile_sources(self, profile: CandidateProfile) -> list[str]:
        labels = []
        for record in [profile.name, profile.summary, profile.country]:
            label = self._source_label(record)
            if label:
                labels.append(label)
        for collection in (profile.emails, profile.phones, profile.skills, profile.locations, profile.notes):
            for record in collection:
                label = self._source_label(record)
                if label:
                    labels.append(label)
        for record in profile.links.values():
            label = self._source_label(record)
            if label:
                labels.append(label)
        for record in profile.experience:
            label = self._friendly_source_label(record.source_path or record.source) if (record.source_path or record.source) else None
            if label:
                labels.append(label)
        for record in profile.education:
            label = self._friendly_source_label(record.source_path or record.source) if (record.source_path or record.source) else None
            if label:
                labels.append(label)
        return labels

    def _matched_on(self, profile: CandidateProfile) -> list[str]:
        matched = []
        if profile.emails:
            matched.append(f"Email matched: {self._record_preview(profile.emails[0])}")
        if profile.phones:
            matched.append(f"Phone matched: {self._record_preview(profile.phones[0])}")
        if profile.name and profile.name.value:
            matched.append(f"Name matched: {profile.name.value}")
        if profile.locations:
            matched.append(f"Location matched: {self._record_preview(profile.locations[0])}")
        if profile.skills:
            matched.append(f"Skills overlapped: {', '.join(record.value for record in profile.skills if record.value)}")
        if profile.summary:
            matched.append(f"Headline matched: {profile.summary.value}")
        if profile.experience:
            matched.append(f"Experience matched: {len(profile.experience)} record(s)")
        return matched

    def _to_dict(self, value):
        if is_dataclass(value):
            return {key: self._to_dict(item) for key, item in asdict(value).items()}
        if isinstance(value, list):
            return [self._to_dict(item) for item in value]
        if isinstance(value, dict):
            return {key: self._to_dict(item) for key, item in value.items()}
        return value

    def _matching_details(self, profile: CandidateProfile) -> list[dict[str, object]]:
        details: list[dict[str, object]] = []
        if profile.name and profile.name.value:
            details.append(self._record_detail(profile.name, "name"))
        if profile.emails:
            details.append(self._collection_detail(profile.emails, "email"))
        if profile.phones:
            details.append(self._collection_detail(profile.phones, "phone"))
        if profile.locations:
            details.append(self._collection_detail(profile.locations, "location"))
        if profile.skills:
            details.append(self._collection_detail(profile.skills, "skills"))
        if profile.summary:
            details.append(self._record_detail(profile.summary, "headline"))
        if profile.experience:
            details.append(self._collection_detail(profile.experience, "experience"))
        return [detail for detail in details if detail]

    def _collection_detail(self, records, field_name: str) -> dict[str, object] | None:
        if not records:
            return None
        items = [detail for detail in (self._record_detail(record, field_name) for record in records) if detail]
        if not items:
            return None
        selected = items[0]
        sources = self._unique_labels(item.get("source") for item in items if item.get("source"))
        return {
            "selected_value": selected.get("value"),
            "selected_source": selected.get("source"),
            "selected_confidence": selected.get("confidence"),
            "selected_reason": selected.get("reason"),
            "selected_from": len(items),
            "sources": sources,
            "items": items,
        }

    def _record_detail(self, record, field_name: str) -> dict[str, object] | None:
        if record is None:
            return None
        has_value_field = hasattr(record, "value")
        value = getattr(record, "value", None)
        if has_value_field and value in (None, ""):
            return None
        detail = self._to_dict(record)
        source = getattr(record, "source_path", None) or getattr(record, "source", None)
        detail["source"] = self._source_label(record)
        detail["source_path"] = source
        detail["confidence"] = round(float(getattr(record, "confidence", 0.0)), 4)
        detail["reason"] = getattr(record, "reason", f"selected {field_name}")
        detail["selected_value"] = self._record_summary(record)
        return detail

    def _record_summary(self, record) -> object:
        if record is None:
            return None
        value = getattr(record, "value", None)
        if value not in (None, ""):
            return self._to_dict(value)
        parts = [
            getattr(record, "company", None),
            getattr(record, "title", None),
            getattr(record, "institution", None),
            getattr(record, "degree", None),
            getattr(record, "field_of_study", None),
            getattr(record, "location", None),
        ]
        summary = " | ".join(part for part in parts if part)
        if summary:
            return summary
        return self._to_dict(record)

    def _record_preview(self, record) -> str:
        value = getattr(record, "value", None)
        if value in (None, ""):
            return "n/a"
        if isinstance(value, str):
            return value
        return str(value)

    def _friendly_message(self, warning: str) -> str:
        if "discarded because no candidate identity exists" in warning:
            return "Recruiter notes ignored (no identifiable candidate)"
        return warning

    def _unique_labels(self, labels) -> list[str]:
        ordered = []
        seen = set()
        for label in labels:
            if label and label not in seen:
                seen.add(label)
                ordered.append(label)
        return ordered

    def _friendly_source_label(self, value: str) -> str:
        if not value:
            return "Unknown"
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
