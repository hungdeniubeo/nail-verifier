from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Tuple
from urllib.parse import urlparse

import pandas as pd

REGISTRY_COLUMNS = [
    "State",
    "Company",
    "Street",
    "City",
    "ZIP",
    "Phone",
    "Source_Name",
    "Source_Tier",
    "Source_URL",
    "Observed_Category",
    "Nail_Service_Evidence",
    "Business_Status_Evidence",
    "Evidence_Direction",
    "Evidence_Notes",
    "Checked_At",
]

TIER_B_HOSTS = {
    "bbb.org",
    "maps.apple.com",
    "chamberofcommerce.com",
    "local.mitchellrepublic.com",
}

TIER_C_HOSTS = {
    "bestprosintown.com",
    "loc8nearme.com",
    "birdeye.com",
    "yellowpages.com",
    "local.yahoo.com",
    "nailsalondirectories.com",
    "localnailsalons.net",
    "salonlookup.com",
    "nailartai.app",
    "restaurantguru.com",
    "waze.com",
    "verview.com",
    "baonail.com",
    "dnb.com",
    "usbeautyaward.com",
    "locally.com",
}

OFFICIAL_CHAIN_HOSTS = {
    "acehardware.com",
    "dollargeneral.com",
    "truevalue.com",
    "coffeecupfuelstops.com",
}


