import json

import pytest
from fastapi.testclient import TestClient

from backend.roi_map import CITIES, roi_map
from backend.roi_map.build import SELF_USE, SYSTEM_KW
from backend.server import app
from backend.analysis.finance.economics.economics import simple_payback


@pytest.mark.parametrize("city", list(CITIES))
def test_built_rows_are_labelled_estimates_with_arithmetic_that_checks(city):
    data = roi_map(city)
    assert "Not an audit" in data["label"] and data["assumptions"]
    assert len(data["rows"]) > 50
    for r in data["rows"]:
        assert r["basis"].startswith("estimate") and len(r["zip"]) == 5
        assert r["annual_savings_usd"] == pytest.approx(r["annual_kwh"] * SELF_USE * r["rate_usd_per_kwh"], abs=1)
        assert r["annual_kwh"] == pytest.approx(r["kwh_per_kw_year"] * SYSTEM_KW, abs=SYSTEM_KW)
        assert r["payback_years"] == pytest.approx(simple_payback(r["net_upfront_usd"], r["annual_savings_usd"]), abs=0.2)


def test_the_route_serves_both_cities_and_404s_the_rest():
    client = TestClient(app)
    for city in CITIES:
        got = client.get("/api/roi-map", params={"city": city})
        assert got.status_code == 200 and got.json()["city"] == city
    assert client.get("/api/roi-map", params={"city": "paris"}).status_code == 404
    assert roi_map("paris") is None


def test_rates_without_a_listed_utility_are_marked_as_state_average():
    rows = roi_map("houston")["rows"]
    assert any(r["rate_source"] == "state_average" for r in rows)
    assert all("state average" in r["utility"] for r in rows if r["rate_source"] == "state_average")
