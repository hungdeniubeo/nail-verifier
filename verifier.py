from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Iterable

import pandas as pd
import requests
from rapidfuzz import fuzz

GOOGLE_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GOOGLE_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.nationalPhoneNumber",
        "places.businessStatus",
        "places.primaryType",
        "places.types",
        "places.googleMapsUri",
        "places.rating",
        "places.userRatingCount",
    ]
)

COLUMN_ALIASES = {
    "company": ["company", "business", "business name", "business_name", "name", "salon", "salon name"],
    "street": ["street", "address", "address 1", "address1", "street address"],
    "city": ["city", "town"],
    "state": ["state", "st"],
    "zip": ["zip", "zipcode", "zip code", "postal", "postal code"],
    "phone": ["phone", "telephone", "tel", "phone number"],
}

NAIL_TYPES = {"nail_salon"}
BEAUTY_TYPES = {
    "beauty_salon",
    "beautician",
    "spa",
    "hair_salon",
    "hair_care",
    "foot_care",
    "makeup_artist",
    "skin_care_clinic",
    "wellness_center",
}
NAIL_WORDS = {"nail", "nails", "manicure", "pedicure", "mani", "pedi"}
INVALID_VALUES = {"", "-", "—", "–", "n/a", "na", "none", "null", "nan"}


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


def normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D", "", clean(value))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) >= 7 else ""


def normalize_zip(value: Any) -> str:
    text = clean(value)
    match = re.search(r"\b(\d{5})(?:-\d{4})?\b", text)
    return match.group(1) if match else ""


def looks_like_street(value: Any) -> bool:
    text = normalize(value)
    if not text:
        return False
    return bool(re.match(r"^\d+\s+", text)) or bool(
        re.search(r"\b(st|street|ave|avenue|rd|road|blvd|boulevard|dr|drive|ct|court|ln|lane|hwy|highway|way|pl|place|pkwy|parkway)\b", text)
    )


def detect_columns(columns: Iterable[str]) -> dict[str, str | None]:
    normalized = {normalize(col): col for col in columns}
    mapping: dict[str, str | None] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        mapping[canonical] = None
        for alias in aliases:
            if normalize(alias) in normalized:
                mapping[canonical] = normalized[normalize(alias)]
                break
    return mapping


def validate_mapping(mapping: dict[str, str | None]) -> None:
    if not mapping.get("company"):
        raise ValueError("CSV cần có cột tên tiệm, ví dụ: Company / Business / Name.")
    if not any(mapping.get(key) for key in ("street", "city", "zip", "phone")):
        raise ValueError("CSV cần ít nhất một cột vị trí hoặc Phone để tìm business.")


def row_value(row: pd.Series, mapping: dict[str, str | None], key: str) -> str:
    column = mapping.get(key)
    return clean(row.get(column, "")) if column else ""


def extract_input(row: pd.Series, mapping: dict[str, str | None]) -> dict[str, str]:
    data = {key: row_value(row, mapping, key) for key in COLUMN_ALIASES}
    if not data["street"] and looks_like_street(data["city"]):
        data["street"] = data["city"]
        data["city"] = ""
    data["zip"] = normalize_zip(data["zip"])
    data["phone"] = normalize_phone(data["phone"])
    return data


def build_query(data: dict[str, str]) -> str:
    parts = [data.get("company", "")]
    for key in ("street", "city", "state", "zip"):
        value = clean(data.get(key, ""))
        if value:
            parts.append(value)
    if len(parts) == 1 and data.get("phone"):
        parts.append(data["phone"])
    return " ".join(dict.fromkeys(part for part in parts if part))


def display_name(place: dict[str, Any]) -> str:
    value = place.get("displayName")
    if isinstance(value, dict):
        return clean(value.get("text"))
    return clean(value)


def place_types(place: dict[str, Any]) -> set[str]:
    values = set(place.get("types") or [])
    if place.get("primaryType"):
        values.add(place["primaryType"])
    return {str(value) for value in values if value}


def extract_street_number(value: Any) -> str:
    match = re.search(r"\b(\d{1,6})\b", clean(value))
    return match.group(1) if match else ""


def address_score(data: dict[str, str], formatted_address: str) -> float:
    candidate = normalize(formatted_address)
    if not candidate:
        return 0.0

    score = 0.0
    weight = 0.0

    zip_code = data.get("zip", "")
    if zip_code:
        weight += 0.25
        if zip_code in formatted_address:
            score += 0.25

    city = normalize(data.get("city", ""))
    if city:
        weight += 0.15
        if city in candidate:
            score += 0.15

    state = normalize(data.get("state", ""))
    if state:
        weight += 0.10
        if re.search(rf"\b{re.escape(state)}\b", candidate):
            score += 0.10

    street = clean(data.get("street", ""))
    if street:
        weight += 0.50
        number = extract_street_number(street)
        number_score = 0.0
        if number:
            number_score = 0.20 if number in re.findall(r"\b\d{1,6}\b", formatted_address) else 0.0
        street_similarity = fuzz.token_set_ratio(normalize(street), candidate) / 100.0
        score += number_score + (0.30 * street_similarity)

    if weight == 0:
        return 0.0
    return max(0.0, min(1.0, score / weight))


