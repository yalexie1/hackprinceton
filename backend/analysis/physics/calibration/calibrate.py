"""Calibration of the building model to twelve months of utility bills (physics 04, MV-06; Option D).

What it does, in the order of MV-06:

1. Checks the bills and decides which fuels to calibrate: electricity always, gas when gas bills are
   given. A gas bill against a model that burns no gas (or the reverse) is a finding, not a fit.
2. Splits bills and simulation into base load, heating slope and cooling slope with the MV-02
   degree-day model on the site's typical weather year, so the result can say which part disagrees.
3. Picks the inputs it may move: the uncertain assumptions that drive the bill (`CANDIDATES`) that
   the model carries as a real range (low < high), that the user may edit, and whose source is not
   `user` or `measured` (a value someone gave or measured is not overruled by a bill). Each is run
   at its low and its high; one that moves no supplied fuel by 0.5 % of its annual bill is dropped,
   and so is one that moves a fuel WITHOUT bills more than any billed fuel (electricity bills must
   not quietly rewrite the gas side).
4. Fits them together by bounded, regularised least squares (scipy `least_squares`, trust-region
   reflective, forward differences, at most 25 steps and 400 simulations, start at the expected values). Each
   input moves on a scale u in [-1, 1] that is piecewise linear through low (-1), expected (0) and
   high (+1), so it can NEVER leave its stated range. The objective is a maximum a posteriori fit:
   monthly residuals divided by 5 % of the mean monthly bill of their fuel, plus 1.2816 u per input
   (low and high are the 10th and 90th percentiles, UNC-01, so 1.2816 u is the input's z-score).
   Bills and priors are weighted in the same currency, so two inputs that the bills cannot tell
   apart (lighting and plug density, say) share the correction in proportion to their ranges
   instead of one of them being pushed to an end.
5. Accepts the result when MV-04 passes (bias within +/- 5 %, CV(RMSE) at most 15 %) for every
   supplied fuel. Then, and only then, the moved inputs are written into the model.
6. Otherwise the model is returned unchanged, with the best in-range values as a proposal, the fit
   statistics, the months that disagree and what the disagreement looks like (see `_diagnose`).

How a calibrated value is recorded, and why:
- It is written with the `set_assumption` callable the caller passes, with source `measured`. The
  contract has no "calibrated" source; `measured` is the one that says the value now rests on
  metered data of this building, and it keeps the registry from overruling it with a default.
  It is NOT a direct measurement, so the confidence is set to 0.7 rather than the 0.95 `measured`
  normally carries [J], and the evidence says it was inferred.
- `set_assumption` collapses the range to the fitted value. The original range, its source and the
  before and after statistics are kept in a new evidence entry (kind `user`, because the bills came
  from the user; ref `bills.electricity_kwh` and/or `bills.gas_kwh`), so a reader sees how far the
  value moved and on what grounds. The result's `moves` carry the same in structured form.
- Inputs the fit left at their expected value keep their range and source: the bills did not
  pin them down.

The simulation is passed in (`simulate(bundle, model) -> BaselineResult`), as is `set_assumption`,
so this module imports nothing from the door or from other packages of the Analysis lane. Run it with
the door's fast simulation (no low and high re-runs); the final baseline with ranges is the
caller's job.

Limits a consultant would state:
- The bills are compared with the site's TYPICAL weather year. FEMP-MV4 4.5.3.1 asks for the actual
  weather of the billing period; a hot or a mild billing year shows up as a seasonal residual, and
  the contract's `UtilityBills` carries no billing dates to fetch it. Months are taken as calendar
  months, January first.
- Only inputs that `set_assumption` carries into `Systems` reach the simulation; envelope U-values
  live on the model's surfaces, which are built once from the bundle, so they are not in
  `CANDIDATES` (they are also nearly impossible to separate from infiltration and setpoints with
  twelve monthly points).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Callable, Iterable, Literal, Optional, Sequence

import numpy as np
from scipy.optimize import least_squares

from backend.schema import (Assumption, BaselineResult, BuildingModel, CalibrationSummary, EvidenceRef, FuelFit,
                            PropertyBundle, Ranged, UtilityBills)

from .changepoint import DAYS_IN_MONTH, DegreeDayModel, choose_degree_day, fit_degree_day_at, monthly_degree_days
from .stats import TOLERANCES, FitStats, calibration_ok, fit_statistics
from .uncertainty import SavingsUncertainty, savings_uncertainty

Fuel = Literal["electricity", "gas"]
Simulate = Callable[[PropertyBundle, BuildingModel], BaselineResult]
SetAssumption = Callable[..., BuildingModel]

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# The inputs calibration may move, in the order they are applied, with what they stand for. Every key
# here reaches `Systems` through set_assumption (physics 02 section 12). `ventilation.outdoor_air_m3_s`
# is left out on purpose: for offices the registry derives it from `occupancy.count`.
CANDIDATES: dict[str, str] = {
    "occupancy.count": "occupants (people, their hot water and the hours the building is in use)",
    "plug.ppd": "plug load density",
    "lighting.lpd": "lighting power density",
    "dhw.uef": "water heater efficiency",
    "setpoint.heating": "heating setpoint",
    "setpoint.cooling": "cooling setpoint",
    "infiltration.ach50": "air leakage",
    "infiltration.leakage_75pa": "air leakage",
    "hvac.heating_rating": "heating equipment efficiency",
    "hvac.heating_efficiency": "heating equipment efficiency",
    "hvac.cooling_rating": "cooling equipment efficiency",
    "hvac.distribution_efficiency": "duct losses",
}
LOCKED_SOURCES = frozenset({"user", "measured"})

SIGMA_FRACTION = 0.05      # [J] monthly residual scale: 5 % of the mean monthly bill of the fuel
PRIOR_Z = 1.2815516        # low/high are P10/P90 (UNC-01): z of the range end
SCREEN_MIN = 0.005         # [J] an input that moves no fuel by 0.5 % of its annual bill is not fitted
MOVED_MIN = 0.01           # [J] a move smaller than 1 % of the range is "left at expected"
AT_BOUND = 0.98            # |u| above this: the input sits at the end of its range
CALIBRATED_CONFIDENCE = 0.7  # [J] see the module docstring
DIFF_STEP = 0.02           # finite-difference step in u (2 % of a half-range)
DEFAULT_BUDGET = 400       # simulations, screening included
MAX_ITERATIONS = 25        # trust-region steps (each costs one run plus one per fitted input)


# ---------------------------------------------------------------- result types

@dataclass(frozen=True)
class Move:
    key: str
    label: str
    unit: str
    before: float              # the expected value before calibration
    after: float               # the fitted value (inside [low, high])
    low: float
    high: float
    source_before: str
    drives: str                # "base load", "heating", "cooling", "base load and heating" or "... and cooling"
    at_bound: bool
    reason: str


@dataclass(frozen=True)
class FuelSplit:
    """MV-02 degree-day split of the bills and of the simulation at the bills' balance points.
    Annual parts in kWh on the typical weather year."""
    kind: str
    tb_heat: Optional[float]
    tb_cool: Optional[float]
    bills: dict[str, float]
    model_before: dict[str, float]
    model_after: dict[str, float]


@dataclass
class CalibrationResult:
    calibrated_to_bills: bool
    model: BuildingModel                  # the calibrated model; the input model when not calibrated
    baseline: BaselineResult              # `simulate(model)` with `calibrated_to_bills` set
    values: dict[str, float]              # best in-range values of the moved inputs (a proposal when not calibrated)
    moves: list[Move]
    before: dict[str, FitStats]
    after: dict[str, FitStats]
    fuels: list[str]
    split: dict[str, FuelSplit] = field(default_factory=dict)
    fitted_keys: list[str] = field(default_factory=list)
    screened_out: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    simulations: int = 0
    measured: dict[str, list[float]] = field(default_factory=dict)        # the bills, per fuel
    simulated_before: dict[str, list[float]] = field(default_factory=dict)
    simulated_after: dict[str, list[float]] = field(default_factory=dict)  # at the best in-range values

    def savings_uncertainty(self, fuel: str, savings_kwh: float, m: int = 12) -> SavingsUncertainty:
        """MV-05 for an expected annual saving of `fuel`, on the calibrated model (MV-06 step 7).
        CV(RMSE) is recomputed with n - p, p = the number of inputs the calibration moved (at least 1,
        and at most n - 2 so that t is defined) [J]."""
        if fuel not in self.after:
            raise ValueError(f"no bills for {fuel}")
        p = min(max(len(self.moves), 1), 10)
        cv = fit_statistics(self.measured[fuel], self.simulated_after[fuel], p).cv_rmse
        out = savings_uncertainty(cv, 12, p, savings_kwh, float(sum(self.simulated_after[fuel])), m)
        if not self.calibrated_to_bills:
            out = replace(out, acceptable=False,
                          note="the model is not calibrated to the bills, so savings cannot be verified against "
                               "them (MV-04 not met); " + out.note)
        return out

    def contract_summary(self) -> CalibrationSummary:
        """The contract's `CalibrationSummary` (0.3.5). NMBE is reported simulated minus billed, the
        contract's sign, which is the negative of MV-03's measured-minus-predicted `FitStats.nmbe`."""
        from .stats import TOLERANCES
        nmbe_tol, cv_tol = TOLERANCES["monthly"]
        fits = []
        for f in self.fuels:
            b, a = self.before[f], self.after[f]
            ok = abs(a.nmbe) <= nmbe_tol and a.cv_rmse <= cv_tol
            fits.append(FuelFit(fuel=f, nmbe_before=round(-b.nmbe, 4), cv_rmse_before=round(b.cv_rmse, 4),
                                nmbe_after=round(-a.nmbe, 4), cv_rmse_after=round(a.cv_rmse, 4), passed=ok))
        moved = [m.key for m in self.moves] if self.calibrated_to_bills else []
        return CalibrationSummary(calibrated=self.calibrated_to_bills, fits=fits, moved=moved,
                                  warnings=[self.summary()] + list(self.warnings))

    def calibrated_model(self) -> BuildingModel:
        """The model to use for every later step, carrying `calibration` (the door's return value)."""
        return self.model.model_copy(update={"calibration": self.contract_summary()})

    def summary(self) -> str:
        """One paragraph in plain words."""
        parts = []
        for f in self.fuels:
            b, a = self.before[f], self.after[f]
            parts.append(f"{f}: model {_side_word(b.nmbe)} the bills by {abs(b.nmbe):.1%} before "
                         f"(CV(RMSE) {b.cv_rmse:.1%}), {abs(a.nmbe):.1%} {_side_word(a.nmbe)} after "
                         f"(CV(RMSE) {a.cv_rmse:.1%})")
        head = ("Calibrated to the bills (ASHRAE Guideline 14 monthly tolerances met). "
                if self.calibrated_to_bills else "Not calibrated: the bills cannot be matched inside the "
                "assumption ranges. ")
        moved = "; ".join(f"{m.label} {_fmt(m.before)} -> {_fmt(m.after)} {m.unit}" for m in self.moves)
        return head + "; ".join(parts) + "." + (f" Moved: {moved}." if moved else "")


class _Budget(Exception):
    pass


# ---------------------------------------------------------------- helpers

def _fmt(x: float) -> str:
    return f"{x:.3g}" if abs(x) < 100 else f"{x:,.0f}"


def _side_word(nmbe: float) -> str:
    return "below" if nmbe > 0 else "above"


def _sig(x: float, digits: int = 4) -> float:
    if x == 0 or not math.isfinite(x):
        return x
    return round(x, digits - 1 - int(math.floor(math.log10(abs(x)))))


def _monthly(result: BaselineResult, fuel: Fuel) -> np.ndarray:
    v = result.monthly_electricity_kwh if fuel == "electricity" else result.monthly_gas_kwh
    out = np.asarray(v, dtype=float)
    if out.shape != (12,):
        return np.zeros(12)
    return out


@dataclass(frozen=True)
class _Param:
    key: str
    label: str
    unit: str
    low: float
    expected: float
    high: float
    source: str
    confidence: float

    @property
    def bounds(self) -> tuple[float, float]:
        return (-1.0 if self.expected > self.low else 0.0, 1.0 if self.high > self.expected else 0.0)

    def value(self, u: float) -> float:
        u = min(max(u, -1.0), 1.0)
        if u < 0:
            return self.expected + u * (self.expected - self.low)
        return self.expected + u * (self.high - self.expected)

    def u_of(self, x: float) -> float:
        if x < self.expected:
            return (x - self.expected) / (self.expected - self.low) if self.expected > self.low else 0.0
        return (x - self.expected) / (self.high - self.expected) if self.high > self.expected else 0.0


def _candidates(model: BuildingModel, keys: Optional[Iterable[str]]) -> tuple[list[_Param], list[str]]:
    wanted = list(CANDIDATES) if keys is None else list(keys)
    by_key = {a.key: a for a in model.assumptions}
    params, skipped = [], []
    for k in wanted:
        a = by_key.get(k)
        if a is None:
            continue
        if not isinstance(a.value, Ranged):
            skipped.append(f"{k}: not a number")
            continue
        r = a.value
        if not r.low < r.high:
            skipped.append(f"{k}: no range (low = high)")
            continue
        if a.source in LOCKED_SOURCES:
            skipped.append(f"{k}: set from {a.source} data, not overruled by the bills")
            continue
        if not a.user_editable:
            skipped.append(f"{k}: not editable")
            continue
        params.append(_Param(k, CANDIDATES.get(k, a.label), r.unit, float(r.low), float(r.expected),
                             float(r.high), a.source, a.confidence))
    return params, skipped


def _apply(model: BuildingModel, params: Sequence[_Param], values: Sequence[float],
           set_assumption: SetAssumption, source: str = "measured") -> BuildingModel:
    for p, v in zip(params, values):
        model = set_assumption(model, p.key, float(v), source)
    return model


def _daily_means(temps: Optional[Sequence[float]]) -> Optional[np.ndarray]:
    if temps is None:
        return None
    t = np.asarray(temps, dtype=float)
    if t.size == 8760:
        return t.reshape(365, 24).mean(axis=1)
    if t.size == 365:
        return t
    raise ValueError(f"outdoor temperatures must be 8760 hourly or 365 daily values; got {t.size}")


def _parts(m: DegreeDayModel, daily) -> dict[str, float]:
    return {k: float(v) for k, v in m.annual_parts(daily).items()}


def _heating_months(daily) -> np.ndarray:
    """Months where heating dominates: more heating than cooling degree days at 18 degC on the weather
    file; without weather, October to April."""
    if daily is None:
        return np.array([m in (0, 1, 2, 3, 9, 10, 11) for m in range(12)])
    return monthly_degree_days(daily, 18.0, "heating") > monthly_degree_days(daily, 18.0, "cooling")


def _response_kind(delta: np.ndarray, daily) -> str:
    """Which part of a fuel an input moves, from the shape of its monthly response (high minus low):
    the part every month shares is base load, the rest is weather, and the weather part is heating
    or cooling by the season it falls in [J]. Shape is used rather than a regression on degree days
    because night heating in mild climates falls in months with almost no daily-mean degree days."""
    d = delta * (1.0 if delta.sum() >= 0 else -1.0)
    total = float(np.abs(d).sum())
    if total <= 0:
        return "nothing"
    base_share = 12.0 * max(float(d.min()), 0.0) / total
    seasonal = d - max(float(d.min()), 0.0)
    heat = float(seasonal[_heating_months(daily)].sum())
    season = "heating" if heat >= 0.5 * float(seasonal.sum()) else "cooling"
    if base_share >= 0.6:
        return "base load"
    if base_share >= 0.3:
        return f"base load and {season}"
    return season


# ---------------------------------------------------------------- the door

def calibrate_to_bills(bundle: PropertyBundle, model: BuildingModel, bills: UtilityBills,
                       simulate: Simulate, set_assumption: SetAssumption,
                       outdoor_temp_c: Optional[Sequence[float]] = None, *,
                       keys: Optional[Iterable[str]] = None, max_simulations: int = DEFAULT_BUDGET,
                       apply_when_uncalibrated: bool = False) -> CalibrationResult:
    """Calibrate `model` to `bills` (MV-06). See the module docstring for the procedure.

    `simulate(bundle, model) -> BaselineResult` and `set_assumption(model, key, value, source) ->
    BuildingModel` come from the door. `outdoor_temp_c` is the weather file's hourly (8760) or daily
    (365) dry-bulb temperature; without it the degree-day split (step 2) is skipped and the
    explanations are coarser. `keys` overrides the list of inputs that may move (still filtered by
    range and source). Deterministic: the same inputs give the same output.
    """
    daily = _daily_means(outdoor_temp_c)
    warnings: list[str] = []
    measured = {"electricity": _check_bills(bills.electricity_kwh, "electricity", warnings)}
    if bills.gas_kwh is not None:
        measured["gas"] = _check_bills(bills.gas_kwh, "gas", warnings)
    count = [0]

    def run(m: BuildingModel, force: bool = False) -> BaselineResult:
        if count[0] >= max_simulations and not force:
            raise _Budget()
        count[0] += 1
        return simulate(bundle, m)

    base = run(model)
    sim0 = {f: _monthly(base, f) for f in measured}
    sim0_all = {f: _monthly(base, f) for f in ("electricity", "gas")}
    fuels = list(measured)
    blocked = _fuel_mismatch(model, base, measured, sim0, warnings)
    _low_months(measured, sim0, blocked, warnings)
    before = {f: calibration_ok(measured[f], sim0[f])[1] for f in fuels}
    _context_warnings(model, base, measured, warnings)

    split_bills: dict[str, DegreeDayModel] = {}
    if daily is not None:
        for f in fuels:
            if measured[f].sum() > 0:
                split_bills[f] = choose_degree_day(measured[f], daily, f)

    params, skipped = _candidates(model, keys)
    fit_fuels = [f for f in fuels if f not in blocked]
    sigma = {f: SIGMA_FRACTION * max(float(measured[f].mean()), 1e-9) for f in fit_fuels}

    # step 3: screening at low and high
    responses: dict[str, dict[str, np.ndarray]] = {}
    kept: list[_Param] = []
    screened_out: list[str] = list(skipped)
    try:
        for p in params:
            try:
                lo = run(set_assumption(model, p.key, p.low, "measured"))
                hi = run(set_assumption(model, p.key, p.high, "measured"))
            except _Budget:
                raise
            except Exception as exc:                    # an input the door cannot set is not fitted
                screened_out.append(f"{p.key}: could not be set ({exc})")
                continue
            d = {f: _monthly(hi, f) - _monthly(lo, f) for f in fit_fuels}
            effect = max((abs(float(d[f].sum())) / max(float(measured[f].sum()), 1e-9) for f in fit_fuels),
                         default=0.0)
            if effect < SCREEN_MIN:
                screened_out.append(f"{p.key}: moves the bills by less than {SCREEN_MIN:.1%} across its range")
                continue
            # an input whose main effect is on a fuel without (usable) bills is not fitted: the bills
            # of one fuel must not quietly rewrite the other [J]
            unbilled = [(f, abs(float((_monthly(hi, f) - _monthly(lo, f)).sum())) / float(sim0_all[f].sum()))
                        for f in ("electricity", "gas") if f not in fit_fuels and float(sim0_all[f].sum()) > 0]
            worst = max(unbilled, key=lambda x: x[1], default=None)
            if worst is not None and worst[1] > effect:
                screened_out.append(f"{p.key}: acts mainly on {worst[0]}, which has no usable bills")
                continue
            responses[p.key] = d
            kept.append(p)
    except _Budget:
        warnings.append("The simulation budget ran out while screening the inputs; only the inputs screened "
                        "so far were fitted.")

    # step 4: bounded regularised least squares
    cache: dict[tuple, dict[str, np.ndarray]] = {}
    best = {"cost": math.inf, "u": np.zeros(len(kept))}

    def sims(u: np.ndarray) -> dict[str, np.ndarray]:
        key = tuple(np.round(u, 10))
        if key not in cache:
            r = run(_apply(model, kept, [p.value(x) for p, x in zip(kept, u)], set_assumption))
            cache[key] = {f: _monthly(r, f) for f in fit_fuels}
        return cache[key]

    def residuals(u: np.ndarray) -> np.ndarray:
        s = sims(u)
        r = np.concatenate([(s[f] - measured[f]) / sigma[f] for f in fit_fuels] + [PRIOR_Z * u])
        c = float(r @ r)
        if c < best["cost"]:
            best["cost"], best["u"] = c, np.array(u, dtype=float)
        return r

    u_star = np.zeros(len(kept))
    if kept and fit_fuels:
        lb = np.array([p.bounds[0] for p in kept])
        ub = np.array([p.bounds[1] for p in kept])

        # The solver works on w = u + 1 (w in [0, 2], start at 1). scipy's trust-region-reflective
        # method sizes its first trust region from the norm of the start point, which is zero (or,
        # nudged off a bound, about 1e-10) at u = 0 and would stall the fit at the start.
        def res_w(w: np.ndarray) -> np.ndarray:
            return residuals(w - 1.0)

        def jac_w(w: np.ndarray) -> np.ndarray:
            # forward differences with a fixed step (2 % of a half-range), stepping inwards at an upper
            # bound; scipy's default relative step (~1e-8) is far below what moves the simulation
            r0 = res_w(w)
            jac = np.empty((r0.size, w.size))
            for i in range(w.size):
                h = DIFF_STEP if w[i] + DIFF_STEP <= ub[i] + 1.0 else -DIFF_STEP
                step = np.array(w, dtype=float)
                step[i] += h
                jac[:, i] = (res_w(step) - r0) / h
            return jac

        try:
            sol = least_squares(res_w, np.ones(len(kept)), jac=jac_w, bounds=(lb + 1.0, ub + 1.0), method="trf",
                                x_scale=1.0, xtol=1e-3, ftol=1e-4, gtol=1e-6, max_nfev=MAX_ITERATIONS)
            u_star = np.clip(sol.x - 1.0, lb, ub)
            if best["cost"] < float(sol.fun @ sol.fun) - 1e-12:
                u_star = np.clip(best["u"], lb, ub)
        except _Budget:
            u_star = np.clip(best["u"], lb, ub)
            warnings.append(f"The simulation budget ({max_simulations} runs) ran out during the fit; the best "
                            "point found so far is reported.")

    # step 5: values, statistics after
    values_all = [float(min(max(_sig(float(p.value(float(x)))), p.low), p.high)) for p, x in zip(kept, u_star)]
    moved = [(p, v, float(x)) for p, v, x in zip(kept, values_all, u_star)
             if abs(v - p.expected) > MOVED_MIN * (p.high - p.low)]
    fitted_model = _apply(model, [p for p, _, _ in moved], [v for _, v, _ in moved], set_assumption)
    final = run(fitted_model, force=True) if moved else base      # the final run is always allowed
    sim1 = {f: _monthly(final, f) for f in fuels}
    after = {}
    passes = {}
    for f in fuels:
        passes[f], after[f] = calibration_ok(measured[f], sim1[f])
    ok = all(passes.values()) and not blocked

    split: dict[str, FuelSplit] = {}
    for f, bm in split_bills.items():
        split[f] = FuelSplit(kind=bm.kind, tb_heat=bm.tb_heat, tb_cool=bm.tb_cool, bills=_parts(bm, daily),
                             model_before=_parts(fit_degree_day_at(sim0[f], daily, bm.kind, bm.tb_heat, bm.tb_cool), daily),
                             model_after=_parts(fit_degree_day_at(sim1[f], daily, bm.kind, bm.tb_heat, bm.tb_cool), daily))

    moves = [_move(p, v, x, responses[p.key], daily, split, measured, sim0, fit_fuels, model)
             for p, v, x in moved]
    if not ok:
        _diagnose(fuels, measured, sim1, after, passes, blocked, split, moves, warnings)

    out_model = model
    if ok or (apply_when_uncalibrated and moved):
        out_model = _record(fitted_model, moved, before, after, fuels, ok)
    out_base = (final if out_model is not model else base).model_copy(update={"calibrated_to_bills": ok})
    if ok:
        warnings.insert(0, "Calibrated to the bills: " + "; ".join(
            f"{f} bias {abs(after[f].nmbe):.1%} {_side_word(after[f].nmbe)} the bills, CV(RMSE) {after[f].cv_rmse:.1%}"
            for f in fuels) + " (tolerances +/- 5 % and 15 %).")
    return CalibrationResult(
        calibrated_to_bills=ok, model=out_model, baseline=out_base,
        values={p.key: v for p, v, _ in moved}, moves=moves, before=before, after=after, fuels=fuels,
        split=split, fitted_keys=[p.key for p in kept], screened_out=screened_out, warnings=warnings,
        simulations=count[0], measured={f: [float(x) for x in measured[f]] for f in fuels},
        simulated_before={f: [float(x) for x in sim0[f]] for f in fuels},
        simulated_after={f: [float(x) for x in sim1[f]] for f in fuels})


# ---------------------------------------------------------------- steps in detail

def _check_bills(values: Sequence[float], fuel: str, warnings: list[str]) -> np.ndarray:
    v = np.asarray(values, dtype=float)
    if v.shape != (12,):
        raise ValueError(f"{fuel} bills must hold 12 monthly values; got {v.size}")
    if not np.all(np.isfinite(v)) or np.any(v < 0):
        raise ValueError(f"{fuel} bills must be finite and not negative")
    if v.sum() <= 0:
        warnings.append(f"The {fuel} bills are zero all year: the building looks vacant or the meter is "
                        "another one; nothing to calibrate against.")
        return v
    return v


def _low_months(measured: dict, sim0: dict, blocked: set, warnings: list[str]) -> None:
    """A month far below what the model's own seasonal shape says it should be: the bill is under a
    quarter of the share of the year the model gives that month [J]. Zero gas in summer is not
    flagged when the model burns no gas in summer either."""
    for f, v in measured.items():
        s = sim0[f]
        if f in blocked or v.sum() <= 0 or s.sum() <= 0:
            continue
        expect = s / s.sum() * v.sum()
        low = [MONTHS[i] for i in range(12) if v[i] < 0.25 * expect[i] and expect[i] > 0.02 * v.sum()]
        if low:
            warnings.append(f"The {f} bill is far below the model's seasonal pattern in {', '.join(low)}: the "
                            "building may have been empty, or a meter reading was estimated. Those months will "
                            "not fit a model of an occupied building.")


def _fuel_mismatch(model: BuildingModel, base: BaselineResult, measured: dict, sim0: dict,
                   warnings: list[str]) -> set[str]:
    blocked = set()
    if "gas" in measured:
        bill, sim = float(measured["gas"].sum()), float(sim0["gas"].sum())
        if bill > 0 and sim < 0.01 * bill:
            blocked.add("gas")
            warnings.append(
                f"The gas bills total {bill:,.0f} kWh a year but the model burns no gas (heating "
                f"{model.systems.heating_fuel}, water heater {model.systems.dhw_fuel}): the fuel of the heating "
                "or the water heater is probably wrong, or there is an unmodelled gas appliance (a range, a "
                "dryer, a pool or spa heater). Gas is not calibrated; correct the fuel and run again.")
        elif bill <= 0 < sim:
            blocked.add("gas")
            warnings.append(f"The gas bills are zero but the model burns {sim:,.0f} kWh of gas a year: the "
                            "building probably has no gas service and heats or heats water electrically.")
    if float(measured["electricity"].sum()) <= 0:
        blocked.add("electricity")
    return blocked


def _context_warnings(model: BuildingModel, base: BaselineResult, measured: dict, warnings: list[str]) -> None:
    by_key = {a.key: a for a in model.assumptions}
    solar = by_key.get("roof.existing_solar")
    if solar is not None and solar.value is True:
        warnings.append("The roof already has solar panels: utility bills record use net of their output, "
                        "which the baseline does not model, so the electricity comparison is biased low.")
    if "gas" not in measured and float(np.sum(base.monthly_gas_kwh)) > 0:
        warnings.append("No gas bills were given, so the gas side of the model (heating or hot water) is not "
                        "checked against the meter.")
    warnings.append("The bills are compared with a simulation on the site's typical weather year, not on the "
                    "weather of the billing year (FEMP-MV4 4.5.3.1 asks for actual weather); an unusually hot "
                    "or mild year shows up as a seasonal difference.")


def _move(p: _Param, v: float, u: float, resp: dict, daily, split: dict, measured: dict, sim0: dict,
          fuels: list[str], model: BuildingModel) -> Move:
    # the fuel the input moves most (in kWh), and which part of that fuel
    f = max(fuels, key=lambda g: abs(float(resp[g].sum())))
    kind = _response_kind(resp[f], daily)
    direction = "raised" if v > p.expected else "lowered"
    why = ""
    sp = split.get(f)
    part = {"base load": "base", "heating": "heating", "cooling": "cooling"}.get(kind.split(" and ")[-1])
    if sp is not None and part is not None:
        b, mb = sp.bills[part], sp.model_before[part]
        name = "base load" if part == "base" else part
        if mb > 0 and abs(b - mb) <= 0.03 * mb:
            why = (f"the {name} part of {f} already agreed with the bills ({b:,.0f} against {mb:,.0f} kWh a year); "
                   "it moved to balance the other inputs and fuels in the joint fit")
        elif mb > 0:
            why = (f"the {name} part of {f} is {b:,.0f} kWh a year in the bills against {mb:,.0f} in the model "
                   f"({(b - mb) / mb:+.0%})")
        else:
            why = f"the bills show a {name} part of {f} of {b:,.0f} kWh a year that the model did not have"
    if not why:
        gap = float(measured[f].sum() - sim0[f].sum()) / max(float(measured[f].sum()), 1e-9)
        why = f"the {f} bills are {abs(gap):.0%} {'above' if gap > 0 else 'below'} the model over the year"
    a = next(x for x in model.assumptions if x.key == p.key)
    label = a.label
    reason = (f"{label} {direction} from {_fmt(p.expected)} to {_fmt(v)} {p.unit} (range {_fmt(p.low)} to "
              f"{_fmt(p.high)}, {p.source}): it drives the {kind} of {f}, and {why}.")
    if abs(u) >= AT_BOUND:
        reason += " It sits at the end of its range."
    return Move(key=p.key, label=label, unit=p.unit, before=p.expected, after=v, low=p.low, high=p.high,
                source_before=p.source, drives=kind, at_bound=abs(u) >= AT_BOUND, reason=reason)


def _diagnose(fuels, measured, sim, after, passes, blocked, split, moves, warnings) -> None:
    """Plain words for a calibration that fails: which months, by how much, and what it looks like."""
    bias_tol, cv_tol = TOLERANCES["monthly"]
    for f in fuels:
        if passes[f] or f in blocked:
            continue
        a = after[f]
        m, s = measured[f], sim[f]
        mean = float(m.mean())
        rel = (m - s) / mean
        bad = [i for i in range(12) if abs(rel[i]) > cv_tol]
        months = ", ".join(f"{MONTHS[i]} ({'bills above' if rel[i] > 0 else 'bills below'} by "
                           f"{abs(m[i] - s[i]):,.0f} kWh)" for i in bad) or "no single month; the error is spread"
        warnings.append(
            f"{f.capitalize()}: the model cannot be brought within the ASHRAE Guideline 14 monthly tolerances "
            f"(bias within +/- {bias_tol:.0%}, CV(RMSE) at most {cv_tol:.0%}) without moving an assumption "
            f"outside its range. Best fit inside the ranges: model {abs(a.nmbe):.1%} {_side_word(a.nmbe)} the "
            f"bills, CV(RMSE) {a.cv_rmse:.1%}. Months that disagree: {months}.")
        sp = split.get(f)
        if sp is not None:
            for part, words in _PART_WORDS[f].items():
                b, mo = sp.bills[part], sp.model_after[part]
                ref = max(sp.bills["base"] + sp.bills["heating"] + sp.bills["cooling"], 1e-9)
                if (b - mo) / ref > 0.10:
                    warnings.append(f"{f.capitalize()} {part} part: the bills carry {b - mo:,.0f} kWh a year more "
                                    f"than the model can reach ({b:,.0f} against {mo:,.0f}). {words[0]}")
                elif (mo - b) / ref > 0.10:
                    warnings.append(f"{f.capitalize()} {part} part: the bills carry {mo - b:,.0f} kWh a year less "
                                    f"than the model's lowest reach ({b:,.0f} against {mo:,.0f}). {words[1]}")
        else:
            gap = float((m - s).sum()) / max(float(m.sum()), 1e-9)
            warnings.append(f"{f.capitalize()}: over the year the bills are {abs(gap):.0%} "
                            f"{'above' if gap > 0 else 'below'} the best fit.")
    stuck = [mv.label for mv in moves if mv.at_bound]
    if stuck:
        warnings.append("In the best fit these assumptions sit at the end of their ranges, so the ranges or the "
                        "model's structure may be wrong; confirm them on site: " + ", ".join(stuck) + ".")
    warnings.append("The model is left as it was (no assumption changed); the best in-range values are "
                    "reported as a proposal only. A consultant would look for what the model is missing "
                    "before trusting its savings figures.")


_PART_WORDS = {
    "electricity": {
        "base": ("Look for a load that runs all year and is not in the model: a pool or spa pump, an electric "
                 "vehicle, a second refrigerator or freezer, a server or equipment room, a well pump.",
                 "The building may have been partly empty, or some of its use is on another meter."),
        "cooling": ("Summer use rises faster with temperature than the model allows: an undersized, failing or "
                    "low-charge air conditioner, more cooled area than the scan shows, or a cooling load "
                    "the model lacks.",
                    "Cooling is used less than the model can reach: the air conditioning may be off, run "
                    "sparingly or only in part of the building."),
        "heating": ("Winter electricity rises faster than the model allows: electric resistance heaters, "
                    "heat tape, or a heat pump on its backup heat.",
                    "Electric heating is used less than modelled: perhaps a fuel or wood stove does the work."),
    },
    "gas": {
        "base": ("Gas use all year beyond the water heater: a gas range, a dryer, a pool or spa heater, or "
                 "more hot water than the occupant count suggests.",
                 "Less gas all year than the water heater alone should burn: fewer occupants or hot water "
                 "made by something else."),
        "heating": ("Gas heating rises faster with cold than the model allows: a less efficient furnace or "
                    "leakier ducts or envelope than the ranges admit.",
                    "Gas heating is lower than the model's lowest reach: the house may be heated only in part, "
                    "or by another source."),
        "cooling": ("Gas use rising in summer is unusual: check for a gas pool heater or a gas cooling plant.",
                    "No summer gas pattern is expected."),
    },
}


def _record(model: BuildingModel, moved, before: dict, after: dict, fuels: list[str], ok: bool) -> BuildingModel:
    """Add the bills as evidence to every moved assumption, keep the original range in the note,
    and set the confidence of an inferred value."""
    stats = "; ".join(f"{f} NMBE {before[f].nmbe:+.1%} -> {after[f].nmbe:+.1%}, CV(RMSE) {before[f].cv_rmse:.1%} -> "
                      f"{after[f].cv_rmse:.1%}" for f in fuels)
    ref = "+".join(f"bills.{f}_kwh" for f in fuels)
    status = ("calibrated to 12 monthly bills (MV-04 met)" if ok else
              "best in-range fit to 12 monthly bills, MV-04 NOT met (proposal applied on request)")
    by_key = {p.key: (p, v) for p, v, _ in moved}
    out: list[Assumption] = []
    for a in model.assumptions:
        if a.key in by_key:
            p, v = by_key[a.key]
            note = (f"Inferred, not measured: {status}. Was {_fmt(p.expected)} {p.unit} in range {_fmt(p.low)} to "
                    f"{_fmt(p.high)} ({p.source}); now {_fmt(v)}. {stats}.")
            a = a.model_copy(update={"evidence": [*a.evidence, EvidenceRef(kind="user", ref=ref, note=note)],
                                     "confidence": CALIBRATED_CONFIDENCE})
        out.append(a)
    return model.model_copy(update={"assumptions": out})
