from nailverifier_v3.consensus import resolve_consensus
from nailverifier_v3.evidence_classifier import EvidenceSignal


def sig(key, tier, direction, category="", service="", status="ACTIVE", checked_at="2026-09-28"):
    return EvidenceSignal(key, key, tier, f"https://{key}/x", direction, tier != "D", category, service, status, checked_at, "note")


def test_one_tier_a_nail_verifies():
    out = resolve_consensus([sig("official.com","A","NAIL",service="manicure")]).to_dict()
    assert out["Verification_Status"] == "VERIFIED_NAIL"


def test_one_tier_a_not_nail_verifies():
    out = resolve_consensus([sig("acehardware.com","A","NOT_NAIL",category="hardware store")]).to_dict()
    assert out["Verification_Status"] == "VERIFIED_NOT_NAIL"


def test_single_tier_c_is_likely_only():
    assert resolve_consensus([sig("dir1.com","C","NAIL")]).to_dict()["Verification_Status"] == "LIKELY_NAIL"
    assert resolve_consensus([sig("dir1.com","C","NOT_NAIL")]).to_dict()["Verification_Status"] == "LIKELY_NOT_NAIL"


def test_two_independent_bc_sources_verify():
    assert resolve_consensus([sig("a.com","B","NAIL"),sig("b.com","C","NAIL")]).to_dict()["Verification_Status"] == "VERIFIED_NAIL"
    assert resolve_consensus([sig("a.com","B","NOT_NAIL"),sig("b.com","C","NOT_NAIL")]).to_dict()["Verification_Status"] == "VERIFIED_NOT_NAIL"


def test_duplicate_rows_same_provider_do_not_satisfy_two_source_gate():
    out = resolve_consensus([sig("same.com","B","NAIL"),sig("same.com","C","NAIL")]).to_dict()
    assert out["Evidence_Source_Count"] == 1
    assert out["Verification_Status"] == "LIKELY_NAIL"


def test_strong_conflict_forces_review_status():
    out = resolve_consensus([sig("nail.com","A","NAIL"),sig("hardware.com","A","NOT_NAIL")]).to_dict()
    assert out["Verification_Status"] == "CONFLICTING_EVIDENCE"
    assert out["Evidence_Conflicts"] >= 1


def test_same_provider_contradiction_counts_one_independent_source():
    out = resolve_consensus([
        sig("same.com", "A", "NAIL"),
        sig("same.com", "A", "NOT_NAIL"),
    ]).to_dict()
    assert out["Verification_Status"] == "CONFLICTING_EVIDENCE"
    assert out["Evidence_Source_Count"] == 1
    assert out["Strong_Evidence_Count"] == 1


def test_primary_source_prefers_newest_within_same_tier_and_direction():
    out = resolve_consensus([
        sig("old.com", "B", "NAIL", checked_at="2026-01-01"),
        sig("new.com", "B", "NAIL", checked_at="2026-09-28"),
    ]).to_dict()
    assert out["Verification_Status"] == "VERIFIED_NAIL"
    assert out["Primary_Source"] == "new.com"


def test_beauty_identity_without_nail_claim_is_unknown():
    out = resolve_consensus([sig("salon.com","A","AMBIGUOUS",category="hair salon")]).to_dict()
    assert out["Verification_Status"] == "UNKNOWN"


def test_tier_d_hint_never_verifies():
    out = resolve_consensus([sig("nailmap","D","NAIL")]).to_dict()
    assert out["Verification_Status"] == "LIKELY_NAIL"
    assert out["Strong_Evidence_Count"] == 0