@dataclass
class Match:
    place: dict[str, Any]
    score: float
    name_score: float
    location_score: float
    phone_match: bool | None


def score_candidate(data: dict[str, str], place: dict[str, Any]) -> Match:
    name = display_name(place)
    name_score = fuzz.token_set_ratio(normalize(data.get("company", "")), normalize(name)) / 100.0
    location_score = address_score(data, clean(place.get("formattedAddress")))

    input_phone = data.get("phone", "")
    candidate_phone = normalize_phone(place.get("nationalPhoneNumber"))
    phone_match: bool | None = None
    if input_phone and candidate_phone:
        phone_match = input_phone == candidate_phone

    if phone_match is True:
        score = 0.45 * name_score + 0.35 * location_score + 0.20
    elif phone_match is False:
        score = 0.50 * name_score + 0.40 * location_score - 0.10
    else:
        score = 0.55 * name_score + 0.45 * location_score

    return Match(
        place=place,
        score=max(0.0, min(1.0, score)),
        name_score=name_score,
        location_score=location_score,
        phone_match=phone_match,
    )


class GooglePlacesClient:
    def __init__(self, api_key: str, timeout: int = 20):
        self.api_key = api_key.strip()
        self.timeout = timeout
        if not self.api_key:
            raise ValueError("Thiếu Google Maps API key.")

    def search(self, query: str, page_size: int = 5) -> list[dict[str, Any]]:
        response = requests.post(
            GOOGLE_TEXT_SEARCH_URL,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": GOOGLE_FIELD_MASK,
            },
            json={
                "textQuery": query,
                "pageSize": max(1, min(int(page_size), 10)),
                "languageCode": "en",
                "regionCode": "US",
            },
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise RuntimeError(f"Google Places API lỗi {response.status_code}: {detail}")
        return response.json().get("places", [])


def has_nail_keyword(*values: Any) -> bool:
    tokens: set[str] = set()
    for value in values:
        tokens.update(normalize(value).split())
    return bool(tokens & NAIL_WORDS)


def classify(data: dict[str, str], best: Match | None) -> dict[str, Any]:
    if best is None:
        return {
            "Is_Real_Nail_Salon": "REVIEW",
            "Verdict": "REVIEW",
            "Confidence": 10,
            "Reason": "Không tìm thấy business đủ khớp trên Google Places; cần kiểm tra tay.",
        }

    place = best.place
    types = place_types(place)
    primary_type = clean(place.get("primaryType"))
    status = clean(place.get("businessStatus")) or "UNKNOWN"
    matched_name = display_name(place)
    strong_match = best.score >= 0.72 and best.name_score >= 0.60
    medium_match = best.score >= 0.55 and best.name_score >= 0.50
    nail_type = bool(types & NAIL_TYPES)
    beauty_type = bool(types & BEAUTY_TYPES)
    nail_keyword = has_nail_keyword(data.get("company"), matched_name)
    confidence = int(round(best.score * 100))

    if strong_match and status in {"CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"}:
        label = "CLOSED_PERMANENTLY" if status == "CLOSED_PERMANENTLY" else "CLOSED_TEMPORARILY"
        return {
            "Is_Real_Nail_Salon": "CLOSED" if (nail_type or (beauty_type and nail_keyword)) else "NO",
            "Verdict": label,
            "Confidence": max(75, confidence),
            "Reason": f"Google Places khớp business nhưng trạng thái là {status}.",
        }

    if strong_match and status == "OPERATIONAL" and nail_type:
        return {
            "Is_Real_Nail_Salon": "YES",
            "Verdict": "REAL_NAIL_SALON",
            "Confidence": max(85, confidence),
            "Reason": "Google Places khớp tên/vị trí và phân loại business là nail_salon, đang OPERATIONAL.",
        }

    if strong_match and status == "OPERATIONAL" and beauty_type and nail_keyword:
        return {
            "Is_Real_Nail_Salon": "YES",
            "Verdict": "LIKELY_REAL_NAIL_SALON",
            "Confidence": max(75, min(94, confidence)),
            "Reason": "Business đang hoạt động, thuộc nhóm beauty/spa và tên có dấu hiệu dịch vụ nail.",
        }

    if strong_match and status == "OPERATIONAL" and not beauty_type and not nail_type:
        return {
            "Is_Real_Nail_Salon": "NO",
            "Verdict": "WRONG_BUSINESS",
            "Confidence": max(80, confidence),
            "Reason": f"Google Places khớp business nhưng loại là {primary_type or 'non-beauty'}, không phải nail/beauty salon.",
        }

    if medium_match and status == "OPERATIONAL" and beauty_type:
        return {
            "Is_Real_Nail_Salon": "REVIEW",
            "Verdict": "REVIEW_BEAUTY_BUSINESS",
            "Confidence": max(45, confidence),
            "Reason": "Tìm thấy business beauty/spa đang hoạt động nhưng chưa đủ bằng chứng để khẳng định là tiệm nail.",
        }

    return {
        "Is_Real_Nail_Salon": "REVIEW",
        "Verdict": "REVIEW",
        "Confidence": max(20, confidence),
        "Reason": "Có kết quả Google Places nhưng mức khớp hoặc loại business chưa đủ chắc chắn.",
    }


