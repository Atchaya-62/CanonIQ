from __future__ import annotations

import json

from .base_parser import BaseParser
from .common import collect_emails, collect_phones, extract_skills, fragment_profile, make_value_record
from ..pipeline.loader import SourceDocument
from ..utils.text_utils import title_case_name


class NotesParser(BaseParser):
    source_types = ("notes_txt", "notes_json")

    def parse(self, document: SourceDocument) -> list:
        self._reset_warnings()
        if not document.text:
            return []
        if document.source_type in {"notes_json", "json"}:
            try:
                payload = json.loads(document.text)
            except json.JSONDecodeError:
                self._warn(document, "Malformed JSON skipped.")
                return []
            if isinstance(payload, dict):
                profile = self._from_text(" ".join(str(v) for v in payload.values()), document)
                return [profile] if profile.has_minimum_identity() else self._reject_orphan_notes(document, profile)
            self._warn(document, "Malformed JSON skipped.")
            return []
        try:
            payload = json.loads(document.text)
            if isinstance(payload, dict):
                profile = self._from_text(" ".join(str(v) for v in payload.values()), document)
                return [profile] if profile.has_minimum_identity() else self._reject_orphan_notes(document, profile)
        except json.JSONDecodeError:
            pass
        profile = self._from_text(document.text, document)
        return [profile] if profile.has_minimum_identity() else self._reject_orphan_notes(document, profile)

    def _from_text(self, text: str, document: SourceDocument):
        profile = fragment_profile("notes_txt", document.path)
        profile.emails = [record for email in collect_emails(text) if (record := make_value_record(email, "notes", "text", 0.7, "notes email", source_path=document.path))]
        profile.phones = [record for phone in collect_phones(text) if (record := make_value_record(phone, "notes", "text", 0.7, "notes phone", source_path=document.path))]
        profile.skills = [record for skill in extract_skills(text) if (record := make_value_record(skill, "notes", "text", 0.7, "notes skills", source_path=document.path))]
        profile.notes = [record for line in self._note_lines(text) if (record := make_value_record(line, "notes", "text", 0.6, "recruiter notes", source_path=document.path))]
        profile.name = self._maybe_name(text, profile)
        return profile

    def _note_lines(self, text: str) -> list[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return lines or ([text.strip()] if text.strip() else [])

    def _maybe_name(self, text: str, profile):
        first_line = self._note_lines(text)[0] if self._note_lines(text) else None
        if not first_line:
            return None
        if len(first_line.split()) > 4:
            return None
        if any(token.lower() in {"recruiter", "notes", "email", "github", "linkedin"} for token in first_line.split()):
            return None
        candidate_name = title_case_name(first_line)
        if candidate_name and len(candidate_name.split()) >= 2:
            return make_value_record(candidate_name, "notes", "text", 0.35, "notes candidate name", source_path=profile.provenance[0].source if profile.provenance else None)
        return None

    def _reject_orphan_notes(self, document: SourceDocument, profile):
        self._warn(document, "Recruiter notes ignored because no candidate identity exists.")
        return []
