"""Goodness-of-fit statistics and the calibration test (physics 04, MV-03 and MV-04).

Sign convention is the one of MV-03: residual = measured - predicted, so a positive NMBE means the
model is BELOW the bills. FEMP-MV4 equation 4-1 writes MBE the other way round (simulated minus
measured); MV-04 notes that the sign does not affect the test, and the plain-words messages of the
calibration say "model above" or "model below" instead of quoting a sign.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Literal, Sequence

import numpy as np

# MV-04 (FEMP-MV4 Table 4-2, reproducing ASHRAE Guideline 14): bias within +/- 5 % and CV(RMSE) at
# most 15 % for monthly data; +/- 10 % and 30 % for hourly data.
TOLERANCES: dict[str, tuple[float, float]] = {"monthly": (0.05, 0.15), "hourly": (0.10, 0.30)}


@dataclass(frozen=True)
class FitStats:
    """MV-03 statistics of measured against predicted values (fractions, not percent)."""
    rmse: float
    cv_rmse: float
    nmbe: float           # sum(E - Ehat) / ((n - p) * mean(E)); positive = model below measured
    ndbe: float           # sum(E - Ehat) / sum(E); equals nmbe when p = 0
    r2: float
    n: int
    p: int

    def as_dict(self) -> dict:
        return asdict(self)


def fit_statistics(measured: Sequence[float], predicted: Sequence[float], p: int) -> FitStats:
    """MV-03. `p` is the number of fitted parameters (0 for a calibrated simulation, MV-04)."""
    e = np.asarray(measured, dtype=float)
    ehat = np.asarray(predicted, dtype=float)
    if e.shape != ehat.shape or e.ndim != 1 or e.size == 0:
        raise ValueError("measured and predicted must be equal-length, non-empty sequences")
    n = int(e.size)
    if not 0 <= p < n:
        raise ValueError(f"p must be in [0, n); got p={p}, n={n}")
    if not (np.all(np.isfinite(e)) and np.all(np.isfinite(ehat))):
        raise ValueError("measured and predicted must be finite")
    mean = float(e.mean())
    resid = e - ehat
    sse = float(np.sum(resid ** 2))
    rmse = math.sqrt(sse / (n - p))
    total = float(e.sum())
    sst = float(np.sum((e - mean) ** 2))
    return FitStats(
        rmse=rmse,
        cv_rmse=rmse / mean if mean != 0 else math.inf,
        nmbe=float(resid.sum()) / ((n - p) * mean) if mean != 0 else math.inf,
        ndbe=float(resid.sum()) / total if total != 0 else math.inf,
        r2=1.0 - sse / sst if sst > 0 else math.nan,
        n=n, p=p)


def model_acceptable(stats: FitStats, interval: Literal["monthly", "hourly"] = "monthly") -> tuple[bool, list[str]]:
    """MV-03 / MV-04 acceptance on CV(RMSE) and bias. Returns the verdict and the reasons it fails."""
    bias_tol, cv_tol = TOLERANCES[interval]
    reasons = []
    if not abs(stats.nmbe) <= bias_tol:
        reasons.append(f"bias {_pct(stats.nmbe)} is outside +/- {bias_tol:.0%}")
    if not stats.cv_rmse <= cv_tol:
        reasons.append(f"CV(RMSE) {_pct(stats.cv_rmse, signed=False)} is above {cv_tol:.0%}")
    return not reasons, reasons


def calibration_ok(measured_monthly: Sequence[float], simulated_monthly: Sequence[float]) -> tuple[bool, FitStats]:
    """MV-04 for monthly data. p = 0: FEMP-MV4 equations 4-1 to 4-4 divide by the number of points
    and by the measured total (the simulation's inputs are not regression parameters)."""
    if len(measured_monthly) != 12 or len(simulated_monthly) != 12:
        raise ValueError("calibration to monthly bills needs 12 measured and 12 simulated values")
    stats = fit_statistics(measured_monthly, simulated_monthly, p=0)
    return model_acceptable(stats, "monthly")[0], stats


def _pct(x: float, signed: bool = True) -> str:
    if not math.isfinite(x):
        return "undefined"
    return f"{x * 100:+.1f} %" if signed else f"{x * 100:.1f} %"
