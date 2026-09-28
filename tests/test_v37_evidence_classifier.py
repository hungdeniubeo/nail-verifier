from __future__ import annotations

from nailverifier_v3.evidence_registry import RegistryEvidence
from nailverifier_v3.features import LocalAssessment
from nailverifier_v3.models import BusinessRecord, Evidence


def registry_row(direction: str, tier: str = "A") -> RegistryEvidence:
    return RegistryEvidence(
        state="SD",
        company="Example Nails",
        street="100 Main St",
        city="Sioux Falls",
        zip_code="57104",
        phone="6055550100",
        source_name="Example Source",
        source_tier=tier,
        source_url="https://example.com/location",
        observed_category="Nail Salon" if direction == "NAIL" else "Hardware Store",
        nail_service_evidence="Manicure" if direction == "NAIL" else "",
        business_status_evidence="Active",
        direction=direction,
        notes="exact identity",
        checked_at="2026-09-28",
        normalized_phone="6055550100",
        source_key="example.com",
    )


def test_registry_nail_and_not_nail_rows_become_directional_signals():
    from nailverifier_v3.evidence_classifier import classify_registry_evidence

    nail = classify_registry_evidence([registry_row("NAIL")])[0]
    not_nail = classify_registry_evidence([registry_row("NOT_NAIL")])[0]

    assert (nail.source_tier, nail.direction, nail.identity_verified) == ("A", "NAIL", True)
    assert (not_nail.source_tier, not_nail.direction, not_nail.identity_verified) == ("A", "NOT_NAIL", True)


def test_official_nail_specific_license_is_tier_a_nail():
    from nailverifier_v3.evidence_classifier import classify_live_evidence

    signal = classify_live_evidence([
        Evidence(
            source="SD_COSMETOLOGY",
            strength="STRONG_OFFICIAL",
            matched_name="Example Nails",
            matched_address="100 Main St, Sioux Falls, SD 57104",
            category="Nail Salon",
            license_type="Nail Salon",
            status="CURRENT",
            source_url="https://apps.sd.gov/license/1",
        )
    ])[0]

    assert signal.source_tier == "A"
    assert signal.direction == "NAIL"
    assert signal.identity_verified is True


def test_official_broad_beauty_license_is_ambiguous_not_nail():
    from nailverifier_v3.evidence_classifier import classify_live_evidence

    signal = classify_live_evidence([
        Evidence(
            source="SD_COSMETOLOGY",
            strength="STRONG_OFFICIAL",
            matched_name="Example Beauty",
            matched_address="100 Main St, Sioux Falls, SD 57104",
            category="Apprentice Salon License",
            license_type="Apprentice Salon License",
            status="CURRENT",
            source_url="https://apps.sd.gov/license/2",
        )
    ])[0]

    assert signal.source_tier == "A"
    assert signal.direction == "AMBIGUOUS"
    assert signal.identity_verified is True


def test_openstreetmap_directional_evidence_is_tier_c():
    from nailverifier_v3.evidence_classifier import classify_live_evidence

    nail, not_nail = classify_live_evidence([
        Evidence(source="OPENSTREETMAP", strength="STRONG_INDEPENDENT_NAIL", category="nail salon", source_url="https://openstreetmap.org/a"),
        Evidence(source="OPENSTREETMAP", strength="STRONG_INDEPENDENT_NOT_NAIL", category="hardware", source_url="https://openstreetmap.org/b"),
    ])

    assert (nail.source_tier, nail.direction) == ("C", "NAIL")
    assert (not_nail.source_tier, not_nail.direction) == ("C", "NOT_NAIL")


def test_local_rules_only_create_tier_d_hints():
    from nailverifier_v3.evidence_classifier import heuristic_signal

    record = BusinessRecord(company="Example Nails", state="SD")
    nail = heuristic_signal(LocalAssessment("R_NAIL_EXPLICIT_STRONG", "KEEP", "NAIL", 94, []), record)
    not_nail = heuristic_signal(LocalAssessment("R_NON_NAIL_CATEGORY_STRONG", "REMOVE", "NOT_NAIL", 94, []), record)

    assert nail is not None and (nail.source_tier, nail.direction, nail.identity_verified) == ("D", "NAIL", False)
    assert not_nail is not None and (not_nail.source_tier, not_nail.direction, not_nail.identity_verified) == ("D", "NOT_NAIL", False)
