from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Union
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

SD_LICENSE_URL = "https://apps.sd.gov/ld19cosmetology/licenseverification.aspx"
SD_BUSINESS_ROSTER_URL = "https://apps.sd.gov/LD19Cosmetology/LicenseListing.aspx?s=SD&t=b"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "NailVerifier/2.0 (https://github.com/hungdeniubeo/nail-verifier)"

COLUMN_ALIASES = {
    "company": ["company", "business", "business name", "business_name", "name", "salon", "salon name"],
    "street": ["street", "address", "address 1", "address1", "street address"],
    "city": ["city", "town"],
    "state": ["state", "st"],
    "zip": ["zip", "zipcode", "zip code", "postal", "postal code"],
    "phone": ["phone", "telephone", "tel", "phone number"],
    "status": ["status", "business status"],
    "rating": ["rating", "stars"],
    "reviews": ["reviews", "review count", "ratings count"],
}

INVALID_VALUES = {"", "-", "—", "–", "n/a", "na", "none", "null", "nan"}
NAIL_WORDS = {"nail", "nails", "manicure", "pedicure", "mani", "pedi"}
BEAUTY_WORDS = {"salon", "spa", "beauty", "cosmetology", "esthetic", "esthetics", "lashes", "lash", "brows", "brow"}

WRONG_NAME_PATTERNS = [
    r"\bhardware\b",
    r"\bdollar general\b",
    r"\btrue value\b",
    r"\bbuilding center\b",
    r"\broadhouse\b",
    r"\bgrill(?:e)?\b",
    r"\brestaurant\b",
    r"\bcafe\b",
    r"\bcoffee\b",
    r"\bfuel\b",
    r"\bgas station\b",
    r"\bconvenience\b",
    r"\bgrocery\b",
    r"\bsupermarket\b",
    r"\bchurch\b",
    r"\bbank\b",
    r"\bauto parts\b",
    r"\btire\b",
    r"\bmotors\b",
    r"\bhotel\b",
    r"\bmotel\b",
    r"\bpharmacy\b",
]

OSM_BEAUTY_TYPES = {"beauty", "hairdresser", "cosmetics", "spa"}
OSM_WRONG_TYPES = {
    "hardware",
    "supermarket",
    "convenience",
    "restaurant",
    "fast_food",
    "fuel",
    "hotel",
    "motel",
    "church",
    "place_of_worship",
    "bank",
    "car_repair",
    "car_parts",
    "department_store",
    "variety_store",
}


def clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in INVALID_VALUES:
        return ""
    return re.sub(r"\s+", " ", text)


