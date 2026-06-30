from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .text_utils import clean_text, remove_accents
from ..pipeline.config_store import load_config
from ..pipeline.normalization_engine import default_normalization_engine

COUNTRY_ALIASES = {
    "united states": "US",
    "usa": "US",
    "u.s.a.": "US",
    "us": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "india": "IN",
    "spain": "ES",
    "canada": "CA",
    "germany": "DE",
    "france": "FR",
    "australia": "AU",
}

CITY_ALIASES = {
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "bombay": "Mumbai",
    "mumbai": "Mumbai",
    "calcutta": "Kolkata",
    "kolkata": "Kolkata",
    "madras": "Chennai",
    "chennai": "Chennai",
}


def normalize_country(value: str | None) -> str | None:
    cleaned = clean_text(remove_accents(value))
    if not cleaned:
        return None
    config = load_config("normalization_config.json") or {}
    aliases = {**COUNTRY_ALIASES, **{str(key).lower(): str(val) for key, val in (config.get("country_aliases") or {}).items()}}
    return aliases.get(cleaned.lower(), cleaned.upper()[:2])


def normalize_location(value: str | None) -> str | None:
    return default_normalization_engine().normalize_location_value(value)
