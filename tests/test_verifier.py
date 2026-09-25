import pandas as pd

from verifier import (
    detect_columns,
    extract_input,
    obvious_wrong_name,
    parse_license_rows,
    verify_dataframe,
)


class FakeLicenseClient:
    def __init__(self, by_zip=None):
        self.by_zip = by_zip or {}

    def search_zip(self, zip_code):
        return self.by_zip.get(zip_code, [])

    def search_company(self, company):
        return []


class FakeOSMClient:
    def __init__(self, items=None):
        self.items = items or []

    def search(self, data):
        return self.items


def df_row(**kwargs):
    return pd.DataFrame([kwargs])


def test_detect_columns_and_shifted_address():
    df = df_row(
        Company="Hang Nails Salon",
        Street="—",
        City="500 E Figzel Ct",
        State="SD",
        ZIP="57064",
        Phone="(605) 408-3617",
    )
    mapping = detect_columns(df.columns)
    data = extract_input(df.iloc[0], mapping)
    assert data["street"] == "500 E Figzel Ct"
    assert data["city"] == ""


def test_obvious_wrong_business_name():
    assert obvious_wrong_name("Alexandria Ace Hardware")
    assert obvious_wrong_name("Dollar General")
    assert not obvious_wrong_name("Luxury Nails Spa")


def test_parse_license_table():
    html = """
    <html><body><table>
      <tr><th>License #</th><th>Company</th><th>City</th><th>State</th><th>Zip</th><th>Type</th></tr>
      <tr><td>1234</td><td>Luxury Nails Spa</td><td>Aberdeen</td><td>SD</td><td>57401</td><td>Nail Salon</td></tr>
    </table></body></html>
    """
    rows = parse_license_rows(html)
    assert len(rows) == 1
    assert rows[0]["Company"] == "Luxury Nails Spa"


def test_real_nail_from_current_license():
    df = df_row(
        Company="Luxury Nails Spa",
        Street="3828 6th Ave SE C",
        City="Aberdeen",
        State="SD",
        ZIP="57401",
        Phone="6052293020",
        Status="OPERATIONAL",
        Reviews="50",
    )
    rows = [
        {
            "License #": "123",
            "Company": "Luxury Nails Spa",
            "City": "Aberdeen",
            "State": "SD",
            "Zip": "57401",
            "Type": "Nail Salon",
            "_raw": "123 | Luxury Nails Spa | Aberdeen | SD | 57401 | Nail Salon",
        }
    ]
    out = verify_dataframe(
        df,
        use_osm=False,
        license_client=FakeLicenseClient({"57401": rows}),
    )
    assert out.iloc[0]["Is_Real_Nail_Salon"] == "YES"
    assert out.iloc[0]["Verdict"] == "REAL_NAIL_SALON"


def test_wrong_business_fast_path():
    df = df_row(
        Company="Alexandria Ace Hardware",
        Street="421 Main St",
        City="Alexandria",
        State="SD",
        ZIP="57311",
        Status="OPERATIONAL",
        Reviews="10",
    )
    out = verify_dataframe(
        df, use_osm=False, license_client=FakeLicenseClient()
    )
    assert out.iloc[0]["Verdict"] == "WRONG_BUSINESS"
    assert out.iloc[0]["Is_Real_Nail_Salon"] == "NO"


def test_closed_from_source():
    df = df_row(
        Company="Old Nails",
        Street="10 Main St",
        City="Test",
        State="SD",
        ZIP="57000",
        Status="CLOSED TEMPORARILY",
        Reviews="20",
    )
    out = verify_dataframe(
        df, use_osm=False, license_client=FakeLicenseClient()
    )
    assert out.iloc[0]["Is_Real_Nail_Salon"] == "CLOSED"
    assert out.iloc[0]["Verdict"] == "CLOSED_FROM_SOURCE"


def test_osm_likely_real_nail():
    df = df_row(
        Company="Happy Nails",
        Street="100 Main St",
        City="Test",
        State="SD",
        ZIP="57000",
        Status="OPERATIONAL",
        Reviews="20",
    )
    item = {
        "display_name": "Happy Nails, 100 Main St, Test, SD 57000, United States",
        "namedetails": {"name": "Happy Nails"},
        "category": "shop",
        "type": "beauty",
        "extratags": {"beauty": "nails"},
    }
    out = verify_dataframe(
        df,
        use_osm=True,
        license_client=FakeLicenseClient(),
        osm_client=FakeOSMClient([item]),
    )
    assert out.iloc[0]["Verdict"] == "LIKELY_REAL_NAIL_SALON"
    assert out.iloc[0]["Is_Real_Nail_Salon"] == "YES"


def test_no_evidence_stays_review():
    df = df_row(
        Company="Unknown Place",
        Street="100 Main St",
        City="Test",
        State="SD",
        ZIP="57000",
        Status="OPERATIONAL",
        Reviews="0",
    )
    out = verify_dataframe(
        df, use_osm=False, license_client=FakeLicenseClient()
    )
    assert out.iloc[0]["Verdict"] == "REVIEW"
    assert out.iloc[0]["Is_Real_Nail_Salon"] == "REVIEW"
