from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

from .evidence_registry import RegistryEvidence
from .features import LocalAssessment
from .models import BusinessRecord, Evidence
from .normalize import normalize_text

NAIL_LICENSE_TERMS = (
    "nail salon",
    "nail shop",
    "manicuring salon",
    "nail technology salon",
    "manicurist",
    "pedicurist",
)


@dataclass(frozen=True)
class EvidenceSignal:
    source_name: str
    source_key: str
    source_tier: str
    source_url: str
    direction: str
    identity_verified: bool
    category: str = ""
    service_evidence: str = ""
    existence_status: str = "UNKNOWN"
    checked_at: str = ""
    notes: str = ""


def _source_key(source_name: str, source_url: str) -> str:
    host = (urlparse(source_url).hostname or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host or normalize_text(source_name).replace(" ", "_")


def _status(value: str) -> str:
    text = normalize_text(value)
    if any(token in text for token in ("closed", "inactive", "expired")):
        return "VERIFIED_CLOSED"
    if any(token in text for token in ("active", "current", "operational", "open")):
        return "VERIFIED_ACTIVE"
    return "UNKNOWN"


def classify_registry_evidence(rows: List[RegistryEvidence]) -> List[EvidenceSignal]:
    return [
        EvidenceSignal(
            source_name=row.source_name,
            source_key=row.source_key,
            source_tier=row.source_tier,
            source_url=row.source_url,
            direction=row.direction,
            identity_verified=True,
            category=row.observed_category,
            service_evidence=row.nail_service_evidence,
            existence_status=_status(row.business_status_evidence),
            checked_at=row.checked_at,
            notes=row.notes,
        )
        for row in rows
    ]


def _live_direction(item: Evidence) -> str:
    strength = (item.strength or "").upper()
    if strength == "STRONG_INDEPENDENT_NAIL":
        return "NAIL"
    if strength == "STRONG_INDEPENDENT_NOT_NAIL":
        return "NOT_NAIL"
    if strength in {"STRONG_INDEPENDENT_BEAUTY", "INDEPENDENT_IDENTITY_ONLY"}:
        return "AMBIGUOUS" if strength == "STRONG_INDEPENDENT_BEAUTY" else "IDENTITY_ONLY"

    if item.source.endswith("COSMETOLOGY") and strength == "STRONG_OFFICIAL":
        license_text = normalize_text(item.license_type or item.category)
        if any(term in license_text for term in NAIL_LICENSE_TERMS):
            return "NAIL"
        return "AMBIGUOUS"

    return "AMBIGUOUS"


def classify_live_evidence(items: List[Evidence]) -> List[EvidenceSignal]:
    signals: List[EvidenceSignal] = []
    for item in items:
        if item.source.endswith("COSMETOLOGY") and item.strength == "STRONG_OFFICIAL":
            tier = "A"
            identity_verified = True
        elif item.source == "OPENSTREETMAP":
            tier = "C"
            identity_verified = item.strength in {
                "STRONG_INDEPENDENT_NAIL",
                "STRONG_INDEPENDENT_NOT_NAIL",
                "STRONG_INDEPENDENT_BEAUTY",
                "INDEPENDENT_IDENTITY_ONLY",
            }
        else:
            tier = "C"
            identity_verified = item.strength.startswith("STRONG")

        signals.append(
            EvidenceSignal(
                source_name=item.source,
                source_key=_source_key(item.source, item.source_url),
                source_tier=tier,
                source_url=item.source_url,
                direction=_live_direction(item),
                identity_verified=identity_verified,
                category=item.category or item.license_type,
                service_evidence=item.license_type or item.category,
                existence_status=_status(item.status),
                checked_at="",
                notes=item.notes,
            )
        )
    return signals


def heuristic_signal(
    local: LocalAssessment,
    record: BusinessRecord,
) -> Optional[EvidenceSignal]:
    if local.rule_id in {"R_NAIL_EXPLICIT_STRONG", "R_NAIL_EXPLICIT_ADDRESS_STRONG", "R_NAIL_EXPLICIT_WEAK", "R_NAIL_STYLING_HINT"}:
        direction = "NAIL"
    elif local.rule_id in {"R_NON_NAIL_CATEGORY_STRONG", "R_NON_NAIL_CATEGORY_ADDRESS_STRONG", "R_NON_NAIL_CATEGORY_WEAK"}:
        direction = "NOT_NAIL"
    else:
        return None

    existence = "LIKELY_ACTIVE" if normalize_text(record.status) == "operational" else "UNKNOWN"
    return EvidenceSignal(
        source_name="NAILMAP_RULE",
        source_key="nailmap",
        source_tier="D",
        source_url="",
        direction=direction,
        identity_verified=False,
        category=local.signal,
        service_evidence="",
        existence_status=existence,
        checked_at="",
        notes="Heuristic local rule only; never sufficient for VERIFIED status.",
    )
