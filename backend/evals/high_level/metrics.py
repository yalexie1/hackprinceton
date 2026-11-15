"""Independent annual-meter scoring; no production model or first-stage scorer imports.

These are cross-sectional metrics, not a time-series calibration certification.
Unknown/refused predictions are counted explicitly rather than scored as zero.
"""
from __future__ import annotations

import math
import statistics


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def score(rows: list[dict], arm: str) -> dict:
    """Score positive-truth rows. Reject invalid ranges; report missing predictions.

    A factor-of-two miss includes prediction/truth <= 0.5 OR >= 2, with
    equality included. Absolute percentage error >=100% measures something else.
    """
    errors, absolute, percentages, ratios, widths = [], [], [], [], []
    truth_sum = predicted_sum = 0.0
    covered = below = above = missing = nonpositive_truth = 0
    for index, row in enumerate(rows):
        truth = _finite(row.get("truth_elec_kwh"), f"row {index} truth")
        if truth <= 0:
            nonpositive_truth += 1
            continue
        prediction = row.get("arms", {}).get(arm, {}).get("elec")
        if prediction is None:
            missing += 1
            continue
        low, expected, high = (
            _finite(prediction.get(key), f"row {index} {key}")
            for key in ("low", "expected", "high")
        )
        if expected < 0 or not low <= expected <= high:
            raise ValueError(f"row {index} invalid prediction/range")
        error = expected - truth
        errors.append(error)
        absolute.append(abs(error))
        percentages.append(100 * error / truth)
        ratios.append(expected / truth)
        widths.append(high - low)
        truth_sum += truth
        predicted_sum += expected
        covered += low <= truth <= high
        below += truth < low
        above += truth > high
    n = len(errors)
    result = {
        "n_input": len(rows), "n_scored": n,
        "n_missing_prediction": missing, "n_nonpositive_truth": nonpositive_truth,
    }
    if not n:
        return {**result, "status": "insufficient_evidence"}
    return {
        **result, "status": "evaluated", "arm": arm,
        "median_signed_pct": statistics.median(percentages),
        "median_absolute_pct": statistics.median(abs(e) for e in percentages),
        "mean_signed_kwh": statistics.fmean(errors),
        "mean_absolute_kwh": statistics.fmean(absolute),
        "aggregate_signed_pct": 100 * (predicted_sum - truth_sum) / truth_sum,
        "weighted_absolute_pct": 100 * sum(absolute) / truth_sum,
        "factor_two_or_more_pct": 100 * sum(r <= 0.5 or r >= 2 for r in ratios) / n,
        "absolute_percentage_error_ge_100_pct": 100 * sum(abs(e) >= 100 for e in percentages) / n,
        "coverage_pct": 100 * covered / n,
        "below_low_pct": 100 * below / n,
        "above_high_pct": 100 * above / n,
        "mean_interval_width_kwh": statistics.fmean(widths),
    }
