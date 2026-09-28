from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from typing import Iterable, Tuple

import pandas as pd

DEFAULT_INPUTS = [
    "benchmarks/sd_rule_calibration_v33.csv",
    "benchmarks/sd_rule_calibration_v34_addendum.csv",
    "benchmarks/sd_address_strong_v35.csv",
]
MANUAL_INPUTS = ["benchmarks/sd_research_evidence_v37.csv"]
OUTPUT = "benchmarks/verified_business_evidence.csv"
REJECTIONS = "benchmarks/evidence_migration_rejections.csv"

REGISTRY_COLUMNS = [
    "State", "Company", "Street", "City", "ZIP", "Phone",
    "Source_Name", "Source_Tier", "Source_URL", "Observed_Category",
    "Nail_Service_Evidence", "Business_Status_Evidence", "Evidence_Direction",
    "Evidence_Notes", "Checked_At",
]
ALLOWED_DIRECTIONS = {"NAIL", "NOT_NAIL", "IDENTITY_ONLY", "STATUS_ONLY", "AMBIGUOUS"}
ALLOWED_TIERS = {"A", "B", "C", "D"}

TIER_A_HOSTS = {
    "acehardware.com", "dollargeneral.com", "truevalue.com", "coffeecupfuelstops.com",
    "rubyhousekeystone.com", "buildingcentersd.com", "silveradofranklin.com",
    "nailworldsd.com", "glamournailsspasd.com", "nailsbyjennytd.com",
    "tnailspasiouxfalls.com", "royalnail-spa.com", "skynailspasiouxfalls.com",
    "qdnailandspa.com", "ap10nailbar.com", "hy-vee.com", "doitbest.com",
    "bgbuildingcenter.com",
}
TIER_B_HOSTS = {
    "bbb.org", "maps.apple.com", "chamberofcommerce.com", "local.mitchellrepublic.com",
    "bowdlesd.com", "dnb.com", "hartfordsdchamber.org", "hbasiouxempire.com",
}
TIER_C_HOSTS = {
    "bestprosintown.com", "loc8nearme.com", "birdeye.com", "yellowpages.com",
    "verview.com", "nailsalondirectories.com", "localnailsalons.net", "local.yahoo.com",
    "restaurantguru.com", "waze.com", "locally.com", "nailartai.app", "baonail.com",
    "salonlookup.com", "usbeautyaward.com", "restaurantji.com", "tripadvisor.com",
}


