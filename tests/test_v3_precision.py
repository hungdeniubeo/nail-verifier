from __future__ import annotations

import pandas as pd

from nailverifier_v3.engine import decide
from nailverifier_v3.models import BusinessRecord, Evidence
from nailverifier_v3.normalize import compare_names, detect_columns, row_to_record
from nailverifier_v3.states.sd import SouthDakotaAdapter, ROSTER_URL


class FakeHttp:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def get_text(self, url, **kwargs):
        self.calls.append(url)
        if url not in self.mapping:
            raise AssertionError("unexpected URL %s" % url)
        return self.mapping[url]


def roster_html(rows):
    body = []
    for license_no, company, city, state, zip_code in rows:
        body.append(
            f'<tr><td><a href="LicenseDetail.aspx?l={license_no}&t=b">{license_no}</a></td>'
            f'<td>12/31/2026</td><td>{company}</td><td>{city}</td><td>{state}</td><td>{zip_code}</td></tr>'
        )
    return (
        "<html><body><table>"
        "<tr><th>License #</th><th>Expires</th><th>Company</th><th>City</th><th>State</th><th>Zip</th></tr>"
        + "".join(body)
        + "</table></body></html>"
    )


def detail_html(license_no, license_type, business, street, city, state, zip_code):
    pairs = [
        ("License #", license_no),
        ("License Type", license_type),
        ("Expires", "12/31/2026"),
        ("Business", business),
        ("Street", street),
        ("City", city),
        ("State", state),
        ("Zip", zip_code),
    ]
    rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in pairs)
    return "<html><body><table>%s</table></body></html>" % rows


def test_generic_spa_words_do_not_false_match():
    match = compare_names("Audra Day Spa & Salon", "Revive Day Spa - Apprentice Salon")
    assert match.score < 0.50
    assert match.core_overlap == 0.0


def test_sd_adapter_rejects_audra_to_revive_same_zip():
    roster = roster_html([
        ("ASL-08594-2027", "REVIVE DAY SPA - APPRENTICE SALON", "ABERDEEN", "SD", "57401")
    ])
    detail_url = "https://apps.sd.gov/LD19Cosmetology/LicenseDetail.aspx?l=ASL-08594-2027&t=b"
    http = FakeHttp(
        {
            ROSTER_URL: roster,
            detail_url: detail_html(
                "ASL-08594-2027",
                "Apprentice Salon",
                "REVIVE DAY SPA - APPRENTICE SALON",
                "301 S MAIN ST",
                "ABERDEEN",
                "SD",
                "57401",
            ),
        }
    )
    adapter = SouthDakotaAdapter(http)
    record = BusinessRecord(
        company="Audra Day Spa & Salon",
        street="18 2nd Ave SE",
        city="Aberdeen",
        state="SD",
        zip_code="57401",
    )
    assert adapter.verify(record) is None


def test_sd_adapter_accepts_strict_pro_nails_match():
    roster = roster_html([
        ("NS-00001-2026", "PRO NAILS", "ABERDEEN", "SD", "57401")
    ])
    detail_url = "https://apps.sd.gov/LD19Cosmetology/LicenseDetail.aspx?l=NS-00001-2026&t=b"
    http = FakeHttp(
        {
            ROSTER_URL: roster,
            detail_url: detail_html(
                "NS-00001-2026",
                "Nail Salon",
                "PRO NAILS",
                "3015 6TH AVE SE #10",
                "ABERDEEN",
                "SD",
                "57401",
            ),
        }
    )
    adapter = SouthDakotaAdapter(http)
    record = BusinessRecord(
        company="Pro Nails",
        street="3015 6th Ave SE #10",
        city="Aberdeen",
        state="SD",
        zip_code="57401",
    )
    evidence = adapter.verify(record)
    assert evidence is not None
    assert evidence.strength == "STRONG_OFFICIAL"
    assert evidence.license_type == "Nail Salon"
    assert evidence.name_score == 100.0


def test_decision_verified_nail_requires_nail_specific_official_type():
    record = BusinessRecord(company="Pro Nails", state="SD")
    ev = Evidence(
        source="SD_COSMETOLOGY",
        strength="STRONG_OFFICIAL",
        matched_name="PRO NAILS",
        license_type="Nail Salon",
    )
    result = decide(record, [ev], [], "OFFICIAL")
    assert result["Decision"] == "VERIFIED_NAIL"
    assert result["Auto_Action"] == "KEEP"
    assert result["Confidence"] == 99


