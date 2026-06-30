from __future__ import annotations

import csv
import io

from .base_parser import BaseParser
from .common import build_education, build_experience, collect_emails, collect_phones, extract_skills, fragment_profile, make_value_record
from ..pipeline.field_mapping import FieldAliasResolver
from ..pipeline.loader import SourceDocument
from ..utils.text_utils import clean_text, title_case_name


class CSVParser(BaseParser):
    source_types = ("csv",)

    def __init__(self) -> None:
        super().__init__()
        self.mapper = FieldAliasResolver()

    def parse(self, document: SourceDocument) -> list:
        self._reset_warnings()
        if not document.text:
            return []
        reader = csv.DictReader(io.StringIO(document.text))
        profiles = []
        for row_number, row in enumerate(reader, start=2):
            profile = self._row_to_profile(row, document, row_number)
            if profile is not None:
                profiles.append(profile)
        return profiles

    def _row_to_profile(self, row: dict[str, str], document: SourceDocument, row_number: int):
        if not any((value or "").strip() for value in row.values()):
            self._warn(document, f"row {row_number}: empty CSV row skipped.")
            return None
        mapped = self.mapper.project(row)
        email_value = row.get("email")
        if email_value and not collect_emails(email_value):
            self._warn(document, f"row {row_number}: invalid email format.")
            return None
        phone_value = row.get("phone")
        if phone_value and not collect_phones(phone_value):
            self._warn(document, f"row {row_number}: invalid phone format.")
            return None
        profile = fragment_profile("csv", document.path)
        profile.name = make_value_record(mapped.get("full_name") or mapped.get("name"), "csv", "column", 0.8, "name column", source_path=document.path)
        profile.name and setattr(profile.name, "value", title_case_name(profile.name.value))
        joined = " ".join(str(value) for value in row.values() if value)
        profile.emails = [record for email in collect_emails(joined) if (record := make_value_record(email, "csv", "column", 0.9, "email column", source_path=document.path))]
        profile.phones = [record for phone in collect_phones(joined) if (record := make_value_record(phone, "csv", "column", 0.8, "phone column", source_path=document.path))]
        profile.skills = [record for skill in extract_skills(mapped.get("skills") or mapped.get("skill")) if (record := make_value_record(skill, "csv", "column", 0.85, "skills column", source_path=document.path))]
        if company := clean_text(mapped.get("company")):
            profile.experience = [build_experience(company, mapped.get("title"), mapped.get("location"), mapped.get("start_date"), mapped.get("end_date"), str(mapped.get("current", "")).lower() in {"1", "true", "yes"}, mapped.get("summary"), "csv", document.path)]
        if institution := clean_text(mapped.get("institution")):
            profile.education = [build_education(institution, mapped.get("degree"), mapped.get("field_of_study"), mapped.get("education_start"), mapped.get("education_end"), "csv", document.path)]
        if location := clean_text(mapped.get("location")):
            profile.locations = [make_value_record(location, "csv", "column", 0.8, "location column", source_path=document.path)]
        if headline := clean_text(mapped.get("headline")):
            profile.summary = make_value_record(headline, "csv", "column", 0.8, "headline column", source_path=document.path)
        profile.links = {k: record for k, v in {"github": mapped.get("github"), "linkedin": mapped.get("linkedin"), "website": mapped.get("website")}.items() if (record := make_value_record(v, "csv", "column", 0.8, "link column", source_path=document.path))}
        if not profile.has_minimum_identity():
            self._warn(document, f"row {row_number}: discarded because no candidate identity exists.")
            return None
        return profile
