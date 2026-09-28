from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.build_verified_business_evidence import build_registry, source_tier


def test_source_tiers_are_conservative():
    assert source_tier("https://www.acehardware.com/store-details/1", "Official Ace page") == "A"
    assert source_tier("https://thenailhaus605.glossgenius.com/about", "Official booking site") == "A"
    assert source_tier("https://www.bbb.org/x", "BBB classifies") == "B"
    assert source_tier("https://maps.apple.com/x", "Apple Maps classifies") == "B"
    assert source_tier("https://www.bestprosintown.com/x", "Independent listing") == "C"
    assert source_tier("https://unknown.example/x", "Independent listing") == "C"


def test_build_registry_rejects_unknown_and_keeps_business_specific_source(tmp_path: Path):
    source = tmp_path / "gold.csv"
    pd.DataFrame([
        {
            "State":"SD","Company":"The Nail Haus By Adamari","Street":"5201 S Solberg Ave suite 205","City":"Sioux Falls","ZIP":"57108","Phone":"",
            "Status":"OPERATIONAL","Expected":"NAIL","Gold_Source_URL":"https://thenailhaus605.glossgenius.com/about","Gold_Notes":"Official booking site lists manicure and pedicure."
        },
        {
            "State":"SD","Company":"K & E Nail Studio LLC","Street":"522 7th St Suite 221","City":"Rapid City","ZIP":"57701","Phone":"",
            "Status":"OPERATIONAL","Expected":"UNKNOWN","Gold_Source_URL":"","Gold_Notes":"Insufficient evidence."
        },
    ]).to_csv(source, index=False)

    accepted, rejected = build_registry([str(source)])

    assert accepted.iloc[0]["Source_Tier"] == "A"
    assert accepted.iloc[0]["Evidence_Direction"] == "NAIL"
    assert "manicure" in accepted.iloc[0]["Nail_Service_Evidence"].lower()
    assert rejected.iloc[0]["Company"] == "K & E Nail Studio LLC"


def test_official_non_nail_source_migrates_as_tier_a(tmp_path: Path):
    source = tmp_path / "gold.csv"
    pd.DataFrame([{
        "State":"SD","Company":"Buche Ace Hardware","Street":"301 US-18","City":"Martin","ZIP":"57551","Phone":"6056856730",
        "Status":"OPERATIONAL","Expected":"NOT_NAIL","Gold_Source_URL":"https://www.acehardware.com/store-details/17989","Gold_Notes":"Official Ace page identifies hardware store."
    }]).to_csv(source, index=False)
    accepted, _ = build_registry([str(source)])
    row = accepted.iloc[0]
    assert row["Source_Tier"] == "A"
    assert row["Evidence_Direction"] == "NOT_NAIL"
    assert "hardware" in row["Observed_Category"].lower()


def test_bowdle_city_directory_is_tier_b_not_auto_primary(tmp_path: Path):
    source = tmp_path / "gold.csv"
    pd.DataFrame([{
        "State":"SD","Company":"Bowdle Building & Hardware","Street":"32575 US-12","City":"Bowdle","ZIP":"57428","Phone":"6052856303",
        "Status":"OPERATIONAL","Expected":"NOT_NAIL","Gold_Source_URL":"https://bowdlesd.com/business-directory","Gold_Notes":"Official city directory lists Building & Hardware."
    }]).to_csv(source, index=False)
    accepted, _ = build_registry([str(source)])
    assert accepted.iloc[0]["Source_Tier"] == "B"
