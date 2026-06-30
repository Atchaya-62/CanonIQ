from __future__ import annotations

import json
from pathlib import Path

from src.parsers.csv_parser import CSVParser
from src.parsers.github_parser import GitHubParser
from src.parsers.json_parser import JSONParser
from src.parsers.linkedin_parser import LinkedInParser
from src.parsers.notes_parser import NotesParser
from src.parsers.resume_parser import ResumeParser
from src.pipeline.loader import InputLoader, SourceDocument


def make_doc(path: str, source_type: str, text: str) -> SourceDocument:
    return SourceDocument(path=path, source_type=source_type, text=text, binary=text.encode("utf-8"), checksum="abc", metadata={})


def test_csv_parser_extracts_candidate():
    text = Path("sample_inputs/candidate.csv").read_text(encoding="utf-8")
    profiles = CSVParser().parse(make_doc("candidate.csv", "csv", text))
    assert len(profiles) == 1
    assert profiles[0].emails[0].value == "alice.doe@example.com"


def test_json_parser_extracts_ats_candidate():
    text = Path("sample_inputs/ats.json").read_text(encoding="utf-8")
    profiles = JSONParser().parse(make_doc("ats.json", "ats_json", text))
    assert len(profiles) == 1
    assert profiles[0].skills


def test_json_parser_handles_integer_experience():
    text = json.dumps({"name": "John Smith", "experience": 4})
    profiles = JSONParser().parse(make_doc("ats.json", "ats_json", text))
    assert profiles[0].years_experience == 4


def test_json_parser_handles_string_experience():
    text = json.dumps({"name": "John Smith", "experience": "4"})
    profiles = JSONParser().parse(make_doc("ats.json", "ats_json", text))
    assert profiles[0].years_experience == 4


def test_json_parser_handles_list_experience():
    text = json.dumps(
        {
            "name": "John Smith",
            "experience": [
                {"company": "Acme", "title": "Engineer", "start_date": "2020-01", "end_date": "2022-01"},
                {"company": "Beta", "title": "Engineer", "start_date": "2022-02", "end_date": "2024-01"},
            ],
        }
    )
    profiles = JSONParser().parse(make_doc("ats.json", "ats_json", text))
    assert profiles[0].years_experience == 4


def test_json_parser_handles_malformed_ats():
    text = json.dumps({"name": "John Smith", "experience": {"unexpected": True}})
    profiles = JSONParser().parse(make_doc("ats.json", "ats_json", text))
    assert profiles[0].warnings


def test_json_parser_skips_malformed_json():
    parser = JSONParser()
    profiles = parser.parse(make_doc("malformed.json", "ats_json", '{"candidateName":"Mike","email":"mike@gmail.com",'))
    assert profiles == []
    assert any("malformed.json" in warning and "Malformed JSON skipped." in warning for warning in parser.warnings)


def test_csv_parser_skips_invalid_rows():
    parser = CSVParser()
    text = "name,email,phone\nBad Row,bad-email,+14155550101\n"
    profiles = parser.parse(make_doc("bad.csv", "csv", text))
    assert profiles == []
    assert any("bad.csv" in warning and "invalid email format" in warning for warning in parser.warnings)


def test_notes_parser_ignores_orphan_notes():
    parser = NotesParser()
    profiles = parser.parse(make_doc("recruiter_notes.txt", "notes_txt", "Malformed input should not crash."))
    assert profiles == []
    assert any("recruiter_notes.txt" in warning and "no candidate identity exists" in warning for warning in parser.warnings)


def test_linkedin_parser_extracts_profile():
    text = Path("sample_inputs/linkedin.json").read_text(encoding="utf-8")
    profiles = LinkedInParser().parse(make_doc("linkedin.json", "linkedin_json", text))
    assert profiles[0].name.value == "Alice Doe"


def test_github_parser_extracts_profile():
    text = Path("sample_inputs/github.json").read_text(encoding="utf-8")
    profiles = GitHubParser().parse(make_doc("github.json", "github_json", text))
    assert profiles[0].links["github"].value == "https://github.com/alicedoe"


def test_github_parser_infers_skills_from_topics_and_repositories():
    text = json.dumps(
        {
            "name": "Alice Doe",
            "languages": ["Python"],
            "topics": ["nlp", "transformers"],
            "repositories": [{"name": "resume-parser"}],
        }
    )
    profiles = GitHubParser().parse(make_doc("github.json", "github_json", text))
    skills = [record.value for record in profiles[0].skills]
    assert "Python" in skills
    assert "NLP" in skills or "Natural Language Processing" in skills
    assert any("topics" in record.reason or "repository" in record.reason for record in profiles[0].skills)


def test_resume_parser_extracts_text():
    text = Path("sample_inputs/resume.txt").read_text(encoding="utf-8")
    profiles = ResumeParser().parse(make_doc("resume.txt", "resume_txt", text))
    assert profiles[0].experience


def test_notes_parser_extracts_skills():
    text = Path("sample_inputs/notes.txt").read_text(encoding="utf-8")
    profiles = NotesParser().parse(make_doc("notes.txt", "notes_txt", text))
    assert "Snowflake" in [record.value for record in profiles[0].skills]
    assert profiles[0].notes


def test_loader_detects_sources():
    loader = InputLoader()
    assert loader.detect_source_type(Path("a.csv"), "x", b"x") == "csv"
    assert loader.detect_source_type(Path("a.json"), '{"linkedin": 1}', b"{}") == "linkedin_json"
    assert loader.detect_source_type(Path("a.txt"), "recruiter notes", b"x") == "notes_txt"
