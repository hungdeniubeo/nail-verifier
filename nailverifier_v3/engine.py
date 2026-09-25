from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from .cache import CacheDB
from .features import LocalAssessment, assess_local
from .http import CachedHttpClient
from .models import BusinessRecord, Evidence
from .normalize import (
    detect_columns,
    has_nail_words,
    normalize_street,
    normalize_text,
    normalize_zip,
    record_identity,
    row_to_record,
    validate_mapping,
)
from .osm import OSMVerifier
from .policy import apply_policy
from .states.sd import SouthDakotaAdapter

ENGINE_VERSION = "3.2.0"

OFFICIAL_ADAPTERS = {
    "SD": SouthDakotaAdapter,
}

NAIL_LICENSE_TERMS = {
    "nail salon",
    "nail shop",
    "manicuring salon",
    "nail technology salon",
}

BEAUTY_LICENSE_TERMS = {
    "cosmetology salon",
    "esthetics salon",
    "esthetic salon",
    "apprentice salon",
    "beauty salon",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _license_is_nail(value: str) -> bool:
    n = normalize_text(value)
    return any(term in n for term in NAIL_LICENSE_TERMS)


def _license_is_beauty(value: str) -> bool:
    n = normalize_text(value)
    return _license_is_nail(value) or any(term in n for term in BEAUTY_LICENSE_TERMS)


def _flatten_evidence(evidence: List[Evidence]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "Official_Source": "",
        "Official_Matched_Name": "",
        "Official_Matched_Address": "",
        "Official_License": "",
        "Official_License_Type": "",
        "Official_Expires": "",
        "Official_URL": "",
        "Official_Name_Score": "",
        "Official_Address_Score": "",
        "OSM_Matched_Name": "",
        "OSM_Matched_Address": "",
        "OSM_Category": "",
        "OSM_URL": "",
        "OSM_Name_Score": "",
        "OSM_Address_Score": "",
        "Evidence_JSON": json.dumps([item.to_dict() for item in evidence], ensure_ascii=False),
    }

    for item in evidence:
        if item.source.endswith("COSMETOLOGY") and not out["Official_Source"]:
            out.update(
                {
                    "Official_Source": item.source,
                    "Official_Matched_Name": item.matched_name,
                    "Official_Matched_Address": item.matched_address,
                    "Official_License": item.license_number,
                    "Official_License_Type": item.license_type,
                    "Official_Expires": item.expires,
                    "Official_URL": item.source_url,
                    "Official_Name_Score": item.name_score,
                    "Official_Address_Score": item.address_score,
                }
            )
        elif item.source == "OPENSTREETMAP" and not out["OSM_Matched_Name"]:
            out.update(
                {
                    "OSM_Matched_Name": item.matched_name,
                    "OSM_Matched_Address": item.matched_address,
                    "OSM_Category": item.category,
                    "OSM_URL": item.source_url,
                    "OSM_Name_Score": item.name_score,
                    "OSM_Address_Score": item.address_score,
                }
            )
    return out


def derive_dimensions(
    record: BusinessRecord,
    evidence: List[Evidence],
    decision: Dict[str, Any],
) -> Dict[str, str]:
    official = next((e for e in evidence if e.strength == "STRONG_OFFICIAL"), None)
    independent_identity = next(
        (
            e
            for e in evidence
            if e.source == "OPENSTREETMAP"
            and e.strength
            in {
                "STRONG_INDEPENDENT_NAIL",
                "STRONG_INDEPENDENT_BEAUTY",
                "STRONG_INDEPENDENT_NOT_NAIL",
                "INDEPENDENT_IDENTITY_ONLY",
            }
        ),
        None,
    )

    d = decision.get("Decision", "")
    if d == "CLOSED_PERMANENTLY":
        exists = "CLOSED"
    elif official or independent_identity:
        exists = "VERIFIED_EXISTS"
    elif normalize_text(record.status) == "operational" and record.phone and record.zip_code:
        exists = "LIKELY_EXISTS"
    else:
        exists = "UNKNOWN"

    if d == "VERIFIED_NAIL":
        nail = "VERIFIED_NAIL"
    elif d == "LIKELY_NAIL":
        nail = "LIKELY_NAIL"
    elif d == "VERIFIED_NOT_NAIL":
        nail = "VERIFIED_NOT_NAIL"
    elif d == "LIKELY_NOT_NAIL":
        nail = "LIKELY_NOT_NAIL"
    elif d == "VERIFIED_BEAUTY_REVIEW_NAIL":
        nail = "UNKNOWN_NAIL_SERVICE"
    else:
        nail = "UNKNOWN"

    return {"Business_Exists": exists, "Nail_Service": nail}


def decide(
    record: BusinessRecord,
    evidence: List[Evidence],
    source_errors: List[str],
    state_support: str,
    local: LocalAssessment,
) -> Dict[str, Any]:
    official = next((e for e in evidence if e.strength == "STRONG_OFFICIAL"), None)
    osm_nail = next((e for e in evidence if e.strength == "STRONG_INDEPENDENT_NAIL"), None)
    osm_beauty = next((e for e in evidence if e.strength == "STRONG_INDEPENDENT_BEAUTY"), None)
    osm_not_nail = next((e for e in evidence if e.strength == "STRONG_INDEPENDENT_NOT_NAIL"), None)

    if local.rule_id == "R_STATUS_PERMANENTLY_CLOSED":
        return {
            "Decision": "CLOSED_PERMANENTLY",
            "Confidence": local.score,
            "Candidate_Action": "REMOVE",
            "Reason": "NailMap marks the business permanently closed. V3.2 treats this as a removal candidate, not an automatic removal, until the rule is benchmark-validated.",
            "Evidence_Tier": "SOURCE_STATUS",
        }

    if local.rule_id == "R_STATUS_TEMPORARILY_CLOSED":
        return {
            "Decision": "TEMPORARILY_CLOSED",
            "Confidence": local.score,
            "Candidate_Action": "REVIEW",
            "Reason": "NailMap marks the business temporarily closed; permanent removal is not allowed.",
            "Evidence_Tier": "SOURCE_STATUS",
        }

    if official and _license_is_nail(official.license_type):
        return {
            "Decision": "VERIFIED_NAIL",
            "Confidence": 99,
            "Candidate_Action": "KEEP",
            "Reason": "Strict identity/location match to a current official state license whose license type is nail-specific.",
            "Evidence_Tier": "OFFICIAL_STATE",
        }

    if official and _license_is_beauty(official.license_type):
        if local.rule_id == "R_NAIL_EXPLICIT_STRONG" or osm_nail:
            return {
                "Decision": "LIKELY_NAIL",
                "Confidence": 96 if osm_nail else 93,
                "Candidate_Action": "KEEP",
                "Reason": "Official source verifies the beauty business identity, and a separate nail-service signal is present. Candidate KEEP still requires policy validation unless the license itself is nail-specific.",
                "Evidence_Tier": "OFFICIAL_STATE_PLUS_NAIL_SIGNAL",
            }
        return {
            "Decision": "VERIFIED_BEAUTY_REVIEW_NAIL",
            "Confidence": 95,
            "Candidate_Action": "REVIEW",
            "Reason": "Official source verifies a real beauty/salon business, but available evidence does not prove nail services.",
            "Evidence_Tier": "OFFICIAL_STATE",
        }

    if osm_not_nail:
        return {
            "Decision": "VERIFIED_NOT_NAIL",
            "Confidence": 97,
            "Candidate_Action": "REMOVE",
            "Reason": "Independent identity/location match classifies the same storefront as a definite non-beauty business.",
            "Evidence_Tier": "INDEPENDENT_OSM",
        }

    if osm_nail:
        return {
            "Decision": "LIKELY_NAIL",
            "Confidence": 92,
            "Candidate_Action": "KEEP",
            "Reason": "Independent identity/location match indicates nail services; candidate KEEP remains benchmark-gated.",
            "Evidence_Tier": "INDEPENDENT_OSM",
        }

    if osm_beauty:
        return {
            "Decision": "VERIFIED_BEAUTY_REVIEW_NAIL",
            "Confidence": 88,
            "Candidate_Action": "REVIEW",
            "Reason": "Independent source verifies a beauty-related business, but nail services are not proven.",
            "Evidence_Tier": "INDEPENDENT_OSM",
        }

    if local.rule_id == "R_NAIL_EXPLICIT_STRONG":
        return {
            "Decision": "LIKELY_NAIL",
            "Confidence": local.score,
            "Candidate_Action": "KEEP",
            "Reason": "Explicit nail-service name plus operational structured listing (address/ZIP/phone/reviews). This is a high-precision local candidate, but not independent verification.",
            "Evidence_Tier": "NAILMAP_STRUCTURED",
        }

    if local.rule_id == "R_NAIL_EXPLICIT_WEAK":
        return {
            "Decision": "LIKELY_NAIL",
            "Confidence": local.score,
            "Candidate_Action": "REVIEW",
            "Reason": "Business name explicitly indicates nail service, but identity/review signals are incomplete.",
            "Evidence_Tier": "NAILMAP_NAME_ONLY",
        }

    if local.rule_id == "R_NON_NAIL_CATEGORY_STRONG":
        return {
            "Decision": "LIKELY_NOT_NAIL",
            "Confidence": local.score,
            "Candidate_Action": "REMOVE",
            "Reason": "Business name is a high-precision non-beauty category and the listing has structured identity data. Removal remains benchmark-gated.",
            "Evidence_Tier": "NAILMAP_STRUCTURED",
        }

    if local.rule_id == "R_NON_NAIL_CATEGORY_WEAK":
        return {
            "Decision": "LIKELY_NOT_NAIL",
            "Confidence": local.score,
            "Candidate_Action": "REVIEW",
            "Reason": "Business name strongly suggests a non-beauty category, but identity data is incomplete.",
            "Evidence_Tier": "NAILMAP_NAME_ONLY",
        }

    if state_support == "UNSUPPORTED" and not evidence:
        return {
            "Decision": "UNSUPPORTED_STATE_REVIEW",
            "Confidence": local.score,
            "Candidate_Action": "REVIEW",
            "Reason": "No official verifier adapter is installed for this state and no benchmark-safe local rule can auto-act.",
            "Evidence_Tier": "LOCAL_ONLY",
        }

    reason = "Insufficient evidence for a precision-first nail-service decision."
    if source_errors:
        reason += " One or more verification sources returned an error; row was not auto-classified."
    return {
        "Decision": "REVIEW",
        "Confidence": 20 if source_errors else max(30, local.score),
        "Candidate_Action": "REVIEW",
        "Reason": reason,
        "Evidence_Tier": "NONE",
    }


class VerificationEngine:
    def __init__(self, cache_path: str = ".cache/nail_verifier_v3.sqlite3", use_osm: bool = True):
        self.cache = CacheDB(cache_path)
        self.http = CachedHttpClient(self.cache)
        self.use_osm = use_osm
        self.osm = OSMVerifier(self.http) if use_osm else None
        self._adapters: Dict[str, Any] = {}

    def _adapter(self, state: str) -> Optional[Any]:
        state = (state or "").upper()
        cls = OFFICIAL_ADAPTERS.get(state)
        if not cls:
            return None
        if state not in self._adapters:
            self._adapters[state] = cls(self.http)
        return self._adapters[state]

    def verify_record(self, record: BusinessRecord, force_refresh: bool = False) -> Dict[str, Any]:
        config_version = ENGINE_VERSION + ("+osm" if self.use_osm else "+noosm")
        key = record_identity(record)
        if not force_refresh:
            cached = self.cache.get_verification(key, config_version)
            if cached is not None:
                cached["Cache_Hit"] = "YES"
                return cached

        local = assess_local(record)
        evidence: List[Evidence] = []
        source_errors: List[str] = []
        adapter = self._adapter(record.state)
        state_support = "OFFICIAL" if adapter else "UNSUPPORTED"

        if adapter:
            try:
                official = adapter.verify(record)
                if official:
                    evidence.append(official)
            except Exception as exc:
                source_errors.append("OFFICIAL_%s: %s" % (record.state or "STATE", exc))

        if self.osm:
            try:
                osm = self.osm.verify(record)
                if osm:
                    evidence.append(osm)
            except Exception as exc:
                source_errors.append("OPENSTREETMAP: %s" % exc)

        decision = decide(record, evidence, source_errors, state_support, local)
        policy = apply_policy(
            record.state,
            decision["Decision"],
            decision["Evidence_Tier"],
            local.rule_id,
            decision["Candidate_Action"],
        )
        dimensions = derive_dimensions(record, evidence, decision)

        result: Dict[str, Any] = {
            **decision,
            **policy,
            **dimensions,
            **local.to_dict(),
            "State_Support": state_support,
            "Checked_At": utc_now(),
            "Cache_Hit": "NO",
            "Source_Errors": " | ".join(source_errors),
            **_flatten_evidence(evidence),
        }

        # Do not cache source failures so a later run can retry.
        if not source_errors:
            self.cache.set_verification(key, config_version, result)
        return result


def _address_group_key(record: BusinessRecord) -> str:
    return "|".join(
        [
            normalize_street(record.street, drop_unit=False),
            normalize_text(record.city),
            record.state.upper(),
            normalize_zip(record.zip_code),
        ]
    )


def verify_dataframe(
    df: pd.DataFrame,
    limit: Optional[int] = None,
    progress: Optional[Callable[[int, int, str], None]] = None,
    use_osm: bool = True,
    force_refresh: bool = False,
    cache_path: str = ".cache/nail_verifier_v3.sqlite3",
    engine: Optional[VerificationEngine] = None,
) -> pd.DataFrame:
    mapping = detect_columns(df.columns)
    validate_mapping(mapping)
    work = df.head(limit).copy() if limit else df.copy()
    verifier = engine or VerificationEngine(cache_path=cache_path, use_osm=use_osm)

    records = [row_to_record(row, mapping) for _, row in work.iterrows()]
    identity_counts = Counter(record_identity(record) for record in records)
    address_counts = Counter(_address_group_key(record) for record in records)

    rows: List[Dict[str, Any]] = []
    total = len(work)

    for pos, record in enumerate(records, start=1):
        try:
            result = verifier.verify_record(record, force_refresh=force_refresh)
        except Exception as exc:
            local = assess_local(record)
            result = {
                "Decision": "ERROR_REVIEW",
                "Confidence": 0,
                "Candidate_Action": "REVIEW",
                "Auto_Action": "REVIEW",
                "Policy_Status": "SOURCE_ERROR",
                "Reason": str(exc),
                "Evidence_Tier": "ERROR",
                **local.to_dict(),
                "Business_Exists": "UNKNOWN",
                "Nail_Service": "UNKNOWN",
                "State_Support": "UNKNOWN",
                "Checked_At": utc_now(),
                "Cache_Hit": "NO",
                "Source_Errors": str(exc),
            }

        result["Exact_Record_Duplicate_Count"] = identity_counts[record_identity(record)]
        result["Shared_Address_Count"] = address_counts[_address_group_key(record)]
        rows.append(result)

        if progress:
            progress(pos, total, record.company)

    verification = pd.DataFrame(rows, index=work.index)
    return pd.concat([work, verification], axis=1)
