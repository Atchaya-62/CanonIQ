from __future__ import annotations

from src.models.candidate import CandidateProfile, ValueRecord
from src.parsers.csv_parser import CSVParser
from src.parsers.resume_parser import ResumeParser
from src.pipeline.matcher import CandidateMatcher
from src.pipeline.merger import CandidateMerger
from src.pipeline.normalizer import CandidateNormalizer
from src.pipeline.loader import SourceDocument
from src.utils.phone_utils import normalize_phone
from src.utils.skill_utils import canonicalize_skill


def test_csv_parser_resolves_field_aliases():
    text = "candidateName,emailAddress,mobileNumber,skills\nAlice Doe,alice@example.com,(987)654-3210,Python3\n"
    document = type("Doc", (), {"path": "aliases.csv", "source_type": "csv", "text": text, "binary": text.encode("utf-8"), "checksum": "abc", "metadata": {}})()
    profiles = CSVParser().parse(document)

    assert len(profiles) == 1
    assert profiles[0].name.value == "Alice Doe"
    assert profiles[0].emails[0].value == "alice@example.com"
    assert profiles[0].phones[0].value == "+919876543210"


def test_phone_normalization_handles_global_prefixes():
    assert normalize_phone("0091 (987) 654-3210") == "+919876543210"


def test_phone_normalization_uses_candidate_context():
    profile = CandidateProfile(
        country=ValueRecord("IN", "csv", "json", "1970-01-01T00:00:00Z", 0.9, "country"),
        locations=[ValueRecord("Bengaluru, India", "csv", "json", "1970-01-01T00:00:00Z", 0.9, "location")],
        phones=[ValueRecord("9876543210", "csv", "json", "1970-01-01T00:00:00Z", 0.9, "phone")],
    )
    normalized = CandidateNormalizer().normalize(profile)

    assert normalized.phones[0].value == "+919876543210"
    assert CandidateMatcher()._normalized_phones(normalized) == ["+919876543210"]


def test_resume_parser_continues_on_broken_pdf():
    document = SourceDocument(path="broken.pdf", source_type="resume_pdf", text=None, binary=b"%PDF-1.4 broken", checksum="abc", metadata={})
    parser = ResumeParser()

    profiles = parser.parse(document)

    assert profiles == []
    assert any("PDF extraction failed" in warning for warning in parser.warnings)


def test_fuzzy_name_matching_handles_token_reordering():
    left = CandidateProfile(name=ValueRecord("John Smith", "resume", "text", "1970-01-01T00:00:00Z", 0.9, "name"))
    right = CandidateProfile(name=ValueRecord("Smith John", "linkedin", "json", "1970-01-01T00:00:00Z", 0.9, "name"))
    clusters, _ = CandidateMatcher().cluster([left, right])

    assert len(clusters) == 1


def test_conflict_resolution_prefers_reliable_source():
    left = CandidateProfile(
        name=ValueRecord("Alice Doe", "resume", "text", "1970-01-01T00:00:00Z", 0.9, "name"),
        emails=[ValueRecord("alice@example.com", "resume", "text", "1970-01-01T00:00:00Z", 0.9, "email")],
        phones=[ValueRecord("+15551112222", "notes", "text", "1970-01-01T00:00:00Z", 0.9, "phone")],
    )
    right = CandidateProfile(
        name=ValueRecord("Alice Doe", "linkedin", "json", "1970-01-01T00:00:00Z", 0.9, "name"),
        emails=[ValueRecord("alice@example.com", "linkedin", "json", "1970-01-01T00:00:00Z", 0.9, "email")],
        phones=[ValueRecord("+15559998888", "resume", "text", "1970-01-01T00:00:00Z", 0.9, "phone")],
    )
    merged = CandidateMerger().merge(CandidateMatcher().cluster([left, right])[0][0])

    assert merged.extra["field_conflicts"]["phones"]["primary"] == "+15559998888"


def test_skill_alias_fuzzy_matching():
    assert canonicalize_skill("MachineLearning") == "Machine Learning"
