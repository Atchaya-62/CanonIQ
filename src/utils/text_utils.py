from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse, urlunparse

from ..pipeline.normalization_engine import default_normalization_engine


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = unicodedata.normalize("NFKC", value).strip()
    cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or None


def remove_accents(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def title_case_name(value: str | None) -> str | None:
    return default_normalization_engine().normalize_name_value(value)


def _title_case_segment(value: str) -> str:
    return "-".join(part.capitalize() for part in value.split("-"))


def normalize_whitespace(value: str | None) -> str | None:
    return clean_text(value)


def normalize_url(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = clean_text(value)
    if not cleaned:
        return None
    if not cleaned.startswith(("http://", "https://")):
        cleaned = "https://" + cleaned
    parsed = urlparse(cleaned)
    if not parsed.netloc:
        return None
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return urlunparse((scheme, netloc, path, "", "", ""))
