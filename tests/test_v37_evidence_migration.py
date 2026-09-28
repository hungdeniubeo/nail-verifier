from __future__ import annotations

from pathlib import Path

import pandas as pd


def _write(path: Path, rows: list[dict[str, str]]) -> Path:
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def row(company: str, expected: str, url: str, notes: str, **overrides: str) -> dict[str, str]:
    result = {
        "State": "SD",
        "Company": company,
        "Street": "100 Main St",
        "City": "Sioux Falls",
        "ZIP": "57104",
        "Phone": "6055550100",
        "Rating": "5.0",
        "Reviews": "10",
        "Status": "OPERATIONAL",
        "Expected": expected,
        "Gold_Source_URL": url,
        "Gold_Notes": notes,
    }
    result.update(overrides)
    return result


def test_source_tier_mapping_is_conservative():
    from scripts.build_verified_business_evidence import source_tier_for

    assert source_tier_for("https://thenailhaus605.glossgenius.com/about", "Official booking site lists nail services") == "A"
    assert source_tier_for("https://www.acehardware.com/store-details/17989", "Official Ace page identifies hardware store") == "A"
    assert source_tier_for("https://rubyhousekeystone.com/", "Official website confirms restaurant") == "A"
    assert source_tier_for("https://www.ap10nailbar.com/locations", "Official business locations page lists this salon") == "A"
    assert source_tier_for("https://www.bbb.org/example", "BBB classifies matching business") == "B"
    assert source_tier_for("https://maps.apple.com/place?id=1", "Apple Maps classifies business") == "B"
    assert source_tier_for("https://www.chamberofcommerce.com/example", "Chamber directory") == "B"
    assert source_tier_for("https://bowdlesd.com/business-directory", "Official city directory") == "B"
    assert source_tier_for("https://www.bestprosintown.com/example", "Independent listing") == "C"
    assert source_tier_for("https://www.loc8nearme.com/example", "Independent listing") == "C"
    assert source_tier_for("https://reviews.birdeye.com/example", "Independent listing") == "C"
    assert source_tier_for("https://unknown-provider.example/item", "Independent listing") == "C"


def test_build_registry_accepts_real_directional_rows_and_rejects_unknown(tmp_path: Path):
    from scripts.build_verified_business_evidence import build_registry

    source = _write(
        tmp_path / "gold.csv",
        [
            row("The Nail Haus By Adamari", "NAIL", "https://thenailhaus605.glossgenius.com/about", "Official booking site lists acrylic, manicure and pedicure services."),
            row("Buche Ace Hardware", "NOT_NAIL", "https://www.acehardware.com/store-details/17989", "Official Ace page identifies matching hardware store."),
            row("Bowdle Building & Hardware", "NOT_NAIL", "https://bowdlesd.com/business-directory", "Official city directory lists Building & Hardware at matching address."),
            row("Anna's Nails", "NAIL", "https://localnailsalons.net/South-Dakota", "Independent directory lists exact business as a nail salon."),
            row("K & E Nail Studio LLC", "UNKNOWN", "", "No sufficiently strong independent source found."),
        ],
    )

    accepted, rejected = build_registry([str(source)])
    indexed = accepted.set_index("Company")

    assert indexed.loc["The Nail Haus By Adamari", "Source_Tier"] == "A"
    assert indexed.loc["The Nail Haus By Adamari", "Evidence_Direction"] == "NAIL"
    assert indexed.loc["Buche Ace Hardware", "Source_Tier"] == "A"
    assert indexed.loc["Buche Ace Hardware", "Evidence_Direction"] == "NOT_NAIL"
    assert indexed.loc["Bowdle Building & Hardware", "Source_Tier"] == "B"
    assert indexed.loc["Anna's Nails", "Source_Tier"] == "C"
    assert "K & E Nail Studio LLC" not in set(accepted["Company"])
    assert "K & E Nail Studio LLC" in set(rejected["Company"])


def test_duplicate_same_identity_url_direction_is_deduplicated(tmp_path: Path):
    from scripts.build_verified_business_evidence import build_registry

    duplicate = row(
        "Zen Nail Studio",
        "NAIL",
        "https://zennailstudiosf.glossgenius.com/about",
        "Official booking site explicitly identifies business as a nail salon.",
    )
    a = _write(tmp_path / "a.csv", [duplicate])
    b = _write(tmp_path / "b.csv", [duplicate])

    accepted, rejected = build_registry([str(a), str(b)])
    assert len(accepted) == 1
    assert rejected.empty


def test_not_nail_without_affirmative_nonbeauty_category_is_rejected(tmp_path: Path):
    from scripts.build_verified_business_evidence import build_registry

    source = _write(
        tmp_path / "gold.csv",
        [row("Mystery Business", "NOT_NAIL", "https://example.com/mystery", "Matching business found, no other details.")],
    )
    accepted, rejected = build_registry([str(source)])
    assert accepted.empty
    assert rejected.iloc[0]["Rejection_Reason"] == "NOT_NAIL_CATEGORY_NOT_AFFIRMATIVE"


def test_location_specific_primary_source_for_another_city_is_rejected(tmp_path: Path):
    from scripts.build_verified_business_evidence import build_registry

    source = _write(
        tmp_path / "gold.csv",
        [
            row(
                "Coffee Cup Fuel Stop",
                "NOT_NAIL",
                "https://www.coffeecupfuelstops.com/hartford",
                "Official site identifies fuel stop/convenience/travel store.",
                City="Vivian",
                Street="US-83",
                ZIP="57576",
                Phone="6056834666",
            )
        ],
    )

    accepted, rejected = build_registry([str(source)])
    assert accepted.empty
    assert rejected.iloc[0]["Rejection_Reason"] == "SOURCE_LOCATION_CONFLICT"


def test_location_specific_primary_source_matching_city_is_accepted(tmp_path: Path):
    from scripts.build_verified_business_evidence import build_registry

    source = _write(
        tmp_path / "gold.csv",
        [
            row(
                "Coffee Cup Fuel Stop",
                "NOT_NAIL",
                "https://www.coffeecupfuelstops.com/hartford",
                "Official site identifies fuel stop/convenience/travel store.",
                City="Hartford",
                Street="1001 S Western Ave",
                ZIP="57033",
                Phone="6055284622",
            )
        ],
    )

    accepted, rejected = build_registry([str(source)])
    assert len(accepted) == 1
    assert rejected.empty