def _host(url: str) -> str:
    host = (urlparse(str(url)).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def source_tier(url: str, notes: str = "") -> str:
    host = _host(url)
    text = str(notes).lower()
    if host.endswith("glossgenius.com") or host.endswith("booksy.com"):
        return "A" if any(term in text for term in ("official", "booking", "service")) else "C"
    if host in TIER_A_HOSTS or any(host.endswith("." + h) for h in TIER_A_HOSTS):
        return "A"
    if host in TIER_B_HOSTS or any(host.endswith("." + h) for h in TIER_B_HOSTS):
        return "B"
    if host in TIER_C_HOSTS or any(host.endswith("." + h) for h in TIER_C_HOSTS):
        return "C"
    return "C"


def _source_name(url: str) -> str:
    host = _host(url)
    return host or "CALIBRATION_SOURCE"


def _category(expected: str, company: str, notes: str) -> str:
    if expected == "NAIL":
        return "Nail Salon"
    text = f"{company} {notes}".lower()
    for label, terms in [
        ("Hardware Store", ("hardware", "building center", "lumberyard", "true value", "ace")),
        ("General Retail", ("dollar general", "discount store", "general retail")),
        ("Grocery Store", ("grocery", "supermarket", "hy-vee")),
        ("Restaurant", ("restaurant", "steakhouse", "buffet")),
        ("Fuel Stop", ("fuel stop", "convenience", "travel store")),
        ("Hotel/Gaming", ("hotel", "gaming")),
    ]:
        if any(term in text for term in terms):
            return label
    return "Clearly Non-Beauty Business"


def _load_manual_research(manual_paths: Iterable[str]) -> tuple[list[dict], list[dict]]:
    accepted: list[dict] = []
    rejected: list[dict] = []
    for path_value in manual_paths:
        path = Path(path_value)
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            item = {col: str(row.get(col, "")).strip() for col in REGISTRY_COLUMNS}
            tier = item["Source_Tier"].upper()
            direction = item["Evidence_Direction"].upper()
            if not item["Source_URL"] or tier not in ALLOWED_TIERS or direction not in ALLOWED_DIRECTIONS:
                rejected.append({
                    "State": item["State"], "Company": item["Company"], "Street": item["Street"],
                    "City": item["City"], "ZIP": item["ZIP"], "Phone": item["Phone"],
                    "Reason": "Invalid manual evidence row: source URL, tier, or direction",
                    "Source_File": path.name,
                })
                continue
            item["Source_Tier"] = tier
            item["Evidence_Direction"] = direction
            accepted.append(item)
    return accepted, rejected


def build_registry(input_paths: Iterable[str], manual_paths: Iterable[str] = ()) -> Tuple[pd.DataFrame, pd.DataFrame]:
    accepted = []
    rejected = []
    for path_value in input_paths:
        path = Path(path_value)
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            expected = str(row.get("Expected", "")).strip().upper()
            url = str(row.get("Gold_Source_URL", "")).strip()
            notes = str(row.get("Gold_Notes", "")).strip()
            if expected not in {"NAIL", "NOT_NAIL"} or not url:
                rejected.append({
                    "State": row.get("State", ""), "Company": row.get("Company", ""),
                    "Street": row.get("Street", ""), "City": row.get("City", ""),
                    "ZIP": row.get("ZIP", ""), "Phone": row.get("Phone", ""),
                    "Reason": "UNKNOWN label or missing business-specific source URL",
                    "Source_File": path.name,
                })
                continue
            tier = source_tier(url, notes)
            accepted.append({
                "State": row.get("State", ""),
                "Company": row.get("Company", ""),
                "Street": row.get("Street", ""),
                "City": row.get("City", ""),
                "ZIP": row.get("ZIP", ""),
                "Phone": row.get("Phone", ""),
                "Source_Name": _source_name(url),
                "Source_Tier": tier,
                "Source_URL": url,
                "Observed_Category": _category(expected, str(row.get("Company", "")), notes),
                "Nail_Service_Evidence": notes if expected == "NAIL" else "",
                "Business_Status_Evidence": row.get("Status", ""),
                "Evidence_Direction": expected,
                "Evidence_Notes": notes,
                "Checked_At": "2026-09-28",
            })

    manual_accepted, manual_rejected = _load_manual_research(manual_paths)
    accepted.extend(manual_accepted)
    rejected.extend(manual_rejected)

    accepted_df = pd.DataFrame(accepted, columns=REGISTRY_COLUMNS)
    rejected_df = pd.DataFrame(rejected)
    if not accepted_df.empty:
        accepted_df = accepted_df.drop_duplicates(subset=["State", "Company", "Street", "City", "ZIP", "Phone", "Source_URL", "Evidence_Direction"])
        accepted_df = accepted_df.sort_values(["State", "Company", "Source_URL"], kind="stable").reset_index(drop=True)
    if not rejected_df.empty:
        rejected_df = rejected_df.sort_values(["State", "Company", "Source_File"], kind="stable").reset_index(drop=True)
    return accepted_df, rejected_df


def main() -> None:
    accepted, rejected = build_registry(DEFAULT_INPUTS, MANUAL_INPUTS)
    Path(OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    accepted.to_csv(OUTPUT, index=False)
    rejected.to_csv(REJECTIONS, index=False)
    print(f"accepted={len(accepted)} rejected={len(rejected)}")


if __name__ == "__main__":
    main()