def verify_row(row: pd.Series, mapping: dict[str, str | None], client: Any, page_size: int = 5) -> dict[str, Any]:
    data = extract_input(row, mapping)
    if not data.get("company"):
        return {"Is_Real_Nail_Salon": "NO", "Verdict": "BAD_DATA", "Confidence": 100, "Reason": "Thiếu tên business.", "Search_Query": ""}

    query = build_query(data)
    if not query or not any(data.get(k) for k in ("street", "city", "zip", "phone")):
        return {
            "Is_Real_Nail_Salon": "REVIEW",
            "Verdict": "BAD_DATA",
            "Confidence": 100,
            "Reason": "Không đủ địa chỉ/ZIP/phone để tìm business đáng tin cậy.",
            "Search_Query": query,
        }

    places = client.search(query, page_size=page_size)
    matches = [score_candidate(data, place) for place in places]
    matches.sort(key=lambda item: item.score, reverse=True)
    best = matches[0] if matches else None

    if (best is None or best.score < 0.50) and data.get("phone"):
        fallback_query = " ".join(
            part for part in [data["phone"], data.get("city", ""), data.get("state", ""), data.get("zip", "")] if part
        )
        fallback_places = client.search(fallback_query, page_size=page_size)
        fallback_matches = [score_candidate(data, place) for place in fallback_places]
        fallback_matches.sort(key=lambda item: item.score, reverse=True)
        if fallback_matches and (best is None or fallback_matches[0].score > best.score):
            best = fallback_matches[0]
            query = f"{query} | fallback: {fallback_query}"

    verdict = classify(data, best)
    result: dict[str, Any] = {**verdict, "Search_Query": query}

    if best is None:
        result.update({
            "Matched_Name": "", "Matched_Address": "", "Matched_Phone": "", "Google_Business_Status": "",
            "Google_Primary_Type": "", "Google_Types": "", "Google_Maps_URL": "", "Google_Rating": "",
            "Google_Review_Count": "", "Match_Score": 0, "Name_Score": 0, "Location_Score": 0, "Phone_Match": "",
        })
        return result

    place = best.place
    result.update({
        "Matched_Name": display_name(place),
        "Matched_Address": clean(place.get("formattedAddress")),
        "Matched_Phone": clean(place.get("nationalPhoneNumber")),
        "Google_Business_Status": clean(place.get("businessStatus")),
        "Google_Primary_Type": clean(place.get("primaryType")),
        "Google_Types": ", ".join(sorted(place_types(place))),
        "Google_Maps_URL": clean(place.get("googleMapsUri")),
        "Google_Rating": place.get("rating", ""),
        "Google_Review_Count": place.get("userRatingCount", ""),
        "Match_Score": round(best.score * 100, 1),
        "Name_Score": round(best.name_score * 100, 1),
        "Location_Score": round(best.location_score * 100, 1),
        "Phone_Match": "YES" if best.phone_match is True else "NO" if best.phone_match is False else "",
    })
    return result


def verify_dataframe(
    df: pd.DataFrame,
    api_key: str,
    limit: int | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    delay_seconds: float = 0.05,
    client: Any | None = None,
) -> pd.DataFrame:
    mapping = detect_columns(df.columns)
    validate_mapping(mapping)
    work = df.head(limit).copy() if limit else df.copy()
    places_client = client or GooglePlacesClient(api_key)

    rows: list[dict[str, Any]] = []
    total = len(work)
    for position, (_, row) in enumerate(work.iterrows(), start=1):
        name = row_value(row, mapping, "company")
        try:
            checked = verify_row(row, mapping, places_client)
        except Exception as exc:
            checked = {
                "Is_Real_Nail_Salon": "REVIEW",
                "Verdict": "API_ERROR",
                "Confidence": 0,
                "Reason": str(exc),
                "Search_Query": build_query(extract_input(row, mapping)),
            }
        rows.append(checked)
        if progress:
            progress(position, total, name)
        if delay_seconds > 0 and position < total:
            time.sleep(delay_seconds)

    verification = pd.DataFrame(rows, index=work.index)
    return pd.concat([work, verification], axis=1)