def _host(url: str) -> str:
    host = (urlparse(str(url or "").strip()).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _host_matches(host: str, candidates: set[str]) -> bool:
    return any(host == candidate or host.endswith("." + candidate) for candidate in candidates)


def source_tier_for(url: str, notes: str) -> str:
    """Conservatively classify an already-researched source into v3.7 tiers."""
    host = _host(url)
    note = str(notes or "").lower()

    if _host_matches(host, TIER_C_HOSTS):
        return "C"
    if _host_matches(host, TIER_B_HOSTS):
        return "B"

    # Official municipal directories are useful independent identity/category
    # corroboration but are not the business itself, so keep them at Tier B.
    if host == "bowdlesd.com" and "business-directory" in str(url):
        return "B"

    if _host_matches(host, OFFICIAL_CHAIN_HOSTS):
        return "A"

    # Business-controlled booking/service pages count as primary when the
    # calibration note explicitly identifies them as official/booking pages.
    if host.endswith("glossgenius.com") and any(
        marker in note for marker in ("official", "first-party", "booking site", "booking/about")
    ):
        return "A"

    if any(
        marker in note
        for marker in (
            "official website",
            "official site",
            "official company site",
            "official salon website",
            "official business locations",
            "first-party",
        )
    ):
        return "A"

    # Unknown/third-party providers never get promoted to primary by guessing.
    return "C"


def _source_name(url: str) -> str:
    return _host(url) or "UNKNOWN_SOURCE"


def _checked_at(notes: str) -> str:
    match = re.search(r"checked\s+(20\d{2}-\d{2}-\d{2})", str(notes or ""), re.I)
    return match.group(1) if match else "2026-09-28"


def _affirmative_non_nail_category(notes: str, company: str) -> str:
    text = (str(notes or "") + " " + str(company or "")).lower()
    if any(term in text for term in ("hardware", "lumber", "building material", "building center", "home-improvement", "home improvement")):
        return "Hardware / Building Materials"
    if any(term in text for term in ("grocery", "supermarket")):
        return "Grocery Store"
    if any(term in text for term in ("restaurant", "steakhouse", "buffet", "grille")):
        return "Restaurant"
    if any(term in text for term in ("fuel stop", "fuel", "convenience", "travel store", "gas station")):
        return "Fuel / Convenience Store"
    if any(term in text for term in ("hotel", "gaming complex", "gaming")):
        return "Hotel / Gaming"
    if any(term in text for term in ("dollar general", "general retail", "discount store", "variety store", "retail store")):
        return "General Retail"
    if any(term in text for term in ("auto parts", "tire store", "bank", "church", "place of worship")):
        return "Clearly Non-Beauty Business"
    return ""


def _reject(row: dict[str, str], reason: str) -> dict[str, str]:
    return {
        "State": str(row.get("State", "")),
        "Company": str(row.get("Company", "")),
        "Street": str(row.get("Street", "")),
        "City": str(row.get("City", "")),
        "ZIP": str(row.get("ZIP", "")),
        "Phone": str(row.get("Phone", "")),
        "Expected": str(row.get("Expected", "")),
        "Gold_Source_URL": str(row.get("Gold_Source_URL", "")),
        "Gold_Notes": str(row.get("Gold_Notes", "")),
        "Rejection_Reason": reason,
    }


def build_registry(input_paths: Iterable[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    accepted_rows: list[dict[str, str]] = []
    rejected_rows: list[dict[str, str]] = []

    for path_value in input_paths:
        frame = pd.read_csv(path_value, dtype=str, keep_default_na=False)
        required = {
            "State", "Company", "Street", "City", "ZIP", "Phone",
            "Expected", "Gold_Source_URL", "Gold_Notes",
        }
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(
                "%s missing calibration columns: %s"
                % (Path(path_value).name, ", ".join(sorted(missing)))
            )

        for row in frame.to_dict(orient="records"):
            expected = str(row.get("Expected", "")).strip().upper()
            url = str(row.get("Gold_Source_URL", "")).strip()
            notes = str(row.get("Gold_Notes", "")).strip()

            if expected not in {"NAIL", "NOT_NAIL"}:
                rejected_rows.append(_reject(row, "UNRESOLVED_LABEL"))
                continue
            if not url:
                rejected_rows.append(_reject(row, "MISSING_BUSINESS_SOURCE"))
                continue

            if expected == "NAIL":
                observed_category = "Nail Salon"
                nail_service = notes
            else:
                observed_category = _affirmative_non_nail_category(notes, str(row.get("Company", "")))
                if not observed_category:
                    rejected_rows.append(_reject(row, "NOT_NAIL_CATEGORY_NOT_AFFIRMATIVE"))
                    continue
                nail_service = ""

            accepted_rows.append(
                {
                    "State": str(row.get("State", "")).strip().upper(),
                    "Company": str(row.get("Company", "")).strip(),
                    "Street": str(row.get("Street", "")).strip(),
                    "City": str(row.get("City", "")).strip(),
                    "ZIP": str(row.get("ZIP", "")).strip(),
                    "Phone": str(row.get("Phone", "")).strip(),
                    "Source_Name": _source_name(url),
                    "Source_Tier": source_tier_for(url, notes),
                    "Source_URL": url,
                    "Observed_Category": observed_category,
                    "Nail_Service_Evidence": nail_service,
                    "Business_Status_Evidence": "",
                    "Evidence_Direction": expected,
                    "Evidence_Notes": notes,
                    "Checked_At": _checked_at(notes),
                }
            )

    accepted = pd.DataFrame(accepted_rows, columns=REGISTRY_COLUMNS)
    if not accepted.empty:
        accepted = accepted.drop_duplicates(
            subset=[
                "State", "Company", "Street", "City", "ZIP", "Phone",
                "Source_URL", "Evidence_Direction",
            ],
            keep="first",
        ).sort_values(
            ["State", "Company", "Street", "Source_URL", "Evidence_Direction"],
            kind="stable",
        ).reset_index(drop=True)

    rejection_columns = [
        "State", "Company", "Street", "City", "ZIP", "Phone",
        "Expected", "Gold_Source_URL", "Gold_Notes", "Rejection_Reason",
    ]
    rejected = pd.DataFrame(rejected_rows, columns=rejection_columns)
    if not rejected.empty:
        rejected = rejected.drop_duplicates().sort_values(
            ["State", "Company", "Street", "Rejection_Reason"],
            kind="stable",
        ).reset_index(drop=True)

    return accepted, rejected


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    inputs = [
        root / "benchmarks" / "sd_rule_calibration_v33.csv",
        root / "benchmarks" / "sd_rule_calibration_v34_addendum.csv",
        root / "benchmarks" / "sd_address_strong_v35.csv",
    ]
    accepted, rejected = build_registry([str(path) for path in inputs])
    accepted.to_csv(root / "benchmarks" / "verified_business_evidence.csv", index=False)
    rejected.to_csv(root / "benchmarks" / "evidence_migration_rejections.csv", index=False)
    print("accepted=%d rejected=%d" % (len(accepted), len(rejected)))


if __name__ == "__main__":
    main()
