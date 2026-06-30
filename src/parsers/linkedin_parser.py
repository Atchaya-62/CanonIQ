from __future__ import annotations

import json

from .base_parser import BaseParser
from .common import build_education, build_experience, collect_emails, collect_phones, extract_skills, fragment_profile, make_value_record
from ..pipeline.field_mapping import FieldAliasResolver
from ..pipeline.loader import SourceDocument
from ..utils.text_utils import clean_text, title_case_name


class LinkedInParser(BaseParser):
    source_types = ("linkedin_json", "linkedin_txt")

    def __init__(self) -> None:
        super().__init__()
        self.mapper = FieldAliasResolver()

    def parse(self, document: SourceDocument) -> list:
        self._reset_warnings()
        if not document.text:
            return []
        if document.source_type == "linkedin_json":
            try:
                payload = json.loads(document.text)
            except json.JSONDecodeError:
                self._warn(document, "Malformed JSON skipped.")
                return []
            if isinstance(payload, dict):
                return [self._from_payload(payload, document)]
            self._warn(document, "Malformed JSON skipped.")
            return []
        return [self._from_text(document.text, document)]

    def _from_payload(self, payload: dict, document: SourceDocument):
        profile = fragment_profile("linkedin_json", document.path)
        mapped = self.mapper.project(payload)
        profile.name = make_value_record(title_case_name(mapped.get("full_name") or mapped.get("name")), "linkedin", "json", 0.95, "linkedin profile", source_path=document.path)
        body = json.dumps(payload)
        profile.emails = [record for email in collect_emails(body) if (record := make_value_record(email, "linkedin", "json", 0.95, "linkedin email", source_path=document.path))]
        profile.phones = [record for phone in collect_phones(body) if (record := make_value_record(phone, "linkedin", "json", 0.9, "linkedin phone", source_path=document.path))]
        profile.links = {k: record for k in ("linkedin", "github", "website") if mapped.get(k) and (record := make_value_record(clean_text(mapped.get(k)), "linkedin", "json", 0.95, f"linkedin {k}", source_path=document.path))}
        profile.skills = [record for skill in extract_skills(mapped.get("skills")) if (record := make_value_record(skill, "linkedin", "json", 0.9, "linkedin skills", source_path=document.path))]
        if headline := clean_text(mapped.get("headline") or mapped.get("title")):
            profile.summary = make_value_record(headline, "linkedin", "json", 0.95, "linkedin headline", source_path=document.path)
        if location := mapped.get("location"):
            location_text = location.get("city") if isinstance(location, dict) else location
            if isinstance(location, dict) and location.get("country"):
                location_text = f"{location.get('city')}, {location.get('country')}"
            if clean_text(location_text):
                profile.locations = [make_value_record(clean_text(location_text), "linkedin", "json", 0.9, "linkedin location", source_path=document.path)]
        profile.experience = [build_experience(self.mapper.get(exp, "company"), self.mapper.get(exp, "title"), self.mapper.get(exp, "location"), self.mapper.get(exp, "start_date"), self.mapper.get(exp, "end_date"), bool(self.mapper.get(exp, "current")), self.mapper.get(exp, "description"), "linkedin", document.path) for exp in mapped.get("experience", []) if isinstance(exp, dict)]
        profile.education = [build_education(self.mapper.get(ed, "school"), self.mapper.get(ed, "degree"), self.mapper.get(ed, "field"), self.mapper.get(ed, "start_date"), self.mapper.get(ed, "end_date"), "linkedin", document.path) for ed in mapped.get("education", []) if isinstance(ed, dict)]
        return profile

    def _from_text(self, text: str, document: SourceDocument):
        profile = fragment_profile("linkedin_txt", document.path)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            profile.name = make_value_record(title_case_name(lines[0]), "linkedin", "text", 0.8, "text first line", source_path=document.path)
        profile.emails = [record for email in collect_emails(text) if (record := make_value_record(email, "linkedin", "text", 0.9, "text email", source_path=document.path))]
        profile.phones = [record for phone in collect_phones(text) if (record := make_value_record(phone, "linkedin", "text", 0.8, "text phone", source_path=document.path))]
        profile.skills = [record for skill in extract_skills(text) if (record := make_value_record(skill, "linkedin", "text", 0.8, "text skill", source_path=document.path))]
        return profile
