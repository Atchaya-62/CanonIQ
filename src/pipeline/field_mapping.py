from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from .config_store import load_config


def normalize_field_key(value: str | None) -> str:
    if not value:
        return ""
    key = re.sub(r"(?<!^)(?=[A-Z])", "_", value)
    key = re.sub(r"[^a-zA-Z0-9]+", "_", key)
    key = re.sub(r"_+", "_", key).strip("_")
    return key.lower()


class FieldAliasResolver:
    def __init__(self, aliases: dict[str, list[str]] | None = None) -> None:
        raw_aliases = aliases if aliases is not None else self._load_aliases()
        self._canonical_to_aliases = {
            normalize_field_key(str(canonical)): [normalize_field_key(str(alias)) for alias in values if alias]
            for canonical, values in raw_aliases.items()
            if canonical
        }
        self._alias_to_canonical = {}
        for canonical, aliases_for_field in self._canonical_to_aliases.items():
            self._alias_to_canonical[canonical] = canonical
            for alias in aliases_for_field:
                self._alias_to_canonical[alias] = canonical

    @lru_cache(maxsize=1)
    def _load_aliases(self) -> dict[str, list[str]]:
        data = load_config("field_aliases.json") or {}
        if isinstance(data, dict) and data:
            result: dict[str, list[str]] = {}
            for key, values in data.items():
                if isinstance(values, list):
                    result[str(key)] = [str(item) for item in values if item is not None]
            if result:
                return result
        return {
            "full_name": ["name", "candidateName", "candidate_name", "personName", "person_name", "fullName"],
            "email": ["email", "emailAddress", "mail"],
            "phone": ["phone", "mobile", "mobileNumber", "contact", "phoneNumber"],
            "skills": ["skills", "skill", "skillset", "skillSet", "competencies"],
            "location": ["location", "city", "currentLocation"],
            "country": ["country", "countryCode"],
            "headline": ["headline", "title", "summary"],
            "experience": ["experience", "workExperience", "work_history"],
            "education": ["education", "educationHistory"],
            "github": ["github", "githubUrl", "html_url"],
            "linkedin": ["linkedin", "linkedinUrl"],
            "website": ["website", "portfolio", "url"],
        }

    def canonical_key(self, key: str | None) -> str:
        normalized = normalize_field_key(key)
        return self._alias_to_canonical.get(normalized, normalized)

    def project(self, payload: dict[str, Any]) -> dict[str, Any]:
        mapped: dict[str, Any] = {}
        for key, value in payload.items():
            canonical = self.canonical_key(key)
            if canonical and canonical not in mapped and value not in (None, "", [], {}):
                mapped[canonical] = value
        return mapped

    def get(self, payload: dict[str, Any], canonical_key: str, default: Any | None = None) -> Any:
        canonical = self.canonical_key(canonical_key)
        if canonical in payload and payload[canonical] not in (None, "", [], {}):
            return payload[canonical]
        normalized = normalize_field_key(canonical_key)
        for key, value in payload.items():
            if normalize_field_key(key) == normalized and value not in (None, "", [], {}):
                return value
            alias = self.canonical_key(key)
            if alias == canonical and value not in (None, "", [], {}):
                return value
        return default

    def nested_value(self, payload: dict[str, Any], canonical_key: str, nested_keys: tuple[str, ...] = ()) -> Any:
        value = self.get(payload, canonical_key)
        if value is not None:
            return value
        for key in nested_keys:
            nested = payload.get(key)
            if isinstance(nested, dict):
                for nested_key in ("value", "name", "label", "city", "country"):
                    nested_value = nested.get(nested_key)
                    if nested_value not in (None, "", [], {}):
                        return nested_value
        return None
