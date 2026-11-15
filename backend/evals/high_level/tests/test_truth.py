from datetime import datetime, timedelta

import pytest

from backend.evals.high_level.audit_truth import annual_meters


def write_meter(path, *, missing=0, drop_last=False, duplicate=False):
    start = datetime(2017, 1, 1)
    lines = ["timestamp,good,sparse"]
    for i in range(8760 - int(drop_last)):
        timestamp = start + timedelta(hours=i)
        lines.append(f"{timestamp.isoformat(sep=' ')},{'' if i < missing else 2},{'' if i < 877 else 1}")
    if duplicate:
        lines.append(lines[-1])
    path.write_text("\n".join(lines) + "\n")


def test_meter_gaps_annualize_but_incomplete_meters_remain_excluded(tmp_path):
    path = tmp_path / "meter.csv"
    write_meter(path, missing=876)
    truth, report, _ = annual_meters(path, {"good", "sparse"}, 2017)
    assert truth == {"good": 17520}
    assert report["unique_timestamps"] == 8760


@pytest.mark.parametrize("kwargs", [{"drop_last": True}, {"duplicate": True}])
def test_missing_or_duplicate_entire_calendar_rows_are_not_hidden_by_annualization(tmp_path, kwargs):
    path = tmp_path / "meter.csv"
    write_meter(path, **kwargs)
    with pytest.raises(ValueError):
        annual_meters(path, {"good"}, 2017)
