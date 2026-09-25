import pandas as pd

from verifier import build_query, detect_columns, extract_input, verify_dataframe


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.queries = []

    def search(self, query, page_size=5):
        self.queries.append(query)
        return self.responses.get(query, self.responses.get("*", []))


def df_row(**kwargs):
    return pd.DataFrame([kwargs])


def test_detect_nailmap_columns():
    df = df_row(Company="A", Street="1 Main St", City="X", State="SD", ZIP="57000", Phone="605-111-2222")
    mapping = detect_columns(df.columns)
    assert mapping["company"] == "Company"
    assert mapping["street"] == "Street"
    assert mapping["phone"] == "Phone"


def test_nailmap_shifted_street_in_city_is_recovered():
    df = df_row(Company="Hang Nails Salon", Street="—", City="500 E Figzel Ct", State="SD", ZIP="57064", Phone="(605) 408-3617")
    mapping = detect_columns(df.columns)
    data = extract_input(df.iloc[0], mapping)
    assert data["street"] == "500 E Figzel Ct"
    assert data["city"] == ""
    assert "500 E Figzel Ct" in build_query(data)


def test_real_nail_salon():
    df = df_row(Company="Luxury Nails Spa", Street="3828 6th Ave SE C", City="Aberdeen", State="SD", ZIP="57401", Phone="6052293020")
    place = {
        "displayName": {"text": "Luxury Nails Spa"},
        "formattedAddress": "3828 6th Ave SE C, Aberdeen, SD 57401, USA",
        "nationalPhoneNumber": "(605) 229-3020",
        "businessStatus": "OPERATIONAL",
        "primaryType": "nail_salon",
        "types": ["nail_salon", "beauty_salon"],
        "googleMapsUri": "https://maps.google.com/example",
    }
    out = verify_dataframe(df, api_key="unused", client=FakeClient({"*": [place]}), delay_seconds=0)
    assert out.iloc[0]["Is_Real_Nail_Salon"] == "YES"
    assert out.iloc[0]["Verdict"] == "REAL_NAIL_SALON"


def test_wrong_business():
    df = df_row(Company="Alexandria Ace Hardware", Street="421 Main St", City="Alexandria", State="SD", ZIP="57311", Phone="6052394445")
    place = {
        "displayName": {"text": "Alexandria Ace Hardware"},
        "formattedAddress": "421 Main St, Alexandria, SD 57311, USA",
        "nationalPhoneNumber": "(605) 239-4445",
        "businessStatus": "OPERATIONAL",
        "primaryType": "hardware_store",
        "types": ["hardware_store", "store"],
    }
    out = verify_dataframe(df, api_key="unused", client=FakeClient({"*": [place]}), delay_seconds=0)
    assert out.iloc[0]["Is_Real_Nail_Salon"] == "NO"
    assert out.iloc[0]["Verdict"] == "WRONG_BUSINESS"


def test_closed_nail_salon():
    df = df_row(Company="Old Nails", Street="10 Main St", City="Test", State="SD", ZIP="57000", Phone="6051112222")
    place = {
        "displayName": {"text": "Old Nails"},
        "formattedAddress": "10 Main St, Test, SD 57000, USA",
        "nationalPhoneNumber": "(605) 111-2222",
        "businessStatus": "CLOSED_PERMANENTLY",
        "primaryType": "nail_salon",
        "types": ["nail_salon"],
    }
    out = verify_dataframe(df, api_key="unused", client=FakeClient({"*": [place]}), delay_seconds=0)
    assert out.iloc[0]["Is_Real_Nail_Salon"] == "CLOSED"
    assert out.iloc[0]["Verdict"] == "CLOSED_PERMANENTLY"


def test_no_result_is_review_not_fake():
    df = df_row(Company="Unknown Nails", Street="99 Main St", City="Nowhere", State="SD", ZIP="57000", Phone="")
    out = verify_dataframe(df, api_key="unused", client=FakeClient({"*": []}), delay_seconds=0)
    assert out.iloc[0]["Is_Real_Nail_Salon"] == "REVIEW"
    assert out.iloc[0]["Verdict"] == "REVIEW"
