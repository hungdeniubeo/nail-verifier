from __future__ import annotations

from typing import Dict, Optional, Tuple

from .models import BusinessRecord
from .normalize import (
    normalize_name,
    normalize_phone,
    normalize_street,
    normalize_text,
    normalize_zip,
)

# State-scoped calibrated rules.
# South Dakota R_NAIL_EXPLICIT_STRONG reached 74/74 labeled correct cases
# across the base calibration + v34 addendum, with Wilson 95% lower bound
# just above the 0.95 gate. The generic REMOVE rule remains shadow-only:
# exact verified NOT_NAIL identities below may REMOVE, but unseen businesses
# never inherit that action from the category rule alone.
VALIDATED_RULES: Dict[str, Dict[str, str]] = {
    "SD": {
        "R_NAIL_EXPLICIT_STRONG": "KEEP",
    },
}

# Exact identities independently verified during the SD v3.5 address-strong
# calibration. This is deliberately NOT a generic rule: name + full normalized
# street (including suite/unit) + city + ZIP must match one of these records.
# K & E Nail Studio LLC is intentionally absent because current public evidence
# was insufficient to verify that exact identity.
VERIFIED_IDENTITY_ALLOWLIST: Dict[str, Dict[Tuple[str, str, str, str], str]] = {
    "SD": {
        (normalize_name("Anna's Nails"), normalize_street("712 University Ave Ste A"), normalize_text("Hot Springs"), "57747"): "KEEP",
        (normalize_name("Nails By Alayna Reyes"), normalize_street("901 N Main St Ste 4"), normalize_text("Mitchell"), "57301"): "KEEP",
        (normalize_name("Olive & Opal Nail Studio"), normalize_street("501 Main St Studio 4"), normalize_text("Rapid City"), "57701"): "KEEP",
        (normalize_name("Simplee Nails"), normalize_street("317 Main St Ste 1"), normalize_text("Rapid City"), "57701"): "KEEP",
        (normalize_name("The Nail Room"), normalize_street("822 Main St Ste 5"), normalize_text("Rapid City"), "57701"): "KEEP",
        (normalize_name("The Nail Haus By Adamari"), normalize_street("5201 S Solberg Ave suite 205"), normalize_text("Sioux Falls"), "57108"): "KEEP",
        (normalize_name("Zen Nail Studio"), normalize_street("5201 S Solberg Ave suite 200"), normalize_text("Sioux Falls"), "57108"): "KEEP",
    },
}

