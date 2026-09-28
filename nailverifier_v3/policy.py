from __future__ import annotations

from typing import Dict

# No local heuristic rule is auto-enabled yet.
# Keep state-scoped validation data separate from production policy until the
# rule has enough independent labels and survives a statistical confidence
# check. Official nail-specific state evidence may still auto KEEP.
VALIDATED_RULES: Dict[str, Dict[str, str]] = {
    "SD": {},
}

# Empirical thresholds are reported, but they are NOT sufficient by themselves
# to enable a rule. benchmark_v3.py also reports a Wilson confidence lower bound.
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
