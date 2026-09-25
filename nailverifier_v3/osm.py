from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from .http import CachedHttpClient
from .models import BusinessRecord, Evidence
from .normalize import compare_addresses, compare_names, has_nail_words, normalize_text

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

BEAUTY_TYPES = {"beauty", "hairdresser", "cosmetics", "spa"}

DEFINITE_NON_BEAUTY_TYPES = {
    "hardware",
    "supermarket",
    "convenience",
    "restaurant",
    "fast_food",
    "fuel",
    "hotel",
    "motel",
    "place_of_worship",
    "bank",
    "car_repair",
    "car_parts",
    "department_store",
    "variety_store",
    "doityourself",
}


def _candidate_name(item: Dict[str, Any]) -> str:
    namedetails = item.get("namedetails") or {}
    if isinstance(namedetails, dict) and namedetails.get("name"):
        return str(namedetails.get("name"))
    if item.get("name"):
        return str(item.get("name"))
    display = str(item.get("display_name") or "")
    return display.split(",", 1)[0].strip()


def _candidate_address(item: Dict[str, Any]) -> Tuple[str, str, str]:
    address = item.get("address") or {}
    house = str(address.get("house_number") or "").strip()
    road = str(address.get("road") or address.get("pedestrian") or address.get("footway") or "").strip()
    street = " ".join(part for part in [house, road] if part)
    city = str(
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or ""
    ).strip()
    zip_code = str(address.get("postcode") or "").strip()
    return street, city, zip_code


def _type_text(item: Dict[str, Any]) -> str:
    extras = item.get("extratags") or {}
    values = [
        str(item.get("category") or ""),
        str(item.get("type") or ""),
        str(extras.get("beauty") or ""),
        str(extras.get("shop") or ""),
        str(extras.get("service") or ""),
    ]
    return " / ".join(value for value in values if value)


def _nail_signal(item: Dict[str, Any], candidate_name: str) -> bool:
    extras = item.get("extratags") or {}
    haystack = " ".join(
        [
            candidate_name,
            str(item.get("type") or ""),
            str(extras.get("beauty") or ""),
            str(extras.get("service") or ""),
        ]
    )
    normalized = normalize_text(haystack)
    return has_nail_words(haystack) or "manicure" in normalized or "pedicure" in normalized


def _beauty_signal(item: Dict[str, Any]) -> bool:
    typ = normalize_text(item.get("type"))
    extras = item.get("extratags") or {}
    beauty = normalize_text(extras.get("beauty"))
    return typ in BEAUTY_TYPES or bool(beauty)


def _definite_non_beauty(item: Dict[str, Any]) -> bool:
    return normalize_text(item.get("type")) in DEFINITE_NON_BEAUTY_TYPES


class OSMVerifier:
    def __init__(self, http: CachedHttpClient):
        self.http = http

    def _search(self, record: BusinessRecord) -> List[Dict[str, Any]]:
        query = ", ".join(
            value
            for value in [record.company, record.street, record.city, record.state, record.zip_code]
            if value
        )
        cache_key = "osm:" + normalize_text(query)
        body = self.http.get_text(
            NOMINATIM_URL,
            cache_key=cache_key,
            ttl_seconds=30 * 24 * 3600,
            min_interval_seconds=1.05,
            params={
                "q": query,
                "format": "jsonv2",
                "addressdetails": "1",
                "extratags": "1",
                "namedetails": "1",
                "limit": "5",
                "countrycodes": "us",
            },
        )
        data = json.loads(body)
        return data if isinstance(data, list) else []

    def verify(self, record: BusinessRecord) -> Optional[Evidence]:
        best: Optional[Tuple[float, Dict[str, Any], float, float]] = None
        for item in self._search(record):
            name = _candidate_name(item)
            name_match = compare_names(record.company, name)
            street, city, zip_code = _candidate_address(item)
            address_match = compare_addresses(
                record.street,
                record.city,
                record.zip_code,
                street,
                city,
                zip_code,
            )

            if address_match.street_number_match is False:
                continue
            if not name_match.exact:
                if name_match.target_core and name_match.candidate_core and name_match.core_overlap < 0.50:
                    continue
                if name_match.score < 0.88:
                    continue
            if address_match.score < 0.72:
                continue

            combined = 0.60 * name_match.score + 0.40 * address_match.score
            if best is None or combined > best[0]:
                best = (combined, item, name_match.score, address_match.score)

        if best is None:
            return None

        _, item, name_score, address_score = best
        name = _candidate_name(item)
        display = str(item.get("display_name") or "")
        type_text = _type_text(item)
        if _nail_signal(item, name):
            strength = "STRONG_INDEPENDENT_NAIL"
        elif _beauty_signal(item):
            strength = "STRONG_INDEPENDENT_BEAUTY"
        elif _definite_non_beauty(item):
            strength = "STRONG_INDEPENDENT_NOT_NAIL"
        else:
            strength = "INDEPENDENT_IDENTITY_ONLY"

        return Evidence(
            source="OPENSTREETMAP",
            strength=strength,
            matched_name=name,
            matched_address=display,
            category=type_text,
            status="LISTED",
            source_url="https://www.openstreetmap.org/" + str(item.get("osm_type") or "") + "/" + str(item.get("osm_id") or ""),
            name_score=round(name_score * 100, 1),
            address_score=round(address_score * 100, 1),
            notes="OpenStreetMap independent identity/category match",
            raw=item,
        )
