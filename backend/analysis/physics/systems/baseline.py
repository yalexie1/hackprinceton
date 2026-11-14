"""S5 baseline from hourly zone loads: HVAC, water heating, lighting, plug loads and appliances,
then cost (TAR), emissions (EMI) and low / expected / high (UNC-02).

Inputs are contract types (`Systems`, `Tariff`, `Assumption`) plus the hourly zone loads as
arrays (`HourlyLoads`, produced by the zone model, A2). This module never imports the zone model:
the door (`backend/analysis/api.py`) runs A2 with `internal_gains_hourly(...)` and hands the
result here.

Ranges. Expected is the run at every input's expected value. Low and high come from one-at-a-time
runs over the `Systems` ranges, the stated bands of the entries used (C_D, the +-15 % seasonal
and DHW bands, the +-30 % hot water volume) and the tariff price ranges in the assumption
registry, combined in quadrature (UNC-02). The zone loads are one fixed input: inputs that also
change the zone loads (setpoints, envelope, and the internal gains of lighting, plug loads and
occupants) are only propagated through the loads when the caller passes zone runs for them in
`load_variants` (key -> (loads at low, loads at high)).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

import numpy as np

from backend.schema import Assumption, BaselineResult, EnergyUse, Ranged, Systems, Tariff

from .constants import (HOME_LPD_REFERENCE_W_M2, HOME_PPD_REFERENCE_W_M2, CD_DEFAULT, CENTRAL_PLANT_BAND, COOL_CURVE_VALID_C, COP_PER_BTU_PER_WH,
                        DHW_ENERGY_BAND, DHW_VOLUME_BAND, DSE_DUCTS_OUTSIDE, HP_COLD_HOURS_WARN,
                        HP_COLD_LIMIT_C, RTU_MIN_CAPACITY_W, SEASONAL_CLIMATE_BAND, SIZING_FACTOR)
from .cost import grid_emission_factor, gas_emission_factor
from .dhw import daily_hot_water_volume, dhw_energy, mains_temperature
from .hvac import (cooling_power_single_stage, cop47_from_hspf, eer_a_from_seer,
                   heat_pump_heating_power, to_base_metric)
from .loads import Calendar, building_kind, default_calendar, end_use_profiles
from .uncertainty import SensitivityRow, propagate

END_USES = ("heating", "cooling", "water_heating", "lighting", "plug", "appliances")
PRICE_GROUP = "price_level"     # UNC-02 correlation group (physics 04)
DEFAULT_GROUPS = {"tariff.electricity_usd_per_kwh": PRICE_GROUP, "tariff.gas_usd_per_kwh": PRICE_GROUP,
                  "tariff.export_usd_per_kwh": PRICE_GROUP}


@dataclass(frozen=True)
class HourlyLoads:
    """Hourly zone results for one year (one value per hour, all the same length).

    heating_need_w, cooling_need_w: sensible need at the zone, both >= 0 (ZON-04 `phi_hc` split by
    sign). outdoor_temp_c: dry bulb of the same hours. latent_oa_w: latent load of outdoor air
    (INF-07), counted in cooling hours; None = 0. The internal latent gains are added here."""
    heating_need_w: np.ndarray
    cooling_need_w: np.ndarray
    outdoor_temp_c: np.ndarray
    latent_oa_w: Optional[np.ndarray] = None

    def __post_init__(self):
        n = len(self.heating_need_w)
        for name in ("cooling_need_w", "outdoor_temp_c") + (("latent_oa_w",) if self.latent_oa_w is not None else ()):
            if len(getattr(self, name)) != n:
                raise ValueError(f"HourlyLoads.{name} has {len(getattr(self, name))} values, expected {n}")


@dataclass(frozen=True)
class SystemsBaseline:
    """A3 output: the contract result plus what the door and measures need beside it."""
    baseline: BaselineResult
    hourly: dict                         # expected run: arrays per hour (kWh per hour, W for gains)
    occupants: float
    occupants_source: str                # "systems" or "schedule_default"
    cooling_route: str                   # "hourly_seer", "hourly_eer", "seasonal", "ieer", "none"
    heating_route: str                   # "furnace", "resistance", "heat_pump_hourly", "heat_pump_seasonal", "none"
    subregion: str
    formula_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    sensitivity: list[SensitivityRow] = field(default_factory=list)


# ---------- helpers ----------

def _ends(r: Optional[Ranged]):
    return None if r is None or r.low == r.high else (r.low, r.high)


def _dse(systems: Systems) -> tuple[Ranged, Optional[str]]:
    """HVAC-08: the model's value; else the DEF-06 upper bound for ducts outside the conditioned
    space; else 1."""
    if systems.distribution_efficiency is not None:
        return systems.distribution_efficiency, None
    if systems.duct_location in ("attic", "garage", "crawlspace"):
        lo, ex, hi = DSE_DUCTS_OUTSIDE
        return Ranged(low=lo, expected=ex, high=hi, unit="-"), \
            "distribution efficiency is an upper bound (HVAC-08, DEF-06): duct losses are understated"
    return Ranged(low=1.0, expected=1.0, high=1.0, unit="-"), None


def _cooling_setup(systems: Systems):
    """Pick the cooling route and the rating it varies. Returns (route, Ranged in the route's metric,
    assumption key, warnings, formula ids)."""
    if systems.hvac_type == "none":
        return "none", None, None, ["no cooling equipment: cooling need is not met"], []
    ducted = systems.duct_location != "none"
    cap = systems.cooling_capacity_w
    variable = systems.compressor_type in ("two_stage", "variable")
    if systems.cooling_rating is not None and systems.cooling_rating_metric is not None:
        r, metric = systems.cooling_rating, systems.cooling_rating_metric
        conv = lambda v: to_base_metric(v, metric, ducted)[0]   # noqa: E731
        base = Ranged(low=conv(r.low), expected=conv(r.expected), high=conv(r.high), unit=to_base_metric(1, metric)[1])
        key = "hvac.cooling_rating"
        m = base.unit
    else:
        c = systems.cooling_cop        # seasonal W/W, read as a SEER equivalent (HVAC-01)
        base = Ranged(low=c.low / COP_PER_BTU_PER_WH, expected=c.expected / COP_PER_BTU_PER_WH,
                      high=c.high / COP_PER_BTU_PER_WH, unit="SEER")
        key, m = "hvac.cooling_cop", "SEER"
    ids = ["HVAC-01"]
    if m == "IEER":
        return "ieer", base, key, [], ids + ["HVAC-07"]
    if m == "EER":
        if systems.hvac_type == "rooftop_unit" and (cap is None or cap >= RTU_MIN_CAPACITY_W):
            return "ieer", base, key, ["rooftop unit rated by EER only: EER used as its IEER, a conservative "
                                       "baseline (HVAC-07)"], ids + ["HVAC-07"]
        return "hourly_eer", base, key, [], ids + ["HVAC-02", "HVAC-03"]
    if variable:
        return "seasonal", base, key, [], ids + ["HVAC-04"]
    return "hourly_seer", base, key, [], ids + ["HVAC-02", "HVAC-03"]


def _heating_setup(systems: Systems, tariff: Tariff):
    """Pick the heating route. Returns (route, Ranged efficiency or rating, key, warnings, ids)."""
    if systems.hvac_type == "none" or systems.heating_fuel == "none":
        return "none", None, None, ["no heating equipment: heating need is not met"], []
    warn: list[str] = []
    rating_is_hspf = systems.heating_rating is not None and systems.heating_rating_metric in ("HSPF", "HSPF2", "COP")
    if systems.hvac_type == "heat_pump":
        if rating_is_hspf:
            metric = systems.heating_rating_metric
            r = systems.heating_rating
            if metric == "COP":
                conv = lambda v: v / COP_PER_BTU_PER_WH   # noqa: E731
            else:
                conv = lambda v: to_base_metric(v, metric, systems.duct_location != "none")[0]   # noqa: E731
            key = "hvac.heating_rating"
        else:
            r = systems.heating_efficiency
            conv = lambda v: v / COP_PER_BTU_PER_WH   # noqa: E731
            key = "hvac.heating_efficiency"
        hspf = Ranged(low=conv(r.low), expected=conv(r.expected), high=conv(r.high), unit="HSPF")
        return "heat_pump", hspf, key, warn, ["HVAC-01", "HVAC-05"]
    fuel = systems.heating_fuel
    if fuel == "unknown":
        fuel = "gas" if tariff.gas_usd_per_kwh is not None else "electricity"
        warn.append(f"heating fuel unknown: {fuel} assumed (gas price {'present' if fuel == 'gas' else 'absent'} "
                    "in the tariff)")
    if systems.heating_rating is not None and systems.heating_rating_metric == "AFUE":
        eff, key = systems.heating_rating, "hvac.heating_rating"
    else:
        eff, key = systems.heating_efficiency, "hvac.heating_efficiency"
    return ("furnace" if fuel == "gas" else "resistance"), eff, key, warn, ["HVAC-06"]


# ---------- public ----------

def internal_gains_hourly(systems: Systems, floor_area_m2: float, calendar: Calendar | None = None,
                          bedrooms: int | None = None, n_hours: int = 8760) -> dict:
    """LGT-03 hourly gains at expected inputs, for the zone model (A2): {'sensible_w', 'latent_w',
    'occupants', 'occupants_source'}. Occupants from `Systems.occupants` when set, else the
    schedule default."""
    cal = calendar or default_calendar(n_hours)
    occ = systems.occupants.expected if systems.occupants is not None else None
    eu = end_use_profiles(occupancy_schedule=systems.occupancy_schedule, floor_area_m2=floor_area_m2, cal=cal,
                          lpd_w_m2=systems.lighting_w_per_m2.expected, ppd_w_m2=systems.plug_w_per_m2.expected,
                          occupants=occ, bedrooms=bedrooms)
    return {"sensible_w": eu.sensible_gain_w, "latent_w": eu.latent_gain_w, "occupants": eu.occupants,
            "occupants_source": eu.occupants_source}


def systems_baseline(systems: Systems, tariff: Tariff, loads: HourlyLoads, *, floor_area_m2: float,
                     subregion: str = "US", bedrooms: int | None = None, calendar: Calendar | None = None,
                     assumptions: Sequence[Assumption] = (),
                     load_variants: Mapping[str, tuple[HourlyLoads, HourlyLoads]] | None = None,
                     groups: Mapping[str, str] | None = None,
                     hourly_path: str | None = None) -> SystemsBaseline:
    """Annual, monthly and end-use energy, cost and CO2 of the building as it is (S5).

    `subregion`: eGRID subregion for EMI-01 (`cost.egrid_subregion`). `assumptions`: the model's
    registry; only `tariff.electricity_usd_per_kwh` and `tariff.gas_usd_per_kwh` are read, for the
    price range (expected stays the `Tariff` price). `groups`: extra UNC-02 correlation groups."""
    n = len(loads.heating_need_w)
    cal = calendar or default_calendar(n)
    if cal.n != n:
        raise ValueError(f"calendar has {cal.n} hours, loads have {n}")
    kind = building_kind(systems.occupancy_schedule)
    warnings: list[str] = []
    ids: list[str] = ["LGT-01", "LGT-02", "LGT-03", "TAR-01", "TAR-05", "EMI-01", "UNC-01", "UNC-02"]

    cool_route, cool_rating, cool_key, w, fids = _cooling_setup(systems)
    warnings += w
    ids += fids
    heat_route, heat_rating, heat_key, w, fids = _heating_setup(systems, tariff)
    warnings += w
    ids += fids
    dse, w = _dse(systems)
    ids.append("HVAC-08")
    if w:
        warnings.append(w)
    if systems.hvac_type == "central_plant":
        warnings.append("central plant: no chiller or boiler model; default efficiency with the range widened "
                        "-25 % / +25 % (HVAC-00)")
    if systems.hvac_type == "unknown":
        warnings.append("HVAC system type unknown: default efficiency class used (HVAC-00)")

    # water heating (homes only, DHW-02)
    dhw_fuel = None
    t = np.asarray(loads.outdoor_temp_c, dtype=float)
    if kind == "home":
        dhw_fuel = systems.dhw_fuel
        if dhw_fuel == "unknown":
            dhw_fuel = "gas" if tariff.gas_usd_per_kwh is not None else "electricity"
            warnings.append(f"water heater fuel unknown: {dhw_fuel} assumed")
        t_avg = float(t.mean())
        monthly_t = np.array([t[cal.month == m].mean() for m in range(1, 13) if np.any(cal.month == m)])
        _, first_hour, day_of_hour = np.unique(cal.day_index, return_index=True, return_inverse=True)
        t_mains_day = mains_temperature(cal.day_of_year[first_hour], t_avg, float(monthly_t.max() - monthly_t.min()))
        ids += ["DHW-01", "DHW-02", "DHW-03"]
        if systems.dhw_type == "heat_pump" and systems.dhw_location == "conditioned":
            warnings.append("heat pump water heater in the conditioned space: its cooling of the space is not "
                            "modelled (DHW-03)")
    else:
        warnings.append("office hot water is not modelled (DHW-02): water heating is 0")

    gas_price = tariff.gas_usd_per_kwh
    occ_r = systems.occupants
    lpd_exp, ppd_exp = systems.lighting_w_per_m2.expected, systems.plug_w_per_m2.expected
    egrid_avg = grid_emission_factor(subregion, "average")
    egrid_nb = grid_emission_factor(subregion, "nonbaseload")
    ef_gas = gas_emission_factor()
    variants = dict(load_variants or {})
    t_clamped = np.clip(t, *COOL_CURVE_VALID_C)

    base: dict = {
        "hvac.cooling": cool_rating.expected if cool_rating else None,
        "hvac.heating": heat_rating.expected if heat_rating else None,
        "hvac.distribution_efficiency": dse.expected,
        "hvac.cycling_degradation": CD_DEFAULT[1],
        "hvac.seasonal_climate": 1.0,
        "hvac.central_plant": 1.0,
        "dhw.uef": systems.dhw_efficiency.expected,
        "dhw.volume": 1.0,
        "dhw.energy": 1.0,
        "lighting.lpd": lpd_exp,
        "plug.ppd": ppd_exp,
        "occupancy.count": occ_r.expected if occ_r is not None else None,
        "tariff.electricity_usd_per_kwh": tariff.electricity_usd_per_kwh,
        "tariff.gas_usd_per_kwh": gas_price if gas_price is not None else 0.0,
    }
    for k in variants:
        base[k] = None

    def run(p: dict, detail: bool = False):
        ld = next((p[k] for k in variants if p[k] is not None), loads)
        eu = end_use_profiles(
            occupancy_schedule=systems.occupancy_schedule, floor_area_m2=floor_area_m2, cal=cal,
            lpd_w_m2=p["lighting.lpd"], ppd_w_m2=p["plug.ppd"], occupants=p["occupancy.count"], bedrooms=bedrooms,
            # homes only (offices use the densities directly): relative to the fixed reference,
            # not to this model's own expected value, so a measure that lowers it saves energy
            lpd_scale=p["lighting.lpd"] / HOME_LPD_REFERENCE_W_M2,
            ppd_scale=p["plug.ppd"] / HOME_PPD_REFERENCE_W_M2)
        heat = np.maximum(np.asarray(ld.heating_need_w, dtype=float), 0.0)
        cool = np.maximum(np.asarray(ld.cooling_need_w, dtype=float), 0.0)
        lat_oa = np.zeros(n) if ld.latent_oa_w is None else np.maximum(np.asarray(ld.latent_oa_w, dtype=float), 0.0)
        latent = np.where(cool > 0, lat_oa + eu.latent_gain_w, 0.0)
        d = p["hvac.distribution_efficiency"]
        q_cool = (cool + latent) / d                              # section 5 and HVAC-08, W
        q_heat = heat / d
        plant = p["hvac.central_plant"]
        tout = np.asarray(ld.outdoor_temp_c, dtype=float)

        # cooling electricity, W averaged over the hour
        r = p["hvac.cooling"]
        if cool_route == "none":
            cool_el = np.zeros(n)
        elif cool_route in ("hourly_seer", "hourly_eer"):
            cd = p["hvac.cycling_degradation"]
            eer_a = eer_a_from_seer(r, cd) if cool_route == "hourly_seer" else r
            cap = systems.cooling_capacity_w or SIZING_FACTOR * float(q_cool.max() or 1.0)
            cool_el = cooling_power_single_stage(q_cool, np.clip(tout, *COOL_CURVE_VALID_C),
                                                 eer_a * COP_PER_BTU_PER_WH * plant, cap, cd)
        else:   # "seasonal" (HVAC-04) and "ieer" (HVAC-07): linear in the load
            cool_el = q_cool / (r * COP_PER_BTU_PER_WH * plant) * p["hvac.seasonal_climate"]

        # heating, W averaged over the hour
        h = p["hvac.heating"]
        heat_el = np.zeros(n)
        heat_gas = np.zeros(n)
        if heat_route == "furnace":
            heat_gas = q_heat / (h * plant)
        elif heat_route == "resistance":
            heat_el = q_heat / (h * plant)
        elif heat_route == "heat_pump":
            cop47 = systems.heating_cop_47f or cop47_from_hspf(h)
            heat_el = heat_pump_heating_power(q_heat, tout, cop_47=cop47, hspf=h) / plant

        # water heating, kWh per hour
        dhw_el = np.zeros(n)
        dhw_gas = np.zeros(n)
        if kind == "home":
            vol = daily_hot_water_volume(eu.bedrooms, t_mains_day) * p["dhw.volume"]
            e_day = dhw_energy(vol, t_mains_day, p["dhw.uef"])["input_kwh"] * p["dhw.energy"]
            e_hour = (e_day / 24.0)[day_of_hour]          # a day's energy spread evenly over its hours
            if dhw_fuel == "gas":
                dhw_gas = e_hour
            else:
                dhw_el = e_hour

        elec_h = (cool_el + heat_el) / 1000.0 + eu.lighting_kwh + eu.plug_kwh + eu.appliances_kwh + dhw_el
        gas_h = heat_gas / 1000.0 + dhw_gas
        elec, gas = float(elec_h.sum()), float(gas_h.sum())
        cost = elec * p["tariff.electricity_usd_per_kwh"] + 12 * tariff.fixed_usd_per_month \
            + gas * p["tariff.gas_usd_per_kwh"]
        out = {"electricity_kwh": elec, "gas_kwh": gas, "cost_usd": cost,
               "co2_kg": elec * egrid_avg + gas * ef_gas, "co2_nonbaseload_kg": elec * egrid_nb + gas * ef_gas}
        if not detail:
            return out
        out["detail"] = dict(
            electricity_kwh=elec_h, gas_kwh=gas_h, cooling_kwh=cool_el / 1000.0,
            heating_electricity_kwh=heat_el / 1000.0, heating_gas_kwh=heat_gas / 1000.0,
            water_heating_kwh=dhw_el + dhw_gas, lighting_kwh=eu.lighting_kwh, plug_kwh=eu.plug_kwh,
            appliances_kwh=eu.appliances_kwh, cooling_load_w=q_cool, heating_load_w=q_heat, latent_w=latent,
            sensible_gain_w=eu.sensible_gain_w, latent_gain_w=eu.latent_gain_w, eu=eu)
        return out

    # one-at-a-time ends (UNC-02); inputs whose low equals high are skipped
    ends: dict = {}

    def add(key, pair):
        if pair is not None and pair[0] != pair[1]:
            ends[key] = pair

    if cool_rating is not None:
        add("hvac.cooling", _ends(cool_rating))
        if cool_route.startswith("hourly"):
            add("hvac.cycling_degradation", (CD_DEFAULT[0], CD_DEFAULT[2]))
        else:
            add("hvac.seasonal_climate", (1 - SEASONAL_CLIMATE_BAND, 1 + SEASONAL_CLIMATE_BAND))
    if heat_rating is not None:
        add("hvac.heating", _ends(heat_rating))
    if cool_route != "none" or heat_route != "none":
        add("hvac.distribution_efficiency", _ends(dse))
    if systems.hvac_type == "central_plant":
        add("hvac.central_plant", (1 - CENTRAL_PLANT_BAND, 1 + CENTRAL_PLANT_BAND))
    if kind == "home":
        add("dhw.uef", _ends(systems.dhw_efficiency))
        add("dhw.volume", (1 - DHW_VOLUME_BAND, 1 + DHW_VOLUME_BAND))
        add("dhw.energy", (1 - DHW_ENERGY_BAND, 1 + DHW_ENERGY_BAND))
    add("lighting.lpd", _ends(systems.lighting_w_per_m2))
    add("plug.ppd", _ends(systems.plug_w_per_m2))
    if occ_r is not None:
        add("occupancy.count", _ends(occ_r))
    for a in assumptions:
        if a.key in ("tariff.electricity_usd_per_kwh", "tariff.gas_usd_per_kwh") and isinstance(a.value, Ranged):
            if a.key == "tariff.gas_usd_per_kwh" and gas_price is None:
                continue
            add(a.key, _ends(a.value))
    for k, (lo, hi) in variants.items():
        ends[k] = (lo, hi)
    key_names = {"hvac.cooling": cool_key, "hvac.heating": heat_key}

    grp = {**DEFAULT_GROUPS, **(groups or {})}
    grp = {**grp, **{k: grp[v] for k, v in key_names.items() if v in grp}}
    totals, rows = propagate(run, base, ends, grp)
    rows = [SensitivityRow(key_names.get(r.key, r.key), r.output, r.y_low_run, r.y_high_run, r.swing) for r in rows]
    full = run(base, detail=True)
    det = full.pop("detail")
    eu = det.pop("eu")
    warnings += list(eu.warnings)

    # validity checks on the expected run
    if cool_route.startswith("hourly"):
        outside = int(np.sum((det["cooling_load_w"] > 0) & (t != t_clamped)))
        if outside:
            warnings.append(f"{outside} cooling hours outside 18 to 46 C: the HVAC-02 curve is held at its limit")
    if heat_route == "heat_pump":
        cold = int(np.sum(t < HP_COLD_LIMIT_C))
        if cold > HP_COLD_HOURS_WARN:
            warnings.append(f"{cold} hours below -5 C: heat pump curve outside its range (HVAC-05)")
        if systems.heating_cop_47f is None and cop47_from_hspf(heat_rating.expected) is None:
            warnings.append("HSPF outside 7.7 to 8.5 and no certified COP at 47 F: seasonal HSPF fallback (HVAC-05)")
    if heat_route in ("furnace",) or (kind == "home" and dhw_fuel == "gas"):
        ids += ["TAR-04", "EMI-02"]
    if gas_price is None and full["gas_kwh"] > 0:
        warnings.append("the tariff has no gas price: gas use is not costed")

    def rng(key, unit):
        lo, ex, hi = totals[key]
        return Ranged(low=lo, expected=ex, high=hi, unit=unit)

    heating_kwh = float(det["heating_electricity_kwh"].sum() + det["heating_gas_kwh"].sum())
    end_use = {
        "heating": heating_kwh,
        "cooling": float(det["cooling_kwh"].sum()),
        "water_heating": float(det["water_heating_kwh"].sum()),
        "lighting": float(det["lighting_kwh"].sum()),
        "plug": float(det["plug_kwh"].sum()),
        "appliances": float(det["appliances_kwh"].sum()),
    }
    monthly_e = np.bincount(cal.month - 1, weights=det["electricity_kwh"], minlength=12)
    monthly_g = np.bincount(cal.month - 1, weights=det["gas_kwh"], minlength=12)
    annual = EnergyUse(electricity_kwh=rng("electricity_kwh", "kWh"), gas_kwh=rng("gas_kwh", "kWh"),
                       cost_usd=rng("cost_usd", "USD"), co2_kg=rng("co2_kg", "kg"),
                       co2_nonbaseload_kg=rng("co2_nonbaseload_kg", "kg"))
    result = BaselineResult(
        annual=annual, end_use_kwh=end_use,
        monthly_electricity_kwh=[float(x) for x in monthly_e], monthly_gas_kwh=[float(x) for x in monthly_g],
        peak_cooling_w=float(det["cooling_load_w"].max(initial=0.0)),
        peak_heating_w=float(det["heating_load_w"].max(initial=0.0)),
        heating_need_kwh=float(np.maximum(loads.heating_need_w, 0).sum() / 1000.0),
        cooling_need_kwh=float(np.maximum(loads.cooling_need_w, 0).sum() / 1000.0),
        latent_cooling_kwh=float(det["latent_w"].sum() / 1000.0),
        hourly_path=hourly_path)
    return SystemsBaseline(
        baseline=result, hourly=det, occupants=eu.occupants, occupants_source=eu.occupants_source,
        cooling_route=cool_route,
        heating_route=("heat_pump_hourly" if heat_route == "heat_pump" and (
            systems.heating_cop_47f or cop47_from_hspf(heat_rating.expected)) else
            "heat_pump_seasonal" if heat_route == "heat_pump" else heat_route),
        subregion=subregion, formula_ids=tuple(dict.fromkeys(ids)), warnings=tuple(dict.fromkeys(warnings)),
        sensitivity=rows)


def baseline_result(systems: Systems, tariff: Tariff, loads: HourlyLoads, **kw) -> BaselineResult:
    """`systems_baseline(...).baseline`."""
    return systems_baseline(systems, tariff, loads, **kw).baseline
