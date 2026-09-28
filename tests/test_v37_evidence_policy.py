import pytest

from nailverifier_v3.policy import apply_evidence_policy


@pytest.mark.parametrize(
    "status,action,policy_status",
    [
        ("VERIFIED_NAIL", "KEEP", "EVIDENCE_VERIFIED_NAIL"),
        ("VERIFIED_NOT_NAIL", "REMOVE", "EVIDENCE_VERIFIED_NOT_NAIL"),
        ("LIKELY_NAIL", "REVIEW", "EVIDENCE_REVIEW"),
        ("LIKELY_NOT_NAIL", "REVIEW", "EVIDENCE_REVIEW"),
        ("CONFLICTING_EVIDENCE", "REVIEW", "EVIDENCE_REVIEW"),
        ("UNKNOWN", "REVIEW", "EVIDENCE_REVIEW"),
    ],
)
def test_evidence_first_policy(status, action, policy_status):
    result = apply_evidence_policy(status)
    assert result["Auto_Action"] == action
    assert result["Policy_Status"] == policy_status
