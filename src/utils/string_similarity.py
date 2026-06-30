from __future__ import annotations

from difflib import SequenceMatcher

from .text_utils import clean_text, remove_accents


def string_similarity(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left.lower(), right.lower()).ratio()


def token_sort_similarity(left: str | None, right: str | None) -> float:
    left_tokens = _sorted_tokens(left)
    right_tokens = _sorted_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return SequenceMatcher(None, left_tokens, right_tokens).ratio()


def normalized_similarity(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    left_clean = clean_text(remove_accents(left)) or ""
    right_clean = clean_text(remove_accents(right)) or ""
    if not left_clean or not right_clean:
        return 0.0
    return max(string_similarity(left_clean, right_clean), token_sort_similarity(left_clean, right_clean))


def _sorted_tokens(value: str | None) -> str:
    if not value:
        return ""
    cleaned = clean_text(remove_accents(value)) or ""
    tokens = [token.lower() for token in cleaned.split() if token]
    return " ".join(sorted(tokens))
