"""Measure PV_ROOF (A19): bill savings from a SolarDesign.

Takes a finished ``SolarDesign`` (A14 lays it out), the ``BaselineResult`` of the state the
measure is evaluated against, and the ``Tariff``. Hourly PV and load arrays are optional; with
them the self-consumption fraction is computed by the hourly balance of TAR-03, without them the
design's own ``self_consumption_fraction`` is used.

Formulas: specs/physics/04-economics-emissions-mv.md TAR-03 (export regimes), TAR-01 (flat
price), EMI-01 (grid emission factors), UNC-02 (ranges). Production range: 01-solar-pv PV-09.

No sibling subfolder is imported (workplan 2.6): the eGRID factors and the propagation rule are
kept locally, each with its entry id.
"""
from __future__ import annotations

import math
import re
from typing import Callable, Literal, Optional, Sequence

import numpy as np

from backend.schema import (BaselineResult, EnergyUse, FetchRecord, Flag, MeasureResult, Ranged, SolarDesign,
                           Tariff)

Regime = Literal["net_metering", "net_billing", "none"]

# ---- EMI-01: eGRID2023 rev 2, CO2e total-output (EF_avg) and non-baseload (EF_nb), kg/kWh ----
EGRID_KG_PER_KWH: dict[str, tuple[float, float]] = {
    "CAMX": (0.19504, 0.43599),   # WECC California: every Los Angeles-area ZIP checked
    "ERCT": (0.33413, 0.56586),   # ERCOT All: CenterPoint delivery area
    "US": (0.3497, 0.6256),       # national reference, used only when the state is unknown
}
STATE_SUBREGION = {"CA": "CAMX", "TX": "ERCT"}   # EMI-01 "Location" for the two golden cities

# ---- UNC-02: import and export prices share the correlation group "price_level" ----
PRICE_GROUP = "price_level"

# ---- TAR-03 "Regime by utility": utilities the tariff string can name ----
_UTILITY_REGIME: list[tuple[re.Pattern, Regime, str]] = [
    (re.compile(r"\bLADWP\b|Los Angeles Department of Water", re.I), "net_metering", "LADWP"),
    (re.compile(r"\bSCE\b|Southern California Edison", re.I), "net_billing", "SCE"),
    (re.compile(r"CenterPoint|retail electric provider|\bERCOT\b", re.I), "none", "Texas retail"),
]

W_NM_STEADY = ("Net metering is modelled as steady-state annual netting at the energy price; "
               "fixed and minimum charges are never offset (physics 04 TAR-03 rule 1).")
W_TX_NONE = ("No export value is assumed: Texas has no mandated buyback, so all savings come from "
             "self-consumption. Export value depends on your retail electricity plan; none assumed.")
W_TX_USER = ("Export value is the buy-back rate of your retail plan; its low end is zero because "
             "Texas has no mandated buyback and the plan can change at renewal.")
W_NB_NO_EXPORT = ("No export price is known for this net-billing tariff, so exported kWh are valued "
                  "at zero (physics 04 TAR-03 rule 2); the retail price is never substituted.")
W_NB_TOU = ("Net billing customers are on time-of-use rates; a flat import price is a stated "
            "approximation (physics 04 TAR-02).")


# ---------------------------------------------------------------- TAR-03 tools

def self_consumption_fraction(hourly_load_kwh: Sequence[float], hourly_pv_kwh: Sequence[float]) -> float:
    """TAR-03: f_sc = 1 - sum(max(G_h - L_h, 0)) / sum(G_h). 1.0 when there is no generation."""
    load = np.asarray(hourly_load_kwh, dtype=float)
    pv = np.asarray(hourly_pv_kwh, dtype=float)
    if load.shape != pv.shape:
        raise ValueError(f"hourly load and PV differ in length: {load.shape} vs {pv.shape}")
    total = float(pv.sum())
    if total <= 0:
        return 1.0
    export = float(np.clip(pv - load, 0.0, None).sum())
    return 1.0 - export / total


def pv_bill_savings(regime: Regime, e_pv_kwh: float, e_load_kwh: float, f_sc: float,
                    p_import: float, p_export: float) -> float:
    """TAR-03 first-year bill savings, USD/yr.

    net_metering, (b): min(E_pv, E_load) * p_energy; the surplus earns nothing.
    net_billing and none, (a): f_sc E_pv p_import + (1 - f_sc) E_pv p_export.
    """
    if regime == "net_metering":
        return min(e_pv_kwh, e_load_kwh) * p_import
    return f_sc * e_pv_kwh * p_import + (1.0 - f_sc) * e_pv_kwh * p_export


