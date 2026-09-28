from __future__ import annotations

from typing import Dict

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

MIN_RULE_SAMPLES_KEEP = 20
MIN_RULE_SAMPLES_REMOVE = 20
MIN_KEEP_PRECISION = 0.99
MIN_REMOVE_PRECISION = 0.995
MIN_WILSON_LOWER_BOUND = 0.95


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
