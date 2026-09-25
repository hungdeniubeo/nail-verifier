from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BusinessRecord:
    company: str
    street: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    phone: str = ""
    rating: float = 0.0
    reviews: int = 0
    status: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NameMatch:
    score: float
    exact: bool
    full_fuzzy: float
    token_fuzzy: float
    core_overlap: float
    target_core: List[str]
    candidate_core: List[str]


@dataclass
class AddressMatch:
    score: float
    street_number_match: Optional[bool]
    street_score: float
    city_match: Optional[bool]
    zip_match: Optional[bool]


@dataclass
class Evidence:
    source: str
    strength: str
    matched_name: str = ""
    matched_address: str = ""
    matched_phone: str = ""
    category: str = ""
    status: str = ""
    license_number: str = ""
    license_type: str = ""
    expires: str = ""
    source_url: str = ""
    name_score: float = 0.0
    address_score: float = 0.0
    phone_match: Optional[bool] = None
    notes: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VerificationResult:
    decision: str
    confidence: int
    auto_action: str
    reason: str
    evidence_tier: str
    state_support: str
    checked_at: str
    cache_hit: bool = False
    evidence: List[Evidence] = field(default_factory=list)
    source_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Decision": self.decision,
            "Confidence": self.confidence,
            "Auto_Action": self.auto_action,
            "Reason": self.reason,
            "Evidence_Tier": self.evidence_tier,
            "State_Support": self.state_support,
            "Checked_At": self.checked_at,
            "Cache_Hit": "YES" if self.cache_hit else "NO",
            "Source_Errors": " | ".join(self.source_errors),
        }
