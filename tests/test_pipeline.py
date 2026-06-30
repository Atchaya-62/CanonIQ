from __future__ import annotations

import json
from pathlib import Path
import shutil
import pytest
from uuid import uuid4

from src.models.candidate import CandidateProfile, ValueRecord
from src.models.education import EducationRecord
from src.models.experience import ExperienceRecord
from src.models.schemas import ProjectionConfig, ProjectionFieldConfig
from src.pipeline.confidence import ConfidenceScorer
from src.pipeline.matcher import CandidateMatcher
from src.pipeline.merger import CandidateMerger
from src.pipeline.normalizer import CandidateNormalizer
from src.pipeline.projector import ProjectionEngine
from src.pipeline.transformer import CandidateTransformer
from src.pipeline.validator import CandidateValidator
from src.pipeline.writer import OutputWriter


def build_profile(name="Alice Doe", email="alice@example.com", phone="+14155550101"):
    profile = CandidateProfile()
    profile.name = ValueRecord(name, "linkedin", "json", "1970-01-01T00:00:00Z", 0.9, "name")
    profile.emails = [ValueRecord(email, "linkedin", "json", "1970-01-01T00:00:00Z", 0.9, "email")]
    profile.phones = [ValueRecord(phone, "linkedin", "json", "1970-01-01T00:00:00Z", 0.9, "phone")]
    profile.skills = [ValueRecord("python3", "linkedin", "json", "1970-01-01T00:00:00Z", 0.6, "skill")]
    profile.experience = [ExperienceRecord(company="stripe", title="data engineer", start_date="2021-04", end_date="2024-05")]
    profile.education = [EducationRecord(institution="uc berkeley", degree="bs computer science", start_date="2014-09", end_date="2018-06")]
    return profile


def test_normalizer_standardizes_profile():
    profile = CandidateNormalizer().normalize(build_profile())
    assert profile.name.value == "Alice Doe"
    assert profile.skills[0].value == "Python"
    assert profile.experience[0].company == "Stripe"
    assert profile.experience[0].title == "Data Engineer"


def test_matcher_clusters_same_candidate():
    left = CandidateNormalizer().normalize(build_profile())
    right = CandidateNormalizer().normalize(build_profile())
    clusters, decisions = CandidateMatcher().cluster([left, right])
    assert len(clusters) == 1
    assert decisions and decisions[0].score >= 0.85


def test_identical_email_merges():
    left = CandidateNormalizer().normalize(build_profile(email="john@example.com"))
    right = CandidateNormalizer().normalize(build_profile(name="John Smith", email="john@example.com", phone="+919999999999"))
    clusters, _ = CandidateMatcher().cluster([left, right])
    assert len(clusters) == 1


def test_identical_phone_merges():
    left = CandidateNormalizer().normalize(build_profile(email="left@example.com", phone="+919876543210"))
    right = CandidateNormalizer().normalize(build_profile(name="John Smith", email="right@example.com", phone="+919876543210"))
    clusters, _ = CandidateMatcher().cluster([left, right])
    assert len(clusters) == 1


def test_matcher_separates_different_candidates():
    left = CandidateNormalizer().normalize(build_profile())
    right = CandidateNormalizer().normalize(
        build_profile(name="Zoe Quinn", email="zoe@example.com", phone="+44 20 7946 0958")
    )
    right.experience[0].company = "Acme"
    right.education[0].institution = "Stanford"
    right.skills = [ValueRecord("go", "github", "json", "1970-01-01T00:00:00Z", 0.6, "skill")]
    right.links["github"] = ValueRecord("https://github.com/zoequinn", "github", "json", "1970-01-01T00:00:00Z", 0.9, "github")
    right.links["linkedin"] = ValueRecord("https://www.linkedin.com/in/zoequinn", "linkedin", "json", "1970-01-01T00:00:00Z", 0.9, "linkedin")
    clusters, _ = CandidateMatcher().cluster([left, right])
    assert len(clusters) == 2


