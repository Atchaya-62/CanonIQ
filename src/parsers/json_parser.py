from __future__ import annotations

import json

from .base_parser import BaseParser
from .common import build_education, build_experience, calculate_years_experience, collect_emails, collect_phones, extract_skills, fragment_profile, make_value_record, parse_years_experience
from ..pipeline.field_mapping import FieldAliasResolver
from ..pipeline.loader import SourceDocument
from ..utils.text_utils import clean_text, title_case_name


class JSONParser(BaseParser):
    source_types = ("json", "ats_json")

    def __init__(self) -> None:
        super().__init__()
        self.mapper = FieldAliasResolver()

    def parse(self, document: SourceDocument) -> list:
        self._reset_warnings()
        if not document.text:
            return []
        try:
            payload = json.loads(document.text)
        except json.JSONDecodeError:
            self._warn(document, "Malformed JSON skipped.")
            return []
        if isinstance(payload, list):
            return [self._item_to_profile(item, document, "json") for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            if any(key in payload for key in ("candidates", "applications", "people")):
                return [self._item_to_profile(item, document, "ats_json") for item in self._iter_nested(payload)]
            return [self._item_to_profile(payload, document, "json")]
        return []

    def _iter_nested(self, payload: dict) -> list[dict]:
        for key in ("candidates", "applications", "people", "records", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]

    def _item_to_profile(self, item: dict, document: SourceDocument, source_type: str):
        profile = fragment_profile(source_type, document.path)
        mapped = self.mapper.project(item)
        name = mapped.get("full_name") or mapped.get("name")
        profile.name = make_value_record(title_case_name(name), source_type, "json", 0.85, "structured json name", source_path=document.path)
        values = " ".join(str(value) for value in item.values())
        profile.emails = [record for email in collect_emails(values) if (record := make_value_record(email, source_type, "json", 0.95, "structured json email", source_path=document.path))]
        profile.phones = [record for phone in collect_phones(values) if (record := make_value_record(phone, source_type, "json", 0.9, "structured json phone", source_path=document.path))]
        profile.skills = [record for skill in extract_skills(mapped.get("skills") or mapped.get("skillset")) if (record := make_value_record(skill, source_type, "json", 0.9, "structured json skill", source_path=document.path))]
        profile.links = {k: record for k in ("github", "linkedin", "website", "portfolio") if mapped.get(k) and (record := make_value_record(clean_text(mapped.get(k)), source_type, "json", 0.85, f"{k} field", source_path=document.path))}
        if headline := clean_text(mapped.get("headline") or mapped.get("title")):
            profile.summary = make_value_record(headline, source_type, "json", 0.9, "headline field", source_path=document.path)
        if location := mapped.get("location"):
            location_text = location.get("city") if isinstance(location, dict) else location
            if isinstance(location, dict) and location.get("country"):
                location_text = f"{location.get('city')}, {location.get('country')}"
            if clean_text(location_text):
                profile.locations = [make_value_record(clean_text(location_text), source_type, "json", 0.8, "location field", source_path=document.path)]
        if mapped.get("country"):
            profile.country = make_value_record(clean_text(str(mapped.get("country"))), source_type, "json", 0.8, "country field", source_path=document.path)
        experience_value = mapped.get("experience")
        if isinstance(experience_value, list):
            profile.experience = []
            for exp in experience_value:
                if not isinstance(exp, dict):
                    profile.warnings.append(f"malformed experience item: {type(exp).__name__}")
                    continue
                mapped_exp = self.mapper.project(exp)
                profile.experience.append(build_experience(mapped_exp.get("company"), mapped_exp.get("title"), mapped_exp.get("location"), mapped_exp.get("start_date"), mapped_exp.get("end_date"), bool(mapped_exp.get("current")), mapped_exp.get("description"), source_type, document.path))
            profile.years_experience = calculate_years_experience(profile.experience)
        else:
            years = parse_years_experience(experience_value)
            if years is not None:
                profile.years_experience = years
            elif experience_value not in (None, "", []):
                profile.warnings.append(f"unsupported experience format: {type(experience_value).__name__}")
        education_value = mapped.get("education")
        if isinstance(education_value, list):
            profile.education = []
            for ed in education_value:
                if not isinstance(ed, dict):
                    profile.warnings.append(f"malformed education item: {type(ed).__name__}")
                    continue
                mapped_ed = self.mapper.project(ed)
                profile.education.append(build_education(mapped_ed.get("institution"), mapped_ed.get("degree"), mapped_ed.get("field"), mapped_ed.get("start_date"), mapped_ed.get("end_date"), source_type, document.path))
        elif education_value not in (None, "", []):
            profile.warnings.append(f"unsupported education format: {type(education_value).__name__}")
        return profile
