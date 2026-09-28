from __future__ import annotations

from pathlib import Path

import pandas as pd

from nailverifier_v3.models import BusinessRecord


COLUMNS = [
    "State", "Company", "Street", "City", "ZIP", "Phone",
    "Source_Name", "Source_Tier", "Source_URL", "Observed_Category",
    "Nail_Service_Evidence", "Business_Status_Evidence",
    "Evidence_Direction", "Evidence_Notes", "Checked_At",
]


class NoOfficialMatch:
    def verify(self, record):
        return None


def write_registry(path: Path, rows: list[dict[str, str]]) -> str:
    pd.DataFrame(rows, columns=COLUMNS).to_csv(path, index=False)
    return str(path)


def evidence_row(
    company: str,
    street: str,
    city: str,
    zip_code: str,
    phone: str,
    direction: str,
    tier: str,
    source: str,
    *,
    category: str = "",
    service: str = "",
) -> dict[str, str]:
    return {
        "State": "SD",
        "Company": company,
        "Street": street,
        "City": city,
        "ZIP": zip_code,
        "Phone": phone,
        "Source_Name": source,
        "Source_Tier": tier,
        "Source_URL": f"https://{source}/business",
        "Observed_Category": category,
        "Nail_Service_Evidence": service,
        "Business_Status_Evidence": "Active",
        "Evidence_Direction": direction,
        "Evidence_Notes": "exact identity evidence",
        "Checked_At": "2026-09-28",
    }


def make_engine(tmp_path: Path, rows: list[dict[str, str]]):
    from nailverifier_v3.engine import VerificationEngine

    registry_path = write_registry(tmp_path / "evidence.csv", rows)
    engine = VerificationEngine(
        cache_path=str(tmp_path / "cache.sqlite3"),
        use_osm=False,
        registry_path=registry_path,
    )
    engine._adapters["SD"] = NoOfficialMatch()
    return engine


def record(company="Example Nails", street="100 Main St", city="Sioux Falls", zip_code="57104", phone="6055550100"):
    return BusinessRecord(
        company=company,
        street=street,
        city=city,
        state="SD",
        zip_code=zip_code,
        phone=phone,
        rating=4.8,
        reviews=20,
        status="OPERATIONAL",
    )


def test_tier_a_nail_registry_evidence_auto_keeps(tmp_path: Path):
    engine = make_engine(tmp_path, [
        evidence_row("Example Nails", "100 Main St", "Sioux Falls", "57104", "6055550100", "NAIL", "A", "official-nails.example", category="Nail Salon", service="Manicure")
    ])
    out = engine.verify_record(record(), force_refresh=True)
    assert out["Verification_Status"] == "VERIFIED_NAIL"
    assert out["Auto_Action"] == "KEEP"
    assert out["Policy_Status"] == "EVIDENCE_VERIFIED_NAIL"
    assert out["Primary_Source_URL"] == "https://official-nails.example/business"


def test_tier_a_not_nail_registry_evidence_auto_removes(tmp_path: Path):
    engine = make_engine(tmp_path, [
        evidence_row("Example Ace Hardware", "100 Main St", "Sioux Falls", "57104", "6055550100", "NOT_NAIL", "A", "ace.example", category="Hardware Store")
    ])
    out = engine.verify_record(record(company="Example Ace Hardware"), force_refresh=True)
    assert out["Verification_Status"] == "VERIFIED_NOT_NAIL"
    assert out["Auto_Action"] == "REMOVE"
    assert out["Policy_Status"] == "EVIDENCE_VERIFIED_NOT_NAIL"


def test_single_tier_c_old_evidence_is_likely_and_review(tmp_path: Path):
    engine = make_engine(tmp_path, [
        evidence_row("Example Nails", "100 Main St", "Sioux Falls", "57104", "6055550100", "NAIL", "C", "directory.example", category="Nail Salon")
    ])
    out = engine.verify_record(record(), force_refresh=True)
    assert out["Verification_Status"] == "LIKELY_NAIL"
    assert out["Auto_Action"] == "REVIEW"


def test_rule_only_strong_nail_and_non_nail_rows_remain_review(tmp_path: Path):
    engine = make_engine(tmp_path, [])
    nail = engine.verify_record(record(), force_refresh=True)
    non_nail = engine.verify_record(record(company="Example Ace Hardware"), force_refresh=True)
    assert nail["Verification_Status"] == "LIKELY_NAIL"
    assert nail["Auto_Action"] == "REVIEW"
    assert non_nail["Verification_Status"] == "LIKELY_NOT_NAIL"
    assert non_nail["Auto_Action"] == "REVIEW"


