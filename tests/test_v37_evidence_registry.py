from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from nailverifier_v3.models import BusinessRecord


def _write_registry(path: Path, **overrides: str) -> Path:
    row = {
        "State": "SD",
        "Company": "Example Nails",
        "Street": "100 Main St Ste 2",
        "City": "Sioux Falls",
        "ZIP": "57104",
        "Phone": "(605) 555-0100",
        "Source_Name": "Example Official",
        "Source_Tier": "A",
        "Source_URL": "https://example.com/location",
        "Observed_Category": "Nail Salon",
        "Nail_Service_Evidence": "Manicure and pedicure services",
        "Business_Status_Evidence": "Active",
        "Evidence_Direction": "NAIL",
        "Evidence_Notes": "Exact business identity",
        "Checked_At": "2026-09-28",
    }
    row.update(overrides)
    pd.DataFrame([row]).to_csv(path, index=False)
    return path


def _record(**overrides: str) -> BusinessRecord:
    values = {
        "company": "Example Nails",
        "street": "100 Main St Ste 2",
        "city": "Sioux Falls",
        "state": "SD",
        "zip_code": "57104",
        "phone": "6055550100",
    }
    values.update(overrides)
    return BusinessRecord(**values)


def test_exact_identity_loads_business_specific_evidence(tmp_path: Path):
    from nailverifier_v3.evidence_registry import EvidenceRegistry

    path = _write_registry(tmp_path / "evidence.csv")
    registry = EvidenceRegistry(str(path))

    matches = registry.match(_record())

    assert len(matches) == 1
    assert matches[0].source_url == "https://example.com/location"
    assert matches[0].source_tier == "A"
    assert matches[0].direction == "NAIL"
    assert len(registry.version) == 64


def test_same_name_wrong_address_does_not_match(tmp_path: Path):
    from nailverifier_v3.evidence_registry import EvidenceRegistry

    registry = EvidenceRegistry(str(_write_registry(tmp_path / "evidence.csv")))
    assert registry.match(_record(street="999 Wrong Ave")) == []


def test_same_identity_wrong_state_does_not_match(tmp_path: Path):
    from nailverifier_v3.evidence_registry import EvidenceRegistry

    registry = EvidenceRegistry(str(_write_registry(tmp_path / "evidence.csv")))
    assert registry.match(_record(state="NE")) == []


def test_two_nonempty_conflicting_phones_reject_match(tmp_path: Path):
    from nailverifier_v3.evidence_registry import EvidenceRegistry

    registry = EvidenceRegistry(str(_write_registry(tmp_path / "evidence.csv")))
    assert registry.match(_record(phone="6055559999")) == []


def test_missing_phone_can_match_exact_name_and_full_location(tmp_path: Path):
    from nailverifier_v3.evidence_registry import EvidenceRegistry

    registry = EvidenceRegistry(
        str(_write_registry(tmp_path / "evidence.csv", Phone=""))
    )
    assert len(registry.match(_record(phone=""))) == 1


def test_missing_required_columns_raise_value_error(tmp_path: Path):
    from nailverifier_v3.evidence_registry import EvidenceRegistry

    path = tmp_path / "bad.csv"
    pd.DataFrame([{"State": "SD", "Company": "Example Nails"}]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="Missing required evidence columns"):
        EvidenceRegistry(str(path))


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("Source_Tier", "Z", "Invalid Source_Tier"),
        ("Evidence_Direction", "MAYBE", "Invalid Evidence_Direction"),
    ],
)
def test_invalid_registry_enums_raise_value_error(
    tmp_path: Path, column: str, value: str, message: str
):
    from nailverifier_v3.evidence_registry import EvidenceRegistry

    path = _write_registry(tmp_path / "bad.csv", **{column: value})
    with pytest.raises(ValueError, match=message):
        EvidenceRegistry(str(path))
