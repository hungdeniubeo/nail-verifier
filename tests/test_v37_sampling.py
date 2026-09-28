import pandas as pd

from nailverifier_v3.sampling import make_validation_sample


def test_sampling_prefers_unresolved_and_keeps_conflicts():
    rows = [
        {"Company":"Verified Nail","Rule_ID":"R_NAIL_EXPLICIT_STRONG","Verification_Status":"VERIFIED_NAIL","Candidate_Action":"KEEP"},
        {"Company":"Verified Other","Rule_ID":"R_NON_NAIL_CATEGORY_STRONG","Verification_Status":"VERIFIED_NOT_NAIL","Candidate_Action":"REMOVE"},
        {"Company":"Beauty Unknown","Rule_ID":"R_BEAUTY_AMBIGUOUS","Verification_Status":"UNKNOWN","Candidate_Action":"REVIEW"},
        {"Company":"Conflicting","Rule_ID":"R_UNKNOWN","Verification_Status":"CONFLICTING_EVIDENCE","Candidate_Action":"REVIEW"},
    ]
    out = make_validation_sample(pd.DataFrame(rows), targets={"R_BEAUTY_AMBIGUOUS": 20, "R_UNKNOWN": 20})
    assert set(out["Company"]) == {"Beauty Unknown", "Conflicting"}
    assert "Research_Source_URL" in out.columns
    assert "Research_Notes" in out.columns
    assert "Verification_Status" in out.columns


def test_sampling_falls_back_to_existing_rows_when_no_verification_status():
    df = pd.DataFrame([
        {"Company":"A","Rule_ID":"R_UNKNOWN","Candidate_Action":"REVIEW"},
        {"Company":"B","Rule_ID":"R_UNKNOWN","Candidate_Action":"REVIEW"},
    ])
    out = make_validation_sample(df, targets={"R_UNKNOWN": 1}, seed=1)
    assert len(out) == 1
