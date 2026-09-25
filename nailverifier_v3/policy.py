from __future__ import annotations

from typing import Dict

# Rules are deliberately disabled until a benchmark has enough manually
# verified examples for that state. This protects large datasets from a rule
# being promoted just because it looked good on a tiny sample.
VALIDATED_RULES: Dict[str, Dict[str, str]] = {
    "SD": {},
}

MIN_RULE_SAMPLES_KEEP = 20
MIN_RULE_SAMPLES_REMOVE = 20
MIN_KEEP_PRECISION = 0.99
MIN_REMOVE_PRECISION = 0.995


def apply_policy(
    state: str,
    decision: str,
    evidence_tier: str,
    rule_id: str,
    candidate_action: str,
) -> Dict[str, str]:
    state = (state or "").upper()

    # A nail-specific current official state license is the strongest source.
    if decision == "VERIFIED_NAIL" and evidence_tier == "OFFICIAL_STATE":
        return {
            "Auto_Action": "KEEP",
            "Policy_Status": "SAFE_OFFICIAL",
        }

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
