"""Measure costs, useful life and O&M (A24; physics 04 COST-00, COST-01, COST-02).

Every number comes from `data/costs.json` and `data/useful_life.json`, each row carrying the
source it was read from. Nothing is invented: a measure with no verified cost raises
`NoCostData`, and the budget algorithm skips it with reason `no_cost_data` (SPEC 6.5).
Pure and deterministic.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from backend.schema import MeasureResult, Ranged

_DATA = Path(__file__).resolve().parent / "data"

# COST-00: CPI-U Oct 2026 / CPI-U of the source year
CPI_FACTORS = {2006: 1.6742, 2013: 1.4488, 2019: 1.3202, 2022: 1.1533}
CPI_OCT_2026 = 337.511
_CPI_BY_YEAR = {2006: 201.592, 2013: 232.957, 2019: 255.657, 2022: 292.655}

PV_OM_USD_PER_KW_YEAR = 35.01     # COST-01: NREL-2023 Table 3, 30.36 USD/kWdc/yr (2022) CPI-adjusted
PV_LARGE_W = 100_000              # COST-01: office PV from 100 kW DC up is priced as large


class NoCostData(Exception):
    """The measure cannot be priced. `code` is `no_cost_data` or `no_quantity`."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def adjust_cost(value: float, from_year: int) -> float:
    """COST-00: bring a source cost to October 2026 dollars."""
    return value * CPI_OCT_2026 / _CPI_BY_YEAR[from_year]


def _rows(name: str) -> list[dict]:
    return json.loads((_DATA / name).read_text())


def cost_table() -> list[dict]:
    return _rows("costs.json")


def _sector_key(measure_id: str, sector: str, quantity: float) -> list[str]:
    if measure_id == "PV_ROOF":
        if sector == "residential":
            return ["residential"]
        return ["commercial_large" if quantity >= PV_LARGE_W else "commercial_small"]
    return [sector, "any"]


def _row(measure_id: str, sector: str, quantity: float = 0.0) -> dict:
    keys = _sector_key(measure_id, sector, quantity)
    for key in keys:
        for row in cost_table():
            if row["measure_id"] == measure_id and row["sector"] == key:
                return row
    raise KeyError(f"no cost entry for {measure_id} ({sector})")


def measure_cost(measure_id: str, quantity: float, sector: str) -> tuple[Ranged, str]:
    """COST-01. Installed cost as low, expected, high, and the `cost_source` string.
    `quantity` is in the row's unit (PV_ROOF: watts DC)."""
    row = _row(measure_id, sector, quantity)
    if row["status"] == "no_source":
        raise NoCostData("no_cost_data", f"{measure_id}: no verified cost source; get a quote")
    low, expected, high = (row[k] * quantity for k in ("low", "expected", "high"))
    unit = row["unit"]
    source = f"{row['source']}; physics 04 COST-01: {row['expected']:g} USD per {unit} x {quantity:g}"
    return Ranged(low=round(low, 2), expected=round(expected, 2), high=round(high, 2), unit="USD"), source


def useful_life(measure_id: str, sector: str) -> tuple[int, str]:
    """COST-02. Years and the status of the figure (verified, judgement or unverified)."""
    for key in (sector, "any"):
        for row in _rows("useful_life.json"):
            if row["measure_id"] == measure_id and row["sector"] == key:
                return row["years"], row["status"]
    raise KeyError(f"no useful life for {measure_id}")


def annual_om_change(measure_id: str, quantity: float) -> float:
    """COST-01 operation and maintenance: PV adds 35.01 USD per kW DC per year, every other
    measure replaces like with like and adds zero. `quantity` is watts DC for PV_ROOF."""
    return round(PV_OM_USD_PER_KW_YEAR * quantity / 1000.0, 2) if measure_id == "PV_ROOF" else 0.0


# ---- quantity: which number of the measure the cost table multiplies ----

_PARAM_KEYS = {
    "ENV_ATTIC": ("area_m2",), "ENV_WALL": ("area_m2",), "ENV_AIRSEAL": ("floor_area_m2", "area_m2"),
    "WIN_REPLACE": ("glazing_area_m2", "area_m2"), "ROOF_COOL": ("roof_area_m2", "area_m2"),
    "HVAC_HP": ("capacity_tons",), "HVAC_RTU": ("capacity_tons",), "HVAC_ECON": ("units",),
    "LGT_LED": ("lamps", "fixtures"), "LGT_CTRL": ("fixtures",), "CTRL_TSTAT": ("thermostats",),
}
_ONE = {"HVAC_DUCT", "DHW_HPWH", "LAYOUT"}     # priced per home, per unit or as a whole


def quantity_of(measure: MeasureResult) -> Optional[float]:
    """The quantity a measure carries in its own result, or None when the caller must supply
    it (for example the conditioned floor area of ENV_AIRSEAL, which lives in the model)."""
    if measure.measure_id == "PV_ROOF":
        return measure.solar.system_kw_dc * 1000.0 if measure.solar else None
    for key in _PARAM_KEYS.get(measure.measure_id, ()):
        if measure.params.get(key) is not None:
            return float(measure.params[key])
    if measure.measure_id == "LAYOUT":
        return 1.0
    if measure.measure_id in _ONE:
        return float(measure.params.get("units", 1))
    return None
