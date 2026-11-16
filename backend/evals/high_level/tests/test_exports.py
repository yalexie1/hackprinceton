import pytest

from backend.evals.high_level.audit_initial import grouped_metrics, normalize_runs
from backend.evals.high_level.metrics import score


def test_trimmed_export_retains_missing_predictions_and_metadata():
    band = {"low": 40, "expected": 50, "high": 60}
    rows, arms = normalize_runs([
        {"building_id": "one", "site_id": "A", "measured_elec_kwh": 100,
         "bdg2temp": band, "openmeteo": None},
        {"building_id": "two", "site_id": "B", "measured_elec_kwh": 100,
         "bdg2temp": None, "openmeteo": band},
    ])
    assert rows[0]["building_id"] == "one"
    assert score(rows, arms[0])["n_missing_prediction"] == 1
    assert score(rows, arms[1])["factor_two_or_more_pct"] == 100
    groups = grouped_metrics(rows, arms)["site_id"]
    assert groups["A"]["openmeteo"]["status"] == "insufficient_evidence"
    assert groups["B"]["openmeteo"]["n_scored"] == 1


def test_full_export_keeps_its_declared_arms():
    original = [{"truth_elec_kwh": 123, "arms": {}}]
    rows, arms = normalize_runs({"runs": original, "arms": ["custom"]})
    assert rows is original
    assert arms == ["custom"]


def test_unrecognized_export_is_rejected():
    with pytest.raises(ValueError):
        normalize_runs(None)