def test_null_name_does_not_prevent_merge():
    left = CandidateNormalizer().normalize(build_profile(name=None, email="john@example.com"))
    right = CandidateNormalizer().normalize(build_profile(name="John Smith", email="john@example.com"))
    cluster = CandidateMatcher().cluster([left, right])[0][0]
    merged = CandidateMerger().merge(cluster)
    assert merged.name.value == "John Smith"


def test_merger_selects_best_value():
    left = CandidateNormalizer().normalize(build_profile())
    right = CandidateNormalizer().normalize(build_profile())
    merged = CandidateMerger().merge([left, right])
    assert merged.candidate_id.startswith("cand_")
    assert merged.emails[0].value == "alice@example.com"
    assert merged.skills[0].value == "Python"


def test_field_enrichment_combines_values():
    left = CandidateNormalizer().normalize(build_profile())
    left.summary = None
    right = CandidateNormalizer().normalize(build_profile())
    right.experience = []
    right.skills = [ValueRecord("TensorFlow", "linkedin", "json", "1970-01-01T00:00:00Z", 0.9, "skill")]
    right.summary = ValueRecord("Machine Learning Engineer", "linkedin", "json", "1970-01-01T00:00:00Z", 0.9, "headline")
    right.locations = [ValueRecord("Bengaluru, IN", "linkedin", "json", "1970-01-01T00:00:00Z", 0.9, "location")]
    merged = CandidateMerger().merge([left, right])
    assert merged.summary.value == "Machine Learning Engineer"
    assert any(record.value == "TensorFlow" for record in merged.skills)
    assert merged.locations


def test_merger_keeps_notes():
    left = CandidateNormalizer().normalize(build_profile())
    left.notes = [ValueRecord("Follow up next week", "notes", "text", "1970-01-01T00:00:00Z", 0.6, "note")]
    merged = CandidateMerger().merge([left])
    assert merged.notes[0].value == "Follow up next week"


def test_confidence_scorer_sets_overall_score():
    profile = ConfidenceScorer().score(CandidateNormalizer().normalize(build_profile()))
    assert 0.0 < profile.confidence <= 0.99


def test_confidence_floor_for_name_only_candidate():
    profile = CandidateProfile()
    profile.name = ValueRecord("Mike", "notes", "text", "1970-01-01T00:00:00Z", 0.35, "name")
    scored = ConfidenceScorer().score(profile)
    assert scored.confidence <= 0.35


def test_confidence_increases_with_more_support():
    profile = CandidateNormalizer().normalize(build_profile())
    profile.emails[0].sources = ["linkedin", "ats", "resume"]
    profile.phones[0].sources = ["linkedin", "resume"]
    scored = ConfidenceScorer().score(profile)
    assert scored.emails[0].confidence > 0.9
    assert scored.phones[0].confidence > 0.8


def test_skill_canonicalization_and_sorting():
    profile = CandidateProfile()
    profile.skills = [
        ValueRecord("machine-learning", "notes", "text", "1970-01-01T00:00:00Z", 0.6, "skill"),
        ValueRecord("ML", "resume", "text", "1970-01-01T00:00:00Z", 0.6, "skill"),
        ValueRecord("Python3", "github", "text", "1970-01-01T00:00:00Z", 0.6, "skill"),
        ValueRecord("Py", "notes", "text", "1970-01-01T00:00:00Z", 0.6, "skill"),
    ]
    normalized = CandidateNormalizer().normalize(profile)
    assert [record.value for record in normalized.skills] == ["Machine Learning", "Python"]


def test_duplicate_candidate_count_becomes_one():
    left = CandidateNormalizer().normalize(build_profile(email="john@example.com"))
    right = CandidateNormalizer().normalize(build_profile(name="John Smith", email="john@example.com"))
    clusters, _ = CandidateMatcher().cluster([left, right])
    assert len(clusters) == 1


