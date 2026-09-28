from __future__ import annotations

from typing import Dict, Optional, Tuple

from .models import BusinessRecord
from .normalize import normalize_name, normalize_street, normalize_text, normalize_zip

# State-scoped calibrated rules.
# South Dakota R_NAIL_EXPLICIT_STRONG reached 74/74 labeled correct cases
# across the base calibration + v34 addendum, with Wilson 95% lower bound
# just above the 0.95 gate. REMOVE rules remain shadow-only because the full
# 35-case SD cohort is empirically clean but the Wilson lower bound is ~0.90.
VALIDATED_RULES: Dict[str, Dict[str, str]] = {
    "SD": {
        "R_NAIL_EXPLICIT_STRONG": "KEEP",
    },
}

# Exact identities independently verified during the SD v3.5 address-strong
# calibration. This is deliberately NOT a generic rule: name + full normalized
# street (including suite/unit) + city + ZIP must match one of these records.
# K & E Nail Studio LLC is intentionally absent because current public evidence
# was insufficient to verify that exact identity.
VERIFIED_IDENTITY_ALLOWLIST: Dict[str, Dict[Tuple[str, str, str, str], str]] = {
    "SD": {
        (normalize_name("Anna's Nails"), normalize_street("712 University Ave Ste A"), normalize_text("Hot Springs"), "57747"): "KEEP",
        (normalize_name("Nails By Alayna Reyes"), normalize_street("901 N Main St Ste 4"), normalize_text("Mitchell"), "57301"): "KEEP",
        (normalize_name("Olive & Opal Nail Studio"), normalize_street("501 Main St Studio 4"), normalize_text("Rapid City"), "57701"): "KEEP",
        (normalize_name("Simplee Nails"), normalize_street("317 Main St Ste 1"), normalize_text("Rapid City"), "57701"): "KEEP",
        (normalize_name("The Nail Room"), normalize_street("822 Main St Ste 5"), normalize_text("Rapid City"), "57701"): "KEEP",
        (normalize_name("The Nail Haus By Adamari"), normalize_street("5201 S Solberg Ave suite 205"), normalize_text("Sioux Falls"), "57108"): "KEEP",
        (normalize_name("Zen Nail Studio"), normalize_street("5201 S Solberg Ave suite 200"), normalize_text("Sioux Falls"), "57108"): "KEEP",
    },
}

MIN_RULE_SAMPLES_KEEP = 20
MIN_RULE_SAMPLES_REMOVE = 20
MIN_KEEP_PRECISION = 0.99
MIN_REMOVE_PRECISION = 0.995
MIN_WILSON_LOWER_BOUND = 0.95


def _verified_identity_key(record: BusinessRecord) -> Tuple[str, str, str, str]:
    return (
        normalize_name(record.company),
        normalize_street(record.street),
        normalize_text(record.city),
        normalize_zip(record.zip_code),
    )


def apply_verified_identity_policy(
    record: BusinessRecord,
    rule_id: str,
    candidate_action: str,
) -> Optional[Dict[str, str]]:
    """Allow only exact, independently verified address-strong identities."""
    if rule_id != "R_NAIL_EXPLICIT_ADDRESS_STRONG" or candidate_action != "KEEP":
        return None

    state = (record.state or "").upper()
    allowed_action = VERIFIED_IDENTITY_ALLOWLIST.get(state, {}).get(_verified_identity_key(record))
    if allowed_action != candidate_action:
        return None

    return {
        "Auto_Action": candidate_action,
        "Policy_Status": "VERIFIED_IDENTITY_ALLOWLIST",
    }


def apply_policy(
    state: str,
    decision: str,
    evidence_tier: str,
    rule_id: str,
    candidate_action: str,
    allow_validated_rules: bool = False,
) -> Dict[str, str]:
    state = (state or "").upper()

    # A nail-specific current official state license is the strongest source.
    if decision == "VERIFIED_NAIL" and evidence_tier == "OFFICIAL_STATE":
        return {
            "Auto_Action": "KEEP",
            "Policy_Status": "SAFE_OFFICIAL",
        }

    if allow_validated_rules:
        enabled = VALIDATED_RULES.get(state, {})
        allowed_action = enabled.get(rule_id)
        if allowed_action and allowed_action == candidate_action:
            return {
                "Auto_Action": candidate_action,
                "Policy_Status": "BENCHMARK_VALIDATED_RULE",
            }

    if candidate_action in {"KEEP", "REMOVE"}:
        return {
            "Auto_Action": "REVIEW",
            "Policy_Status": "CANDIDATE_NEEDS_BENCHMARK",
        }

    return {
        "Auto_Action": "REVIEW",
        "Policy_Status": "REVIEW_ONLY",
    }