def normalize(value: Any) -> str:
    text = clean(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_zip(value: Any) -> str:
    match = re.search(r"\b(\d{5})(?:-\d{4})?\b", clean(value))
    return match.group(1) if match else ""


def normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D", "", clean(value))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) >= 7 else ""


def looks_like_street(value: Any) -> bool:
    text = normalize(value)
    if not text:
        return False
    return bool(re.match(r"^\d+\s+", text)) or bool(
        re.search(
            r"\b(st|street|ave|avenue|rd|road|blvd|boulevard|dr|drive|ct|court|ln|lane|hwy|highway|way|pl|place|pkwy|parkway)\b",
            text,
        )
    )


def detect_columns(columns: Iterable[str]) -> dict[str, Optional[str]]:
    normalized = {normalize(col): col for col in columns}
    mapping: dict[str, Optional[str]] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        mapping[canonical] = None
        for alias in aliases:
            found = normalized.get(normalize(alias))
            if found:
                mapping[canonical] = found
                break
    return mapping


def validate_mapping(mapping: dict[str, Optional[str]]) -> None:
    if not mapping.get("company"):
        raise ValueError("CSV cần có cột tên tiệm, ví dụ Company / Business / Name.")
    if not any(mapping.get(key) for key in ("street", "city", "zip", "phone")):
        raise ValueError("CSV cần ít nhất một cột địa chỉ/ZIP/Phone.")


def row_value(row: pd.Series, mapping: dict[str, Optional[str]], key: str) -> str:
    column = mapping.get(key)
    return clean(row.get(column, "")) if column else ""


def extract_input(row: pd.Series, mapping: dict[str, Optional[str]]) -> dict[str, str]:
    data = {key: row_value(row, mapping, key) for key in COLUMN_ALIASES}
    if not data["street"] and looks_like_street(data["city"]):
        data["street"] = data["city"]
        data["city"] = ""
    data["zip"] = normalize_zip(data["zip"])
    data["phone"] = normalize_phone(data["phone"])
    return data


def has_words(value: Any, words: set[str]) -> bool:
    return bool(set(normalize(value).split()) & words)


def obvious_wrong_name(company: str) -> bool:
    value = normalize(company)
    if has_words(company, NAIL_WORDS | BEAUTY_WORDS):
        return False
    return any(re.search(pattern, value) for pattern in WRONG_NAME_PATTERNS)


def business_status_closed(status: str) -> bool:
    value = normalize(status)
    return "closed permanently" in value or "closed temporarily" in value or value.startswith("closed")


def _tag_haystack(tag: Any) -> str:
    attrs = [
        tag.get("name", ""),
        tag.get("id", ""),
        tag.get("placeholder", ""),
        tag.get("aria-label", ""),
    ]
    label_text = ""
    tag_id = tag.get("id")
    if tag_id:
        root = tag.find_parent("form") or tag.find_parent() or tag
        label = root.find("label", attrs={"for": tag_id}) if hasattr(root, "find") else None
        if label:
            label_text = label.get_text(" ", strip=True)
    parent_text = tag.parent.get_text(" ", strip=True) if tag.parent else ""
    return normalize(" ".join(attrs + [label_text, parent_text]))


def _find_control(form: Any, keywords: list[str], tags: tuple[str, ...] = ("input", "select")) -> Optional[Any]:
    candidates = form.find_all(list(tags))
    scored: list[tuple[int, Any]] = []
    for tag in candidates:
        hay = _tag_haystack(tag)
        score = sum(5 for kw in keywords if normalize(kw) in hay)
        attr_hay = normalize(
            " ".join([tag.get("name", ""), tag.get("id", ""), tag.get("placeholder", "")])
        )
        score += sum(10 for kw in keywords if normalize(kw) in attr_hay)
        if score:
            scored.append((score, tag))
    return max(scored, key=lambda item: item[0])[1] if scored else None


def _initial_form_payload(form: Any) -> dict[str, str]:
    payload: dict[str, str] = {}
    for tag in form.find_all(["input", "select", "textarea"]):
        name = tag.get("name")
        if not name:
            continue
        if tag.name == "input":
            typ = (tag.get("type") or "text").lower()
            if typ in {"submit", "button", "image", "file"}:
                continue
            if typ in {"radio", "checkbox"} and not tag.has_attr("checked"):
                continue
            payload[name] = tag.get("value", "")
        elif tag.name == "select":
            selected = tag.find("option", selected=True) or tag.find("option")
            if selected:
                payload[name] = selected.get("value", selected.get_text(" ", strip=True))
        else:
            payload[name] = tag.get_text("", strip=False)
    return payload


def _set_business_radio(form: Any, payload: dict[str, str]) -> None:
    radios = form.find_all("input", attrs={"type": re.compile("radio", re.I)})
    for radio in radios:
        if "business" in _tag_haystack(radio):
            if radio.get("name"):
                payload[radio["name"]] = radio.get("value", "")
            return


def _set_select_by_text(select: Any, payload: dict[str, str], choices: list[str]) -> None:
    if not select or not select.get("name"):
        return
    wanted = {normalize(choice) for choice in choices}
    for option in select.find_all("option"):
        text = normalize(option.get_text(" ", strip=True))
        value = normalize(option.get("value", ""))
        if text in wanted or value in wanted:
            payload[select["name"]] = option.get(
                "value", option.get_text(" ", strip=True)
            )
            return


def parse_license_rows(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []
    header_words = {
        "license",
        "company",
        "business",
        "city",
        "state",
        "zip",
        "expiration",
        "type",
        "status",
    }

    for table in soup.find_all("table"):
        raw_rows = []
        for tr in table.find_all("tr"):
            cells = [
                clean(cell.get_text(" ", strip=True))
                for cell in tr.find_all(["th", "td"], recursive=False)
            ]
            if cells:
                raw_rows.append(cells)
        if len(raw_rows) < 2:
            continue

        header_index = None
        for idx, cells in enumerate(raw_rows[:4]):
            tokens = set()
            for cell in cells:
                tokens.update(normalize(cell).split())
            if len(tokens & header_words) >= 2:
                header_index = idx
                break
        if header_index is None:
            continue

        headers = [
            cell or f"column_{i + 1}"
            for i, cell in enumerate(raw_rows[header_index])
        ]
        for cells in raw_rows[header_index + 1 :]:
            if len(cells) < 2 or all(not cell for cell in cells):
                continue
            padded = cells + [""] * max(0, len(headers) - len(cells))
            row = {
                headers[i]: padded[i]
                for i in range(min(len(headers), len(padded)))
            }
            row["_raw"] = " | ".join(cells)
            if any(re.search(r"\d", value) for value in cells) or any(
                has_words(value, NAIL_WORDS | BEAUTY_WORDS) for value in cells
            ):
                results.append(row)
    return results


def _field(row: dict[str, str], aliases: tuple[str, ...]) -> str:
    for key, value in row.items():
        nk = normalize(key)
        if any(normalize(alias) in nk for alias in aliases):
            return clean(value)
    return ""


def score_license_candidate(
    data: dict[str, str], candidate: dict[str, str]
) -> tuple[float, float, bool]:
    company = _field(candidate, ("company", "business", "name"))
    raw = candidate.get("_raw", "")
    target_name = normalize(data.get("company", ""))
    name_basis = normalize(company or raw)
    name_score = (
        fuzz.token_set_ratio(target_name, name_basis) / 100.0
        if target_name and name_basis
        else 0.0
    )

    target_zip = data.get("zip", "")
    candidate_zip = normalize_zip(_field(candidate, ("zip", "postal")) or raw)
    zip_match = bool(target_zip and candidate_zip and target_zip == candidate_zip)

    target_city = normalize(data.get("city", ""))
    candidate_city = normalize(_field(candidate, ("city",)) or raw)
    city_match = bool(target_city and target_city in candidate_city)

    score = (
        0.75 * name_score
        + (0.20 if zip_match else 0.0)
        + (0.05 if city_match else 0.0)
    )
    return min(1.0, score), name_score, zip_match


@dataclass
class LicenseMatch:
    candidate: dict[str, str]
    score: float
    name_score: float
    zip_match: bool


class SouthDakotaLicenseClient:
    """Read the public current-business roster from South Dakota.

    Important: do NOT submit the ASP.NET search form. The form flow can redirect
    automated clients into a protected renewals/error page and return 401.
    Instead, fetch the public Business License Search Results list directly once,
    cache it in memory, then filter locally by ZIP/company for every CSV row.
    """

    def __init__(self, timeout: int = 30):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        self.timeout = timeout
        self._roster: Optional[list[dict[str, str]]] = None
        self._zip_cache: dict[str, list[dict[str, str]]] = {}

    def _load_roster(self) -> list[dict[str, str]]:
        if self._roster is not None:
            return self._roster

        response = self.session.get(
            SD_BUSINESS_ROSTER_URL,
            timeout=self.timeout,
            allow_redirects=True,
        )
        response.raise_for_status()

        rows = parse_license_rows(response.text)
        if not rows:
            raise RuntimeError(
                "Không đọc được roster Business License công khai của South Dakota. "
                f"URL cuối: {response.url}"
            )

        self._roster = rows
        return rows

    def search_zip(self, zip_code: str) -> list[dict[str, str]]:
        zip_code = normalize_zip(zip_code)
        if not zip_code:
            return []

        if zip_code in self._zip_cache:
            return self._zip_cache[zip_code]

        rows = self._load_roster()
        matches: list[dict[str, str]] = []
        for row in rows:
            raw = row.get("_raw", "")
            candidate_zip = normalize_zip(
                _field(row, ("zip", "postal")) or raw
            )
            if candidate_zip == zip_code:
                matches.append(row)

        self._zip_cache[zip_code] = matches
        return matches

    def search_company(self, company: str) -> list[dict[str, str]]:
        target = normalize(company)
        if not target:
            return []

        rows = self._load_roster()
        scored: list[tuple[float, dict[str, str]]] = []
        for row in rows:
            candidate = _field(row, ("company", "business", "name")) or row.get("_raw", "")
            score = fuzz.token_set_ratio(target, normalize(candidate)) / 100.0
            if score >= 0.55:
                scored.append((score, row))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [row for _, row in scored[:25]]


class NominatimClient:
    def __init__(
        self,
        cache_file: Union[str, Path] = ".cache/nominatim.json",
        timeout: int = 20,
        min_interval: float = 1.05,
    ):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.timeout = timeout
        self.min_interval = min_interval
        self.last_request = 0.0
        self.cache_file = Path(cache_file)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.cache = (
                json.loads(self.cache_file.read_text(encoding="utf-8"))
                if self.cache_file.exists()
                else {}
            )
        except Exception:
            self.cache = {}

    def _save(self) -> None:
        self.cache_file.write_text(
            json.dumps(self.cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def search(self, data: dict[str, str]) -> list[dict[str, Any]]:
        query = ", ".join(
            part
            for part in [
                data.get("company"),
                data.get("street"),
                data.get("city"),
                data.get("state"),
                data.get("zip"),
            ]
            if clean(part)
        )
        key = normalize(query)
        if key in self.cache:
            return self.cache[key]

        wait = self.min_interval - (time.monotonic() - self.last_request)
        if wait > 0:
            time.sleep(wait)

        response = self.session.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "jsonv2",
                "addressdetails": 1,
                "extratags": 1,
                "namedetails": 1,
                "limit": 5,
                "countrycodes": "us",
            },
            timeout=self.timeout,
        )
        self.last_request = time.monotonic()
        response.raise_for_status()
        results = response.json()
        self.cache[key] = results
        self._save()
        return results


def score_osm_candidate(
    data: dict[str, str], item: dict[str, Any]
) -> tuple[float, float, bool]:
    name = clean(
        (item.get("namedetails") or {}).get("name") or item.get("name") or ""
    )
    display = clean(item.get("display_name"))
    name_score = (
        fuzz.token_set_ratio(
            normalize(data.get("company")), normalize(name or display)
        )
        / 100.0
    )
    zip_match = bool(data.get("zip", "") and data["zip"] in display)
    street_num = re.match(r"^\s*(\d+)", clean(data.get("street")))
    number_match = bool(
        street_num
        and re.search(
            rf"\b{re.escape(street_num.group(1))}\b", display
        )
    )
    score = (
        0.65 * name_score
        + (0.20 if zip_match else 0.0)
        + (0.15 if number_match else 0.0)
    )
    return min(1.0, score), name_score, zip_match


def best_osm_match(
    data: dict[str, str], items: list[dict[str, Any]]
) -> tuple[Optional[dict[str, Any]], float]:
    scored = [
        (score_osm_candidate(data, item)[0], item) for item in items
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return (scored[0][1], scored[0][0]) if scored else (None, 0.0)


def osm_type(item: Optional[dict[str, Any]]) -> str:
    if not item:
        return ""
    category = clean(item.get("category"))
    typ = clean(item.get("type"))
    beauty = clean((item.get("extratags") or {}).get("beauty"))
    return " / ".join(
        part for part in [category, typ, beauty] if part
    )


def osm_is_nail_or_beauty(
    item: Optional[dict[str, Any]], company: str
) -> bool:
    if not item:
        return False
    typ = normalize(item.get("type"))
    beauty = normalize((item.get("extratags") or {}).get("beauty"))
    return (
        typ in OSM_BEAUTY_TYPES
        or "nail" in beauty
        or has_words(company, NAIL_WORDS | BEAUTY_WORDS)
    )


def osm_is_wrong_business(item: Optional[dict[str, Any]]) -> bool:
    if not item:
        return False
    return normalize(item.get("type")) in OSM_WRONG_TYPES


def best_license_match(
    data: dict[str, str], candidates: list[dict[str, str]]
) -> Optional[LicenseMatch]:
    matches = []
    for candidate in candidates:
        score, name_score, zip_match = score_license_candidate(
            data, candidate
        )
        matches.append(
            LicenseMatch(candidate, score, name_score, zip_match)
        )
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[0] if matches else None


def verify_row(
    row: pd.Series,
    mapping: dict[str, Optional[str]],
    license_client: Any,
    osm_client: Optional[Any] = None,
) -> dict[str, Any]:
    data = extract_input(row, mapping)
    company = data.get("company", "")
    status = data.get("status", "")

    base = {
        "Is_Real_Nail_Salon": "REVIEW",
        "Verdict": "REVIEW",
        "Confidence": 0,
        "Reason": "",
        "SD_Current_License": "NO_MATCH",
        "SD_License_Matched_Row": "",
        "SD_License_Match_Score": "",
        "OSM_Match": "",
        "OSM_Type": "",
        "OSM_Display_Name": "",
        "OSM_Match_Score": "",
    }

    if not company:
        return {
            **base,
            "Verdict": "BAD_DATA",
            "Confidence": 100,
            "Reason": "Thiếu tên business.",
        }

    if business_status_closed(status):
        return {
            **base,
            "Is_Real_Nail_Salon": "CLOSED",
            "Verdict": "CLOSED_FROM_SOURCE",
            "Confidence": 85,
            "Reason": f"CSV nguồn đang ghi trạng thái {status}.",
        }

    if obvious_wrong_name(company):
        return {
            **base,
            "Is_Real_Nail_Salon": "NO",
            "Verdict": "WRONG_BUSINESS",
            "Confidence": 95,
            "Reason": "Tên business cho thấy đây rõ ràng là loại hình khác, không phải nail/beauty salon.",
        }

    license_candidates = []
    try:
        if data.get("zip"):
            license_candidates = license_client.search_zip(data["zip"])
        else:
            license_candidates = license_client.search_company(company)
    except Exception as exc:
        base["Reason"] = (
            f"Không truy cập được SD license database: {exc}"
        )

    lic = best_license_match(data, license_candidates)
    if lic:
        base["SD_License_Matched_Row"] = lic.candidate.get("_raw", "")
        base["SD_License_Match_Score"] = round(lic.score * 100, 1)
        if (
            lic.score >= 0.78
            and lic.name_score >= 0.72
            and (lic.zip_match or not data.get("zip"))
        ):
            base["SD_Current_License"] = "MATCH"
            lic_text = normalize(lic.candidate.get("_raw", ""))

            if has_words(company, NAIL_WORDS) or "nail" in lic_text:
                return {
                    **base,
                    "Is_Real_Nail_Salon": "YES",
                    "Verdict": "REAL_NAIL_SALON",
                    "Confidence": max(
                        90, int(round(lic.score * 100))
                    ),
                    "Reason": "Khớp business trong roster license hiện hành của South Dakota và có dấu hiệu rõ là nail salon.",
                }

            if has_words(company, BEAUTY_WORDS) or any(
                word in lic_text
                for word in ("salon", "cosmetology", "esthetic", "spa")
            ):
                return {
                    **base,
                    "Is_Real_Nail_Salon": "REVIEW",
                    "Verdict": "REAL_BEAUTY_BUSINESS_REVIEW_NAIL",
                    "Confidence": max(
                        80, int(round(lic.score * 100))
                    ),
                    "Reason": "Khớp business có license hiện hành ở South Dakota, nhưng license/name chưa đủ để khẳng định riêng dịch vụ nail.",
                }

    if osm_client is not None:
        try:
            items = osm_client.search(data)
            item, osm_score = best_osm_match(data, items)
            if item:
                base["OSM_Match"] = (
                    "MATCH" if osm_score >= 0.72 else "WEAK"
                )
                base["OSM_Type"] = osm_type(item)
                base["OSM_Display_Name"] = clean(
                    item.get("display_name")
                )
                base["OSM_Match_Score"] = round(
                    osm_score * 100, 1
                )

                if osm_score >= 0.72 and osm_is_wrong_business(item):
                    return {
                        **base,
                        "Is_Real_Nail_Salon": "NO",
                        "Verdict": "WRONG_BUSINESS",
                        "Confidence": max(
                            80, int(round(osm_score * 100))
                        ),
                        "Reason": "OpenStreetMap khớp business nhưng loại địa điểm không phải nail/beauty salon.",
                    }

                if (
                    osm_score >= 0.72
                    and osm_is_nail_or_beauty(item, company)
                ):
                    verdict = (
                        "LIKELY_REAL_NAIL_SALON"
                        if has_words(company, NAIL_WORDS)
                        else "REVIEW_BEAUTY_BUSINESS"
                    )
                    answer = (
                        "YES"
                        if verdict == "LIKELY_REAL_NAIL_SALON"
                        else "REVIEW"
                    )
                    return {
                        **base,
                        "Is_Real_Nail_Salon": answer,
                        "Verdict": verdict,
                        "Confidence": max(
                            70, int(round(osm_score * 100))
                        ),
                        "Reason": "OpenStreetMap khớp tên/vị trí và cho thấy đây là business beauty/nail; không mạnh bằng license chính thức.",
                    }
        except Exception as exc:
            extra = f" OpenStreetMap lỗi: {exc}"
            base["Reason"] = (base["Reason"] + extra).strip()

    try:
        reviews = int(float(data.get("reviews") or 0))
    except ValueError:
        reviews = 0

    if (
        has_words(company, NAIL_WORDS)
        and normalize(status) == "operational"
        and reviews >= 3
    ):
        return {
            **base,
            "Is_Real_Nail_Salon": "REVIEW",
            "Verdict": "REVIEW_NAILMAP_SIGNAL",
            "Confidence": 55,
            "Reason": "Tên giống nail salon và NailMap có trạng thái/review, nhưng chưa có bằng chứng độc lập đủ mạnh từ nguồn miễn phí.",
        }

    return {
        **base,
        "Is_Real_Nail_Salon": "REVIEW",
        "Verdict": "REVIEW",
        "Confidence": 30 if not base["Reason"] else 20,
        "Reason": base["Reason"]
        or "Chưa có đủ bằng chứng miễn phí để khẳng định tiệm nail thật hay business sai.",
    }


def verify_dataframe(
    df: pd.DataFrame,
    limit: Optional[int] = None,
    progress: Optional[Callable[[int, int, str], None]] = None,
    use_osm: bool = True,
    license_client: Optional[Any] = None,
    osm_client: Optional[Any] = None,
) -> pd.DataFrame:
    mapping = detect_columns(df.columns)
    validate_mapping(mapping)
    work = df.head(limit).copy() if limit else df.copy()
    lic_client = license_client or SouthDakotaLicenseClient()
    nom_client = (
        osm_client
        if osm_client is not None
        else (NominatimClient() if use_osm else None)
    )

    checked_rows = []
    total = len(work)
    for pos, (_, row) in enumerate(work.iterrows(), start=1):
        name = row_value(row, mapping, "company")
        try:
            result = verify_row(
                row, mapping, lic_client, nom_client
            )
        except Exception as exc:
            result = {
                "Is_Real_Nail_Salon": "REVIEW",
                "Verdict": "ERROR",
                "Confidence": 0,
                "Reason": str(exc),
            }
        checked_rows.append(result)
        if progress:
            progress(pos, total, name)

    verification = pd.DataFrame(checked_rows, index=work.index)
    return pd.concat([work, verification], axis=1)
