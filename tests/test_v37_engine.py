from __future__ import annotations

from pathlib import Path

import pandas as pd

from nailverifier_v3.engine import ENGINE_VERSION, VerificationEngine, verify_dataframe
from nailverifier_v3.models import BusinessRecord


HEADER = (
    "State,Company,Street,City,ZIP,Phone,Source_Name,Source_Tier,Source_URL,Observed_Category,"
    "Nail_Service_Evidence,Business_Status_Evidence,Evidence_Direction,Evidence_Notes,Checked_At\n"
)


class NoOfficialMatch:
    def verify(self, record):
        return None


def make_registry(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / "registry.csv"
    path.write_text(HEADER + rows, encoding="utf-8")
    return path


def make_engine(tmp_path: Path, rows: str = "") -> VerificationEngine:
    registry = make_registry(tmp_path, rows)
    engine = VerificationEngine(cache_path=str(tmp_path / "cache.sqlite3"), use_osm=False, registry_path=str(registry))
    engine._adapters["SD"] = NoOfficialMatch()
    return engine


def record(company="Example Nails", street="1 Main St", city="Sioux Falls", zip_code="57104", phone="6055550100"):
    return BusinessRecord(company=company, street=street, city=city, state="SD", zip_code=zip_code, phone=phone, reviews=20, rating=4.8, status="OPERATIONAL")


def test_tier_a_nail_registry_evidence_auto_keeps(tmp_path):
    engine = make_engine(tmp_path, "SD,Example Nails,1 Main St,Sioux Falls,57104,6055550100,Official,A,https://official.example/nails,Nail Salon,manicure,ACTIVE,NAIL,note,2026-09-28\n")
    result = engine.verify_record(record(), force_refresh=True)
    assert result["Verification_Status"] == "VERIFIED_NAIL"
    assert result["Auto_Action"] == "KEEP"
    assert result["Policy_Status"] == "EVIDENCE_VERIFIED_NAIL"


def test_tier_a_non_nail_registry_evidence_auto_removes(tmp_path):
    engine = make_engine(tmp_path, "SD,Example Ace Hardware,1 Main St,Sioux Falls,57104,6055550100,Ace Hardware,A,https://ace.example/store,Hardware Store,,ACTIVE,NOT_NAIL,note,2026-09-28\n")
    result = engine.verify_record(record(company="Example Ace Hardware"), force_refresh=True)
    assert result["Verification_Status"] == "VERIFIED_NOT_NAIL"
    assert result["Auto_Action"] == "REMOVE"


def test_single_tier_c_old_allowlist_style_source_is_likely_review(tmp_path):
    engine = make_engine(tmp_path, "SD,Example Nails,1 Main St,Sioux Falls,57104,6055550100,Directory,C,https://directory.example/nails,Nail Salon,nail salon,ACTIVE,NAIL,note,2026-09-28\n")
    result = engine.verify_record(record(), force_refresh=True)
    assert result["Verification_Status"] == "LIKELY_NAIL"
    assert result["Auto_Action"] == "REVIEW"


def test_rule_only_strong_nail_and_non_nail_stay_review(tmp_path):
    engine = make_engine(tmp_path)
    nail = engine.verify_record(record(company="Example Nails"), force_refresh=True)
    hardware = engine.verify_record(record(company="Example Ace Hardware"), force_refresh=True)
    assert nail["Verification_Status"] == "LIKELY_NAIL"
    assert nail["Auto_Action"] == "REVIEW"
    assert hardware["Verification_Status"] == "LIKELY_NOT_NAIL"
    assert hardware["Auto_Action"] == "REVIEW"


def test_conflicting_strong_evidence_forces_review(tmp_path):
    rows = (
        "SD,Example Nails,1 Main St,Sioux Falls,57104,6055550100,Official Nail,A,https://nail.example/x,Nail Salon,manicure,ACTIVE,NAIL,note,2026-09-28\n"
        "SD,Example Nails,1 Main St,Sioux Falls,57104,6055550100,Official Other,A,https://other.example/x,Hardware Store,,ACTIVE,NOT_NAIL,note,2026-09-28\n"
    )
    result = make_engine(tmp_path, rows).verify_record(record(), force_refresh=True)
    assert result["Verification_Status"] == "CONFLICTING_EVIDENCE"
    assert result["Auto_Action"] == "REVIEW"


def test_collision_blocks_verified_remove(tmp_path):
    rows = "SD,Hy-Vee Grocery Store,201 E Willow St,Harrisburg,57032,6052132222,Official,A,https://hyvee.example/x,Grocery Store,,ACTIVE,NOT_NAIL,note,2026-09-28\n"
    engine = make_engine(tmp_path, rows)
    df = pd.DataFrame([
        {"State":"SD","Company":"Hy-Vee Grocery Store","Street":"201 E Willow St","City":"Harrisburg","ZIP":"57032","Phone":"6052132222","Rating":"4.5","Reviews":"174","Status":"OPERATIONAL"},
        {"State":"SD","Company":"Hy-Vee Pickup","Street":"201 E Willow St","City":"Harrisburg","ZIP":"57032","Phone":"6052132222","Rating":"5","Reviews":"1","Status":"OPERATIONAL"},
    ])
    out = verify_dataframe(df, engine=engine, use_osm=False, force_refresh=True)
    row = out.iloc[0]
    assert row["Verification_Status"] == "VERIFIED_NOT_NAIL"
    assert row["Identity_Collision"] == "YES"
    assert row["Auto_Action"] == "REVIEW"
    assert row["Policy_Status"] == "IDENTITY_COLLISION_REVIEW"


def test_shifted_address_recovery_survives_v37(tmp_path):
    engine = make_engine(tmp_path)
    df = pd.DataFrame([{"State":"SD","Company":"Hang Nails Salon","Street":"—","City":"500 E Figzel Ct","ZIP":"57064","Phone":"6054083617","Rating":"4.9","Reviews":"64","Status":"OPERATIONAL"}])
    out = verify_dataframe(df, engine=engine, use_osm=False, force_refresh=True)
    assert out.iloc[0]["Normalized_Street"] == "500 e figzel ct"


def test_registry_digest_is_part_of_cache_version(tmp_path):
    path = make_registry(tmp_path, "SD,Example Nails,1 Main St,Sioux Falls,57104,6055550100,Dir,C,https://dir.example/x,Nail Salon,nail,ACTIVE,NAIL,note,2026-09-28\n")
    first = VerificationEngine(cache_path=str(tmp_path / "cache.sqlite3"), use_osm=False, registry_path=str(path))
    first._adapters["SD"] = NoOfficialMatch()
    r1 = first.verify_record(record(), force_refresh=False)
    path.write_text(HEADER + "SD,Example Nails,1 Main St,Sioux Falls,57104,6055550100,Official,A,https://official.example/x,Nail Salon,manicure,ACTIVE,NAIL,note,2026-09-28\n", encoding="utf-8")
    second = VerificationEngine(cache_path=str(tmp_path / "cache.sqlite3"), use_osm=False, registry_path=str(path))
    second._adapters["SD"] = NoOfficialMatch()
    r2 = second.verify_record(record(), force_refresh=False)
    assert r1["Verification_Status"] == "LIKELY_NAIL"
    assert r2["Verification_Status"] == "VERIFIED_NAIL"
    assert r2["Cache_Hit"] == "NO"
    assert ENGINE_VERSION == "3.7.0"
