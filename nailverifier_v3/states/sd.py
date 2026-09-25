from __future__ import annotations

from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http import CachedHttpClient
from ..models import BusinessRecord, Evidence
from ..normalize import clean, compare_addresses, compare_names, normalize_text, normalize_zip

ROSTER_URL = "https://apps.sd.gov/LD19Cosmetology/LicenseListing.aspx?s=SD&t=b"
DETAIL_BASE = "https://apps.sd.gov/LD19Cosmetology/"
DETAIL_TEMPLATE = "https://apps.sd.gov/LD19Cosmetology/LicenseDetail.aspx?l={license_no}&t=b"


def _headers_and_rows(table: Any) -> Tuple[List[str], List[Any]]:
    trs = table.find_all("tr")
    if not trs:
        return [], []
    for idx, tr in enumerate(trs[:6]):
        cells = tr.find_all(["th", "td"], recursive=False)
        values = [clean(cell.get_text(" ", strip=True)) for cell in cells]
        joined = " ".join(normalize_text(value) for value in values)
        if "license" in joined and ("company" in joined or "business" in joined):
            return values, trs[idx + 1 :]
    return [], []


def field(item: Dict[str, str], needle: str) -> str:
    n = normalize_text(needle)
    for key, value in item.items():
        if key.startswith("_"):
            continue
        nk = normalize_text(key)
        if n == nk or n in nk:
            return clean(value)
    return ""


def parse_roster(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict[str, str]] = []
    for table in soup.find_all("table"):
        headers, rows = _headers_and_rows(table)
        if not headers:
            continue
        for tr in rows:
            cells = tr.find_all(["th", "td"], recursive=False)
            values = [clean(cell.get_text(" ", strip=True)) for cell in cells]
            if not values or len(values) < 3:
                continue
            padded = values + [""] * max(0, len(headers) - len(values))
            item = {headers[i]: padded[i] for i in range(min(len(headers), len(padded)))}
            item["_raw"] = " | ".join(values)
            link = tr.find("a", href=True)
            if link:
                item["_detail_url"] = urljoin(DETAIL_BASE, link["href"])
            if _license_no(item):
                out.append(item)
        if out:
            break
    return out


