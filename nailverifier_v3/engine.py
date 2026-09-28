from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from .cache import CacheDB
from .consensus import resolve_consensus
from .evidence_classifier import (
    classify_live_evidence,
    classify_registry_evidence,
    heuristic_signal,
)
from .evidence_registry import EvidenceRegistry
from .features import LocalAssessment, assess_local
from .http import CachedHttpClient
from .models import BusinessRecord, Evidence
from .normalize import (
    detect_columns,
    normalize_phone,
    normalize_street,
    normalize_text,
    normalize_zip,
    record_identity,
    row_to_record,
    validate_mapping,
)
from .osm import OSMVerifier
from .policy import apply_evidence_policy
from .states.sd import SouthDakotaAdapter

ENGINE_VERSION = "3.7.0"

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
    """Legacy v3 decision fields retained for audit and rule prioritization."""
    official = next((e for e in evidence if e.strength == "STRONG_OFFICIAL"), None)
    osm_nail = next((e for e in evidence if e.strength == "STRONG_INDEPENDENT_NAIL"), None)
    osm_beauty = next((e for e in evidence if e.strength == "STRONG_INDEPENDENT_BEAUTY"), None)
    osm_not_nail = next((e for e in evidence if e.strength == "STRONG_INDEPENDENT_NOT_NAIL"), None)

    if local.rule_id == "R_STATUS_PERMANENTLY_CLOSED":
        return {
            "Decision": "CLOSED_PERMANENTLY",
            "Confidence": local.score,
            "Candidate_Action": "REMOVE",
            "Reason": "NailMap marks the business permanently closed. Removal stays evidence-gated.",
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
        if local.rule_id in {"R_NAIL_EXPLICIT_STRONG", "R_NAIL_EXPLICIT_ADDRESS_STRONG"} or osm_nail:
            return {
                "Decision": "LIKELY_NAIL",
                "Confidence": 96 if osm_nail else 93,
                "Candidate_Action": "KEEP",
                "Reason": "Official source verifies the beauty business identity and a separate nail-service signal is present.",
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
            "Reason": "Independent identity/location match indicates nail services; evidence policy decides automatic action.",
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
    if local.rule_id in {"R_NAIL_EXPLICIT_STRONG", "R_NAIL_EXPLICIT_ADDRESS_STRONG"}:
        return {
            "Decision": "LIKELY_NAIL",
            "Confidence": local.score,
            "Candidate_Action": "KEEP",
            "Reason": "Explicit nail-service name plus operational structured listing; this is a heuristic candidate, not business-specific verification.",
            "Evidence_Tier": "NAILMAP_STRUCTURED",
        }
    if local.rule_id in {"R_NAIL_EXPLICIT_WEAK", "R_NAIL_STYLING_HINT"}:
        return {
            "Decision": "LIKELY_NAIL",
            "Confidence": local.score,
            "Candidate_Action": "REVIEW",
            "Reason": "Business name indicates or hints at nail service, but identity/evidence is not strong enough for automatic action.",
            "Evidence_Tier": "NAILMAP_NAME_ONLY",
        }
    if local.rule_id in {"R_NON_NAIL_CATEGORY_STRONG", "R_NON_NAIL_CATEGORY_ADDRESS_STRONG"}:
        return {
            "Decision": "LIKELY_NOT_NAIL",
            "Confidence": local.score,
            "Candidate_Action": "REMOVE",
            "Reason": "Business name is a high-precision non-beauty category candidate; business-specific evidence is still required for removal.",
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
            "Reason": "No official verifier adapter is installed for this state; evidence-first policy remains REVIEW without verified evidence.",
            "Evidence_Tier": "LOCAL_ONLY",
        }

    reason = "Insufficient evidence for a precision-first nail-service decision."
    if source_errors:
        reason += " One or more verification sources returned an error; row was not auto-classified by that source."
    return {
        "Decision": "REVIEW",
        "Confidence": 20 if source_errors else max(30, local.score),
        "Candidate_Action": "REVIEW",
        "Reason": reason,
        "Evidence_Tier": "NONE",
    }


class VerificationEngine:
    def __init__(
        self,
        cache_path: str = ".cache/nail_verifier_v3.sqlite3",
        use_osm: bool = True,
        registry_path: str = "benchmarks/verified_business_evidence.csv",
    ):
        self.cache = CacheDB(cache_path)
        self.http = CachedHttpClient(self.cache)
        self.use_osm = use_osm
        self.osm = OSMVerifier(self.http) if use_osm else None
        self.registry = EvidenceRegistry(registry_path)
        self._adapters: Dict[str, Any] = {}

    def _adapter(self, state: str) -> Optional[Any]:
        state = (state or "").upper()
        cls = OFFICIAL_ADAPTERS.get(state)
        if not cls:
            return None
        if state not in self._adapters:
            self._adapters[state] = cls(self.http)
        return self._adapters[state]

    def _config_version(self) -> str:
        return "%s+registry:%s%s" % (
            ENGINE_VERSION,
            self.registry.version,
            "+osm" if self.use_osm else "+noosm",
        )

    def verify_record(self, record: BusinessRecord, force_refresh: bool = False) -> Dict[str, Any]:
        config_version = self._config_version()
        key = record_identity(record)
        if not force_refresh:
            cached = self.cache.get_verification(key, config_version)
            if cached is not None:
                cached["Cache_Hit"] = "YES"
                return cached

        local = assess_local(record)
        live_evidence: List[Evidence] = []
        source_errors: List[str] = []
        adapter = self._adapter(record.state)
        state_support = "OFFICIAL" if adapter else "UNSUPPORTED"

        if adapter:
            try:
                official = adapter.verify(record)
                if official:
                    live_evidence.append(official)
            except Exception as exc:
                source_errors.append("OFFICIAL_%s: %s" % (record.state or "STATE", exc))

        if self.osm:
            try:
                osm = self.osm.verify(record)
                if osm:
                    live_evidence.append(osm)
            except Exception as exc:
                source_errors.append("OPENSTREETMAP: %s" % exc)

        decision = decide(record, live_evidence, source_errors, state_support, local)
        legacy_dimensions = derive_dimensions(record, live_evidence, decision)

        registry_rows = self.registry.match(record)
        signals = classify_registry_evidence(registry_rows)
        signals.extend(classify_live_evidence(live_evidence))
        heuristic = heuristic_signal(local, record)
        if heuristic:
            signals.append(heuristic)

        consensus = resolve_consensus(signals).to_dict()
        policy = apply_evidence_policy(str(consensus["Verification_Status"]))

        result: Dict[str, Any] = {
            **decision,
            **policy,
            **legacy_dimensions,
            **local.to_dict(),
            **consensus,
            "Nail_Service": consensus["Nail_Service_Status"],
            "Policy_Profile": "EVIDENCE_FIRST_V1_COLLISION_GUARD",
            "State_Support": state_support,
            "Checked_At": utc_now(),
            "Cache_Hit": "NO",
            "Source_Errors": " | ".join(source_errors),
            "Registry_Evidence_Count": len(registry_rows),
            "Registry_Version": self.registry.version,
            **_flatten_evidence(live_evidence),
        }

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


def _collision_group_key(record: BusinessRecord) -> str:
    phone = normalize_phone(record.phone)
    street = normalize_street(record.street, drop_unit=True)
    if not phone or not street:
        return ""
    return "|".join(
        [
            phone,
            street,
            normalize_text(record.city),
            record.state.upper(),
            normalize_zip(record.zip_code),
        ]
    )


def _identity_collisions(records: List[BusinessRecord]) -> Dict[int, Dict[str, Any]]:
    buckets: Dict[str, List[int]] = defaultdict(list)
    for index, record in enumerate(records):
        key = _collision_group_key(record)
        if key:
            buckets[key].append(index)

    collisions: Dict[int, Dict[str, Any]] = {}
    for indexes in buckets.values():
        if len(indexes) < 2:
            continue
        normalized_names = {
            normalize_text(records[index].company)
            for index in indexes
            if normalize_text(records[index].company)
        }
        if len(normalized_names) < 2:
            continue
        names = sorted({records[index].company for index in indexes})
        display_names = " | ".join(names)
        for index in indexes:
            collisions[index] = {
                "Identity_Collision": "YES",
                "Collision_Group_Size": len(indexes),
                "Collision_Names": display_names,
            }
    return collisions


def _normalized_identity(record: BusinessRecord) -> Dict[str, str]:
    return {
        "Normalized_Street": normalize_street(record.street, drop_unit=False),
        "Normalized_City": normalize_text(record.city),
        "Normalized_ZIP": normalize_zip(record.zip_code),
        "Normalized_Phone": normalize_phone(record.phone),
    }


def _error_result(record: BusinessRecord, exc: Exception) -> Dict[str, Any]:
    local = assess_local(record)
    return {
        "Decision": "ERROR_REVIEW",
        "Confidence": 0,
        "Candidate_Action": "REVIEW",
        "Auto_Action": "REVIEW",
        "Policy_Status": "SOURCE_ERROR",
        "Policy_Profile": "EVIDENCE_FIRST_V1_COLLISION_GUARD",
        "Reason": str(exc),
        "Evidence_Tier": "ERROR",
        **local.to_dict(),
        "Business_Exists": "UNKNOWN",
        "Nail_Service": "UNKNOWN",
        "Verification_Status": "UNKNOWN",
        "Identity_Status": "UNKNOWN",
        "Existence_Status": "UNKNOWN",
        "Nail_Service_Status": "UNKNOWN",
        "Evidence_Source_Count": 0,
        "Strong_Evidence_Count": 0,
        "Evidence_Agrees": "",
        "Evidence_Conflicts": 0,
        "Primary_Source": "",
        "Primary_Source_Tier": "",
        "Primary_Source_URL": "",
        "Verification_Evidence": "",
        "Verification_Reason": "Verification failed before evidence consensus could complete.",
        "Verified_At": "",
        "Registry_Evidence_Count": 0,
        "Registry_Version": "",
        "State_Support": "UNKNOWN",
        "Checked_At": utc_now(),
        "Cache_Hit": "NO",
        "Source_Errors": str(exc),
        **_flatten_evidence([]),
    }


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
    collisions = _identity_collisions(records)

    rows: List[Dict[str, Any]] = []
    total = len(work)
    for pos, record in enumerate(records, start=1):
        try:
            result = verifier.verify_record(record, force_refresh=force_refresh)
        except Exception as exc:
            result = _error_result(record, exc)

        result.update(_normalized_identity(record))
        result["Exact_Record_Duplicate_Count"] = identity_counts[record_identity(record)]
        result["Shared_Address_Count"] = address_counts[_address_group_key(record)]

        collision = collisions.get(pos - 1)
        if collision:
            result.update(collision)
            if result.get("Auto_Action") in {"KEEP", "REMOVE"}:
                result["Auto_Action"] = "REVIEW"
                result["Policy_Status"] = "IDENTITY_COLLISION_REVIEW"
                prior_reason = str(result.get("Reason", "")).strip()
                collision_reason = (
                    "Same normalized phone and base address appear under multiple business names; "
                    "automatic action is blocked pending identity review."
                )
                result["Reason"] = (prior_reason + " " + collision_reason).strip()
                verification_reason = str(result.get("Verification_Reason", "")).strip()
                result["Verification_Reason"] = (
                    verification_reason + " " + collision_reason
                ).strip()
        else:
            result["Identity_Collision"] = "NO"
            result["Collision_Group_Size"] = 1
            result["Collision_Names"] = ""

        rows.append(result)
        if progress:
            progress(pos, total, record.company)

    verification = pd.DataFrame(rows, index=work.index)
    return pd.concat([work, verification], axis=1)
