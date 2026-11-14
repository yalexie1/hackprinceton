"""Change-point and degree-day regression of monthly energy on outdoor temperature (physics 04, MV-02).

The calibration uses the degree-day form to split a set of twelve monthly values into a base load
(kWh per day), a heating slope and a cooling slope, for the bills and for the simulation alike, so
that it can say which part of the model disagrees with the bills (MV-06 step 2).

Fitting rule (MV-02): for each candidate change point on a 0.5 K grid from 10 to 26 degC, fit the
other coefficients by ordinary least squares; keep the candidate with the smallest sum of squared
errors. p counts the change points.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Optional, Sequence

import numpy as np

DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
GRID_C = tuple(10.0 + 0.5 * i for i in range(33))          # 10.0 .. 26.0 degC
Kind = Literal["2P", "3PC", "3PH", "4P", "5P"]
DDKind = Literal["1P", "3PH", "3PC", "5P"]
_PARAMS = {"2P": 2, "3PC": 3, "3PH": 3, "4P": 4, "5P": 5, "1P": 1}
T_CRITICAL = 2.0     # BPA-REG 5.2.2: |t| above the two-sided 95 % critical value, "about 2"


@dataclass(frozen=True)
class ChangePointModel:
    kind: str
    b0: float
    b1: float = 0.0
    b2: float = 0.0
    tb_heat: Optional[float] = None
    tb_cool: Optional[float] = None
    p: int = 2
    n: int = 0
    sse: float = 0.0
    t_stats: tuple[float, ...] = field(default_factory=tuple)    # of the slopes, in the order b1, b2


def _ols(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ coef
    return coef, float(resid @ resid)


def _t_stats(x: np.ndarray, coef: np.ndarray, sse: float, dof: int) -> np.ndarray:
    if dof <= 0:
        return np.full(coef.shape, math.nan)
    s2 = sse / dof
    try:
        cov = s2 * np.linalg.inv(x.T @ x)
    except np.linalg.LinAlgError:
        return np.full(coef.shape, math.nan)
    se = np.sqrt(np.maximum(np.diag(cov), 0.0))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(se > 0, coef / se, math.inf)


def _cp_design(t: np.ndarray, kind: str, tb: Optional[float], tb2: Optional[float]) -> np.ndarray:
    one = np.ones_like(t)
    if kind == "2P":
        return np.column_stack([one, t])
    if kind == "3PC":
        return np.column_stack([one, np.maximum(t - tb, 0.0)])
    if kind == "3PH":
        return np.column_stack([one, np.maximum(tb - t, 0.0)])
    if kind == "4P":
        return np.column_stack([one, np.maximum(tb - t, 0.0), np.maximum(t - tb, 0.0)])
    if kind == "5P":
        return np.column_stack([one, np.maximum(tb - t, 0.0), np.maximum(t - tb2, 0.0)])
    raise ValueError(f"unknown change-point model {kind!r}")


def fit_change_point(temps_c: Sequence[float], energy_per_day: Sequence[float], kind: Kind) -> ChangePointModel:
    """MV-02: fit E = b0 + slopes * (T - Tb)+ ... to period means (kWh/day against degC)."""
    t = np.asarray(temps_c, dtype=float)
    y = np.asarray(energy_per_day, dtype=float)
    if t.shape != y.shape or t.size < 3:
        raise ValueError("temps_c and energy_per_day must have equal length, at least 3")
    if kind == "2P":
        cands = [(None, None)]
    elif kind == "5P":
        cands = [(a, b) for a in GRID_C for b in GRID_C if a <= b]
    else:
        cands = [(a, None) for a in GRID_C]
    best = None
    for tb, tb2 in cands:
        x = _cp_design(t, kind, tb, tb2)
        coef, sse = _ols(x, y)
        if best is None or sse < best[0] - 1e-12:
            best = (sse, tb, tb2, coef, x)
    sse, tb, tb2, coef, x = best
    p = _PARAMS[kind]
    ts = tuple(float(v) for v in _t_stats(x, coef, sse, t.size - p)[1:])
    b1 = float(coef[1]) if coef.size > 1 else 0.0
    b2 = float(coef[2]) if coef.size > 2 else 0.0
    heat = {"3PH": tb, "4P": tb, "5P": tb}.get(kind)
    cool = {"3PC": tb, "4P": tb, "5P": tb2}.get(kind)
    return ChangePointModel(kind=kind, b0=float(coef[0]), b1=b1, b2=b2, tb_heat=heat, tb_cool=cool,
                            p=p, n=int(t.size), sse=sse, t_stats=ts)


def predict(model: ChangePointModel, temps_c: Sequence[float]) -> list[float]:
    """Energy per day of a fitted MV-02 model at the given period mean temperatures."""
    t = np.asarray(temps_c, dtype=float)
    tb = model.tb_heat if model.kind in ("3PH", "4P", "5P") else model.tb_cool
    x = _cp_design(t, model.kind, tb, model.tb_cool if model.kind == "5P" else None)
    coef = np.array([model.b0, model.b1, model.b2][: x.shape[1]])
    return [float(v) for v in x @ coef]


def degree_days(daily_mean_c: Sequence[float], base_c: float, kind: Literal["heating", "cooling"]) -> float:
    """Degree days to base `base_c` from daily mean temperatures (K day)."""
    t = np.asarray(daily_mean_c, dtype=float)
    d = base_c - t if kind == "heating" else t - base_c
    return float(np.maximum(d, 0.0).sum())


# ---------------------------------------------------------------- degree-day form, monthly

def _months(daily_mean_c: Sequence[float]) -> list[np.ndarray]:
    t = np.asarray(daily_mean_c, dtype=float)
    if t.size != 365:
        raise ValueError(f"daily_mean_c must hold 365 daily means (a non-leap year); got {t.size}")
    edges = np.cumsum((0,) + DAYS_IN_MONTH)
    return [t[edges[i]:edges[i + 1]] for i in range(12)]


def monthly_mean_temps(daily_mean_c: Sequence[float]) -> list[float]:
    return [float(m.mean()) for m in _months(daily_mean_c)]


def monthly_degree_days(daily_mean_c: Sequence[float], base_c: float, kind: Literal["heating", "cooling"]) -> np.ndarray:
    return np.array([degree_days(m, base_c, kind) for m in _months(daily_mean_c)])


@dataclass(frozen=True)
class DegreeDayModel:
    """E_month = base * days + heat * HDD(tb_heat) + cool * CDD(tb_cool)  (MV-02 degree-day form)."""
    kind: str
    base_kwh_per_day: float
    heat_kwh_per_kday: float = 0.0
    cool_kwh_per_kday: float = 0.0
    tb_heat: Optional[float] = None
    tb_cool: Optional[float] = None
    p: int = 1
    sse: float = 0.0
    t_heat: float = math.nan
    t_cool: float = math.nan

    def monthly(self, daily_mean_c: Sequence[float]) -> np.ndarray:
        """Predicted twelve monthly totals."""
        e = self.base_kwh_per_day * np.array(DAYS_IN_MONTH, dtype=float)
        if self.tb_heat is not None:
            e = e + self.heat_kwh_per_kday * monthly_degree_days(daily_mean_c, self.tb_heat, "heating")
        if self.tb_cool is not None:
            e = e + self.cool_kwh_per_kday * monthly_degree_days(daily_mean_c, self.tb_cool, "cooling")
        return e

    def annual_parts(self, daily_mean_c: Sequence[float]) -> dict[str, float]:
        """Annual base, heating and cooling parts (kWh) on the weather given."""
        out = {"base": self.base_kwh_per_day * 365.0, "heating": 0.0, "cooling": 0.0}
        if self.tb_heat is not None:
            out["heating"] = self.heat_kwh_per_kday * degree_days(daily_mean_c, self.tb_heat, "heating")
        if self.tb_cool is not None:
            out["cooling"] = self.cool_kwh_per_kday * degree_days(daily_mean_c, self.tb_cool, "cooling")
        return out


def _dd_design(daily_mean_c, kind: str, tbh: Optional[float], tbc: Optional[float]) -> np.ndarray:
    cols = [np.array(DAYS_IN_MONTH, dtype=float)]
    if kind in ("3PH", "5P"):
        cols.append(monthly_degree_days(daily_mean_c, tbh, "heating"))
    if kind in ("3PC", "5P"):
        cols.append(monthly_degree_days(daily_mean_c, tbc, "cooling"))
    return np.column_stack(cols)


def _dd_model(kind, coef, tbh, tbc, sse, ts) -> DegreeDayModel:
    heat = cool = 0.0
    th = tc = math.nan
    i = 1
    if kind in ("3PH", "5P"):
        heat, th = float(coef[i]), float(ts[i])
        i += 1
    if kind in ("3PC", "5P"):
        cool, tc = float(coef[i]), float(ts[i])
    return DegreeDayModel(kind=kind, base_kwh_per_day=float(coef[0]), heat_kwh_per_kday=heat,
                          cool_kwh_per_kday=cool, tb_heat=tbh if kind in ("3PH", "5P") else None,
                          tb_cool=tbc if kind in ("3PC", "5P") else None, p=_PARAMS[kind], sse=sse,
                          t_heat=th, t_cool=tc)


def fit_degree_day_at(monthly_kwh: Sequence[float], daily_mean_c: Sequence[float], kind: DDKind,
                      tb_heat: Optional[float] = None, tb_cool: Optional[float] = None) -> DegreeDayModel:
    """Degree-day fit with the balance points given (used to read the simulation at the bills' points)."""
    y = np.asarray(monthly_kwh, dtype=float)
    x = _dd_design(daily_mean_c, kind, tb_heat, tb_cool)
    coef, sse = _ols(x, y)
    return _dd_model(kind, coef, tb_heat, tb_cool, sse, _t_stats(x, coef, sse, y.size - _PARAMS[kind]))


def fit_degree_day(monthly_kwh: Sequence[float], daily_mean_c: Sequence[float], kind: DDKind) -> DegreeDayModel:
    """Degree-day fit with the balance points searched on the MV-02 grid."""
    if kind == "1P":
        return fit_degree_day_at(monthly_kwh, daily_mean_c, "1P")
    if kind == "5P":
        cands = [(a, b) for a in GRID_C for b in GRID_C if a <= b]
    elif kind == "3PH":
        cands = [(a, None) for a in GRID_C]
    else:
        cands = [(None, b) for b in GRID_C]
    best = None
    for tbh, tbc in cands:
        m = fit_degree_day_at(monthly_kwh, daily_mean_c, kind, tbh, tbc)
        if best is None or m.sse < best.sse - 1e-9:
            best = m
    return best


def _valid(m: DegreeDayModel) -> bool:
    """Slopes must be positive and significant (MV-02 sign rule, BPA-REG 5.2.2 t test)."""
    ok = True
    if m.tb_heat is not None:
        ok &= m.heat_kwh_per_kday > 0 and m.t_heat > T_CRITICAL
    if m.tb_cool is not None:
        ok &= m.cool_kwh_per_kday > 0 and m.t_cool > T_CRITICAL
    return bool(ok)


def choose_degree_day(monthly_kwh: Sequence[float], daily_mean_c: Sequence[float],
                      fuel: Literal["electricity", "gas"]) -> DegreeDayModel:
    """The degree-day model of the bills (MV-02 model choice): gas 3PH; electricity 3PC, 3PH or 5P.
    A model is valid when every slope is positive and significant. Among valid models the one with
    the smallest residual variance sse / (n - p) is kept, so that a five-parameter model wins only
    when its second slope pays for its two extra parameters [J: MV-02 says "the simplest model that
    passes MV-03"; with twelve monthly points that test is passed by almost any model, so the
    variance rule is used to decide between them]. When no weather slope is positive and
    significant the base-only model is returned."""
    kinds: tuple[DDKind, ...] = ("3PH",) if fuel == "gas" else ("3PC", "3PH", "5P")
    fits = [fit_degree_day(monthly_kwh, daily_mean_c, k) for k in kinds]
    valid = [m for m in fits if _valid(m)]
    if not valid:
        return fit_degree_day(monthly_kwh, daily_mean_c, "1P")
    return min(valid, key=lambda m: (m.sse / (12 - m.p), m.p))
