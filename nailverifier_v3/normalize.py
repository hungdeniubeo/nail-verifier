from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Set

from rapidfuzz import fuzz

from .models import AddressMatch, BusinessRecord, NameMatch

INVALID_VALUES = {"", "-", "—", "–", "n/a", "na", "none", "null", "nan"}

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

GENERIC_NAME_TOKENS: Set[str] = {
    "a",
    "an",
    "and",
    "at",
    "bar",
    "beauty",
    "business",
    "co",
    "company",
    "corp",
    "corporation",
    "day",
    "inc",
    "llc",
    "llp",
    "ltd",
    "nail",
    "nails",
    "of",
    "pllc",
    "salon",
    "spa",
    "studio",
    "the",
}

NAIL_WORDS = {"nail", "nails", "manicure", "manicures", "pedicure", "pedicures", "mani", "pedi"}
BEAUTY_WORDS = {
    "beauty",
    "cosmetology",
    "esthetic",
    "esthetics",
    "esthetician",
    "hair",
    "lash",
    "lashes",
    "salon",
    "spa",
}

STREET_SUFFIX_MAP = {
    "street": "st",
    "avenue": "ave",
    "road": "rd",
    "boulevard": "blvd",
    "drive": "dr",
    "court": "ct",
    "lane": "ln",
    "highway": "hwy",
    "parkway": "pkwy",
    "place": "pl",
    "circle": "cir",
    "terrace": "ter",
}

UNIT_MARKERS = {"suite", "ste", "unit", "#"}


def clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in INVALID_VALUES:
        return ""
    return re.sub(r"\s+", " ", text)


