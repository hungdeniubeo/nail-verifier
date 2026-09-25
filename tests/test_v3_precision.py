from __future__ import annotations

import pandas as pd

from nailverifier_v3.engine import decide
from nailverifier_v3.features import assess_local
from nailverifier_v3.models import BusinessRecord, Evidence
from nailverifier_v3.normalize import compare_names, detect_columns, row_to_record
from nailverifier_v3.policy import apply_policy
from nailverifier_v3.states.sd import ROSTER_URL, SouthDakotaAdapter


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
                "Apprentice Salon License",
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
                "Apprentice Salon License",
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


def test_official_nail_license_is_safe_auto_keep():
    record = BusinessRecord(company="Pro Nails", state="SD")
    local = assess_local(record)
    ev = Evidence(
        source="SD_COSMETOLOGY",
        strength="STRONG_OFFICIAL",
        matched_name="PRO NAILS",
        license_type="Nail Salon",
    )
    decision = decide(record, [ev], [], "OFFICIAL", local)
    policy = apply_policy(
        "SD",
        decision["Decision"],
        decision["Evidence_Tier"],
        local.rule_id,
        decision["Candidate_Action"],
    )
    assert decision["Decision"] == "VERIFIED_NAIL"
    assert decision["Candidate_Action"] == "KEEP"
    assert policy["Auto_Action"] == "KEEP"
    assert policy["Policy_Status"] == "SAFE_OFFICIAL"


def test_broad_beauty_license_does_not_become_verified_nail():
    record = BusinessRecord(company="Audra Day Spa & Salon", state="SD")
    local = assess_local(record)
    ev = Evidence(
        source="SD_COSMETOLOGY",
        strength="STRONG_OFFICIAL",
        matched_name="Audra Day Spa & Salon",
        license_type="Cosmetology Salon",
    )
    result = decide(record, [ev], [], "OFFICIAL", local)
    assert result["Decision"] == "VERIFIED_BEAUTY_REVIEW_NAIL"
    assert result["Candidate_Action"] == "REVIEW"


def test_explicit_nail_structured_listing_is_candidate_keep_but_policy_blocks():
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
    local = assess_local(record)
    result = decide(record, [], [], "OFFICIAL", local)
    policy = apply_policy(
        "SD",
        result["Decision"],
        result["Evidence_Tier"],
        local.rule_id,
        result["Candidate_Action"],
    )
    assert local.rule_id == "R_NAIL_EXPLICIT_STRONG"
    assert result["Candidate_Action"] == "KEEP"
    assert policy["Auto_Action"] == "REVIEW"
    assert policy["Policy_Status"] == "CANDIDATE_NEEDS_BENCHMARK"


def test_explicit_non_nail_structured_listing_is_candidate_remove_but_policy_blocks():
    record = BusinessRecord(
        company="Alexandria Ace Hardware",
        street="701 Spruce St",
        city="Alexandria",
        state="SD",
        zip_code="57311",
        phone="6052394444",
        reviews=20,
        status="OPERATIONAL",
    )
    local = assess_local(record)
    result = decide(record, [], [], "OFFICIAL", local)
    policy = apply_policy(
        "SD",
        result["Decision"],
        result["Evidence_Tier"],
        local.rule_id,
        result["Candidate_Action"],
    )
    assert local.rule_id == "R_NON_NAIL_CATEGORY_STRONG"
    assert result["Candidate_Action"] == "REMOVE"
    assert policy["Auto_Action"] == "REVIEW"


def test_low_evidence_nail_name_never_auto_keeps():
    record = BusinessRecord(
        company="Kathy's Nails",
        street="412 4th St",
        city="Brookings",
        state="SD",
        zip_code="57006",
        phone="6056925556",
        reviews=1,
        status="OPERATIONAL",
    )
    local = assess_local(record)
    assert local.rule_id == "R_NAIL_EXPLICIT_WEAK"
    assert local.candidate_action == "REVIEW"


def test_permanently_closed_source_is_candidate_only_not_auto_remove():
    record = BusinessRecord(
        company="Example Nails",
        street="1 Main St",
        city="Test",
        state="SD",
        zip_code="57000",
        phone="6050000000",
        reviews=20,
        status="CLOSED PERMANENTLY",
    )
    local = assess_local(record)
    result = decide(record, [], [], "OFFICIAL", local)
    policy = apply_policy(
        "SD",
        result["Decision"],
        result["Evidence_Tier"],
        local.rule_id,
        result["Candidate_Action"],
    )
    assert result["Candidate_Action"] == "REMOVE"
    assert policy["Auto_Action"] == "REVIEW"


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
