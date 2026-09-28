from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse

import pandas as pd

from .models import BusinessRecord
from .normalize import normalize_name, normalize_phone, normalize_street, normalize_text, normalize_zip

REQUIRED_COLUMNS = {
    "State", "Company", "Street", "City", "ZIP", "Phone",
    "Source_Name", "Source_Tier", "Source_URL", "Observed_Category",
    "Nail_Service_Evidence", "Business_Status_Evidence",
    "Evidence_Direction", "Evidence_Notes", "Checked_At",
}
VALID_TIERS = {"A", "B", "C", "D"}
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
    evidence_direction: str
    evidence_notes: str
    checked_at: str
    source_key: str


def _source_key(source_url: str, source_name: str) -> str:
    host = (urlparse(source_url).hostname or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host or normalize_text(source_name)


class EvidenceRegistry:
    def __init__(self, path: str = "benchmarks/verified_business_evidence.csv"):
        self.path = Path(path)
        raw = self.path.read_bytes()
        self.version = hashlib.sha256(raw).hexdigest()
        frame = pd.read_csv(self.path, dtype=str, keep_default_na=False)
        missing = REQUIRED_COLUMNS - set(frame.columns)
        if missing:
            raise ValueError("Missing required evidence columns: %s" % ", ".join(sorted(missing)))
        bad_tiers = sorted(set(frame["Source_Tier"]) - VALID_TIERS)
        if bad_tiers:
            raise ValueError("Invalid Source_Tier: %s" % ", ".join(bad_tiers))
        bad_directions = sorted(set(frame["Evidence_Direction"]) - VALID_DIRECTIONS)
        if bad_directions:
            raise ValueError("Invalid Evidence_Direction: %s" % ", ".join(bad_directions))

        self._by_identity: Dict[str, List[RegistryEvidence]] = {}
        for _, row in frame.iterrows():
            item = RegistryEvidence(
                state=str(row["State"]).strip().upper(),
                company=str(row["Company"]),
                street=str(row["Street"]),
                city=str(row["City"]),
                zip_code=str(row["ZIP"]),
                phone=str(row["Phone"]),
                source_name=str(row["Source_Name"]),
                source_tier=str(row["Source_Tier"]).strip().upper(),
                source_url=str(row["Source_URL"]),
                observed_category=str(row["Observed_Category"]),
                nail_service_evidence=str(row["Nail_Service_Evidence"]),
                business_status_evidence=str(row["Business_Status_Evidence"]),
                evidence_direction=str(row["Evidence_Direction"]).strip().upper(),
                evidence_notes=str(row["Evidence_Notes"]),
                checked_at=str(row["Checked_At"]),
                source_key=_source_key(str(row["Source_URL"]), str(row["Source_Name"])),
            )
            self._by_identity.setdefault(self._identity_key(item), []).append(item)

    @staticmethod
    def _identity_key(item: RegistryEvidence) -> str:
        return "|".join([
            item.state,
            normalize_name(item.company),
            normalize_street(item.street, drop_unit=False),
            normalize_text(item.city),
            normalize_zip(item.zip_code),
        ])

    @staticmethod
    def _record_key(record: BusinessRecord) -> str:
        return "|".join([
            (record.state or "").upper(),
            normalize_name(record.company),
            normalize_street(record.street, drop_unit=False),
            normalize_text(record.city),
            normalize_zip(record.zip_code),
        ])

    def match(self, record: BusinessRecord) -> List[RegistryEvidence]:
        candidates = self._by_identity.get(self._record_key(record), [])
        record_phone = normalize_phone(record.phone)
        out: List[RegistryEvidence] = []
        for item in candidates:
            item_phone = normalize_phone(item.phone)
            if record_phone and item_phone and record_phone != item_phone:
                continue
            out.append(item)
        return out
