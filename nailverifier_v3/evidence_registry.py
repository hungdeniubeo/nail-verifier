from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse

import pandas as pd

from .models import BusinessRecord
from .normalize import (
    clean,
    normalize_name,
    normalize_phone,
    normalize_street,
    normalize_text,
    normalize_zip,
)

REQUIRED_COLUMNS = {
    "State",
    "Company",
    "Street",
    "City",
    "ZIP",
    "Phone",
    "Source_Name",
    "Source_Tier",
    "Source_URL",
    "Observed_Category",
    "Nail_Service_Evidence",
    "Business_Status_Evidence",
    "Evidence_Direction",
    "Evidence_Notes",
    "Checked_At",
}
VALID_SOURCE_TIERS = {"A", "B", "C", "D"}
VALID_DIRECTIONS = {"NAIL", "NOT_NAIL", "IDENTITY_ONLY", "STATUS_ONLY", "AMBIGUOUS"}


@dataclass(frozen=True)
class RegistryEvidence:
    state: str
    company: str
    street: str
    city: str
    zip_code: str
    phone: str
    source_name: str
    source_tier: str
    source_url: str
    observed_category: str
    nail_service_evidence: str
    business_status_evidence: str
    direction: str
    notes: str
    checked_at: str
    normalized_phone: str
    source_key: str


def _source_key(source_url: str, source_name: str) -> str:
    host = normalize_text(urlparse(clean(source_url)).hostname or "")
    if host.startswith("www "):
        host = host[4:]
    if host:
        return host.replace(" ", ".")
    return normalize_text(source_name)


def _identity_key(
    state: str,
    company: str,
    street: str,
    city: str,
    zip_code: str,
) -> Tuple[str, str, str, str, str]:
    return (
        clean(state).upper(),
        normalize_name(company),
        normalize_street(street, drop_unit=False),
        normalize_text(city),
        normalize_zip(zip_code),
    )


class EvidenceRegistry:
    def __init__(self, path: str = "benchmarks/verified_business_evidence.csv"):
        self.path = Path(path)
        raw = self.path.read_bytes()
        self.version = hashlib.sha256(raw).hexdigest()
        frame = pd.read_csv(self.path, dtype=str, keep_default_na=False)

        missing = REQUIRED_COLUMNS - set(frame.columns)
        if missing:
            raise ValueError(
                "Missing required evidence columns: %s" % ", ".join(sorted(missing))
            )

        invalid_tiers = sorted(set(frame["Source_Tier"]) - VALID_SOURCE_TIERS)
        if invalid_tiers:
            raise ValueError("Invalid Source_Tier: %s" % ", ".join(invalid_tiers))

        invalid_directions = sorted(
            set(frame["Evidence_Direction"]) - VALID_DIRECTIONS
        )
        if invalid_directions:
            raise ValueError(
                "Invalid Evidence_Direction: %s" % ", ".join(invalid_directions)
            )

        self._index: Dict[Tuple[str, str, str, str, str], List[RegistryEvidence]] = {}
        for row in frame.to_dict(orient="records"):
            key = _identity_key(
                row["State"], row["Company"], row["Street"], row["City"], row["ZIP"]
            )
            evidence = RegistryEvidence(
                state=clean(row["State"]).upper(),
                company=clean(row["Company"]),
                street=clean(row["Street"]),
                city=clean(row["City"]),
                zip_code=normalize_zip(row["ZIP"]),
                phone=clean(row["Phone"]),
                source_name=clean(row["Source_Name"]),
                source_tier=clean(row["Source_Tier"]).upper(),
                source_url=clean(row["Source_URL"]),
                observed_category=clean(row["Observed_Category"]),
                nail_service_evidence=clean(row["Nail_Service_Evidence"]),
                business_status_evidence=clean(row["Business_Status_Evidence"]),
                direction=clean(row["Evidence_Direction"]).upper(),
                notes=clean(row["Evidence_Notes"]),
                checked_at=clean(row["Checked_At"]),
                normalized_phone=normalize_phone(row["Phone"]),
                source_key=_source_key(row["Source_URL"], row["Source_Name"]),
            )
            self._index.setdefault(key, []).append(evidence)

    def match(self, record: BusinessRecord) -> List[RegistryEvidence]:
        key = _identity_key(
            record.state,
            record.company,
            record.street,
            record.city,
            record.zip_code,
        )
        record_phone = normalize_phone(record.phone)
        matches: List[RegistryEvidence] = []
        for evidence in self._index.get(key, []):
            if record_phone and evidence.normalized_phone and record_phone != evidence.normalized_phone:
                continue
            matches.append(evidence)
        return matches
