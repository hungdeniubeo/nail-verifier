from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Set

from .evidence_classifier import EvidenceSignal
from .normalize import normalize_text

TIER_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}
STRONG_TIERS = {"A", "B", "C"}
DIRECTIONAL = {"NAIL", "NOT_NAIL"}
BEAUTY_WORDS = {"beauty", "hair", "salon", "spa", "cosmetology", "esthetic", "aesthetic", "lash"}
NAIL_WORDS = {"nail", "nails", "manicure", "pedicure", "acrylic", "gel", "gel x", "dip powder"}


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


def _explicit_directional(signal: EvidenceSignal) -> bool:
    text = normalize_text(" ".join([signal.category, signal.service_evidence, signal.notes]))
    if signal.direction == "NAIL":
        return bool(signal.service_evidence.strip()) or any(word in text for word in NAIL_WORDS)
    if signal.direction == "NOT_NAIL":
        category = normalize_text(signal.category)
        if not category:
            return False
        tokens = set(category.split())
        return "nail" not in tokens and not any(word in tokens for word in BEAUTY_WORDS)
    return False


def _source_directions(signals: Iterable[EvidenceSignal]) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {}
    for signal in signals:
        if (
            signal.identity_verified
            and signal.source_tier in STRONG_TIERS
            and signal.direction in DIRECTIONAL
            and _explicit_directional(signal)
        ):
            out.setdefault(signal.source_key, set()).add(signal.direction)
    return out


def _primary(signals: List[EvidenceSignal]) -> EvidenceSignal | None:
    if not signals:
        return None

    def key(signal: EvidenceSignal):
        explicit = 0 if signal.direction in DIRECTIONAL and _explicit_directional(signal) else 1
        date_rank = "".join(chr(255 - ord(ch)) if ord(ch) < 256 else ch for ch in signal.checked_at)
        return (TIER_RANK.get(signal.source_tier, 9), explicit, date_rank, signal.source_name)

    return sorted(signals, key=key)[0]


def resolve_consensus(signals: List[EvidenceSignal]) -> ConsensusResult:
    unique_sources = {signal.source_key for signal in signals if signal.source_key}
    strong_direction_map = _source_directions(signals)
    nail_sources = {key for key, directions in strong_direction_map.items() if "NAIL" in directions}
    not_nail_sources = {key for key, directions in strong_direction_map.items() if "NOT_NAIL" in directions}
    strong_keys = nail_sources | not_nail_sources

    conflict = bool(nail_sources and not_nail_sources)
    conflict_count = min(len(nail_sources), len(not_nail_sources)) if conflict else 0

    tier_a_nail = any(
        s.source_tier == "A"
        and s.identity_verified
        and s.direction == "NAIL"
        and _explicit_directional(s)
        for s in signals
    )
    tier_a_not_nail = any(
        s.source_tier == "A"
        and s.identity_verified
        and s.direction == "NOT_NAIL"
        and _explicit_directional(s)
        for s in signals
    )

    weak_nail = any(s.direction == "NAIL" for s in signals)
    weak_not_nail = any(s.direction == "NOT_NAIL" for s in signals)

    if conflict:
        status = "CONFLICTING_EVIDENCE"
        reason = "Strong identity-matched sources disagree on nail versus not-nail classification."
    elif tier_a_nail or len(nail_sources) >= 2:
        status = "VERIFIED_NAIL"
        reason = "Business-specific evidence meets the v3.7 nail verification gate."
    elif tier_a_not_nail or len(not_nail_sources) >= 2:
        status = "VERIFIED_NOT_NAIL"
        reason = "Business-specific evidence meets the v3.7 affirmative non-nail verification gate."
    elif nail_sources or (weak_nail and not weak_not_nail):
        status = "LIKELY_NAIL"
        reason = "Evidence points to nail services but does not meet the multi-source VERIFIED gate."
    elif not_nail_sources or (weak_not_nail and not weak_nail):
        status = "LIKELY_NOT_NAIL"
        reason = "Evidence points to a non-nail business but does not meet the multi-source VERIFIED gate."
    else:
        status = "UNKNOWN"
        reason = "Available evidence does not resolve nail-service status."

    identity_status = "VERIFIED" if any(
        s.identity_verified and s.source_tier in STRONG_TIERS for s in signals
    ) else "UNKNOWN"

    existence_values = {s.existence_status for s in signals}
    if "VERIFIED_ACTIVE" in existence_values:
        existence_status = "VERIFIED_ACTIVE"
    elif "VERIFIED_CLOSED" in existence_values:
        existence_status = "VERIFIED_CLOSED"
    elif "LIKELY_ACTIVE" in existence_values:
        existence_status = "LIKELY_ACTIVE"
    else:
        existence_status = "UNKNOWN"

    service_status = {
        "VERIFIED_NAIL": "VERIFIED_NAIL",
        "VERIFIED_NOT_NAIL": "VERIFIED_NOT_NAIL",
        "LIKELY_NAIL": "LIKELY_NAIL",
        "LIKELY_NOT_NAIL": "LIKELY_NOT_NAIL",
        "CONFLICTING_EVIDENCE": "CONFLICTING",
        "UNKNOWN": "UNKNOWN",
    }[status]

    primary = _primary(signals)
    ordered = sorted(
        signals,
        key=lambda s: (TIER_RANK.get(s.source_tier, 9), s.source_key, s.direction),
    )
    evidence_text = " | ".join(
        f"{s.source_tier}:{s.source_name}:{s.direction}:{s.category or s.service_evidence or s.notes}"
        for s in ordered
    )
    verified_dates = [s.checked_at for s in signals if s.checked_at]

    return ConsensusResult(
        verification_status=status,
        identity_status=identity_status,
        existence_status=existence_status,
        nail_service_status=service_status,
        evidence_source_count=len(unique_sources),
        strong_evidence_count=len(strong_keys),
        evidence_agrees="NO" if conflict else ("YES" if strong_keys else ""),
        evidence_conflicts=conflict_count,
        primary_source=primary.source_name if primary else "",
        primary_source_tier=primary.source_tier if primary else "",
        primary_source_url=primary.source_url if primary else "",
        verification_evidence=evidence_text,
        verification_reason=reason,
        verified_at=max(verified_dates) if verified_dates else "",
    )