def parse_detail(html: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    detail: Dict[str, str] = {}

    # Most state detail pages are rendered as two-column rows.
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if len(cells) < 2:
            continue
        key = clean(cells[0].get_text(" ", strip=True)).rstrip(":")
        value = clean(cells[1].get_text(" ", strip=True))
        if key and value:
            detail[key] = value

    # Fallback for label/value elements that are not direct table children.
    if not detail:
        labels = soup.find_all(["label", "span", "strong"])
        for label in labels:
            key = clean(label.get_text(" ", strip=True)).rstrip(":")
            if not key:
                continue
            sibling = label.find_next(["span", "td"])
            if sibling and sibling is not label:
                value = clean(sibling.get_text(" ", strip=True))
                if value and value != key:
                    detail[key] = value
    return detail


def _company(item: Dict[str, str]) -> str:
    return field(item, "company") or field(item, "business") or field(item, "name")


def _license_no(item: Dict[str, str]) -> str:
    return field(item, "license #") or field(item, "license")


def _license_type(detail: Dict[str, str]) -> str:
    return field(detail, "license type") or field(detail, "type")


def _detail_address(detail: Dict[str, str]) -> str:
    return ", ".join(
        value
        for value in [
            field(detail, "street"),
            field(detail, "city"),
            field(detail, "state"),
            field(detail, "zip"),
        ]
        if value
    )


def _distinctive_overlap_ok(record: BusinessRecord, candidate_name: str) -> bool:
    nm = compare_names(record.company, candidate_name)
    if nm.exact:
        return True
    target = set(nm.target_core)
    candidate = set(nm.candidate_core)
    if not target or not candidate:
        return False
    shared = target & candidate
    if not shared:
        return False
    return nm.core_overlap >= 0.50


def _is_strong_match(
    record: BusinessRecord,
    roster: Dict[str, str],
    detail: Dict[str, str],
) -> Tuple[bool, float, float, str]:
    candidate_name = field(detail, "business") or _company(roster)
    name_match = compare_names(record.company, candidate_name)

    if not _distinctive_overlap_ok(record, candidate_name):
        return False, name_match.score, 0.0, "distinctive business-name tokens do not match"

    candidate_street = field(detail, "street") or field(detail, "address")
    candidate_city = field(detail, "city") or field(roster, "city")
    candidate_zip = field(detail, "zip") or field(roster, "zip")
    address_match = compare_addresses(
        record.street,
        record.city,
        record.zip_code,
        candidate_street,
        candidate_city,
        candidate_zip,
    )

    if address_match.street_number_match is False:
        return False, name_match.score, address_match.score, "street number mismatch"

    # If both sides expose street data, address identity is the strongest guard.
    if record.street and candidate_street:
        if address_match.street_score < 0.82:
            return False, name_match.score, address_match.score, "street match below strict threshold"
        if address_match.zip_match is False or address_match.city_match is False:
            return False, name_match.score, address_match.score, "city/ZIP conflict"
        # Non-exact names may be legal/DBA variants, but must share distinctive tokens.
        if not name_match.exact and name_match.core_overlap < 0.50:
            return False, name_match.score, address_match.score, "name identity too weak"
        return True, name_match.score, address_match.score, "strict distinctive-name + street match"

    # Missing detail street: only exact business names are safe enough to accept.
    if name_match.exact and (address_match.zip_match is True or address_match.city_match is True):
        return True, name_match.score, address_match.score, "exact name + city/ZIP fallback"

    return False, name_match.score, address_match.score, "detail page lacks enough location evidence"


class SouthDakotaAdapter:
    state = "SD"
    support = "OFFICIAL_BATCH"

    def __init__(self, http: CachedHttpClient):
        self.http = http
        self._roster: Optional[List[Dict[str, str]]] = None
        self._by_zip: DefaultDict[str, List[Dict[str, str]]] = defaultdict(list)
        self._by_city: DefaultDict[str, List[Dict[str, str]]] = defaultdict(list)

    def _build_indexes(self, roster: List[Dict[str, str]]) -> None:
        self._by_zip.clear()
        self._by_city.clear()
        for item in roster:
            zip_code = normalize_zip(field(item, "zip"))
            city = normalize_text(field(item, "city"))
            if zip_code:
                self._by_zip[zip_code].append(item)
            if city:
                self._by_city[city].append(item)

    def _load_roster(self) -> List[Dict[str, str]]:
        if self._roster is not None:
            return self._roster
        html = self.http.get_text(
            ROSTER_URL,
            cache_key="sd:business-roster:v31",
            ttl_seconds=24 * 3600,
        )
        roster = parse_roster(html)
        if not roster:
            raise RuntimeError("South Dakota public business license roster could not be parsed")
        self._roster = roster
        self._build_indexes(roster)
        return roster

    def warmup(self) -> Dict[str, int]:
        roster = self._load_roster()
        return {
            "roster_rows": len(roster),
            "zip_buckets": len(self._by_zip),
            "city_buckets": len(self._by_city),
        }

    def _detail(self, item: Dict[str, str]) -> Dict[str, str]:
        license_no = _license_no(item)
        url = item.get("_detail_url") or DETAIL_TEMPLATE.format(license_no=license_no)
        if not license_no and not url:
            return {}
        html = self.http.get_text(
            url,
            cache_key="sd:detail:v31:" + (license_no or url),
            ttl_seconds=7 * 24 * 3600,
        )
        detail = parse_detail(html)
        detail["_source_url"] = url
        return detail

    def _candidate_pool(self, record: BusinessRecord) -> List[Dict[str, str]]:
        self._load_roster()
        zip_code = normalize_zip(record.zip_code)
        city = normalize_text(record.city)
        if zip_code and self._by_zip.get(zip_code):
            return list(self._by_zip[zip_code])
        if city and self._by_city.get(city):
            return list(self._by_city[city])
        return []

    def verify(self, record: BusinessRecord) -> Optional[Evidence]:
        candidates: List[Tuple[float, Dict[str, str]]] = []

        for item in self._candidate_pool(record):
            candidate_name = _company(item)
            nm = compare_names(record.company, candidate_name)
            distinctive_ok = _distinctive_overlap_ok(record, candidate_name)
            if nm.exact or nm.score >= 0.78 or distinctive_ok:
                # Distinctive overlap gets a floor so DBA/legal name variants reach detail validation.
                rank = max(nm.score, 0.80 if distinctive_ok else 0.0)
                candidates.append((rank, item))

        candidates.sort(key=lambda pair: pair[0], reverse=True)

        # Only a small shortlist needs a detail-page request; each detail is cached.
        for _, item in candidates[:8]:
            detail = self._detail(item)
            strong, name_score, address_score, note = _is_strong_match(record, item, detail)
            if not strong:
                continue

            matched_name = field(detail, "business") or _company(item)
            license_no = field(detail, "license #") or _license_no(item)
            license_type = _license_type(detail)
            expires = field(detail, "expires") or field(item, "expires")
            source_url = detail.get("_source_url", "")
            return Evidence(
                source="SD_COSMETOLOGY",
                strength="STRONG_OFFICIAL",
                matched_name=matched_name,
                matched_address=_detail_address(detail),
                category=license_type,
                status="CURRENT",
                license_number=license_no,
                license_type=license_type,
                expires=expires,
                source_url=source_url,
                name_score=round(name_score * 100, 1),
                address_score=round(address_score * 100, 1),
                notes=note,
                raw={"roster": item, "detail": detail},
            )

        return None
