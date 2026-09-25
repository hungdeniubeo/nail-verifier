from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
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
    for idx, tr in enumerate(trs[:5]):
        cells = tr.find_all(["th", "td"], recursive=False)
        values = [clean(cell.get_text(" ", strip=True)) for cell in cells]
        norm = {normalize_text(value) for value in values}
        joined = " ".join(norm)
        if "license" in joined and ("company" in joined or "business" in joined):
            return values, trs[idx + 1 :]
    return [], []


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
            license_no = field(item, "license")
            if license_no:
                out.append(item)
        if out:
            break
    return out


def parse_detail(html: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    detail: Dict[str, str] = {}
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if len(cells) < 2:
            continue
        key = clean(cells[0].get_text(" ", strip=True)).rstrip(":")
        value = clean(cells[1].get_text(" ", strip=True))
        if key and value:
            detail[key] = value
    return detail


def field(item: Dict[str, str], needle: str) -> str:
    n = normalize_text(needle)
    for key, value in item.items():
        if key.startswith("_"):
            continue
        nk = normalize_text(key)
        if n == nk or n in nk:
            return clean(value)
    return ""


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


def _is_strong_match(record: BusinessRecord, roster: Dict[str, str], detail: Dict[str, str]) -> Tuple[bool, float, float, str]:
    candidate_name = field(detail, "business") or _company(roster)
    name_match = compare_names(record.company, candidate_name)

    candidate_street = field(detail, "street")
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

    if not name_match.exact:
        if name_match.target_core and name_match.candidate_core and name_match.core_overlap < 0.50:
            return False, name_match.score, address_match.score, "discriminating name tokens do not match"
        if name_match.score < 0.90:
            return False, name_match.score, address_match.score, "name match below strict threshold"

    zip_match = address_match.zip_match
    city_match = address_match.city_match

    if record.street and candidate_street:
        location_ok = address_match.street_score >= 0.82 and (zip_match is not False) and (city_match is not False)
    else:
        location_ok = name_match.exact and (zip_match is True or city_match is True)

    if not location_ok:
        return False, name_match.score, address_match.score, "location did not meet strict threshold"

    return True, name_match.score, address_match.score, "strict official match"


class SouthDakotaAdapter:
    state = "SD"
    support = "OFFICIAL"

    def __init__(self, http: CachedHttpClient):
        self.http = http
        self._roster: Optional[List[Dict[str, str]]] = None

    def _load_roster(self) -> List[Dict[str, str]]:
        if self._roster is not None:
            return self._roster
        html = self.http.get_text(
            ROSTER_URL,
            cache_key="sd:business-roster",
            ttl_seconds=24 * 3600,
        )
        roster = parse_roster(html)
        if not roster:
            raise RuntimeError("South Dakota public business license roster could not be parsed")
        self._roster = roster
        return roster

    def _detail(self, item: Dict[str, str]) -> Dict[str, str]:
        license_no = _license_no(item)
        url = item.get("_detail_url") or DETAIL_TEMPLATE.format(license_no=license_no)
        if not license_no and not url:
            return {}
        html = self.http.get_text(
            url,
            cache_key="sd:detail:" + (license_no or url),
            ttl_seconds=24 * 3600,
        )
        detail = parse_detail(html)
        detail["_source_url"] = url
        return detail

    def verify(self, record: BusinessRecord) -> Optional[Evidence]:
        roster = self._load_roster()
        candidates: List[Tuple[float, Dict[str, str]]] = []
        target_zip = normalize_zip(record.zip_code)
        target_city = normalize_text(record.city)

        for item in roster:
            candidate_zip = normalize_zip(field(item, "zip"))
            candidate_city = normalize_text(field(item, "city"))
            if target_zip:
                if candidate_zip != target_zip:
                    continue
            elif target_city:
                if candidate_city != target_city:
                    continue
            else:
                continue

            nm = compare_names(record.company, _company(item))
            if nm.exact or nm.score >= 0.78:
                candidates.append((nm.score, item))

        candidates.sort(key=lambda pair: pair[0], reverse=True)
        for _, item in candidates[:6]:
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
