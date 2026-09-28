from __future__ import annotations

import pandas as pd

from nailverifier_v3.engine import ENGINE_VERSION, VerificationEngine, verify_dataframe
from nailverifier_v3.models import BusinessRecord


class NoOfficialMatch:
    def verify(self, record):
        return None


def make_engine(tmp_path):
    engine = VerificationEngine(cache_path=str(tmp_path / "cache.sqlite3"), use_osm=False)
    engine._adapters["SD"] = NoOfficialMatch()
    return engine


def test_tier_a_verified_not_nail_identity_auto_removes(tmp_path):
    engine = make_engine(tmp_path)
    record = BusinessRecord(company="Buche Ace Hardware", street="301 US-18", city="Martin", state="SD", zip_code="57551", phone="6056856730", reviews=49, rating=4.5, status="OPERATIONAL")
    result = engine.verify_record(record, force_refresh=True)
    assert result["Verification_Status"] == "VERIFIED_NOT_NAIL"
    assert result["Auto_Action"] == "REMOVE"
    assert result["Policy_Status"] == "EVIDENCE_VERIFIED_NOT_NAIL"


def test_single_tier_b_old_remove_identity_is_now_likely_review(tmp_path):
    engine = make_engine(tmp_path)
    record = BusinessRecord(company="Bowdle Building & Hardware", street="32575 US-12", city="Bowdle", state="SD", zip_code="57428", phone="6052856303", reviews=8, rating=4.9, status="OPERATIONAL")
    result = engine.verify_record(record, force_refresh=True)
    assert result["Verification_Status"] == "LIKELY_NOT_NAIL"
    assert result["Auto_Action"] == "REVIEW"


def test_verified_not_nail_name_at_wrong_address_stays_review(tmp_path):
    engine = make_engine(tmp_path)
    record = BusinessRecord(company="Buche Ace Hardware", street="1 Wrong St", city="Martin", state="SD", zip_code="57551", phone="6056856730", reviews=49, rating=4.5, status="OPERATIONAL")
    result = engine.verify_record(record, force_refresh=True)
    assert result["Verification_Status"] == "LIKELY_NOT_NAIL"
    assert result["Auto_Action"] == "REVIEW"


def test_unseen_strong_non_nail_business_stays_review(tmp_path):
    engine = make_engine(tmp_path)
    record = BusinessRecord(company="Example Ace Hardware", street="1 Main St", city="Example", state="SD", zip_code="57000", phone="6055550100", reviews=20, rating=4.8, status="OPERATIONAL")
    result = engine.verify_record(record, force_refresh=True)
    assert result["Verification_Status"] == "LIKELY_NOT_NAIL"
    assert result["Auto_Action"] == "REVIEW"


def test_verified_not_nail_evidence_is_state_scoped(tmp_path):
    engine = VerificationEngine(cache_path=str(tmp_path / "cache.sqlite3"), use_osm=False)
    record = BusinessRecord(company="Buche Ace Hardware", street="301 US-18", city="Martin", state="NE", zip_code="57551", phone="6056856730", reviews=49, rating=4.5, status="OPERATIONAL")
    result = engine.verify_record(record, force_refresh=True)
    assert result["Verification_Status"] != "VERIFIED_NOT_NAIL"
    assert result["Auto_Action"] == "REVIEW"


def test_identity_collision_still_blocks_verified_remove(tmp_path):
    # Build a temporary registry containing the exact Hy-Vee identity so this
    # regression specifically proves collision override rather than registry data.
    registry = tmp_path / "registry.csv"
    registry.write_text(
        "State,Company,Street,City,ZIP,Phone,Source_Name,Source_Tier,Source_URL,Observed_Category,Nail_Service_Evidence,Business_Status_Evidence,Evidence_Direction,Evidence_Notes,Checked_At\n"
        "SD,Hy-Vee Grocery Store,201 E Willow St,Harrisburg,57032,6052132222,Hy-Vee,A,https://hyvee.example/store,Grocery Store,,ACTIVE,NOT_NAIL,official store,2026-09-28\n",
        encoding="utf-8",
    )
    engine = VerificationEngine(cache_path=str(tmp_path / "cache.sqlite3"), use_osm=False, registry_path=str(registry))
    engine._adapters["SD"] = NoOfficialMatch()
    df = pd.DataFrame([
        {"State":"SD","Company":"Hy-Vee Grocery Store","Street":"201 E Willow St","City":"Harrisburg","ZIP":"57032","Phone":"(605) 213-2222","Rating":"4.5","Reviews":"174","Status":"OPERATIONAL"},
        {"State":"SD","Company":"Hy-Vee Pickup","Street":"201 E Willow St","City":"Harrisburg","ZIP":"57032","Phone":"(605) 213-2222","Rating":"5.0","Reviews":"1","Status":"OPERATIONAL"},
    ])
    result = verify_dataframe(df, use_osm=False, force_refresh=True, engine=engine)
    grocery = result[result["Company"] == "Hy-Vee Grocery Store"].iloc[0]
    assert grocery["Verification_Status"] == "VERIFIED_NOT_NAIL"
    assert grocery["Identity_Collision"] == "YES"
    assert grocery["Auto_Action"] == "REVIEW"
    assert grocery["Policy_Status"] == "IDENTITY_COLLISION_REVIEW"


def test_v37_bumps_cache_version_and_policy_profile(tmp_path):
    assert ENGINE_VERSION == "3.7.0"
    engine = make_engine(tmp_path)
    record = BusinessRecord(company="Buche Ace Hardware", street="301 US-18", city="Martin", state="SD", zip_code="57551", phone="6056856730", reviews=49, rating=4.5, status="OPERATIONAL")
    result = engine.verify_record(record, force_refresh=True)
    assert result["Policy_Profile"] == "EVIDENCE_FIRST_V1_COLLISION_GUARD"