def named_utility(utility: str) -> Optional[tuple[Regime, str]]:
    """The regime and short name of a utility the tariff string names, or None (unconfirmed)."""
    for pat, regime, name in _UTILITY_REGIME:
        if pat.search(utility or ""):
            return regime, name
    return None


def export_regime(tariff: Tariff) -> tuple[Regime, list[str]]:
    """The regime used to value exports, with the warnings that come with the choice.

    ``Tariff.export_regime`` (set by the Data lane) wins. A utility string that names no utility
    (for example "CA state average (RES)") is unconfirmed: it is never read as LADWP.
    """
    warnings: list[str] = []
    named = named_utility(tariff.utility)
    if named is None:
        warnings.append(
            f"The electric utility is unconfirmed (tariff names '{tariff.utility}'). Solar "
            "savings depend on it (SPEC 6.6): inside the City of Los Angeles LADWP nets kWh at the "
            "energy price, in SCE territory net billing pays less for exports. Confirm the utility "
            "on a bill.")
    if tariff.export_regime is not None:
        regime: Regime = tariff.export_regime
        if named is not None and named[0] != regime:
            warnings.append(f"The tariff names {named[1]}, whose regime is {named[0]}, but its export "
                            f"regime is {regime}; exports are valued as {regime}.")
        elif named is None:
            warnings.append(f"Exports are valued by the tariff's export regime, {regime}.")
        return regime, warnings
    if named is not None:
        warnings.append(f"The tariff has no export regime; {named[0]} is taken from the utility "
                        f"({named[1]}, physics 04 TAR-03).")
        return named[0], warnings
    warnings.append("The tariff has no export regime and names no utility; exports are valued as "
                    "net billing (physics 04 TAR-03 rule 2).")
    return "net_billing", warnings


# ---------------------------------------------------------------- UNC-02

def propagate(f: Callable[[dict[str, float]], float],
              inputs: dict[str, tuple[float, float, float]],
              groups: dict[str, str] | None = None) -> tuple[float, float, float]:
    """UNC-02: one-at-a-time runs, linear within a correlation group, quadrature between groups."""
    groups = groups or {}
    x0 = {k: v[1] for k, v in inputs.items()}
    y0 = f(x0)
    lo_g: dict[str, float] = {}
    hi_g: dict[str, float] = {}
    for k, (lo, _, hi) in inputs.items():
        if lo == hi:
            continue
        d = [f({**x0, k: lo}) - y0, f({**x0, k: hi}) - y0]
        g = groups.get(k, k)
        lo_g[g] = lo_g.get(g, 0.0) + min(*d, 0.0)
        hi_g[g] = hi_g.get(g, 0.0) + max(*d, 0.0)
    y_lo = y0 - math.sqrt(sum(v * v for v in lo_g.values()))
    y_hi = y0 + math.sqrt(sum(v * v for v in hi_g.values()))
    return y_lo, y0, y_hi


# ---------------------------------------------------------------- helpers

def _r(lo: float, ex: float, hi: float, unit: str, nd: int = 2) -> Ranged:
    lo, ex, hi = round(lo, nd), round(ex, nd), round(hi, nd)
    return Ranged(low=min(lo, ex), expected=ex, high=max(hi, ex), unit=unit)


def _t(r: Ranged) -> tuple[float, float, float]:
    return (r.low, r.expected, r.high)


def hourly_load_from_monthly(monthly_kwh: Sequence[float], n_hours: int = 8760) -> np.ndarray:
    """A load flat within each month that sums to the twelve monthly totals (non-leap year for
    8760 hours, leap year for 8784). An approximation: it has no daily shape."""
    year = {8760: 2023, 8784: 2024}.get(n_hours)
    if year is None or len(monthly_kwh) != 12:
        raise ValueError("needs 12 monthly values and 8760 or 8784 hours")
    hours = np.arange(f"{year}-01-01T00", f"{year + 1}-01-01T00", dtype="datetime64[h]")
    month = hours.astype("datetime64[M]").astype(int) % 12
    counts = np.bincount(month, minlength=12)
    per_hour = np.asarray(monthly_kwh, dtype=float) / counts
    return per_hour[month]


