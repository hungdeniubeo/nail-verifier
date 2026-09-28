from __future__ import annotations

from pathlib import Path

import pytest

from nailverifier_v3.evidence_registry import EvidenceRegistry
from nailverifier_v3.models import BusinessRecord


HEADER = (
    "State,Company,Street,City,ZIP,Phone,Source_Name,Source_Tier,Source_URL,"
    "Observed_Category,Nail_Service_Evidence,Business_Status_Evidence,"
    "Evidence_Direction,Evidence_Notes,Checked_At\n"
)


def write_registry(path: Path, body: str) -> None:
    path.write_text(HEADER + body, encoding="utf-8")


def make_record(**overrides) -> BusinessRecord:
    values = dict(
        company="Zen Nail Studio",
        street="5201 S Solberg Ave suite 200",
        city="Sioux Falls",
        state="SD",
        zip_code="57108",
        phone="6055550100",
    )
    values.update(overrides)
    return BusinessRecord(**values)


def test_exact_identity_loads_evidence_and_version(tmp_path: Path):
    path = tmp_path / "registry.csv"
    write_registry(
        path,
        "SD,Zen Nail Studio,5201 S Solberg Ave suite 200,Sioux Falls,57108,6055550100,Official Booking,A,https://example.com/zen,Nail Salon,manicure|pedicure,ACTIVE,NAIL,exact match,2026-09-28\n",
    )
    registry = EvidenceRegistry(str(path))

    matches = registry.match(make_record())

    assert len(matches) == 1
    assert matches[0].source_url == "https://example.com/zen"
    assert matches[0].source_key == "example.com"
    assert len(registry.version) == 64


def test_same_name_wrong_address_does_not_match(tmp_path: Path):
    path = tmp_path / "registry.csv"
    write_registry(path, "SD,Zen Nail Studio,5201 S Solberg Ave suite 200,Sioux Falls,57108,6055550100,Official Booking,A,https://example.com/zen,Nail Salon,manicure,ACTIVE,NAIL,exact,2026-09-28\n")
    registry = EvidenceRegistry(str(path))
    assert registry.match(make_record(street="1 Wrong St")) == []


def test_same_identity_wrong_state_does_not_match(tmp_path: Path):
    path = tmp_path / "registry.csv"
    write_registry(path, "SD,Zen Nail Studio,5201 S Solberg Ave suite 200,Sioux Falls,57108,6055550100,Official Booking,A,https://example.com/zen,Nail Salon,manicure,ACTIVE,NAIL,exact,2026-09-28\n")
    registry = EvidenceRegistry(str(path))
    assert registry.match(make_record(state="NE")) == []


def test_nonempty_conflicting_phone_rejects_registry_row(tmp_path: Path):
    path = tmp_path / "registry.csv"
    write_registry(path, "SD,Zen Nail Studio,5201 S Solberg Ave suite 200,Sioux Falls,57108,6055550100,Official Booking,A,https://example.com/zen,Nail Salon,manicure,ACTIVE,NAIL,exact,2026-09-28\n")
    registry = EvidenceRegistry(str(path))
    assert registry.match(make_record(phone="6059999999")) == []


def test_missing_phone_can_match_exact_name_and_location(tmp_path: Path):
    path = tmp_path / "registry.csv"
    write_registry(path, "SD,Zen Nail Studio,5201 S Solberg Ave suite 200,Sioux Falls,57108,,Official Booking,A,https://example.com/zen,Nail Salon,manicure,ACTIVE,NAIL,exact,2026-09-28\n")
    registry = EvidenceRegistry(str(path))
    assert len(registry.match(make_record(phone=""))) == 1


@pytest.mark.parametrize(
    "header,body",
    [
        ("State,Company\n", "SD,Zen Nail Studio\n"),
        (HEADER, "SD,Zen Nail Studio,5201 S Solberg Ave suite 200,Sioux Falls,57108,,Source,Z,https://example.com,Nail Salon,manicure,ACTIVE,NAIL,note,2026-09-28\n"),
        (HEADER, "SD,Zen Nail Studio,5201 S Solberg Ave suite 200,Sioux Falls,57108,,Source,A,https://example.com,Nail Salon,manicure,ACTIVE,MAYBE,note,2026-09-28\n"),
    ],
)
def test_invalid_registry_schema_or_enum_raises(tmp_path: Path, header: str, body: str):
    path = tmp_path / "registry.csv"
    path.write_text(header + body, encoding="utf-8")
    with pytest.raises(ValueError):
        EvidenceRegistry(str(path))
