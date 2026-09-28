from __future__ import annotations

from typing import Dict

# Legacy calibration metadata is retained for benchmark reporting only.
# The v3.7 evidence-first engine does not use these rules to auto-act.
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


def apply_evidence_policy(verification_status: str) -> Dict[str, str]:
    """Translate evidence-level truth into an automatic action.

    Business identities do not live in policy code. Only consensus outcomes
    may unlock automatic actions in the v3.7 evidence-first profile.
    """
    if verification_status == "VERIFIED_NAIL":
        return {"Auto_Action": "KEEP", "Policy_Status": "EVIDENCE_VERIFIED_NAIL"}
    if verification_status == "VERIFIED_NOT_NAIL":
        return {"Auto_Action": "REMOVE", "Policy_Status": "EVIDENCE_VERIFIED_NOT_NAIL"}
    return {"Auto_Action": "REVIEW", "Policy_Status": "EVIDENCE_REVIEW"}


def apply_policy(
    state: str,
    decision: str,
    evidence_tier: str,
    rule_id: str,
    candidate_action: str,
    allow_validated_rules: bool = False,
) -> Dict[str, str]:
    """Legacy calibration policy kept for benchmark tooling/tests.

    New production verification must call :func:`apply_evidence_policy`.
    """
    state = (state or "").upper()

    if decision == "VERIFIED_NAIL" and evidence_tier == "OFFICIAL_STATE":
        return {"Auto_Action": "KEEP", "Policy_Status": "SAFE_OFFICIAL"}

    if allow_validated_rules:
        allowed_action = VALIDATED_RULES.get(state, {}).get(rule_id)
        if allowed_action and allowed_action == candidate_action:
            return {"Auto_Action": candidate_action, "Policy_Status": "BENCHMARK_VALIDATED_RULE"}

    if candidate_action in {"KEEP", "REMOVE"}:
        return {"Auto_Action": "REVIEW", "Policy_Status": "CANDIDATE_NEEDS_BENCHMARK"}

    return {"Auto_Action": "REVIEW", "Policy_Status": "REVIEW_ONLY"}