def _blocking(flags: Sequence[Flag]) -> Optional[Flag]:
    for fl in flags:
        if fl.status == "blocked":
            return fl
    return None


def _flag_warning(fl: Flag) -> Optional[str]:
    if fl.status not in ("unknown", "likely_upgrade") or fl.added_cost_usd is None:
        return None
    c = fl.added_cost_usd
    what = "unknown" if fl.status == "unknown" else "likely to need an upgrade"
    return (f"{fl.key} is {what}: it could add {c.low:,.0f} to {c.high:,.0f} {c.unit}, "
            "which is not in the installed cost.")


def _skip(design: Optional[SolarDesign], reason: str, flags: list[Flag]) -> MeasureResult:
    kw = f", {design.system_kw_dc:.2f} kW" if design is not None and design.system_kw_dc > 0 else ""
    return MeasureResult(measure_id="PV_ROOF", title=f"Rooftop solar{kw}", applicable=False,
                         not_applicable_reason=reason, flags=flags)


# ---------------------------------------------------------------- system parameters (A4)

def design_with_system_parameters(design: SolarDesign) -> SolarDesign:
    """Fill the system parameters the layout leaves empty with the A4 values the yield used.

    The layout (A14) places modules; the yield behind ``annual_kwh`` is A4's PV chain, which
    assumes the DC/AC ratio, the PVWatts loss stack and, over the life, PV-07 degradation.
    Finance reads ``degradation_rate`` (ECO-07): left empty it prices the array as if it never
    degrades, which overstates life-cycle savings by several percent. A value already on the
    design (e.g. a quoted product) is kept.
    """
    from backend.analysis.physics.pv import chain as _pv_chain
    from backend.analysis.physics.pv import constants as _pv
    upd: dict = {}
    if design.dc_ac_ratio is None:
        upd["dc_ac_ratio"] = _pv.DC_AC_RATIO
    ratio = upd.get("dc_ac_ratio", design.dc_ac_ratio)
    if design.inverter_kw_ac is None and design.system_kw_dc > 0 and ratio:
        upd["inverter_kw_ac"] = round(design.system_kw_dc / ratio, 3)
    if design.losses_percent is None:
        upd["losses_percent"] = round(100 * _pv_chain.system_loss_fraction(), 4)
    if design.degradation_rate is None:
        upd["degradation_rate"] = _pv.DEGRADATION_RATE_EXPECTED
    return design.model_copy(update=upd) if upd else design


# ---------------------------------------------------------------- roof extent (D16)

EXTENT_RECORD = "property/extract:extent"


def extent_warnings(provenance: Sequence[FetchRecord]) -> list[str]:
    """A larger roof outline at the same property (D16), as a PV_ROOF warning.

    The design roof is the structure whose footprint matches CoStar's floor plate (the
    tower on a tower-and-podium site). Other aerial captures can outline a larger extent,
    sometimes with panels already on it; that changes the possible system size and
    whether solar is already there, so the result says so instead of hiding it.
    """
    out = []
    for r in provenance:
        if r.layer == "vexcel" and r.what == EXTENT_RECORD:
            out.append("The solar design uses the building whose footprint matches CoStar's floor area per "
                       "storey; aerial captures also outline a larger roof at this property. "
                       + (r.detail or "").replace("**", ""))
    return out


# ---------------------------------------------------------------- the measure

