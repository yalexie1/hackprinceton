"""PV-07 degradation, PV-08 array rating, PV-09 range of the annual energy."""
from __future__ import annotations

from typing import Iterable, Optional

from backend.schema import Ranged

from . import constants as C


# ---------------------------------------------------------------- PV-07

def degraded_energy(year1_kwh: float, year: int, rate: float = C.DEGRADATION_RATE_EXPECTED) -> float:
    """PV-07. E(y) = E1 * (1 - d)^(y - 1), y = 1, 2, ..."""
    if year < 1:
        raise ValueError("year starts at 1")
    return year1_kwh * (1.0 - rate) ** (year - 1)


def lifetime_energy(year1_kwh: float, years: int, rate: float = C.DEGRADATION_RATE_EXPECTED) -> float:
    """PV-07. Sum of years 1..N, closed form E1 * (1 - (1 - d)^N) / d."""
    if years < 0:
        raise ValueError("years must be >= 0")
    if rate == 0.0:
        return year1_kwh * years
    return year1_kwh * (1.0 - (1.0 - rate) ** years) / rate


# ---------------------------------------------------------------- PV-08

def array_rating(panel_count: int, module_w: float) -> float:
    """PV-08. Pdc0 in kW DC = N * Pmod / 1000.

    The module rating has no sourced default (physics 01 section 8); the caller
    passes the quoted product's rating or carries ``MODULE_W_UNVERIFIED`` as an
    assumption with a range.
    """
    if panel_count < 0 or module_w <= 0:
        raise ValueError("panel_count >= 0 and module_w > 0 required")
    return panel_count * module_w / 1000.0


# ---------------------------------------------------------------- PV-09

#: PV-09 step 4: chain settings of the expected run and the two "other bounds".
PV09_SCENARIOS: dict[str, dict] = {
    "expected": {"temperature_row": C.TEMPERATURE_ROW_EXPECTED, "gamma_per_c": C.GAMMA_PDC_EXPECTED},
    "low": {"temperature_row": C.TEMPERATURE_ROW_HOT, "gamma_per_c": C.GAMMA_PDC_LOW_YIELD},
    "high": {"temperature_row": C.TEMPERATURE_ROW_COOL, "gamma_per_c": C.GAMMA_PDC_EXPECTED},
}


def weather_sigma(pvgis_sd_kwh: float, pvgis_annual_kwh: float) -> float:
    """PV-09 step 6: sigma_w = SD_y / E_y."""
    if pvgis_annual_kwh <= 0:
        raise ValueError("annual energy must be positive")
    return pvgis_sd_kwh / pvgis_annual_kwh


def energy_range(expected_kwh: float, other_runs_kwh: Iterable[float],
                 sigma_w: Optional[float] = None, unit: str = "kWh") -> tuple[Ranged, dict]:
    """PV-09 steps 5 and 6. Combine PV-06 runs into a ``Ranged``.

    ``expected_kwh`` is step 1. ``other_runs_kwh`` are the results of steps 2
    to 4 (every tilt, ridge alternative and bound run; the expected run may be
    repeated among them). ``sigma_w`` (step 6, e.g. ``ClimateSite.pvgis_sd_fraction``)
    widens the ends by the 10 % and 90 % normal points, stacked end to end. Without
    it the weather step is skipped and ``params`` says so.

    Returns the ``Ranged`` and the params to write to ``MeasureResult.params``:
    ``L_in``, ``H_in`` and ``sigma_w``.
    """
    runs = [float(expected_kwh), *map(float, other_runs_kwh)]
    l_in, h_in = min(runs), max(runs)
    widen = 0.0 if sigma_w is None else C.Z_10_90 * float(sigma_w)
    if widen < 0:
        raise ValueError("sigma_w must be >= 0")
    low = l_in * (1.0 - widen)
    high = h_in * (1.0 + widen)
    params = {"L_in": l_in, "H_in": h_in, "sigma_w": sigma_w,
              "weather_step_applied": sigma_w is not None}
    return Ranged(low=low, expected=float(expected_kwh), high=high, unit=unit), params
