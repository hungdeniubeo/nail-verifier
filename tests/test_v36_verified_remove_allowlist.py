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


def test_old_verified_not_nail_allowlist_no_longer_auto_removes(tmp_path):
    engine = make_engine(tmp_path)
    record = BusinessRecord(
        company="Bowdle Building & Hardware",
        street="32575 US-12",
        city="Bowdle",
        state="SD",
        zip_code="57428",
        phone="6052856303",
        reviews=8,
        rating=4.9,
        status="OPERATIONAL",
    )

    result = engine.verify_record(record, force_refresh=True)

    assert result["Rule_ID"] == "R_NON_NAIL_CATEGORY_STRONG"
    assert result["Candidate_Action"] == "REMOVE"
    assert result["Auto_Action"] == "REVIEW"
    assert result["Policy_Status"] == "CANDIDATE_NEEDS_BENCHMARK"


def test_verified_not_nail_name_at_wrong_address_stays_review(tmp_path):
    engine = make_engine(tmp_path)
    record = BusinessRecord(
        company="Bowdle Building & Hardware",
        street="1 Wrong St",
        city="Bowdle",
        state="SD",
        zip_code="57428",
        phone="6052856303",
        reviews=8,
        rating=4.9,
        status="OPERATIONAL",
    )

    result = engine.verify_record(record, force_refresh=True)

    assert result["Candidate_Action"] == "REMOVE"
    assert result["Auto_Action"] == "REVIEW"
    assert result["Policy_Status"] == "CANDIDATE_NEEDS_BENCHMARK"


def test_unseen_strong_non_nail_business_stays_review(tmp_path):
    engine = make_engine(tmp_path)
    record = BusinessRecord(
        company="Example Ace Hardware",
        street="1 Main St",
        city="Example",
        state="SD",
        zip_code="57000",
        phone="6055550100",
        reviews=20,
        rating=4.8,
        status="OPERATIONAL",
    )

    result = engine.verify_record(record, force_refresh=True)

    assert result["Rule_ID"] == "R_NON_NAIL_CATEGORY_STRONG"
    assert result["Candidate_Action"] == "REMOVE"
    assert result["Auto_Action"] == "REVIEW"
    assert result["Policy_Status"] == "CANDIDATE_NEEDS_BENCHMARK"


def test_legacy_not_nail_allowlist_path_is_state_scoped(tmp_path):
    engine = VerificationEngine(cache_path=str(tmp_path / "cache.sqlite3"), use_osm=False)
    record = BusinessRecord(
        company="Bowdle Building & Hardware",
        street="32575 US-12",
        city="Bowdle",
        state="NE",
        zip_code="57428",
        phone="6052856303",
        reviews=8,
        rating=4.9,
        status="OPERATIONAL",
    )

    result = engine.verify_record(record, force_refresh=True)

    assert result["Auto_Action"] == "REVIEW"
    assert result["Policy_Status"] != "VERIFIED_IDENTITY_ALLOWLIST"


def test_identity_collision_still_blocks_candidate_remove(tmp_path):
    engine = make_engine(tmp_path)
    df = pd.DataFrame(
        [
            {
                "State": "SD",
                "Company": "Hy-Vee Grocery Store",
                "Street": "201 E Willow St",
                "City": "Harrisburg",
                "ZIP": "57032",
                "Phone": "(605) 213-2222",
                "Rating": "4.5",
                "Reviews": "174",
                "Status": "OPERATIONAL",
            },
            {
                "State": "SD",
                "Company": "Hy-Vee Pickup",
                "Street": "201 E Willow St",
                "City": "Harrisburg",
                "ZIP": "57032",
                "Phone": "(605) 213-2222",
                "Rating": "4.5",
                "Reviews": "10",
                "Status": "OPERATIONAL",
            },
        ]
    )

    result = verify_dataframe(df, use_osm=False, force_refresh=True, engine=engine)
    grocery = result[result["Company"] == "Hy-Vee Grocery Store"].iloc[0]

    assert grocery["Candidate_Action"] == "REMOVE"
    assert grocery["Identity_Collision"] == "YES"
    assert grocery["Auto_Action"] == "REVIEW"


def test_v36_engine_version_remains_until_engine_migration(tmp_path):
    assert ENGINE_VERSION == "3.6.0"

    engine = make_engine(tmp_path)
    record = BusinessRecord(
        company="Bowdle Building & Hardware",
        street="32575 US-12",
        city="Bowdle",
        state="SD",
        zip_code="57428",
        phone="6052856303",
        reviews=8,
        rating=4.9,
        status="OPERATIONAL",
    )

    result = engine.verify_record(record, force_refresh=True)
    assert result["Policy_Profile"] == "SD_EXACT_KEEP_REMOVE_V1_COLLISION_GUARD"
