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


def test_old_address_strong_allowlist_no_longer_auto_keeps(tmp_path):
    engine = make_engine(tmp_path)
    record = BusinessRecord(
        company="Anna's Nails",
        street="712 University Ave Ste A",
        city="Hot Springs",
        state="SD",
        zip_code="57747",
        reviews=11,
        rating=4.6,
        status="OPERATIONAL",
    )

    result = engine.verify_record(record, force_refresh=True)

    assert result["Rule_ID"] == "R_NAIL_EXPLICIT_ADDRESS_STRONG"
    assert result["Candidate_Action"] == "KEEP"
    assert result["Verification_Status"] == "LIKELY_NAIL"
    assert result["Auto_Action"] == "REVIEW"
    assert result["Policy_Status"] == "EVIDENCE_REVIEW"


def test_allowlisted_name_at_wrong_address_stays_review(tmp_path):
    engine = make_engine(tmp_path)
    record = BusinessRecord(
        company="Anna's Nails",
        street="999 Wrong Ave",
        city="Hot Springs",
        state="SD",
        zip_code="57747",
        reviews=11,
        rating=4.6,
        status="OPERATIONAL",
    )

    result = engine.verify_record(record, force_refresh=True)

    assert result["Verification_Status"] == "LIKELY_NAIL"
    assert result["Auto_Action"] == "REVIEW"
    assert result["Policy_Status"] == "EVIDENCE_REVIEW"


def test_unknown_address_strong_business_stays_review(tmp_path):
    engine = make_engine(tmp_path)
    record = BusinessRecord(
        company="K & E Nail Studio LLC",
        street="522 7th St Suite 221",
        city="Rapid City",
        state="SD",
        zip_code="57701",
        reviews=6,
        rating=5.0,
        status="OPERATIONAL",
    )

    result = engine.verify_record(record, force_refresh=True)

    assert result["Rule_ID"] == "R_NAIL_EXPLICIT_ADDRESS_STRONG"
    assert result["Verification_Status"] == "LIKELY_NAIL"
    assert result["Auto_Action"] == "REVIEW"
    assert result["Policy_Status"] == "EVIDENCE_REVIEW"


def test_legacy_exact_identity_path_does_not_leak_outside_sd(tmp_path):
    engine = VerificationEngine(cache_path=str(tmp_path / "cache.sqlite3"), use_osm=False)
    record = BusinessRecord(
        company="Anna's Nails",
        street="712 University Ave Ste A",
        city="Hot Springs",
        state="NE",
        zip_code="57747",
        reviews=11,
        rating=4.6,
        status="OPERATIONAL",
    )

    result = engine.verify_record(record, force_refresh=True)

    assert result["Auto_Action"] == "REVIEW"
    assert result["Policy_Status"] == "EVIDENCE_REVIEW"
    assert result["Verification_Status"] != "VERIFIED_NAIL"
