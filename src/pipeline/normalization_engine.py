from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from .config_store import load_config
from .field_mapping import normalize_field_key

try:  # pragma: no cover - optional dependency
    import phonenumbers
except Exception:  # pragma: no cover - optional dependency
    phonenumbers = None

try:  # pragma: no cover - optional dependency
    import rapidfuzz  # noqa: F401
except Exception:  # pragma: no cover - optional dependency
    rapidfuzz = None


CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
WHITESPACE_RE = re.compile(r"\s+")
NON_DIGIT_RE = re.compile(r"\D+")


@dataclass(slots=True)
class NormalizationContext:
    field_name: str
    source: str | None = None
    location: str | None = None
    default_region: str | None = None
    fallback_region: str | None = None


class Normalizer:
    field_name = ""

    def normalize(self, value: Any, context: NormalizationContext | None = None) -> Any:
        if value is None:
            return None
        text = self._base_normalize(value)
        if not text:
            return None
        normalized = self._field_normalize(text, context)
        return normalized if normalized not in ("", [], {}) else None

    def _base_normalize(self, value: Any) -> str:
        text = unicodedata.normalize("NFKC", str(value)).strip()
        text = CONTROL_CHAR_RE.sub(" ", text)
        text = WHITESPACE_RE.sub(" ", text)
        return text.strip()

    def _field_normalize(self, value: str, context: NormalizationContext | None = None) -> Any:
        return value


class EmailNormalizer(Normalizer):
    field_name = "email"

    def _field_normalize(self, value: str, context: NormalizationContext | None = None) -> str | None:
        lowered = value.lower()
        if "@" not in lowered or lowered.startswith("@") or lowered.endswith("@"):
            return None
        local, _, domain = lowered.partition("@")
        if not local or "." not in domain:
            return None
        return f"{local}@{domain}"


class PhoneNormalizer(Normalizer):
    field_name = "phone"

    def _field_normalize(self, value: str, context: NormalizationContext | None = None) -> str | None:
        region = self._region(context)
        if phonenumbers is not None:
            try:
                parsed = phonenumbers.parse(value, region or None)
                if phonenumbers.is_valid_number(parsed):
                    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            except Exception:
                pass
        digits = NON_DIGIT_RE.sub("", value)
        if not digits:
            return None
        if value.startswith("+"):
            return f"+{digits}"
        if digits.startswith("00") and len(digits) > 2:
            return f"+{digits[2:]}"
        calling_code = self._calling_code(region)
        if len(digits) == 11 and digits.startswith("0") and (region == "GB" or digits[1] == "7"):
            return f"+44{digits[1:]}"
        if len(digits) == 12 and digits.startswith("91"):
            return f"+{digits}"
        if region == "IN" and len(digits) == 10:
            if digits[0] in {"6", "7", "8", "9"}:
                return f"+91{digits}"
            return f"+1{digits}"
        if region == "US" and len(digits) == 10:
            return f"+1{digits}"
        if calling_code and len(digits) == 10 and region not in {"IN", "US"}:
            return f"+{calling_code}{digits}"
        if calling_code and len(digits) >= 11 and digits.startswith(calling_code):
            return f"+{digits}"
        if len(digits) == 10 and digits[0] in {"6", "7", "8", "9"}:
            return f"+91{digits}"
        if len(digits) >= 10:
            return f"+{digits}"
        return None

    def _region(self, context: NormalizationContext | None) -> str:
        if context and context.default_region:
            return context.default_region.upper()
        if context and context.location:
            country = self._country_from_location(context.location)
            if country:
                return country
        if context and context.fallback_region:
            return context.fallback_region.upper()
        config = load_config("normalization_config.json") or {}
        for key in ("fallback_region", "default_region"):
            value = str(config.get(key, "")).strip().upper()
            if value:
                return value
        return "IN"

    def _country_from_location(self, location: str) -> str | None:
        normalized = location.replace(",", " ").strip().upper()
        if "INDIA" in normalized or normalized.endswith(" IN"):
            return "IN"
        if "UNITED STATES" in normalized or "USA" in normalized or normalized.endswith(" US"):
            return "US"
        if "UNITED KINGDOM" in normalized or "UK" in normalized or normalized.endswith(" GB"):
            return "GB"
        return None

    def _calling_code(self, region: str) -> str | None:
        return {"IN": "91", "US": "1", "GB": "44"}.get(region.upper())