def test_complementary_records_merge_into_one_candidate():
    identity = CandidateNormalizer().normalize(build_profile(name="John Smith", email="john@example.com"))
    identity.summary = None
    identity.skills = [
        ValueRecord("Machine Learning", "resume", "text", "1970-01-01T00:00:00Z", 0.8, "skill"),
        ValueRecord("Python", "resume", "text", "1970-01-01T00:00:00Z", 0.8, "skill"),
    ]
    identity.locations = []

    profile = CandidateProfile()
    profile.name = ValueRecord("John Smith", "linkedin", "json", "1970-01-01T00:00:00Z", 0.9, "name")
    profile.skills = [
        ValueRecord("Machine Learning", "linkedin", "json", "1970-01-01T00:00:00Z", 0.9, "skill"),
        ValueRecord("TensorFlow", "linkedin", "json", "1970-01-01T00:00:00Z", 0.9, "skill"),
    ]
    profile.locations = [ValueRecord("Bengaluru, India", "linkedin", "json", "1970-01-01T00:00:00Z", 0.9, "location")]
    profile.summary = ValueRecord("Machine Learning Engineer", "linkedin", "json", "1970-01-01T00:00:00Z", 0.9, "headline")
    profile = CandidateNormalizer().normalize(profile)

    clusters, _ = CandidateMatcher().cluster([identity, profile])
    assert len(clusters) == 1


def _profile_with_name_and_city(name: str) -> CandidateProfile:
    profile = CandidateProfile()
    profile.name = ValueRecord(name, "linkedin", "json", "1970-01-01T00:00:00Z", 0.9, "name")
    profile.locations = [ValueRecord("Bengaluru, India", "linkedin", "json", "1970-01-01T00:00:00Z", 0.8, "location")]
    return CandidateNormalizer().normalize(profile)


@pytest.mark.parametrize(
    "left_name,right_name",
    [
        ("Sara Khan", "Sarah Khan"),
        ("Jon Smith", "John Smith"),
        ("Bob Brown", "Robert Brown"),
        ("José Alvarez", "Jose Alvarez"),
    ],
)
def test_common_name_variants_merge_with_supporting_field(left_name, right_name):
    left = _profile_with_name_and_city(left_name)
    right = _profile_with_name_and_city(right_name)
    clusters, _ = CandidateMatcher().cluster([left, right])
    assert len(clusters) == 1


def test_hyphenated_and_middle_names_merge_with_supporting_field():
    left = _profile_with_name_and_city("Jean-Luc Picard")
    right = _profile_with_name_and_city("Jean Luc Picard")
    clusters, _ = CandidateMatcher().cluster([left, right])
    assert len(clusters) == 1


def test_aliases_are_preserved_during_merge():
    left = _profile_with_name_and_city("Sara Khan")
    right = _profile_with_name_and_city("Sarah Khan")
    cluster = CandidateMatcher().cluster([left, right])[0][0]
    merged = CandidateMerger().merge(cluster)
    projected = ProjectionEngine.from_file("src/config/default_projection.json").project(merged)
    assert projected["name"] in {"Sarah Khan", "Sara Khan"}
    assert projected["provenance"]


def test_validator_accepts_valid_profile():
    profile = ConfidenceScorer().score(CandidateNormalizer().normalize(build_profile()))
    report = CandidateValidator().validate(profile)
    assert report.is_valid


def test_validator_flags_bad_email():
    profile = build_profile(email="bad-email")
    profile.emails[0].value = "bad-email"
    report = CandidateValidator().validate(profile)
    assert any("invalid email" in warning for warning in report.warnings)


def test_validator_flags_bad_link():
    profile = build_profile()
    profile.links["github"] = ValueRecord("not-a-url", "github", "json", "1970-01-01T00:00:00Z", 0.2, "bad")
    report = CandidateValidator().validate(profile)
    assert any("malformed url" in warning for warning in report.warnings)