# All 35 current SD R_NON_NAIL_CATEGORY_STRONG rows were independently checked
# in sd_rule_calibration_v33.csv + sd_rule_calibration_v34_addendum.csv. We do
# NOT generalize that result to future hardware/retail/restaurant rows. REMOVE
# requires exact name + full street + city + ZIP + phone identity match here.
VERIFIED_NOT_NAIL_ALLOWLIST: Dict[
    str, Dict[Tuple[str, str, str, str, str], str]
] = {
    "SD": {
        (normalize_name("Bowdle Building & Hardware"), normalize_street("32575 US-12"), normalize_text("Bowdle"), "57428", "6052856303"): "REMOVE",
        (normalize_name("Burke Building Center"), normalize_street("1307 Main St"), normalize_text("Burke"), "57523", "6057752400"): "REMOVE",
        (normalize_name("Burke True Value"), normalize_street("906 Main St"), normalize_text("Burke"), "57523", "6057752804"): "REMOVE",
        (normalize_name("Chamberlain Ace Hardware"), normalize_street("1951 E King St"), normalize_text("Chamberlain"), "57325", "6052341066"): "REMOVE",
        (normalize_name("Dollar General"), normalize_street("200 S Main Ave"), normalize_text("Colton"), "57018", "6052218568"): "REMOVE",
        (normalize_name("Corsica Hardware"), normalize_street("140 E Main St"), normalize_text("Corsica"), "57328", "6059465481"): "REMOVE",
        (normalize_name("Silverado Franklin Historic Hotel & Gaming Complex, Legends Steakhouse & Silverado Grand Buffet"), normalize_street("709 Main St"), normalize_text("Deadwood"), "57732", "6055783670"): "REMOVE",
        (normalize_name("Elk Point Ace Hardware"), normalize_street("609 W Main St"), normalize_text("Elk Point"), "57025", "6053563311"): "REMOVE",
        (normalize_name("Dollar General"), normalize_street("25378 485th Ave"), normalize_text("Garretson"), "57030", "6052150987"): "REMOVE",
        (normalize_name("Dollar General"), normalize_street("410 W Garfield Ave"), normalize_text("Gettysburg"), "57442", "6052299912"): "REMOVE",
        (normalize_name("Gettysburg Ace Hardware Inc."), normalize_street("30960 US-212"), normalize_text("Gettysburg"), "57442", "6057659400"): "REMOVE",
        (normalize_name("Gettysburg True Value"), normalize_street("107 W Commercial Ave"), normalize_text("Gettysburg"), "57442", "6057652183"): "REMOVE",
        (normalize_name("Dollar General"), normalize_street("207 US-18"), normalize_text("Gregory"), "57533", "6052991996"): "REMOVE",
        (normalize_name("Gregory Building Center & Rental"), normalize_street("122 S Main St"), normalize_text("Gregory"), "57533", "6058358781"): "REMOVE",
        (normalize_name("Harrisburg Ace Hardware"), normalize_street("200 E Willow St"), normalize_text("Harrisburg"), "57032", "6052130600"): "REMOVE",
        (normalize_name("Hy-Vee Grocery Store"), normalize_street("201 E Willow St"), normalize_text("Harrisburg"), "57032", "6052132222"): "REMOVE",
        (normalize_name("Coffee Cup Fuel Stop"), normalize_street("1001 S Western Ave"), normalize_text("Hartford"), "57033", "6055284622"): "REMOVE",
        (normalize_name("Hartford Ace Hardware"), normalize_street("701 S Western Ave"), normalize_text("Hartford"), "57033", "6055283300"): "REMOVE",
        (normalize_name("Hartford Building Center"), normalize_street("1001 N Oaks Ave"), normalize_text("Hartford"), "57033", "6055283495"): "REMOVE",
        (normalize_name("Ruby House Restaurant"), normalize_street("124 Winter St"), normalize_text("Keystone"), "57751", "6056664404"): "REMOVE",
        (normalize_name("Ace Hardware - Lead"), normalize_street("145 Glendale Dr"), normalize_text("Lead"), "57754", "6055591110"): "REMOVE",
        (normalize_name("Schmidt Country True Value"), normalize_street("303 W Park Ave"), normalize_text("Marion"), "57043", "6056483631"): "REMOVE",
        (normalize_name("Buche Ace Hardware"), normalize_street("301 US-18"), normalize_text("Martin"), "57551", "6056856730"): "REMOVE",
        (normalize_name("Dollar General"), normalize_street("217 Bennett Ave"), normalize_text("Martin"), "57551", "6053054115"): "REMOVE",
        (normalize_name("Newell Hardware & Supply"), normalize_street("320 Girard Ave"), normalize_text("Newell"), "57760", "6054562313"): "REMOVE",
        (normalize_name("Parker Ace Hardware"), normalize_street("1105 E 6th St"), normalize_text("Parker"), "57053", "6057893031"): "REMOVE",
        (normalize_name("Roscoe Trustworthy Hardware"), normalize_street("104 Mitchell St"), normalize_text("Roscoe"), "57471", "6052874411"): "REMOVE",
        (normalize_name("Scotland Hardware"), normalize_street("511 Main St"), normalize_text("Scotland"), "57059", "6055834512"): "REMOVE",
        (normalize_name("Tyndall Ace Hardware"), normalize_street("802 Main St"), normalize_text("Tyndall"), "57066", "6055894700"): "REMOVE",
        (normalize_name("Dakota Ace Hardware"), normalize_street("106 N Main St"), normalize_text("Viborg"), "57070", "6057665097"): "REMOVE",
        (normalize_name("Coffee Cup Fuel Stop"), normalize_street("US-83"), normalize_text("Vivian"), "57576", "6056834666"): "REMOVE",
        (normalize_name("Dollar General"), normalize_street("204 US-14"), normalize_text("Volga"), "57071", "6056271027"): "REMOVE",
        (normalize_name("Volga Ace Hardware"), normalize_street("114 US-14"), normalize_text("Volga"), "57071", "6058272020"): "REMOVE",
        (normalize_name("New Frontier - Steakhouse & Lounge"), normalize_street("500 Main St"), normalize_text("Webster"), "57274", "6053459988"): "REMOVE",
        (normalize_name("Webster Ace Hardware"), normalize_street("20 US-12"), normalize_text("Webster"), "57274", "6053453821"): "REMOVE",
    },
}

