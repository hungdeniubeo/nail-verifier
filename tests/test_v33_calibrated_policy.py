from __future__ import annotations

from nailverifier_v3.features import assess_local
from nailverifier_v3.models import BusinessRecord
from nailverifier_v3.policy import apply_policy


def structured(name: str) -> BusinessRecord:
    return BusinessRecord(
        company=name,
        street="100 Main St",
        city="Sioux Falls",
        state="SD",
        zip_code="57104",
        phone="6055550100",
        rating=4.8,
        reviews=25,
        status="OPERATIONAL",
    )


def test_nail_supply_is_not_candidate_keep():
    result = assess_local(structured("Dakota Nail Supply"))
    assert result.candidate_action == "REVIEW"
    assert result.rule_id == "R_NAIL_NON_SERVICE_CONFLICT"


def test_nail_academy_is_not_candidate_keep():
    result = assess_local(structured("Elite Nail Academy"))
    assert result.candidate_action == "REVIEW"
    assert result.rule_id == "R_NAIL_NON_SERVICE_CONFLICT"


def test_regular_nail_spa_remains_strong_candidate_keep():
    result = assess_local(structured("Luxury Nails Spa"))
    assert result.rule_id == "R_NAIL_EXPLICIT_STRONG"
    assert result.candidate_action == "KEEP"


def test_calibrated_sd_strong_nail_rule_auto_keeps():
    policy = apply_policy(
        "SD",
        "LIKELY_NAIL",
        "NAILMAP_STRUCTURED",
        "R_NAIL_EXPLICIT_STRONG",
        "KEEP",
        allow_validated_rules=True,
    )
    assert policy["Auto_Action"] == "KEEP"
    assert policy["Policy_Status"] == "BENCHMARK_VALIDATED_RULE"


def test_calibrated_sd_non_nail_rule_auto_removes():
    policy = apply_policy(
        "SD",
        "LIKELY_NOT_NAIL",
        "NAILMAP_STRUCTURED",
        "R_NON_NAIL_CATEGORY_STRONG",
        "REMOVE",
        allow_validated_rules=True,
    )
    assert policy["Auto_Action"] == "REMOVE"
    assert policy["Policy_Status"] == "BENCHMARK_VALIDATED_RULE"


def test_same_rules_remain_blocked_outside_sd():
    policy = apply_policy(
        "CA",
        "LIKELY_NAIL",
        "NAILMAP_STRUCTURED",
        "R_NAIL_EXPLICIT_STRONG",
        "KEEP",
        allow_validated_rules=True,
    )
    assert policy["Auto_Action"] == "REVIEW"
