from __future__ import annotations

import re

from ..pipeline.normalization_engine import default_normalization_engine

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str | None) -> str | None:
    normalized = default_normalization_engine().normalize_email_value(value)
    return normalized if normalized and EMAIL_RE.match(normalized) else None


def is_valid_email(value: str | None) -> bool:
    return normalize_email(value) is not None