def test_strong_conflicting_sources_force_review(tmp_path: Path):
    rows = [
        evidence_row("Example Nails", "100 Main St", "Sioux Falls", "57104", "6055550100", "NAIL", "A", "nail.example", service="Manicure"),
        evidence_row("Example Nails", "100 Main St", "Sioux Falls", "57104", "6055550100", "NOT_NAIL", "A", "other.example", category="Hardware Store"),
    ]
    out = make_engine(tmp_path, rows).verify_record(record(), force_refresh=True)
    assert out["Verification_Status"] == "CONFLICTING_EVIDENCE"
    assert out["Auto_Action"] == "REVIEW"


def test_collision_overrides_verified_not_nail_remove(tmp_path: Path):
    from nailverifier_v3.engine import verify_dataframe

    rows = [evidence_row("Hy-Vee Grocery Store", "201 E Willow St", "Harrisburg", "57032", "6052132222", "NOT_NAIL", "A", "hyvee.example", category="Grocery Store")]
    engine = make_engine(tmp_path, rows)
    df = pd.DataFrame([
        {"State":"SD","Company":"Hy-Vee Grocery Store","Street":"201 E Willow St","City":"Harrisburg","ZIP":"57032","Phone":"6052132222","Rating":"4.5","Reviews":"174","Status":"OPERATIONAL"},
        {"State":"SD","Company":"Hy-Vee Pickup","Street":"201 E Willow St","City":"Harrisburg","ZIP":"57032","Phone":"6052132222","Rating":"5.0","Reviews":"1","Status":"OPERATIONAL"},
    ])
    out = verify_dataframe(df, engine=engine, use_osm=False, force_refresh=True)
    grocery = out[out["Company"] == "Hy-Vee Grocery Store"].iloc[0]
    assert grocery["Verification_Status"] == "VERIFIED_NOT_NAIL"
    assert grocery["Identity_Collision"] == "YES"
    assert grocery["Auto_Action"] == "REVIEW"
    assert grocery["Policy_Status"] == "IDENTITY_COLLISION_REVIEW"


def test_collision_overrides_verified_nail_keep(tmp_path: Path):
    from nailverifier_v3.engine import verify_dataframe

    rows = [
        evidence_row("Cobe Nails", "3001 Broadway Ave", "Yankton", "57078", "6056650782", "NAIL", "A", "cobe.example", service="Manicure"),
        evidence_row("Rose Nails", "3001 Broadway Ave", "Yankton", "57078", "6056650782", "NAIL", "A", "rose.example", service="Manicure"),
    ]
    engine = make_engine(tmp_path, rows)
    df = pd.DataFrame([
        {"State":"SD","Company":"Cobe Nails","Street":"3001 Broadway Ave","City":"Yankton","ZIP":"57078","Phone":"6056650782","Rating":"3.0","Reviews":"46","Status":"OPERATIONAL"},
        {"State":"SD","Company":"Rose Nails","Street":"3001 Broadway Ave","City":"Yankton","ZIP":"57078","Phone":"6056650782","Rating":"4.0","Reviews":"50","Status":"OPERATIONAL"},
    ])
    out = verify_dataframe(df, engine=engine, use_osm=False, force_refresh=True)
    assert out["Verification_Status"].tolist() == ["VERIFIED_NAIL", "VERIFIED_NAIL"]
    assert out["Auto_Action"].tolist() == ["REVIEW", "REVIEW"]


def test_shifted_address_recovery_still_exports_normalized_identity(tmp_path: Path):
    from nailverifier_v3.engine import verify_dataframe

    engine = make_engine(tmp_path, [])
    df = pd.DataFrame([{
        "State":"SD","Company":"Hang Nails Salon","Street":"—","City":"500 E Figzel Ct","ZIP":"57064","Phone":"(605) 408-3617","Rating":"4.9","Reviews":"64","Status":"OPERATIONAL"
    }])
    out = verify_dataframe(df, engine=engine, use_osm=False, force_refresh=True)
    assert out.iloc[0]["Normalized_Street"] == "500 e figzel ct"


def test_registry_digest_invalidates_verification_cache(tmp_path: Path):
    from nailverifier_v3.engine import VerificationEngine

    registry = tmp_path / "evidence.csv"
    cache = tmp_path / "cache.sqlite3"
    write_registry(registry, [evidence_row("Example Nails", "100 Main St", "Sioux Falls", "57104", "6055550100", "NAIL", "C", "directory.example", category="Nail Salon")])
    first = VerificationEngine(cache_path=str(cache), use_osm=False, registry_path=str(registry))
    first._adapters["SD"] = NoOfficialMatch()
    before = first.verify_record(record(), force_refresh=False)
    assert before["Auto_Action"] == "REVIEW"

    write_registry(registry, [evidence_row("Example Nails", "100 Main St", "Sioux Falls", "57104", "6055550100", "NAIL", "A", "official.example", category="Nail Salon", service="Manicure")])
    second = VerificationEngine(cache_path=str(cache), use_osm=False, registry_path=str(registry))
    second._adapters["SD"] = NoOfficialMatch()
    after = second.verify_record(record(), force_refresh=False)
    assert after["Auto_Action"] == "KEEP"
    assert after["Cache_Hit"] == "NO"
