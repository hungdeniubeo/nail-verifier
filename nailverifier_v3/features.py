from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List

from .models import BusinessRecord
from .normalize import has_beauty_words, has_nail_words, normalize_text

# High precision terms that identify a clearly different business category.
# Beauty/hair/spa terms are intentionally excluded because many real nail
# providers are multi-service salons.
STRONG_NON_NAIL_PATTERNS = [
    r"\bace hardware\b",
    r"\btrue value\b",
    r"\bhardware\b",
    r"\bbuilding center\b",
    r"\bdollar general\b",
    r"\bgrocery\b",
    r"\bsupermarket\b",
    r"\brestaurant\b",
    r"\bgrille\b",
    r"\bsteakhouse\b",
    r"\bbuffet\b",
    r"\bcoffee shop\b",
    r"\bfuel stop\b",
    r"\bgas station\b",
    r"\bauto parts\b",
    r"\btire\b",
    r"\bbank\b",
    r"\bhotel\b",
    r"\bmotel\b",
    r"\bchurch\b",
]

# Explicit nail words in the business name are a strong service signal.
EXPLICIT_NAIL_RE = re.compile(
    r"\b(nail|nails|manicure|manicures|pedicure|pedicures|mani|pedi)\b",
    re.IGNORECASE,
)


@dataclass
class LocalAssessment:
    rule_id: str
    candidate_action: str
    signal: str
    score: int
    risk_flags: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "Rule_ID": self.rule_id,
            "Candidate_Action": self.candidate_action,
            "Local_Signal": self.signal,
            "Local_Score": self.score,
            "Risk_Flags": " | ".join(self.risk_flags),
        }


def _has_identity(record: BusinessRecord) -> bool:
    return bool(record.zip_code and (record.street or record.city) and record.phone)


def _strong_non_nail_name(name: str) -> bool:
    text = normalize_text(name)
    if has_nail_words(name) or has_beauty_words(name):
        return False
    return any(re.search(pattern, text) for pattern in STRONG_NON_NAIL_PATTERNS)


def assess_local(record: BusinessRecord) -> LocalAssessment:
    status = normalize_text(record.status)
    operational = status == "operational"
    identity = _has_identity(record)
    explicit_nail = bool(EXPLICIT_NAIL_RE.search(record.company or ""))
    beauty = has_beauty_words(record.company)
    strong_non_nail = _strong_non_nail_name(record.company)

    risks: List[str] = []
    if not record.phone:
        risks.append("MISSING_PHONE")
    if not record.street:
        risks.append("MISSING_STREET")
    if not record.zip_code:
        risks.append("MISSING_ZIP")
    if record.reviews < 3:
        risks.append("LOW_REVIEW_COUNT")
    if record.rating <= 0:
        risks.append("MISSING_RATING")
    if status not in {"", "operational"}:
        risks.append("NON_OPERATIONAL_STATUS")

    if "permanently closed" in status or "closed permanently" in status:
        return LocalAssessment(
            rule_id="R_STATUS_PERMANENTLY_CLOSED",
            candidate_action="REMOVE",
            signal="SOURCE_STATUS_CLOSED",
            score=90,
            risk_flags=risks,
        )

    if "temporarily closed" in status or "closed temporarily" in status:
        return LocalAssessment(
            rule_id="R_STATUS_TEMPORARILY_CLOSED",
            candidate_action="REVIEW",
            signal="SOURCE_STATUS_TEMP_CLOSED",
            score=85,
            risk_flags=risks,
        )

    if explicit_nail and operational and identity and record.reviews >= 3:
        score = 92
        if record.reviews >= 20:
            score += 2
        if record.reviews >= 100:
            score += 1
        return LocalAssessment(
            rule_id="R_NAIL_EXPLICIT_STRONG",
            candidate_action="KEEP",
            signal="EXPLICIT_NAIL_NAME_PLUS_STRUCTURED_LISTING",
            score=min(score, 95),
            risk_flags=risks,
        )

    if explicit_nail and operational:
        return LocalAssessment(
            rule_id="R_NAIL_EXPLICIT_WEAK",
            candidate_action="REVIEW",
            signal="EXPLICIT_NAIL_NAME_BUT_WEAK_IDENTITY_OR_REVIEWS",
            score=82,
            risk_flags=risks,
        )

    if strong_non_nail and operational and identity:
        return LocalAssessment(
            rule_id="R_NON_NAIL_CATEGORY_STRONG",
            candidate_action="REMOVE",
            signal="EXPLICIT_NON_BEAUTY_CATEGORY_PLUS_STRUCTURED_LISTING",
            score=94,
            risk_flags=risks,
        )

    if strong_non_nail:
        return LocalAssessment(
            rule_id="R_NON_NAIL_CATEGORY_WEAK",
            candidate_action="REVIEW",
            signal="EXPLICIT_NON_BEAUTY_CATEGORY_BUT_WEAK_IDENTITY",
            score=80,
            risk_flags=risks,
        )

    if beauty:
        return LocalAssessment(
            rule_id="R_BEAUTY_AMBIGUOUS",
            candidate_action="REVIEW",
            signal="BEAUTY_BUSINESS_NAIL_SERVICE_UNKNOWN",
            score=55,
            risk_flags=risks,
        )

    return LocalAssessment(
        rule_id="R_UNKNOWN",
        candidate_action="REVIEW",
        signal="NO_HIGH_PRECISION_LOCAL_RULE",
        score=25,
        risk_flags=risks,
    )