class LocationNormalizer(Normalizer):
    field_name = "location"

    def _field_normalize(self, value: str, context: NormalizationContext | None = None) -> str | None:
        config = load_config("normalization_config.json") or {}
        city_aliases = {str(key).lower(): str(val) for key, val in (config.get("city_aliases") or {}).items()}
        parts = [part.strip() for part in value.split(",") if part.strip()]
        if not parts:
            return None
        normalized_parts: list[str] = []
        for index, part in enumerate(parts):
            lowered = self._strip_accents(part).lower()
            normalized_parts.append(city_aliases.get(lowered, self._title_case(part)))
        return ", ".join(normalized_parts)

    def _strip_accents(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))

    def _title_case(self, value: str) -> str:
        return " ".join(part.capitalize() for part in value.split())

class SkillNormalizer(Normalizer):
    field_name = "skill"

    def _field_normalize(self, value: str, context: NormalizationContext | None = None) -> str | None:
        from ..utils.skill_utils import canonicalize_skill

        return canonicalize_skill(value)


class NameNormalizer(Normalizer):
    field_name = "name"

    def _field_normalize(self, value: str, context: NormalizationContext | None = None) -> str | None:
        value = value.replace("_", " ").replace(".", " ")
        value = re.sub(r"\s+", " ", value)
        parts = [part for part in value.split(" ") if part]
        if not parts:
            return None
        return " ".join(self._title_segment(part) for part in parts)

    def _title_segment(self, segment: str) -> str:
        return "-".join("'".join(part.capitalize() for part in piece.split("'")) for piece in segment.split("-"))


class DateNormalizer(Normalizer):
    field_name = "date"

    def _field_normalize(self, value: str, context: NormalizationContext | None = None) -> str | None:
        from datetime import datetime

        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%Y", "%Y-%m"):
            try:
                parsed = datetime.strptime(value, fmt)
                return parsed.strftime("%Y-%m")
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(value)
            return parsed.strftime("%Y-%m")
        except ValueError:
            return None


class TextNormalizer(Normalizer):
    field_name = "text"

    def _field_normalize(self, value: str, context: NormalizationContext | None = None) -> str | None:
        return value


class NormalizationEngine:
    def __init__(self) -> None:
        self._normalizers: dict[str, Normalizer] = {
            "email": EmailNormalizer(),
            "phone": PhoneNormalizer(),
            "location": LocationNormalizer(),
            "skill": SkillNormalizer(),
            "skills": SkillNormalizer(),
            "name": NameNormalizer(),
            "full_name": NameNormalizer(),
            "headline": TextNormalizer(),
            "summary": TextNormalizer(),
            "date": DateNormalizer(),
        }

    def normalize(self, field_name: str, value: Any, context: NormalizationContext | None = None) -> Any:
        canonical = normalize_field_key(field_name)
        normalizer = self._normalizers.get(canonical, TextNormalizer())
        context = context or NormalizationContext(field_name=canonical)
        return normalizer.normalize(value, context)

    def normalize_name_value(self, value: Any) -> str | None:
        return self.normalize("name", value)

    def normalize_email_value(self, value: Any) -> str | None:
        return self.normalize("email", value)

    def normalize_phone_value(self, value: Any, context: NormalizationContext | None = None) -> str | None:
        return self.normalize("phone", value, context=context)

    def normalize_location_value(self, value: Any) -> str | None:
        return self.normalize("location", value)

    def normalize_skill_value(self, value: Any) -> str | None:
        return self.normalize("skill", value)

    def normalize_date_value(self, value: Any) -> str | None:
        return self.normalize("date", value)


@lru_cache(maxsize=1)
def default_normalization_engine() -> NormalizationEngine:
    return NormalizationEngine()
