from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .evidence_classifier import EvidenceSignal

TIER_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}
DIRECTIONAL = {"NAIL", "NOT_NAIL"}
CONFLICT_MARKER = "#conflict#"


@dataclass(frozen=True)
class ConsensusResult:
    verification_status: str
    identity_status: str
    existence_status: str
    nail_service_status: str
    evidence_source_count: int
    strong_evidence_count: int
    evidence_agrees: str
    evidence_conflicts: int
    primary_source: str
    primary_source_tier: str
    primary_source_url: str
    verification_evidence: str
    verification_reason: str
    verified_at: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "Verification_Status": self.verification_status,
            "Identity_Status": self.identity_status,
            "Existence_Status": self.existence_status,
            "Nail_Service_Status": self.nail_service_status,
            "Evidence_Source_Count": self.evidence_source_count,
            "Strong_Evidence_Count": self.strong_evidence_count,
            "Evidence_Agrees": self.evidence_agrees,
            "Evidence_Conflicts": self.evidence_conflicts,
            "Primary_Source": self.primary_source,
            "Primary_Source_Tier": self.primary_source_tier,
            "Primary_Source_URL": self.primary_source_url,
            "Verification_Evidence": self.verification_evidence,
            "Verification_Reason": self.verification_reason,
            "Verified_At": self.verified_at,
        }


def _base_source_key(value: str) -> str:
    return value.split(CONFLICT_MARKER, 1)[0]


def _dedupe(signals: List[EvidenceSignal]) -> List[EvidenceSignal]:
    best = {}
    for signal in signals:
        current = best.get(signal.source_key)
        if current is None:
            best[signal.source_key] = signal
            continue
        current_rank = (
            TIER_RANK.get(current.source_tier, 9),
            0 if current.direction in DIRECTIONAL else 1,
        )
        new_rank = (
            TIER_RANK.get(signal.source_tier, 9),
            0 if signal.direction in DIRECTIONAL else 1,
        )
        if new_rank < current_rank:
            best[signal.source_key] = signal
        elif signal.direction in DIRECTIONAL and current.direction in DIRECTIONAL and signal.direction != current.direction:
            # Preserve a same-provider contradiction for conflict detection, but
            # source counts later collapse the synthetic key to the provider.
            best[signal.source_key + CONFLICT_MARKER + signal.direction] = signal
        elif new_rank == current_rank and signal.checked_at > current.checked_at:
            best[signal.source_key] = signal
    return list(best.values())


def _primary(signals: List[EvidenceSignal]) -> EvidenceSignal | None:
    if not signals:
        return None
    best_tier = min(TIER_RANK.get(s.source_tier, 9) for s in signals)
    tier_candidates = [s for s in signals if TIER_RANK.get(s.source_tier, 9) == best_tier]
    if any(s.direction in DIRECTIONAL for s in tier_candidates):
        tier_candidates = [s for s in tier_candidates if s.direction in DIRECTIONAL]
    return max(tier_candidates, key=lambda s: s.checked_at or "")


def resolve_consensus(signals: List[EvidenceSignal]) -> ConsensusResult:
    unique = _dedupe(signals)
    strong = [s for s in unique if s.identity_verified and s.source_tier in {"A", "B", "C"} and s.direction in DIRECTIONAL]
    nail = [s for s in strong if s.direction == "NAIL"]
    not_nail = [s for s in strong if s.direction == "NOT_NAIL"]
    tier_d = [s for s in unique if s.source_tier == "D" and s.direction in DIRECTIONAL]

    conflicts = 1 if nail and not_nail else 0
    status = "UNKNOWN"
    reason = "No business-specific directional evidence meets the verification gate."

    if conflicts:
        status = "CONFLICTING_EVIDENCE"
        reason = "Strong identity-matched sources disagree on nail versus not-nail classification."
    elif nail:
        independent_nail = {_base_source_key(s.source_key) for s in nail if s.source_tier in {"B", "C"}}
        if any(s.source_tier == "A" for s in nail) or len(independent_nail) >= 2:
            status = "VERIFIED_NAIL"
            reason = "Business-specific evidence meets the v3.7 nail verification gate."
        else:
            status = "LIKELY_NAIL"
            reason = "Directional nail evidence exists but is not sufficiently corroborated."
    elif not_nail:
        independent_not_nail = {_base_source_key(s.source_key) for s in not_nail if s.source_tier in {"B", "C"}}
        if any(s.source_tier == "A" for s in not_nail) or len(independent_not_nail) >= 2:
            status = "VERIFIED_NOT_NAIL"
            reason = "Business-specific affirmative non-nail evidence meets the v3.7 verification gate."
        else:
            status = "LIKELY_NOT_NAIL"
            reason = "Directional non-nail evidence exists but is not sufficiently corroborated."
    elif tier_d:
        directions = {s.direction for s in tier_d}
        if directions == {"NAIL"}:
            status = "LIKELY_NAIL"
            reason = "Only heuristic NailMap/name-rule evidence points to nail service."
        elif directions == {"NOT_NAIL"}:
            status = "LIKELY_NOT_NAIL"
            reason = "Only heuristic NailMap/name-rule evidence points to a non-nail category."

    identity_status = "VERIFIED" if any(s.identity_verified and s.source_tier in {"A", "B", "C"} for s in unique) else "UNVERIFIED"
    existence_status = "UNKNOWN"
    statuses = " ".join((s.existence_status or "").upper() for s in unique)
    if "CLOSED" in statuses:
        existence_status = "VERIFIED_CLOSED"
    elif any(token in statuses for token in ("ACTIVE", "CURRENT", "OPERATIONAL")) and identity_status == "VERIFIED":
        existence_status = "VERIFIED_ACTIVE"
    elif any(token in statuses for token in ("ACTIVE", "CURRENT", "OPERATIONAL")):
        existence_status = "LIKELY_ACTIVE"

    if status == "VERIFIED_NAIL":
        nail_service = "VERIFIED_NAIL"
    elif status == "VERIFIED_NOT_NAIL":
        nail_service = "VERIFIED_NOT_NAIL"
    elif status == "LIKELY_NAIL":
        nail_service = "LIKELY_NAIL"
    elif status == "LIKELY_NOT_NAIL":
        nail_service = "LIKELY_NOT_NAIL"
    elif status == "CONFLICTING_EVIDENCE":
        nail_service = "CONFLICTING"
    else:
        nail_service = "UNKNOWN"

    primary = _primary(unique)
    evidence_text = " | ".join(
        f"{s.source_name} [{s.source_tier}] {s.direction}: {(s.service_evidence or s.category or s.notes).strip()}"
        for s in unique
    )
    checked = max((s.checked_at for s in unique if s.checked_at), default="")
    agrees = "YES" if strong and not conflicts else "NO"

    source_keys = {_base_source_key(s.source_key) for s in unique}
    strong_source_keys = {_base_source_key(s.source_key) for s in strong}

    return ConsensusResult(
        verification_status=status,
        identity_status=identity_status,
        existence_status=existence_status,
        nail_service_status=nail_service,
        evidence_source_count=len(source_keys),
        strong_evidence_count=len(strong_source_keys),
        evidence_agrees=agrees,
        evidence_conflicts=conflicts,
        primary_source=primary.source_name if primary else "",
        primary_source_tier=primary.source_tier if primary else "",
        primary_source_url=primary.source_url if primary else "",
        verification_evidence=evidence_text,
        verification_reason=reason,
        verified_at=checked,
    )
