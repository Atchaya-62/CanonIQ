from __future__ import annotations

import io
import re

import pdfplumber

from .base_parser import BaseParser
from .common import build_education, build_experience, collect_emails, collect_phones, extract_skills, fragment_profile, make_value_record
from ..pipeline.loader import SourceDocument
from ..utils.text_utils import clean_text, title_case_name


class ResumeParser(BaseParser):
    source_types = ("resume_txt", "resume_pdf")

    def parse(self, document: SourceDocument) -> list:
        self._reset_warnings()
        text = document.text or ""
        if document.source_type == "resume_pdf" and document.binary:
            try:
                text = self._extract_pdf(document.binary)
            except Exception as exc:  # pragma: no cover - defensive guard
                self._warn(document, f"PDF extraction failed: {exc}")
                return []
        if not text:
            return []
        return [self._from_text(text, document)]

    def _extract_pdf(self, data: bytes) -> str:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)

    def _from_text(self, text: str, document: SourceDocument):
        profile = fragment_profile(document.source_type, document.path)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        profile.name = make_value_record(title_case_name(lines[0] if lines else None), "resume", "text", 0.8, "resume first line", source_path=document.path)
        profile.emails = [make_value_record(email, "resume", "text", 0.9, "resume email", source_path=document.path) for email in collect_emails(text)]
        profile.phones = [make_value_record(phone, "resume", "text", 0.85, "resume phone", source_path=document.path) for phone in collect_phones(text)]
        profile.skills = [make_value_record(skill, "resume", "text", 0.85, "resume skills", source_path=document.path) for skill in extract_skills(text)]
        profile.links = {"github": make_value_record(self._match_url(text, "github"), "resume", "text", 0.7, "resume github", source_path=document.path), "linkedin": make_value_record(self._match_url(text, "linkedin"), "resume", "text", 0.7, "resume linkedin", source_path=document.path)}
        profile.links = {key: value for key, value in profile.links.items() if value and value.value}
        experience, education = self._extract_sections(lines, document)
        profile.experience = experience
        profile.education = education
        return profile

    def _match_url(self, text: str, marker: str) -> str | None:
        match = re.search(rf"https?://[^\s)>\]]*{marker}[^\s)>\]]*", text, re.I)
        return match.group(0) if match else None

    def _extract_sections(self, lines: list[str], document: SourceDocument):
        experience: list = []
        education: list = []
        for line in lines:
            lowered = line.lower()
            parts = [part.strip() for part in line.split("|")]
            if len(parts) >= 3 and "experience" in lowered:
                company = parts[1] if parts[0].lower().startswith("experience") else parts[0]
                title = parts[2] if parts[0].lower().startswith("experience") else parts[1]
                location = parts[3] if len(parts) > 3 else None
                start_date = parts[4] if len(parts) > 4 else None
                end_date = parts[5] if len(parts) > 5 else None
                experience.append(build_experience(company, title, location, start_date, end_date, False, line, "resume", document.path))
            if "education" in lowered or "university" in lowered or "college" in lowered:
                institution = parts[1] if len(parts) > 1 and parts[0].lower().startswith("education") else parts[0]
                degree = parts[2] if len(parts) > 2 else None
                start_date = parts[3] if len(parts) > 3 else None
                end_date = parts[4] if len(parts) > 4 else None
                education.append(build_education(institution, degree, None, start_date, end_date, "resume", document.path))
        return experience, education