def test_broad_beauty_license_does_not_become_verified_nail():
    record = BusinessRecord(company="Audra Day Spa & Salon", state="SD")
    ev = Evidence(
        source="SD_COSMETOLOGY",
        strength="STRONG_OFFICIAL",
        matched_name="Audra Day Spa & Salon",
        license_type="Cosmetology Salon",
    )
    result = decide(record, [ev], [], "OFFICIAL")
    assert result["Decision"] == "VERIFIED_BEAUTY_REVIEW_NAIL"
    assert result["Auto_Action"] == "REVIEW"


def test_osm_nonbeauty_can_auto_remove_only_when_independently_matched():
    record = BusinessRecord(company="Alexandria Ace Hardware", state="SD")
    ev = Evidence(
        source="OPENSTREETMAP",
        strength="STRONG_INDEPENDENT_NOT_NAIL",
        matched_name="Alexandria Ace Hardware",
        category="shop / hardware",
    )
    result = decide(record, [ev], [], "OFFICIAL")
    assert result["Decision"] == "VERIFIED_NOT_NAIL"
    assert result["Auto_Action"] == "REMOVE"


def test_name_only_non_nail_never_auto_removes():
    record = BusinessRecord(company="Alexandria Ace Hardware", state="SD", status="OPERATIONAL")
    result = decide(record, [], [], "OFFICIAL")
    assert result["Decision"] == "LIKELY_NOT_NAIL"
    assert result["Auto_Action"] == "REVIEW"


def test_nailmap_only_never_becomes_verified():
    record = BusinessRecord(
        company="Luxury Nails Spa",
        street="3828 6th Ave SE C",
        city="Aberdeen",
        state="SD",
        zip_code="57401",
        phone="6052293020",
        rating=4.1,
        reviews=161,
        status="OPERATIONAL",
    )
    result = decide(record, [], [], "OFFICIAL")
    assert result["Decision"] == "LIKELY_NAIL"
    assert result["Auto_Action"] == "REVIEW"
    assert result["Confidence"] <= 85


def test_shifted_address_is_recovered():
    df = pd.DataFrame([
        {
            "State": "SD",
            "Company": "Hang Nails Salon",
            "Street": "—",
            "City": "500 E Figzel Ct",
            "ZIP": "57064",
            "Phone": "(605) 408-3617",
        }
    ])
    mapping = detect_columns(df.columns)
    record = row_to_record(df.iloc[0], mapping)
    assert record.street == "500 E Figzel Ct"
    assert record.city == ""
    assert record.phone == "6054083617"


def test_sd_adapter_accepts_distinctive_dba_variant_at_same_address():
    roster = roster_html([
        ("ASL-08594-2027", "REVIVE DAY SPA - APPRENTICE SALON", "ABERDEEN", "SD", "57401")
    ])
    detail_url = "https://apps.sd.gov/LD19Cosmetology/LicenseDetail.aspx?l=ASL-08594-2027&t=b"
    http = FakeHttp(
        {
            ROSTER_URL: roster,
            detail_url: detail_html(
                "ASL-08594-2027",
                "Apprentice Salon",
                "REVIVE DAY SPA - APPRENTICE SALON",
                "301 S MAIN ST",
                "ABERDEEN",
                "SD",
                "57401",
            ),
        }
    )
    adapter = SouthDakotaAdapter(http)
    record = BusinessRecord(
        company="Revive Salon & Day Spa",
        street="301 S Main St",
        city="Aberdeen",
        state="SD",
        zip_code="57401",
    )
    evidence = adapter.verify(record)
    assert evidence is not None
    assert evidence.matched_name == "REVIVE DAY SPA - APPRENTICE SALON"


def test_sd_warmup_builds_local_indexes_once():
    roster = roster_html([
        ("NS-1", "PRO NAILS", "ABERDEEN", "SD", "57401"),
        ("NS-2", "OTHER NAILS", "TEA", "SD", "57064"),
    ])
    http = FakeHttp({ROSTER_URL: roster})
    adapter = SouthDakotaAdapter(http)

    stats1 = adapter.warmup()
    stats2 = adapter.warmup()

    assert stats1["roster_rows"] == 2
    assert stats1["zip_buckets"] == 2
    assert stats2 == stats1
    assert http.calls.count(ROSTER_URL) == 1
