from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from os import getenv
import re

from ..pipeline.normalization_engine import NormalizationContext, default_normalization_engine

try:  # pragma: no cover - optional dependency
    import phonenumbers
except Exception:  # pragma: no cover - optional dependency
    phonenumbers = None

PHONE_DIGITS_RE = re.compile(r"\D+")
DATE_LIKE_PHONE_RE = re.compile(r"^20\d{2}[-/ ]?\d{2}([-/ ]?\d{2})?$")
COUNTRY_CALLING_CODES = {
    "IN": "91",
    "GB": "44",
    "US": "1",
}


@lru_cache(maxsize=1)
def _default_country() -> str:
    override = getenv("EIGHTFOLD_DEFAULT_COUNTRY")
    if override:
        return override.strip().upper()
    config_path = Path(__file__).resolve().parents[1] / "config" / "phone_settings.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        country = str(data.get("default_country", "")).strip().upper()
        if country:
            return country
    return "IN"


def normalize_phone(
    value: str | None,
    default_country: str | None = None,
    location: str | None = None,
    fallback_region: str | None = None,
) -> str | None:
    if value is None:
        return None
    raw = value.strip()
    if DATE_LIKE_PHONE_RE.match(raw.replace(".", "-")):
        return None
    context = NormalizationContext(
        field_name="phone",
        location=location,
        default_region=(default_country or fallback_region or _default_country()).strip().upper(),
        fallback_region=(fallback_region or _default_country()).strip().upper(),
    )
    normalized = default_normalization_engine().normalize_phone_value(raw, context=context)
    return normalized


def is_valid_phone(value: str | None, default_country: str | None = None) -> bool:
    return normalize_phone(value, default_country=default_country) is not None