MIN_RULE_SAMPLES_KEEP = 20
MIN_RULE_SAMPLES_REMOVE = 20
MIN_KEEP_PRECISION = 0.99
MIN_REMOVE_PRECISION = 0.995
MIN_WILSON_LOWER_BOUND = 0.95


def _verified_identity_key(record: BusinessRecord) -> Tuple[str, str, str, str]:
    return (
        normalize_name(record.company),
        normalize_street(record.street),
        normalize_text(record.city),
        normalize_zip(record.zip_code),
    )


def _verified_not_nail_identity_key(
    record: BusinessRecord,
) -> Tuple[str, str, str, str, str]:
    return (
        normalize_name(record.company),
        normalize_street(record.street),
        normalize_text(record.city),
        normalize_zip(record.zip_code),
        normalize_phone(record.phone),
    )


def apply_verified_identity_policy(
    record: BusinessRecord,
    rule_id: str,
    candidate_action: str,
) -> Optional[Dict[str, str]]:
    """Allow only exact independently verified identities; never generalize."""
    state = (record.state or "").upper()

    if rule_id == "R_NAIL_EXPLICIT_ADDRESS_STRONG" and candidate_action == "KEEP":
        allowed_action = VERIFIED_IDENTITY_ALLOWLIST.get(state, {}).get(
            _verified_identity_key(record)
        )
        if allowed_action == candidate_action:
            return {
                "Auto_Action": candidate_action,
                "Policy_Status": "VERIFIED_IDENTITY_ALLOWLIST",
            }

    if rule_id == "R_NON_NAIL_CATEGORY_STRONG" and candidate_action == "REMOVE":
        allowed_action = VERIFIED_NOT_NAIL_ALLOWLIST.get(state, {}).get(
            _verified_not_nail_identity_key(record)
        )
        if allowed_action == candidate_action:
            return {
                "Auto_Action": candidate_action,
                "Policy_Status": "VERIFIED_IDENTITY_ALLOWLIST",
            }

    return None


def apply_policy(
    state: str,
    decision: str,
    evidence_tier: str,
    rule_id: str,
    candidate_action: str,
    allow_validated_rules: bool = False,
) -> Dict[str, str]:
    state = (state or "").upper()

    # A nail-specific current official state license is the strongest source.
    if decision == "VERIFIED_NAIL" and evidence_tier == "OFFICIAL_STATE":
        return {
            "Auto_Action": "KEEP",
            "Policy_Status": "SAFE_OFFICIAL",
        }

    if allow_validated_rules:
        enabled = VALIDATED_RULES.get(state, {})
        allowed_action = enabled.get(rule_id)
        if allowed_action and allowed_action == candidate_action:
            return {
                "Auto_Action": candidate_action,
                "Policy_Status": "BENCHMARK_VALIDATED_RULE",
            }

    if candidate_action in {"KEEP", "REMOVE"}:
        return {
            "Auto_Action": "REVIEW",
            "Policy_Status": "CANDIDATE_NEEDS_BENCHMARK",
        }

    return {
        "Auto_Action": "REVIEW",
        "Policy_Status": "REVIEW_ONLY",
    }
