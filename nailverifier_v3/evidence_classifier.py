from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

from .evidence_registry import RegistryEvidence
from .features import LocalAssessment
from .models import BusinessRecord, Evidence
from .normalize import normalize_text

NAIL_LICENSE_TERMS = {"nail salon", "nail shop", "manicuring salon", "nail technology salon"}


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
    existence_status: str = ""
    checked_at: str = ""
    notes: str = ""


def _source_key(url: str, name: str) -> str:
    host = (urlparse(url).hostname or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host or normalize_text(name)


def classify_registry_evidence(rows: List[RegistryEvidence]) -> List[EvidenceSignal]:
    return [
        EvidenceSignal(
            source_name=row.source_name,
            source_key=row.source_key,
            source_tier=row.source_tier,
            source_url=row.source_url,
            direction=row.evidence_direction,
            identity_verified=True,
            category=row.observed_category,
            service_evidence=row.nail_service_evidence,
            existence_status=row.business_status_evidence,
            checked_at=row.checked_at,
            notes=row.evidence_notes,
        )
        for row in rows
    ]


def _official_direction(item: Evidence) -> str:
    license_type = normalize_text(item.license_type or item.category)
    if any(term in license_type for term in NAIL_LICENSE_TERMS):
        return "NAIL"
    return "AMBIGUOUS"


def classify_live_evidence(items: List[Evidence]) -> List[EvidenceSignal]:
    out: List[EvidenceSignal] = []
    for item in items:
        tier = "C"
        direction = "AMBIGUOUS"
        verified = False
        if item.source.endswith("COSMETOLOGY") and item.strength == "STRONG_OFFICIAL":
            tier = "A"
            direction = _official_direction(item)
            verified = True
        elif item.source == "OPENSTREETMAP":
            verified = item.strength in {
                "STRONG_INDEPENDENT_NAIL",
                "STRONG_INDEPENDENT_BEAUTY",
                "STRONG_INDEPENDENT_NOT_NAIL",
                "INDEPENDENT_IDENTITY_ONLY",
            }
            if item.strength == "STRONG_INDEPENDENT_NAIL":
                direction = "NAIL"
            elif item.strength == "STRONG_INDEPENDENT_NOT_NAIL":
                direction = "NOT_NAIL"
            else:
                direction = "AMBIGUOUS"
        out.append(
            EvidenceSignal(
                source_name=item.source,
                source_key=_source_key(item.source_url, item.source),
                source_tier=tier,
                source_url=item.source_url,
                direction=direction,
                identity_verified=verified,
                category=item.category or item.license_type,
                service_evidence=item.notes if direction == "NAIL" else "",
                existence_status=item.status,
                notes=item.notes,
            )
        )
    return out


def heuristic_signal(local: LocalAssessment, record: BusinessRecord) -> Optional[EvidenceSignal]:
    direction = ""
    if local.rule_id.startswith("R_NAIL_") and local.rule_id != "R_NAIL_NON_SERVICE_CONFLICT":
        direction = "NAIL"
    elif local.rule_id.startswith("R_NON_NAIL_"):
        direction = "NOT_NAIL"
    if not direction:
        return None
    return EvidenceSignal(
        source_name="NAILMAP_HEURISTIC",
        source_key="nailmap-heuristic",
        source_tier="D",
        source_url="",
        direction=direction,
        identity_verified=False,
        category="",
        service_evidence=local.signal,
        existence_status=record.status,
        notes="Rule hint only; not business-specific verification.",
    )