def evaluate_pv(design: SolarDesign, baseline: BaselineResult, tariff: Tariff, *,
                hourly_pv_kwh: Optional[Sequence[float]] = None,
                hourly_load_kwh: Optional[Sequence[float]] = None,
                flags: Sequence[Flag] = (),
                existing_solar: bool = False,
                state: Optional[str] = None,
                electricity_price: Optional[Ranged] = None,
                export_price: Optional[Ranged] = None,
                provenance: Sequence[FetchRecord] = ()) -> MeasureResult:
    """``PV_ROOF`` as a ``MeasureResult`` with ``savings`` and ``solar`` filled, finance empty.

    design             the layout (A14); ``annual_kwh`` is the PV-09 production range.
    baseline           the state the measure is evaluated against; its annual electricity is
                       the site load E_load.
    tariff             import price, export price and ``export_regime``.
    hourly_pv_kwh      optional hourly production (any scale: only its shape is used).
    hourly_load_kwh    optional hourly site load (shape only). With PV but no load, a load flat
                       within each month of ``baseline.monthly_electricity_kwh`` is used.
    flags              more feasibility flags; any ``blocked`` flag skips the measure.
    existing_solar     the roof already carries PV (A11 reports it outside the contract).
    state              "CA" or "TX", picks the eGRID subregion (EMI-01).
    electricity_price  the ``tariff.electricity_usd_per_kwh`` assumption as a range, if any.
    export_price       an export price range, e.g. the user's Texas buy-back rate.
    provenance         the bundle's FetchRecords; a D16 extent disagreement becomes a warning.
    """
    design_flags = [design.electrical, design.structural]
    all_flags = design_flags + [f for f in flags if f not in design_flags]

    if existing_solar:
        return _skip(design, "Already done: the roof already carries solar panels (Vexcel solar "
                     "attribute).", [])
    blocker = _blocking(all_flags)
    if blocker is not None:
        return _skip(design, f"Blocked by feasibility flag {blocker.key}: {blocker.message}",
                     [blocker])
    if design.panel_count <= 0 or design.annual_kwh.expected <= 0:
        return _skip(design, "No module fits on the usable roof area.", all_flags)

    warnings: list[str] = []
    regime, w = export_regime(tariff)
    warnings += w

    # ---- prices: import (TAR-01 marginal price) and export (TAR-03) ----
    p_imp = _t(electricity_price) if electricity_price is not None else (
        tariff.electricity_usd_per_kwh,) * 3
    if regime == "net_metering":
        p_exp = (0.0, 0.0, 0.0)    # (b) has no separate export price: surplus earns nothing
        warnings.append(W_NM_STEADY)
    elif regime == "none":
        # TAR-03 rule 2a: low is zero always; expected = high = the plan's rate when known
        rate = export_price.expected if export_price is not None else tariff.export_usd_per_kwh
        if rate is None or rate <= 0:
            p_exp = (0.0, 0.0, 0.0)
            warnings.append(W_TX_NONE)
        else:
            hi = max(rate, export_price.high) if export_price is not None else rate
            p_exp = (0.0, rate, hi)
            warnings.append(W_TX_USER)
    else:
        if export_price is not None:
            p_exp = _t(export_price)
        elif tariff.export_usd_per_kwh is not None:
            p_exp = (tariff.export_usd_per_kwh,) * 3
        else:
            p_exp = (0.0, 0.0, 0.0)
            warnings.append(W_NB_NO_EXPORT)
        warnings.append(W_NB_TOU)

    e_pv = _t(design.annual_kwh)
    e_load = _t(baseline.annual.electricity_kwh)
    inputs: dict[str, tuple[float, float, float]] = {
        "e_pv": e_pv, "e_load": e_load, "p_import": p_imp, "p_export": p_exp}
    groups = {"p_import": PRICE_GROUP, "p_export": PRICE_GROUP}

    # ---- self-consumption (TAR-03 hourly balance) ----
    fsc_fn: Optional[Callable[[float, float], float]] = None
    fsc_source = None
    if hourly_pv_kwh is not None:
        pv_shape = np.asarray(hourly_pv_kwh, dtype=float)
        if hourly_load_kwh is not None:
            load_shape = np.asarray(hourly_load_kwh, dtype=float)
            fsc_source = "hourly"
        else:
            load_shape = hourly_load_from_monthly(baseline.monthly_electricity_kwh, len(pv_shape))
            fsc_source = "hourly_pv_monthly_load"
            if regime != "net_metering":
                warnings.append("Self-consumption uses hourly PV against a load flat within each "
                                "month; the load's daily shape is not modelled.")
        pv_sum, load_sum = float(pv_shape.sum()), float(load_shape.sum())
        if pv_sum <= 0 or load_sum <= 0:
            raise ValueError("hourly PV and load must each have a positive total")

        def fsc_fn(epv: float, eload: float) -> float:
            return self_consumption_fraction(load_shape * (eload / load_sum),
                                             pv_shape * (epv / pv_sum))
    elif design.self_consumption_fraction is not None:
        fsc0 = float(design.self_consumption_fraction)
        inputs["f_sc"] = (fsc0, fsc0, fsc0)
        fsc_source = "design"
    else:
        # No hourly data and no figure on the design: f_sc runs from 0 to its upper bound
        # min(1, E_load / E_pv); the midpoint as expected has no source and is an assumption.
        up = min(1.0, e_load[1] / e_pv[1])
        inputs["f_sc"] = (0.0, up / 2.0, up)
        fsc_source = "assumed_range"
        if regime != "net_metering":
            warnings.append("Self-consumption was not computed (no hourly data): it is carried as "
                            "a range from 0 to the annual upper bound, with the midpoint as "
                            "expected; that midpoint has no source.")

    def fsc_of(x: dict[str, float]) -> float:
        return fsc_fn(x["e_pv"], x["e_load"]) if fsc_fn is not None else x["f_sc"]

    def savings_usd(x: dict[str, float]) -> float:
        return pv_bill_savings(regime, x["e_pv"], x["e_load"], fsc_of(x), x["p_import"], x["p_export"])

    def export_usd(x: dict[str, float]) -> float:
        if regime == "net_metering":
            return 0.0
        return (1.0 - fsc_of(x)) * x["e_pv"] * x["p_export"]

    cost = propagate(savings_usd, inputs, groups)
    export_value = propagate(export_usd, inputs, groups)
    x0 = {k: v[1] for k, v in inputs.items()}
    fsc0 = fsc_of(x0)

    # ---- kWh and CO2 (EMI-01: the reduction includes PV used on site or exported) ----
    sub = STATE_SUBREGION.get((state or "").upper(), "US")
    ef_avg, ef_nb = EGRID_KG_PER_KWH[sub]
    if sub == "US":
        warnings.append("State unknown: emissions use the U.S. average eGRID rate (EMI-01).")
    surplus = max(e_pv[1] - e_load[1], 0.0)
    if surplus > 0:
        if regime == "net_metering":
            warnings.append(f"Production exceeds the site's annual use by {surplus:,.0f} kWh; under "
                            "net metering that surplus credit is valued at zero.")
        else:
            warnings.append(f"Production exceeds the site's annual use by {surplus:,.0f} kWh.")
        if regime == "none":
            warnings.append("Annual production above annual consumption has a registration "
                            "consequence in Texas (legal spec TX-SOL-36).")
    for fl in all_flags:
        fw = _flag_warning(fl)
        if fw:
            warnings.append(fw)
    warnings += extent_warnings(provenance)

    savings = EnergyUse(
        electricity_kwh=_r(*e_pv, "kWh"),
        gas_kwh=_r(0.0, 0.0, 0.0, "kWh"),
        cost_usd=_r(*cost, "USD"),
        co2_kg=_r(e_pv[0] * ef_avg, e_pv[1] * ef_avg, e_pv[2] * ef_avg, "kg"),
        co2_nonbaseload_kg=_r(e_pv[0] * ef_nb, e_pv[1] * ef_nb, e_pv[2] * ef_nb, "kg"),
    )

    self_kwh = fsc0 * e_pv[1]
    params = {
        "export_regime": regime,
        "self_consumption_source": fsc_source,
        "self_consumption_fraction": round(fsc0, 4),
        "self_consumed_kwh": round(self_kwh, 1),
        "exported_kwh": round(e_pv[1] - self_kwh, 1),
        "netted_kwh": round(min(e_pv[1], e_load[1]), 1),
        "surplus_kwh": round(surplus, 1),
        "import_usd_per_kwh": _r(*p_imp, "USD/kWh", 4).model_dump(),
        "export_usd_per_kwh": _r(*p_exp, "USD/kWh", 4).model_dump(),
        "export_value_usd": _r(*export_value, "USD").model_dump(),
        "egrid_subregion": sub,
    }
    solar = design_with_system_parameters(design)
    if fsc_source in ("hourly", "hourly_pv_monthly_load"):
        solar = solar.model_copy(update={"self_consumption_fraction": round(fsc0, 4)})

    if regime == "net_metering":
        how = "kWh are netted at the energy price over the year"
    elif regime == "none":
        how = "only the self-consumed share is sure to earn; Texas mandates no export price"
    else:
        how = "self-consumed kWh save the import price and exports earn the export price"
    return MeasureResult(
        measure_id="PV_ROOF",
        title=f"Rooftop solar, {design.system_kw_dc:.2f} kW",
        applicable=True,
        description=(f"{design.panel_count} modules, {design.system_kw_dc:.2f} kW DC, about "
                     f"{e_pv[1]:,.0f} kWh a year; {how}."),
        params=params,
        savings=savings,
        flags=all_flags,
        formula_ids=["PV-09", "TAR-01", "TAR-03", "EMI-01", "UNC-02"],
        solar=solar,
        warnings=warnings,
    )