def test_projection_engine_renames_fields():
    profile = CandidateNormalizer().normalize(build_profile())
    profile.candidate_id = "cand_test"
    projected = ProjectionEngine.from_file("src/config/default_projection.json").project(profile)
    assert list(projected.keys()) == [
        "name",
        "primary_email",
        "primary_phone",
        "experience",
        "location",
        "all_skills",
        "overall_confidence",
        "provenance",
    ]
    assert projected["name"] == "Alice Doe"
    assert projected["primary_email"] == "alice@example.com"
    assert projected["primary_phone"] == "+14155550101"
    assert "Python" in projected["all_skills"]
    assert projected["provenance"]


def test_projection_engine_supports_defaults_and_missing_modes():
    profile = CandidateNormalizer().normalize(build_profile())
    engine = ProjectionEngine(
        ProjectionConfig(
            format="custom",
            fields={
                "summary.value": ProjectionFieldConfig(rename="headline", normalize=True, on_missing="default", default="  unknown  "),
                "candidate_id": ProjectionFieldConfig(rename="id", on_missing="null"),
                "notes.0.value": ProjectionFieldConfig(rename="first_note", on_missing="omit"),
            },
        )
    )
    projected = engine.project(profile)

    assert projected["headline"] == "unknown"
    assert projected["id"] is None
    assert "first_note" not in projected


def test_projection_engine_can_raise_on_field_error(monkeypatch):
    profile = CandidateNormalizer().normalize(build_profile())
    engine = ProjectionEngine(
        ProjectionConfig(
            format="custom",
            fields={
                "name.value": ProjectionFieldConfig(rename="full_name", on_error="error"),
            },
        )
    )

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(engine, "_get_path", boom)

    with pytest.raises(ValueError, match="Projection failed for field 'name.value'"):
        engine.project(profile)


def test_projection_engine_uses_filename_provenance():
    from src.parsers.linkedin_parser import LinkedInParser
    from src.pipeline.loader import SourceDocument

    text = Path("sample_inputs/linkedin.json").read_text(encoding="utf-8")
    document = SourceDocument(path="linkedin.json", source_type="linkedin_json", text=text, binary=text.encode("utf-8"), checksum="abc", metadata={})
    profile = LinkedInParser().parse(document)[0]
    projected = ProjectionEngine.from_file("src/config/default_projection.json").project(CandidateNormalizer().normalize(profile))
    assert any(entry["field"] == "name" and entry["source"] == "LinkedIn Profile" for entry in projected["provenance"])


def test_merge_conflicts_are_reported():
    left = CandidateNormalizer().normalize(build_profile(email="alice@example.com", phone="+15551112222"))
    right = CandidateNormalizer().normalize(build_profile(name="Alice Doe", email="alice@example.com", phone="+15559998888"))
    cluster = CandidateMatcher().cluster([left, right])[0][0]
    merged = CandidateMerger().merge(cluster)
    projected = ProjectionEngine.from_file("src/config/default_projection.json").project(merged)
    assert projected["name"] == "Alice Doe"
    assert projected["primary_email"] == "alice@example.com"
    assert projected["primary_phone"] in {"+15551112222", "+15559998888"}
    assert any(entry["field"] == "primary_email" and entry["source"] == "LinkedIn Profile" for entry in projected["provenance"])


def test_html_report_contains_candidate_and_stats():
    profile = CandidateNormalizer().normalize(build_profile())
    projected = ProjectionEngine.from_file("src/config/default_projection.json").project(profile)
    output_root = Path("report_tmp") / f"report_{uuid4().hex}"
    output_root.mkdir(parents=True, exist_ok=False)
    output = output_root / "report.html"
    writer = CandidateTransformer(ProjectionEngine.from_file("src/config/default_projection.json")).writer
    writer.write_html({"candidates": [projected], "stats": {"records_processed": 1}, "warnings": [], "explanations": {}, "validation_report": {}}, output)
    html = output.read_text(encoding="utf-8")
    assert "Multi-Source Candidate Report" in html
    assert "Alice Doe" in html
    assert "records_processed" in html


