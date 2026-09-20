import json
from pathlib import Path


def test_country_parity():
    backend_path = Path("src/pitchvalue/data/countries.json")
    mobile_path = Path("mobile/lib/countries.json")

    assert backend_path.exists(), "Backend canonical country source missing"
    assert mobile_path.exists(), "Mobile country artifact missing"

    with open(backend_path, encoding="utf-8") as f:
        backend_data = json.load(f)

    with open(mobile_path, encoding="utf-8") as f:
        mobile_data = json.load(f)

    assert backend_data == mobile_data, (
        "Mobile country artifact diverges from backend canonical source"
    )  # noqa: E501
