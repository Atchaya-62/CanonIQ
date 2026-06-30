from __future__ import annotations

import pytest

from src.utils.date_utils import normalize_date
from src.utils.email_utils import normalize_email
from src.utils.location_utils import normalize_country, normalize_location
from src.utils.phone_utils import normalize_phone
from src.utils.skill_utils import canonicalize_skill, canonicalize_skills, skill_alias_map
from src.utils.string_similarity import string_similarity
from src.utils.text_utils import clean_text, normalize_url, title_case_name


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Alice.Doe@Example.com", "alice.doe@example.com"),
        (" alice@example.com ", "alice@example.com"),
        ("bad@", None),
        (None, None),
        ("john+label@company.io", "john+label@company.io"),
    ],
)
def test_normalize_email(value, expected):
    assert normalize_email(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("+1 (415) 555-0101", "+14155550101"),
        ("415-555-0101", "+14155550101"),
        ("+44 20 7946 0958", "+442079460958"),
        ("9876543210", "+919876543210"),
        ("07123456789", "+447123456789"),
        ("123", None),
        (None, None),
    ],
)
def test_normalize_phone(value, expected):
    assert normalize_phone(value) == expected


def test_normalize_phone_can_use_configured_region():
    assert normalize_phone("07123456789", default_country="GB") == "+447123456789"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2024-05-21", "2024-05"),
        ("2024/05/21", "2024-05"),
        ("05/2024", "2024-05"),
        ("not-a-date", None),
    ],
)
def test_normalize_date(value, expected):
    assert normalize_date(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("san francisco, united states", "San Francisco, United States"),
        ("münchen, germany", "München, Germany"),
        ("são paulo, brazil", "São Paulo, Brazil"),
        ("", None),
        (None, None),
    ],
)
def test_normalize_location(value, expected):
    assert normalize_location(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("united states", "US"),
        ("India", "IN"),
        ("uk", "GB"),
        ("Japan", "JA"),
        ("Spain", "ES"),
    ],
)
def test_normalize_country(value, expected):
    assert normalize_country(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("AI", "Artificial Intelligence"),
        ("DL", "Deep Learning"),
        ("ML", "Machine Learning"),
        ("Java Script", "JavaScript"),
        ("NodeJS", "Node.js"),
        ("Python3", "Python"),
        ("Tensor Flow", "TensorFlow"),
        ("Scikit Learn", "scikit-learn"),
        ("machine-learning", "Machine Learning"),
        ("Snowflake", "Snowflake"),
        ("unknown skill", "Unknown Skill"),
    ],
)
def test_canonicalize_skill(value, expected):
    assert canonicalize_skill(value) == expected


def test_skill_alias_map_is_large_enough():
    assert len(skill_alias_map()) >= 300


def test_canonicalize_skills_deduplicates():
    assert canonicalize_skills(["Python", "python3", "ML", "machine-learning"]) == ["Python", "Machine Learning"]


@pytest.mark.parametrize(
    ("left", "right", "minimum"),
    [
        ("Alice Doe", "Alice Doe", 1.0),
        ("Alice Doe", "Alicia Doe", 0.6),
        ("Python", "Java", 0.0),
    ],
)
def test_string_similarity(left, right, minimum):
    assert string_similarity(left, right) >= minimum


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("josé álvarez", "José Álvarez"),
        ("łukasz nowak", "Łukasz Nowak"),
        ("zoë kravitz", "Zoë Kravitz"),
        ("renée zellweger", "Renée Zellweger"),
        ("müller", "Müller"),
        ("são paulo", "São Paulo"),
        ("jean-luc picard", "Jean-Luc Picard"),
        ("محمد علي", "محمد علي"),
        ("张伟", "张伟"),
        ("やまだ たろう", "やまだ たろう"),
    ],
)
def test_title_case_name_preserves_unicode(value, expected):
    assert title_case_name(value) == expected


def test_text_helpers():
    assert clean_text("  A  B  ") == "A B"
    assert title_case_name("maria del mar") == "Maria Del Mar"
    assert normalize_url("github.com/alice") == "https://github.com/alice"
