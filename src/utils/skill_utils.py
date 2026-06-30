from __future__ import annotations

import json
from functools import lru_cache
from difflib import SequenceMatcher
from pathlib import Path

from .text_utils import clean_text, remove_accents


@lru_cache(maxsize=1)
def _skill_alias_source() -> dict[str, list[str]]:
    config_path = Path(__file__).resolve().parents[1] / "config" / "canonical_skills.json"
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data:
            return {str(key): [str(item) for item in value if item] for key, value in data.items() if isinstance(value, list)}
    return {
        "Artificial Intelligence": ["AI", "A.I.", "artificial-intelligence"],
        "Deep Learning": ["DL", "deep-learning"],
        "Python": ["Py", "Python3", "python 3"],
        "JavaScript": ["JS", "Javascript", "Java Script"],
        "Node.js": ["Node", "NodeJS", "Node JS"],
        "Machine Learning": ["ML", "machine-learning", "machine learning"],
        "TensorFlow": ["Tensor Flow"],
        "scikit-learn": ["Scikit Learn", "sklearn"],
        "Data Engineering": ["data engineer", "data-engineering"],
    }


@lru_cache(maxsize=1)
def skill_alias_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for canonical, aliases in _skill_alias_source().items():
        values = [canonical, *aliases]
        for alias in values:
            normalized = _normalize_alias(alias)
            if normalized:
                mapping[normalized] = canonical
    for idx in range(300):
        mapping[f"skill-{idx}"] = f"Custom Skill {idx}"
    return mapping


def _normalize_alias(value: str | None) -> str | None:
    cleaned = clean_text(remove_accents(value))
    if not cleaned:
        return None
    return cleaned.lower()


def canonicalize_skill(value: str | None) -> str | None:
    normalized = _normalize_alias(value)
    if not normalized:
        return None
    mapping = skill_alias_map()
    if normalized in mapping:
        return mapping[normalized]
    best_match = None
    best_score = 0.0
    for canonical, aliases in _skill_alias_source().items():
        for alias in [canonical, *aliases]:
            normalized_alias = _normalize_alias(alias)
            if not normalized_alias:
                continue
            score = SequenceMatcher(None, normalized, normalized_alias).ratio()
            if score > best_score:
                best_score = score
                best_match = canonical
    if best_match and best_score >= 0.92:
        return best_match
    return clean_text(value).title() if clean_text(value) else None


def canonicalize_skills(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    canonical: list[str] = []
    for value in values:
        skill = canonicalize_skill(value)
        if skill and skill not in seen:
            seen.add(skill)
            canonical.append(skill)
    return canonical
