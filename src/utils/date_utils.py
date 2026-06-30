from __future__ import annotations

from datetime import date, datetime


def normalize_date(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
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


def normalize_month(value: str | None) -> str | None:
    return normalize_date(value)


def current_month() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"