def test_writer_exports_csv_rows():
    profile = CandidateNormalizer().normalize(build_profile())
    projected = ProjectionEngine.from_file("src/config/default_projection.json").project(profile)
    csv_text = OutputWriter().write_csv({"candidates": [projected]}, None)
    assert "Candidate ID" in csv_text
    assert "Full Name" in csv_text
    assert "Alice Doe" in csv_text
    assert "Confidence" in csv_text
    assert "field_provenance" not in csv_text
    assert "merge_score" not in csv_text
    assert "validation_report" not in csv_text


def test_invalid_data_case_emits_warnings_and_no_fake_candidates():
    temp_root = Path("case5_tmp")
    temp_root.mkdir(exist_ok=True)
    temp_path = temp_root / f"case5_{uuid4().hex}"
    temp_path.mkdir(parents=True, exist_ok=False)
    (temp_path / "malformed.json").write_text('{"candidateName":"Mike","email":"mike@gmail.com",', encoding="utf-8")
    (temp_path / "bad.csv").write_text("name,email,phone\nBad Row,bad-email,+14155550101\n", encoding="utf-8")
    (temp_path / "recruiter_notes.txt").write_text("Malformed input should not crash.", encoding="utf-8")
    (temp_path / "empty_candidate.json").write_text('{"name": ""}', encoding="utf-8")

    transformer = CandidateTransformer(ProjectionEngine.from_file("src/config/default_projection.json"))
    result = transformer.run(str(temp_path))

    assert result.candidates == []
    assert any("malformed.json" in warning and "Malformed JSON skipped." in warning for warning in result.warnings)
    assert any("bad.csv" in warning and "invalid email format" in warning for warning in result.warnings)
    assert any("recruiter_notes.txt" in warning and "no candidate identity exists" in warning for warning in result.warnings)
    assert any("discarded because no candidate identity exists" in warning for warning in result.warnings)


@pytest.mark.parametrize(
    "left_name,right_name",
    [
        ("José Alvarez", "Jose Alvarez"),
        ("Łukasz Kowalski", "Lukasz Kowalski"),
        ("Zoë Kravitz", "Zoe Kravitz"),
        ("Renée Zellweger", "Renee Zellweger"),
        ("Müller", "Muller"),
        ("Jean-Luc Picard", "Jean Luc Picard"),
    ],
)
def test_unicode_name_variants_merge(left_name, right_name):
    left = _profile_with_name_and_city(left_name)
    right = _profile_with_name_and_city(right_name)
    clusters, _ = CandidateMatcher().cluster([left, right])
    assert len(clusters) == 1


def test_linkedin_enrichment_preserves_unicode_and_location():
    csv_profile = CandidateNormalizer().normalize(build_profile(name="Jose Alvarez", email="jose@gmail.com", phone="+34612345678"))

    linkedin_profile = CandidateProfile()
    linkedin_profile.name = ValueRecord("José Álvarez", "linkedin", "json", "1970-01-01T00:00:00Z", 0.95, "linkedin profile")
    linkedin_profile.summary = ValueRecord("AI Engineer", "linkedin", "json", "1970-01-01T00:00:00Z", 0.95, "headline")
    linkedin_profile.locations = [ValueRecord("Madrid, Spain", "linkedin", "json", "1970-01-01T00:00:00Z", 0.95, "location")]
    linkedin_profile = CandidateNormalizer().normalize(linkedin_profile)

    clusters, _ = CandidateMatcher().cluster([csv_profile, linkedin_profile])
    assert len(clusters) == 1

    merged = CandidateMerger().merge(clusters[0])
    projected = ProjectionEngine.from_file("src/config/default_projection.json").project(merged)
    assert projected["name"] == "José Álvarez"
    assert projected["primary_email"] == "jose@gmail.com"
    assert projected["provenance"]