def normalize_text(value: Any) -> str:
    text = clean(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9#]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_name(value: Any) -> str:
    return normalize_text(value)


def name_tokens(value: Any) -> List[str]:
    return [token for token in normalize_name(value).split() if token]


def core_name_tokens(value: Any) -> List[str]:
    return [token for token in name_tokens(value) if token not in GENERIC_NAME_TOKENS]


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / float(len(sa | sb))


def compare_names(target: Any, candidate: Any) -> NameMatch:
    a = normalize_name(target)
    b = normalize_name(candidate)
    if not a or not b:
        return NameMatch(0.0, False, 0.0, 0.0, 0.0, core_name_tokens(target), core_name_tokens(candidate))

    exact = a == b
    full_fuzzy = fuzz.ratio(a, b) / 100.0
    token_fuzzy = fuzz.token_set_ratio(a, b) / 100.0
    target_core = core_name_tokens(target)
    candidate_core = core_name_tokens(candidate)
    core_overlap = _jaccard(target_core, candidate_core)

    if exact:
        score = 1.0
    else:
        score = 0.45 * full_fuzzy + 0.35 * token_fuzzy + 0.20 * core_overlap

        if target_core and candidate_core and not (set(target_core) & set(candidate_core)):
            score = min(score, 0.45)
        elif target_core and candidate_core and core_overlap < 0.34:
            score = min(score, 0.68)

        if (a in b or b in a) and core_overlap >= 0.66:
            score = max(score, 0.90)

    return NameMatch(
        score=max(0.0, min(1.0, score)),
        exact=exact,
        full_fuzzy=full_fuzzy,
        token_fuzzy=token_fuzzy,
        core_overlap=core_overlap,
        target_core=target_core,
        candidate_core=candidate_core,
    )


def normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D", "", clean(value))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) >= 7 else ""


def normalize_zip(value: Any) -> str:
    match = re.search(r"\b(\d{5})(?:-\d{4})?\b", clean(value))
    return match.group(1) if match else ""


def parse_number(value: Any, default: float = 0.0) -> float:
    text = clean(value).replace(",", "")
    if not text:
        return default
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def looks_like_street(value: Any) -> bool:
    text = normalize_text(value)
    if not text:
        return False
    return bool(re.match(r"^\d+\s+", text)) or bool(
        re.search(r"\b(st|street|ave|avenue|rd|road|blvd|boulevard|dr|drive|ct|court|ln|lane|hwy|highway|way|pl|place|pkwy|parkway)\b", text)
    )


def normalize_street(value: Any, drop_unit: bool = False) -> str:
    tokens = normalize_text(value).split()
    normalized: List[str] = []
    stop = False
    for token in tokens:
        if drop_unit and (token in UNIT_MARKERS or token.startswith("#")):
            stop = True
        if stop:
            continue
        normalized.append(STREET_SUFFIX_MAP.get(token, token))
    return " ".join(normalized)


def street_number(value: Any) -> str:
    match = re.match(r"^\s*(\d+[a-zA-Z]?)\b", clean(value))
    return match.group(1).lower() if match else ""


def compare_addresses(
    target_street: Any,
    target_city: Any,
    target_zip: Any,
    candidate_street: Any,
    candidate_city: Any,
    candidate_zip: Any,
) -> AddressMatch:
    target_street_n = normalize_street(target_street, drop_unit=True)
    candidate_street_n = normalize_street(candidate_street, drop_unit=True)
    target_city_n = normalize_text(target_city)
    candidate_city_n = normalize_text(candidate_city)
    target_zip_n = normalize_zip(target_zip)
    candidate_zip_n = normalize_zip(candidate_zip)

    tnum = street_number(target_street)
    cnum = street_number(candidate_street)
    number_match: Optional[bool] = None
    if tnum and cnum:
        number_match = tnum == cnum

    street_score = 0.0
    if target_street_n and candidate_street_n:
        street_score = fuzz.token_set_ratio(target_street_n, candidate_street_n) / 100.0
        if number_match is False:
            street_score = min(street_score, 0.35)

    city_match: Optional[bool] = None
    if target_city_n and candidate_city_n:
        city_match = target_city_n == candidate_city_n

    zip_match: Optional[bool] = None
    if target_zip_n and candidate_zip_n:
        zip_match = target_zip_n == candidate_zip_n

    weights = 0.0
    score = 0.0
    if target_street_n and candidate_street_n:
        weights += 0.60
        score += 0.60 * street_score
    if city_match is not None:
        weights += 0.15
        score += 0.15 if city_match else 0.0
    if zip_match is not None:
        weights += 0.25
        score += 0.25 if zip_match else 0.0

    normalized_score = score / weights if weights else 0.0
    return AddressMatch(
        score=max(0.0, min(1.0, normalized_score)),
        street_number_match=number_match,
        street_score=street_score,
        city_match=city_match,
        zip_match=zip_match,
    )


def detect_columns(columns: Iterable[str]) -> Dict[str, Optional[str]]:
    normalized = {normalize_text(col): col for col in columns}
    mapping: Dict[str, Optional[str]] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        mapping[canonical] = None
        for alias in aliases:
            found = normalized.get(normalize_text(alias))
            if found:
                mapping[canonical] = found
                break
    return mapping


def validate_mapping(mapping: Dict[str, Optional[str]]) -> None:
    if not mapping.get("company"):
        raise ValueError("CSV cần có cột tên business (Company / Business / Name).")
    if not any(mapping.get(key) for key in ("street", "city", "zip", "phone")):
        raise ValueError("CSV cần ít nhất một cột Street/City/ZIP/Phone để xác minh business.")


def row_value(row: Any, mapping: Dict[str, Optional[str]], key: str) -> str:
    column = mapping.get(key)
    return clean(row.get(column, "")) if column else ""


def row_to_record(row: Any, mapping: Dict[str, Optional[str]]) -> BusinessRecord:
    company = row_value(row, mapping, "company")
    street = row_value(row, mapping, "street")
    city = row_value(row, mapping, "city")
    if not street and looks_like_street(city):
        street, city = city, ""

    return BusinessRecord(
        company=company,
        street=street,
        city=city,
        state=row_value(row, mapping, "state").upper(),
        zip_code=normalize_zip(row_value(row, mapping, "zip")),
        phone=normalize_phone(row_value(row, mapping, "phone")),
        rating=parse_number(row_value(row, mapping, "rating"), 0.0),
        reviews=int(parse_number(row_value(row, mapping, "reviews"), 0.0)),
        status=row_value(row, mapping, "status"),
        raw={str(k): clean(v) for k, v in row.to_dict().items()},
    )


def record_identity(record: BusinessRecord) -> str:
    payload = "|".join(
        [
            normalize_name(record.company),
            normalize_street(record.street),
            normalize_text(record.city),
            record.state.upper(),
            normalize_zip(record.zip_code),
            normalize_phone(record.phone),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def has_nail_words(value: Any) -> bool:
    return bool(set(name_tokens(value)) & NAIL_WORDS)


def has_beauty_words(value: Any) -> bool:
    return bool(set(name_tokens(value)) & BEAUTY_WORDS)
