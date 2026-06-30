from __future__ import annotations

import json

from .base_parser import BaseParser
from .common import collect_emails, fragment_profile, make_value_record
from ..pipeline.field_mapping import FieldAliasResolver
from ..pipeline.loader import SourceDocument
from ..utils.skill_utils import canonicalize_skill
from ..utils.text_utils import clean_text, title_case_name, normalize_url


class GitHubParser(BaseParser):
    source_types = ("github_json", "github_txt")

    def __init__(self) -> None:
        super().__init__()
        self.mapper = FieldAliasResolver()

    def parse(self, document: SourceDocument) -> list:
        self._reset_warnings()
        if not document.text:
            return []
        if document.source_type == "github_json":
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
        profile = fragment_profile("github_json", document.path)
        mapped = self.mapper.project(payload)
        profile.name = make_value_record(title_case_name(mapped.get("full_name") or mapped.get("name") or mapped.get("login")), "github", "json", 0.9, "github profile", source_path=document.path)
        profile.emails = [record for email in collect_emails(json.dumps(payload)) if (record := make_value_record(email, "github", "json", 0.85, "github email", source_path=document.path))]
        profile.links = {"github": record} if (record := make_value_record(normalize_url(mapped.get("github") or mapped.get("html_url") or mapped.get("url")), "github", "json", 0.95, "github url", source_path=document.path)) else {}
        if mapped.get("bio"):
            profile.summary = make_value_record(clean_text(mapped.get("bio")), "github", "json", 0.8, "github bio", source_path=document.path)
        profile.skills.extend(self._language_skills(mapped.get("languages"), document.path))
        profile.skills.extend(self._topic_skills(mapped.get("topics") or mapped.get("repository_topics"), document.path))
        profile.skills.extend(self._repository_skills(mapped.get("repos") or mapped.get("repositories"), document.path))
        return profile

    def _from_text(self, text: str, document: SourceDocument):
        profile = fragment_profile("github_txt", document.path)
        profile.links = {"github": make_value_record(normalize_url(text), "github", "text", 0.6, "text github url")}
        return profile

    def _language_skills(self, languages, source_path: str | None) -> list:
        if not languages:
            return []
        if isinstance(languages, str):
            raw_values = [part.strip() for part in languages.split(",") if part.strip()]
        elif isinstance(languages, list):
            raw_values = [str(item).strip() for item in languages if str(item).strip()]
        else:
            return []
        records = []
        for raw_value in raw_values:
            canonical = canonicalize_skill(raw_value)
            if canonical:
                records.append(make_value_record(canonical, "github", "inferred_from_languages", 0.72, "github languages", source_path=source_path))
        return records

    def _topic_skills(self, topics, source_path: str | None) -> list:
        if not topics:
            return []
        if isinstance(topics, str):
            raw_topics = [part.strip() for part in topics.split(",") if part.strip()]
        elif isinstance(topics, list):
            raw_topics = [str(topic).strip() for topic in topics if str(topic).strip()]
        else:
            return []
        records = []
        for topic in raw_topics:
            canonical = canonicalize_skill(topic)
            if canonical:
                records.append(make_value_record(canonical, "github", "inferred_from_topics", 0.7, "github topics", source_path=source_path))
        return records

    def _repository_skills(self, repositories, source_path: str | None) -> list:
        if not repositories:
            return []
        if not isinstance(repositories, list):
            return []
        records = []
        for repository in repositories:
            repo_name = repository.get("name") if isinstance(repository, dict) else str(repository)
            if not repo_name:
                continue
            parts = repo_name.replace("_", " ").replace("-", " ").split()
            for part in parts:
                canonical = canonicalize_skill(part)
                if canonical and canonical not in {record.value for record in records}:
                    records.append(make_value_record(canonical, "github", "inferred_from_repository", 0.68, "github repository name", source_path=source_path))
        return records
