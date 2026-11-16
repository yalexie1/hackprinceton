"""Reconcile the initial cohort and annual truth directly from hashed public CSVs.

No production evaluator imports. This checks owner outputs, not model accuracy.
Run with --cache-dir /private/cache/bdg2 --predictions /path/per_building.json
--output /tmp/truth-check.json. Raw data stay outside Git.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

SITES = {"Bear", "Cockatoo", "Fox", "Panther", "Rat"}


def eligible_metadata(row: dict, year: int) -> bool:
    try:
        return (row["site_id"] in SITES and bool(row["electricity"])
                and 50 < float(row["sqm"]) < 200000
                and 1850 < float(row["yearbuilt"]) <= year
                and math.isfinite(float(row["lat"]))
                and row["primaryspaceusage"] != "Parking")
    except (ValueError, TypeError):
        return False


def annual_meters(path: Path, ids: set[str], year: int) -> tuple[dict, dict, set]:
    """Require the whole hourly calendar before annualizing <=10% meter gaps."""
    hours = 8784 if calendar.isleap(year) else 8760
    start = datetime(year, 1, 1)
    expected_times = {start + timedelta(hours=i) for i in range(hours)}
    sums, counts, times = defaultdict(float), defaultdict(int), set()
    with path.open() as handle:
        reader = csv.DictReader(handle)
        meters = ids.intersection(reader.fieldnames or [])
        for row in reader:
            timestamp = datetime.fromisoformat(row["timestamp"])
            if timestamp.year != year:
                continue
            if timestamp not in expected_times or timestamp in times:
                raise ValueError("Duplicate, off-hour or timezone-aware meter timestamp")
            times.add(timestamp)
            for bid in meters:
                raw = row[bid]
                if not raw or raw.lower() == "nan":
                    continue
                value = float(raw)
                if not math.isfinite(value):
                    raise ValueError("Non-finite meter value")
                sums[bid] += value
                counts[bid] += 1
    if times != expected_times:
        raise ValueError(f"Incomplete calendar: {len(times)} of {hours} hours")
    truth = {bid: sums[bid] * hours / counts[bid] for bid in meters
             if counts[bid] >= .9 * hours and sums[bid] > 0}
    return truth, {"calendar_hours": hours, "unique_timestamps": len(times),
                   "duplicate_timestamps": 0}, meters


def audit(cache: Path, predictions: Path, year: int = 2017) -> dict:
    with (cache / "metadata.csv").open() as handle:
        pool = [r for r in csv.DictReader(handle) if eligible_metadata(r, year)]
    ids = {r["building_id"] for r in pool}
    truth, calendar_report, meters = annual_meters(cache / "electricity_cleaned.csv", ids, year)
    rows = json.loads(predictions.read_bytes())
    owner = {r["building_id"]: r["measured_elec_kwh"] for r in rows}
    if len(owner) != len(rows):
        raise ValueError("Duplicate building in owner predictions")
    common = truth.keys() & owner.keys()
    differences = {bid: truth[bid] - owner[bid] for bid in common}
    return {
        "evidence_type": "independent raw-meter truth/cohort check; no model rerun",
        "year": year, **calendar_report, "metadata_eligible": len(pool),
        "metadata_without_electricity_column": len(ids - meters),
        "truth_eligible": len(truth), "owner_output_n": len(owner),
        "eligible_not_in_owner": sorted(truth.keys() - owner.keys()),
        "owner_not_eligible": sorted(owner.keys() - truth.keys()),
        "n_truth_compared": len(common),
        "max_absolute_truth_difference_kwh": max(map(abs, differences.values()), default=None),
        "max_relative_truth_difference": max((abs(v) / owner[bid] for bid, v in differences.items()), default=None),
        "sha256": {str(path.name): hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in (cache / "metadata.csv", cache / "electricity_cleaned.csv", predictions)},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.cache_dir, args.predictions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
