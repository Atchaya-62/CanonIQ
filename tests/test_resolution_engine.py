from __future__ import annotations

from src.models.candidate import CandidateProfile, ValueRecord
from src.pipeline.matcher import CandidateMatcher
from src.pipeline.normalizer import CandidateNormalizer
from src.utils.location_utils import normalize_location
from src.utils.phone_utils import normalize_phone
from src.utils.skill_utils import canonicalize_skill


def test_weighted_matching_merges_linkedin_enrichment():
    csv_profile = CandidateProfile()
    csv_profile.name = ValueRecord("Jose Alvarez", "csv", "csv", "1970-01-01T00:00:00Z", 0.9, "name")
    csv_profile.emails = [ValueRecord("jose@gmail.com", "csv", "csv", "1970-01-01T00:00:00Z", 0.9, "email")]
    csv_profile.phones = [ValueRecord("+34612345678", "csv", "csv", "1970-01-01T00:00:00Z", 0.9, "phone")]
    csv_profile = CandidateNormalizer().normalize(csv_profile)

    linkedin_profile = CandidateProfile()
    linkedin_profile.name = ValueRecord("José Álvarez", "linkedin", "json", "1970-01-01T00:00:00Z", 0.95, "name")
    linkedin_profile.summary = ValueRecord("AI Engineer", "linkedin", "json", "1970-01-01T00:00:00Z", 0.95, "headline")
    linkedin_profile.locations = [ValueRecord("Madrid, Spain", "linkedin", "json", "1970-01-01T00:00:00Z", 0.95, "location")]
    linkedin_profile = CandidateNormalizer().normalize(linkedin_profile)

    clusters, decisions = CandidateMatcher().cluster([csv_profile, linkedin_profile])
    assert len(clusters) == 1
    assert decisions and decisions[0].score >= 0.85


def test_location_alias_and_phone_normalization_are_contextual():
    assert normalize_location("bangalore, india") == "Bengaluru, India"
    assert normalize_phone("9876543210") == "+919876543210"


def test_skill_canonicalization_uses_alias_dictionary():
    assert canonicalize_skill("Tensor Flow") == "TensorFlow"
    assert canonicalize_skill("ML") == "Machine Learning"
