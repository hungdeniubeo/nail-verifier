from nailverifier_v3.evidence_classifier import classify_live_evidence, classify_registry_evidence, heuristic_signal
from nailverifier_v3.evidence_registry import RegistryEvidence
from nailverifier_v3.features import LocalAssessment
from nailverifier_v3.models import BusinessRecord, Evidence


def reg(tier="A", direction="NAIL"):
    return RegistryEvidence("SD","X","1 Main St","X","57000","","Source",tier,"https://example.com","Nail Salon","manicure","ACTIVE",direction,"note","2026-09-28","example.com")


def test_registry_direction_and_tier_are_preserved():
    signals = classify_registry_evidence([reg("A","NAIL"), reg("A","NOT_NAIL")])
    assert [(s.source_tier, s.direction) for s in signals] == [("A","NAIL"),("A","NOT_NAIL")]
    assert all(s.identity_verified for s in signals)


def test_nail_specific_official_license_is_tier_a_nail():
    ev = Evidence(source="SD_COSMETOLOGY", strength="STRONG_OFFICIAL", license_type="Nail Salon", source_url="https://apps.sd.gov/x")
    signal = classify_live_evidence([ev])[0]
    assert (signal.source_tier, signal.direction, signal.identity_verified) == ("A","NAIL",True)


def test_broad_official_beauty_license_is_ambiguous():
    ev = Evidence(source="SD_COSMETOLOGY", strength="STRONG_OFFICIAL", license_type="Apprentice Salon License", source_url="https://apps.sd.gov/x")
    signal = classify_live_evidence([ev])[0]
    assert signal.source_tier == "A"
    assert signal.direction == "AMBIGUOUS"


def test_osm_directional_evidence_is_tier_c():
    ev = Evidence(source="OPENSTREETMAP", strength="STRONG_INDEPENDENT_NOT_NAIL", category="hardware", source_url="https://openstreetmap.org/x")
    signal = classify_live_evidence([ev])[0]
    assert (signal.source_tier, signal.direction) == ("C","NOT_NAIL")


def test_local_rules_are_tier_d_hints_only():
    record = BusinessRecord(company="Example Nails", state="SD")
    nail = heuristic_signal(LocalAssessment("R_NAIL_EXPLICIT_STRONG","KEEP","x",90,[]), record)
    non = heuristic_signal(LocalAssessment("R_NON_NAIL_CATEGORY_STRONG","REMOVE","x",90,[]), record)
    assert (nail.source_tier, nail.direction, nail.identity_verified) == ("D","NAIL",False)
    assert (non.source_tier, non.direction, non.identity_verified) == ("D","NOT_NAIL",False)
