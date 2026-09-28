import pandas as pd

from nailverifier_v3.audit import audit_verification_output


def row(**overrides):
    base = {
        "Company":"X",
        "Verification_Status":"VERIFIED_NAIL",
        "Auto_Action":"KEEP",
        "Identity_Collision":"NO",
        "Evidence_Source_Count":1,
        "Primary_Source_URL":"https://example.com",
    }
    base.update(overrides)
    return base


def test_clean_verified_rows_have_no_audit_errors():
    df = pd.DataFrame([
        row(),
        row(Company="Y", Verification_Status="VERIFIED_NOT_NAIL", Auto_Action="REMOVE"),
        row(Company="Z", Verification_Status="UNKNOWN", Auto_Action="REVIEW", Evidence_Source_Count=0, Primary_Source_URL=""),
    ])
    assert audit_verification_output(df) == []


def test_remove_requires_verified_not_nail():
    errors = audit_verification_output(pd.DataFrame([row(Verification_Status="LIKELY_NOT_NAIL", Auto_Action="REMOVE")]))
    assert any("Auto REMOVE" in e for e in errors)


def test_keep_requires_verified_nail():
    errors = audit_verification_output(pd.DataFrame([row(Verification_Status="LIKELY_NAIL", Auto_Action="KEEP")]))
    assert any("Auto KEEP" in e for e in errors)


def test_collision_cannot_auto_act():
    errors = audit_verification_output(pd.DataFrame([row(Identity_Collision="YES")]))
    assert any("collision" in e.lower() for e in errors)


def test_verified_row_requires_evidence_and_source_url():
    errors = audit_verification_output(pd.DataFrame([row(Evidence_Source_Count=0, Primary_Source_URL="")]))
    assert any("zero evidence" in e.lower() for e in errors)
    assert any("source url" in e.lower() for e in errors)
