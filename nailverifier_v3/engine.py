from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from .cache import CacheDB
from .http import CachedHttpClient
from .models import BusinessRecord, Evidence
from .normalize import (
    detect_columns,
    has_beauty_words,
    has_nail_words,
    normalize_text,
    record_identity,
    row_to_record,
    validate_mapping,
)
from .osm import OSMVerifier
from .states.sd import SouthDakotaAdapter

ENGINE_VERSION = "3.0.0"

OFFICIAL_ADAPTERS = {
    "SD": SouthDakotaAdapter,
}

NAIL_LICENSE_TERMS = {
    "nail salon",
    "nail shop",
    "manicuring salon",
}

BEAUTY_LICENSE_TERMS = {
    "cosmetology salon",
    "esthetics salon",
    "esthetic salon",
    "apprentice salon",
    "beauty salon",
}

OBVIOUS_NON_NAIL_PATTERNS = {
    "hardware",
    "restaurant",
    "grille",
    "grocery",
    "supermarket",
    "fuel",
    "gas station",
    "bank",
    "hotel",
    "motel",
    "church",
    "building center",
    "dollar general",
    "true value",
    "ace hardware",
    "auto parts",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _license_is_nail(value: str) -> bool:
    n = normalize_text(value)
    return any(term in n for term in NAIL_LICENSE_TERMS)


def _license_is_beauty(value: str) -> bool:
    n = normalize_text(value)
    return _license_is_nail(value) or any(term in n for term in BEAUTY_LICENSE_TERMS)


def _obvious_non_nail_name(value: str) -> bool:
    n = normalize_text(value)
    if has_nail_words(value) or has_beauty_words(value):
        return False
    return any(term in n for term in OBVIOUS_NON_NAIL_PATTERNS)


def _closed_status(value: str) -> Optional[str]:
    n = normalize_text(value)
    if "closed permanently" in n or "permanently closed" in n:
        return "CLOSED_PERMANENTLY"
    if "closed temporarily" in n or "temporarily closed" in n:
        return "TEMPORARILY_CLOSED"
    return None


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


def decide(record: BusinessRecord, evidence: List[Evidence], source_errors: List[str], state_support: str) -> Dict[str, Any]:
    closed = _closed_status(record.status)
    if closed == "CLOSED_PERMANENTLY":
        return {
            "Decision": "CLOSED_PERMANENTLY",
            "Confidence": 95,
            "Auto_Action": "REMOVE",
            "Reason": "NailMap source marks this business permanently closed.",
            "Evidence_Tier": "SOURCE_STATUS",
        }
    if closed == "TEMPORARILY_CLOSED":
        return {
            "Decision": "TEMPORARILY_CLOSED",
            "Confidence": 90,
            "Auto_Action": "REVIEW",
            "Reason": "NailMap source marks this business temporarily closed; do not permanently remove automatically.",
            "Evidence_Tier": "SOURCE_STATUS",
        }

    official = next((e for e in evidence if e.strength == "STRONG_OFFICIAL"), None)
    osm_nail = next((e for e in evidence if e.strength == "STRONG_INDEPENDENT_NAIL"), None)
    osm_beauty = next((e for e in evidence if e.strength == "STRONG_INDEPENDENT_BEAUTY"), None)
    osm_not_nail = next((e for e in evidence if e.strength == "STRONG_INDEPENDENT_NOT_NAIL"), None)

    if official and _license_is_nail(official.license_type):
        return {
            "Decision": "VERIFIED_NAIL",
            "Confidence": 99,
            "Auto_Action": "KEEP",
            "Reason": "Strict name/location match to a current official state business license whose license type is nail-specific.",
            "Evidence_Tier": "OFFICIAL_STATE",
        }

    if official and _license_is_beauty(official.license_type):
        if has_nail_words(record.company) or osm_nail:
            return {
                "Decision": "LIKELY_NAIL",
                "Confidence": 94 if osm_nail else 91,
                "Auto_Action": "KEEP_REVIEW_OPTIONAL",
                "Reason": "Business identity is verified by a current official beauty/salon license and the business has an independent or name-level nail signal.",
                "Evidence_Tier": "OFFICIAL_STATE_PLUS_NAIL_SIGNAL",
            }
        return {
            "Decision": "VERIFIED_BEAUTY_REVIEW_NAIL",
            "Confidence": 95,
            "Auto_Action": "REVIEW",
            "Reason": "The business is real and licensed as a beauty/salon business, but available evidence does not prove it offers nail services.",
            "Evidence_Tier": "OFFICIAL_STATE",
        }

    if osm_not_nail:
        return {
            "Decision": "VERIFIED_NOT_NAIL",
            "Confidence": 97,
            "Auto_Action": "REMOVE",
            "Reason": "Independent OpenStreetMap identity/location match classifies the same storefront as a definite non-beauty business.",
            "Evidence_Tier": "INDEPENDENT_OSM",
        }

    if osm_nail:
        return {
            "Decision": "LIKELY_NAIL",
            "Confidence": 90,
            "Auto_Action": "KEEP_REVIEW_OPTIONAL",
            "Reason": "Independent OpenStreetMap identity/location match indicates nail services, but no strict official nail-license match was available.",
            "Evidence_Tier": "INDEPENDENT_OSM",
        }

    if osm_beauty:
        return {
            "Decision": "VERIFIED_BEAUTY_REVIEW_NAIL",
            "Confidence": 88,
            "Auto_Action": "REVIEW",
            "Reason": "Independent source verifies the business as beauty-related, but nail services are not proven.",
            "Evidence_Tier": "INDEPENDENT_OSM",
        }

    has_identity = bool(record.phone and record.zip_code and (record.street or record.city))
    if has_nail_words(record.company) and normalize_text(record.status) == "operational" and has_identity and record.reviews >= 3:
        confidence = 78
        if record.reviews >= 10:
            confidence += 3
        if record.reviews >= 50:
            confidence += 2
        if record.rating >= 4.0:
            confidence += 2
        return {
            "Decision": "LIKELY_NAIL",
            "Confidence": min(confidence, 85),
            "Auto_Action": "REVIEW",
            "Reason": "NailMap has a strong nail-name, active listing, address/phone and reviews, but v3 found no independent strict verification.",
            "Evidence_Tier": "NAILMAP_ONLY",
        }

    if _obvious_non_nail_name(record.company):
        return {
            "Decision": "LIKELY_NOT_NAIL",
            "Confidence": 75,
            "Auto_Action": "REVIEW",
            "Reason": "Business name strongly suggests a non-nail category, but no independent identity/category source verified it in this run.",
            "Evidence_Tier": "NAME_HEURISTIC_ONLY",
        }

    if state_support == "UNSUPPORTED" and not evidence:
        return {
            "Decision": "UNSUPPORTED_STATE_REVIEW",
            "Confidence": 0,
            "Auto_Action": "REVIEW",
            "Reason": "No official verifier adapter is installed for this state yet and no strong independent evidence was found.",
            "Evidence_Tier": "NONE",
        }

    reason = "Insufficient evidence for a precision-first decision."
    if source_errors:
        reason += " One or more verification sources returned an error; row was not auto-classified."
    return {
        "Decision": "REVIEW",
        "Confidence": 20 if source_errors else 30,
        "Auto_Action": "REVIEW",
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

        decision = decide(record, evidence, source_errors, state_support)
        result: Dict[str, Any] = {
            **decision,
            "State_Support": state_support,
            "Checked_At": utc_now(),
            "Cache_Hit": "NO",
            "Source_Errors": " | ".join(source_errors),
            **_flatten_evidence(evidence),
        }

        if not source_errors:
            self.cache.set_verification(key, config_version, result)
        return result


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

    rows: List[Dict[str, Any]] = []
    total = len(work)
    for pos, (_, row) in enumerate(work.iterrows(), start=1):
        record = row_to_record(row, mapping)
        try:
            result = verifier.verify_record(record, force_refresh=force_refresh)
        except Exception as exc:
            result = {
                "Decision": "ERROR_REVIEW",
                "Confidence": 0,
                "Auto_Action": "REVIEW",
                "Reason": str(exc),
                "Evidence_Tier": "ERROR",
                "State_Support": "UNKNOWN",
                "Checked_At": utc_now(),
                "Cache_Hit": "NO",
                "Source_Errors": str(exc),
            }
        rows.append(result)
        if progress:
            progress(pos, total, record.company)

    verification = pd.DataFrame(rows, index=work.index)
    return pd.concat([work, verification], axis=1)
