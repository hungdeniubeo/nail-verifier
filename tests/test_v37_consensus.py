from __future__ import annotations

from nailverifier_v3.evidence_classifier import EvidenceSignal


def sig(
    direction: str,
    tier: str,
    key: str,
    *,
    category: str = "",
    service: str = "",
    identity: bool = True,
    checked_at: str = "2026-09-28",
) -> EvidenceSignal:
    return EvidenceSignal(
        source_name=key,
        source_key=key,
        source_tier=tier,
        source_url=f"https://{key}/business",
        direction=direction,
        identity_verified=identity,
        category=category,
        service_evidence=service,
        existence_status="VERIFIED_ACTIVE" if identity else "LIKELY_ACTIVE",
        checked_at=checked_at,
        notes="evidence",
    )


def resolve(*signals: EvidenceSignal):
    from nailverifier_v3.consensus import resolve_consensus

    return resolve_consensus(list(signals)).to_dict()


def test_one_tier_a_explicit_nail_is_verified_nail():
    out = resolve(sig("NAIL", "A", "official.example", category="Nail Salon", service="Manicure"))
    assert out["Verification_Status"] == "VERIFIED_NAIL"
    assert out["Identity_Status"] == "VERIFIED"
    assert out["Nail_Service_Status"] == "VERIFIED_NAIL"
    assert out["Strong_Evidence_Count"] == 1


def test_one_tier_a_affirmative_nonbeauty_is_verified_not_nail():
    out = resolve(sig("NOT_NAIL", "A", "hardware.example", category="Hardware Store"))
    assert out["Verification_Status"] == "VERIFIED_NOT_NAIL"
    assert out["Nail_Service_Status"] == "VERIFIED_NOT_NAIL"


def test_single_tier_c_direction_is_likely_only():
    nail = resolve(sig("NAIL", "C", "directory-a.example", category="Nail Salon"))
    not_nail = resolve(sig("NOT_NAIL", "C", "directory-b.example", category="Hardware Store"))
    assert nail["Verification_Status"] == "LIKELY_NAIL"
    assert not_nail["Verification_Status"] == "LIKELY_NOT_NAIL"


def test_two_independent_b_c_sources_can_verify_each_direction():
    nail = resolve(
        sig("NAIL", "B", "source-a.example", category="Nail Salon"),
        sig("NAIL", "C", "source-b.example", service="Pedicure"),
    )
    not_nail = resolve(
        sig("NOT_NAIL", "B", "source-c.example", category="Hardware Store"),
        sig("NOT_NAIL", "C", "source-d.example", category="Hardware Store"),
    )
    assert nail["Verification_Status"] == "VERIFIED_NAIL"
    assert not_nail["Verification_Status"] == "VERIFIED_NOT_NAIL"


def test_duplicate_rows_from_same_provider_count_as_one_source():
    out = resolve(
        sig("NAIL", "B", "same.example", category="Nail Salon"),
        sig("NAIL", "C", "same.example", service="Manicure"),
    )
    assert out["Evidence_Source_Count"] == 1
    assert out["Strong_Evidence_Count"] == 1
    assert out["Verification_Status"] == "LIKELY_NAIL"


def test_strong_nail_and_not_nail_sources_conflict_and_review():
    out = resolve(
        sig("NAIL", "A", "nail.example", service="Manicure"),
        sig("NOT_NAIL", "A", "hardware.example", category="Hardware Store"),
    )
    assert out["Verification_Status"] == "CONFLICTING_EVIDENCE"
    assert out["Evidence_Agrees"] == "NO"
    assert out["Evidence_Conflicts"] >= 1


def test_beauty_identity_without_nail_claim_is_unknown_not_not_nail():
    out = resolve(sig("AMBIGUOUS", "A", "salon.example", category="Hair Salon"))
    assert out["Verification_Status"] == "UNKNOWN"
    assert out["Identity_Status"] == "VERIFIED"


def test_tier_d_heuristic_never_verifies():
    nail = resolve(sig("NAIL", "D", "nailmap", identity=False))
    not_nail = resolve(sig("NOT_NAIL", "D", "nailmap", identity=False))
    assert nail["Verification_Status"] == "LIKELY_NAIL"
    assert not_nail["Verification_Status"] == "LIKELY_NOT_NAIL"


def test_primary_source_prefers_tier_a_and_newest_within_tier():
    out = resolve(
        sig("NAIL", "C", "c.example", checked_at="2026-09-28"),
        sig("NAIL", "A", "old-a.example", checked_at="2026-09-20"),
        sig("NAIL", "A", "new-a.example", checked_at="2026-09-27"),
    )
    assert out["Primary_Source"] == "new-a.example"
    assert out["Primary_Source_Tier"] == "A"
    assert out["Primary_Source_URL"] == "https://new-a.example/business"
