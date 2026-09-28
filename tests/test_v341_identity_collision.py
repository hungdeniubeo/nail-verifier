from __future__ import annotations

import pandas as pd

from nailverifier_v3.engine import verify_dataframe


class FakeEngine:
    def verify_record(self, record, force_refresh=False):
        return {
            "Decision": "LIKELY_NAIL",
            "Confidence": 95,
            "Candidate_Action": "KEEP",
            "Auto_Action": "KEEP",
            "Policy_Status": "BENCHMARK_VALIDATED_RULE",
            "Business_Exists": "LIKELY_EXISTS",
            "Nail_Service": "LIKELY_NAIL",
            "Rule_ID": "R_NAIL_EXPLICIT_STRONG",
            "Local_Candidate_Action": "KEEP",
            "Local_Signal": "EXPLICIT_NAIL_NAME_PLUS_STRUCTURED_LISTING",
            "Local_Score": 95,
            "Risk_Flags": "",
            "Policy_Profile": "SD_KEEP_V1",
            "State_Support": "OFFICIAL",
            "Checked_At": "2026-09-28T00:00:00+00:00",
            "Cache_Hit": "NO",
            "Source_Errors": "",
            "Official_Source": "",
            "Official_Matched_Name": "",
            "Official_Matched_Address": "",
            "Official_License": "",
            "Official_License_Type": "",
            "Official_Expires": "",
            "Official_URL": "",
            "Official_Name_Score": "",
            "Official_Address_Score": "",
            "OSM_Matched_Name": "",
            "OSM_Matched_Address": "",
            "OSM_Category": "",
            "OSM_URL": "",
            "OSM_Name_Score": "",
            "OSM_Address_Score": "",
            "Evidence_JSON": "[]",
            "Evidence_Tier": "NAILMAP_STRUCTURED",
            "Reason": "calibrated keep",
        }


def frame(rows):
    return pd.DataFrame(rows, columns=[
        "State", "Company", "Street", "City", "ZIP", "Phone",
        "Rating", "Reviews", "Status",
    ])


def test_same_phone_and_base_address_with_different_names_forces_review():
    df = frame([
        ["SD", "LOVELY NAILS", "951 Eglin St", "Rapid City", "57701", "(605) 791-1043", "4.3", "56", "OPERATIONAL"],
        ["SD", "My Lash Lounge & Nails", "951 Eglin St Ste 101", "Rapid City", "57701", "(605) 791-1043", "4.8", "90", "OPERATIONAL"],
    ])

    out = verify_dataframe(df, engine=FakeEngine(), use_osm=False)

    assert out["Identity_Collision"].tolist() == ["YES", "YES"]
    assert out["Collision_Group_Size"].tolist() == [2, 2]
    assert out["Auto_Action"].tolist() == ["REVIEW", "REVIEW"]
    assert out["Policy_Status"].tolist() == [
        "IDENTITY_COLLISION_REVIEW",
        "IDENTITY_COLLISION_REVIEW",
    ]
    assert all("LOVELY NAILS" in names and "My Lash Lounge & Nails" in names for names in out["Collision_Names"])


def test_same_phone_at_different_addresses_does_not_collide():
    df = frame([
        ["SD", "A Perfect 10 Nail & Beauty Bar / Omaha", "1109 W Omaha St B", "Rapid City", "57701", "(605) 791-2600", "4.3", "158", "OPERATIONAL"],
        ["SD", "A Perfect 10 Nail & Beauty Bar/ Rushmore Crossing", "1745 Eglin St #770", "Rapid City", "57701", "(605) 791-2600", "4.3", "124", "OPERATIONAL"],
    ])

    out = verify_dataframe(df, engine=FakeEngine(), use_osm=False)

    assert out["Identity_Collision"].tolist() == ["NO", "NO"]
    assert out["Auto_Action"].tolist() == ["KEEP", "KEEP"]


def test_exact_duplicate_name_is_not_identity_collision():
    df = frame([
        ["SD", "Cobe Nails", "3001 Broadway Ave", "Yankton", "57078", "(605) 665-0782", "3.0", "46", "OPERATIONAL"],
        ["SD", "Cobe Nails", "3001 Broadway Ave", "Yankton", "57078", "(605) 665-0782", "3.0", "46", "OPERATIONAL"],
    ])

    out = verify_dataframe(df, engine=FakeEngine(), use_osm=False)

    assert out["Identity_Collision"].tolist() == ["NO", "NO"]
    assert out["Exact_Record_Duplicate_Count"].tolist() == [2, 2]


def test_output_contains_normalized_identity_fields_and_shifted_address_recovery():
    df = frame([
        ["SD", "Hang Nails Salon", "—", "500 E Figzel Ct", "57064", "(605) 408-3617", "4.9", "64", "OPERATIONAL"],
    ])

    out = verify_dataframe(df, engine=FakeEngine(), use_osm=False)
    row = out.iloc[0]

    assert row["Normalized_Street"] == "500 e figzel ct"
    assert row["Normalized_City"] == ""
    assert row["Normalized_ZIP"] == "57064"
    assert row["Normalized_Phone"] == "6054083617"
