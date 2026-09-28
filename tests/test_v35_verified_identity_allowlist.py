from __future__ import annotations

from nailverifier_v3.engine import VerificationEngine
from nailverifier_v3.models import BusinessRecord


class NoOfficialMatch:
    def verify(self, record):
        return None


def make_engine(tmp_path):
    engine = VerificationEngine(cache_path=str(tmp_path / "cache.sqlite3"), use_osm=False)
    engine._adapters["SD"] = NoOfficialMatch()
    return engine


def test_single_secondary_old_allowlist_identity_is_now_likely_review(tmp_path):
    engine = make_engine(tmp_path)
    record = BusinessRecord(company="Anna's Nails", street="712 University Ave Ste A", city="Hot Springs", state="SD", zip_code="57747", reviews=11, rating=4.6, status="OPERATIONAL")
    result = engine.verify_record(record, force_refresh=True)
    assert result["Verification_Status"] == "LIKELY_NAIL"
    assert result["Auto_Action"] == "REVIEW"
    assert result["Policy_Status"] == "EVIDENCE_REVIEW"


def test_tier_a_address_strong_identity_can_verify_and_keep(tmp_path):
    engine = make_engine(tmp_path)
    record = BusinessRecord(company="The Nail Haus By Adamari", street="5201 S Solberg Ave suite 205", city="Sioux Falls", state="SD", zip_code="57108", reviews=14, rating=4.7, status="OPERATIONAL")
    result = engine.verify_record(record, force_refresh=True)
    assert result["Verification_Status"] == "VERIFIED_NAIL"
    assert result["Auto_Action"] == "KEEP"
    assert result["Policy_Status"] == "EVIDENCE_VERIFIED_NAIL"


def test_unknown_address_strong_business_stays_review(tmp_path):
    engine = make_engine(tmp_path)
    record = BusinessRecord(company="K & E Nail Studio LLC", street="522 7th St Suite 221", city="Rapid City", state="SD", zip_code="57701", reviews=6, rating=5.0, status="OPERATIONAL")
    result = engine.verify_record(record, force_refresh=True)
    assert result["Verification_Status"] == "LIKELY_NAIL"
    assert result["Auto_Action"] == "REVIEW"


def test_business_evidence_does_not_leak_across_state(tmp_path):
    engine = VerificationEngine(cache_path=str(tmp_path / "cache.sqlite3"), use_osm=False)
    record = BusinessRecord(company="The Nail Haus By Adamari", street="5201 S Solberg Ave suite 205", city="Sioux Falls", state="NE", zip_code="57108", reviews=14, rating=4.7, status="OPERATIONAL")
    result = engine.verify_record(record, force_refresh=True)
    assert result["Verification_Status"] != "VERIFIED_NAIL"
    assert result["Auto_Action"] == "REVIEW"
