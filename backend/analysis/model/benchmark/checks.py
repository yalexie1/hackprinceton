"""The door: contract objects in, ``(warnings, result)`` out.

``check_baseline`` (BEN-01 to BEN-03) and ``check_pv`` (PV-10) never raise on missing inputs;
they return ``status="not_checked"`` with one warning that says what was missing.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Optional

from backend.schema import BaselineResult, ClimateSite, RoofPlane, SolarDesign

from .eui import EuiBenchmark, benchmark_eui
from .pv import PVWATTS_LOSSES_DEFAULT, PVWATTS_LOSSES_NO_SHADING, Plane, PvCrossCheck, cross_check_pv, read_weather_csv

FLAT_TILT_DEG = 9.5             # physics 01 ROOF-03 / LAY-03: below this a plane is flat
RACK_TILT_DEG = 15.0            # physics 01 LAY-02: modules on a flat plane sit on a rack at this tilt


def check_baseline(baseline: BaselineResult, floor_area_m2: Optional[float], building_type: Optional[str],
                   climate_zone: Optional[str], *, building_area_m2: Optional[float] = None
                   ) -> tuple[list[str], EuiBenchmark]:
    """EUI of the baseline against RECS 2020 (homes) or CBECS 2018 (offices).

    ``floor_area_m2``: conditioned floor area the baseline covers (sum of conditioned zones).
    ``building_type``: ``PropertySummary.use_type`` ("single_family", "multifamily_unit", "office").
    ``building_area_m2``: gross area of the whole building (``CostarData.building_area_m2``), offices only.
    """
    e, g = baseline.annual.electricity_kwh, baseline.annual.gas_kwh
    result = benchmark_eui(e.expected, g.expected, floor_area_m2, building_type, climate_zone,
                           building_area_m2=building_area_m2,
                           electricity_range_kwh=(e.low, e.high), gas_range_kwh=(g.low, g.high))
    return list(result.warnings), result


def pv_inputs(solar: SolarDesign, roof_planes: Iterable[RoofPlane], params: Optional[dict] = None) -> dict:
    """Plane orientations, losses without shading and the energy-weighted shading of a design.

    Shading enters a design one of two ways (physics 01 PV-04): inside ``losses_percent`` (the
    3 percent default, total 14.08) or, for ray-cast panels, as ``PanelPlacement.shading_loss_fraction``
    with ``losses_percent`` 11.42. Whatever lies above the no-shading total is read as shading. A
    design that does not record ``losses_percent`` is read as the A4 chain's default, 14.08 with
    the 3 percent shading in it, which is what the chain applies when it is given no losses.
    """
    params = params or {}
    by_id = {p.id: p for p in roof_planes}
    kw = defaultdict(float)
    for panel in solar.panels:
        kw[panel.plane_id] += 1.0
    module_kw = solar.system_kw_dc / max(solar.panel_count or sum(kw.values()), 1)
    planes = []
    for pid, count in kw.items():
        plane = by_id.get(pid)
        if plane is None:
            continue
        tilt, az = plane.tilt_deg.expected, plane.azimuth_deg
        if tilt < FLAT_TILT_DEG:                       # racked, facing the plane's azimuth (LAY-02)
            tilt = float(params.get("rack_tilt_deg", RACK_TILT_DEG))
            az = float(params.get("rack_azimuth_deg", az))
        planes.append(Plane(tilt, az, count * module_kw))

    losses = PVWATTS_LOSSES_DEFAULT if solar.losses_percent is None else solar.losses_percent
    if losses > PVWATTS_LOSSES_NO_SHADING + 0.05:
        shading = 1.0 - (1.0 - losses / 100.0) / (1.0 - PVWATTS_LOSSES_NO_SHADING / 100.0)
        losses = PVWATTS_LOSSES_NO_SHADING
    else:
        shaded = sum(p.annual_kwh for p in solar.panels)
        unshaded = sum(p.annual_kwh / (1.0 - p.shading_loss_fraction) for p in solar.panels
                       if p.shading_loss_fraction < 1.0)
        shading = 1.0 - shaded / unshaded if unshaded > 0 else 0.0
    return {"planes": planes, "losses_percent": losses, "shading_fraction": max(shading, 0.0)}


def check_pv(solar: Optional[SolarDesign], roof_planes: Iterable[RoofPlane], climate: ClimateSite, *,
             params: Optional[dict] = None, weather_csv: Optional[str] = None
             ) -> tuple[list[str], PvCrossCheck]:
    """PV-10 for a PV_ROOF design. ``params`` is ``MeasureResult.params``; ``weather_csv`` is the
    site's weather file (``ClimateSite.weather_path`` resolved to disk), optional."""
    if solar is None:
        r = cross_check_pv(None, None, [], climate.pvgis_annual_kwh_per_kw, climate.pvgis_sd_fraction,
                           climate.lat, climate.lon)
        return list(r.warnings), r
    inputs = pv_inputs(solar, roof_planes, params)
    weather = None
    if weather_csv:
        try:
            weather = read_weather_csv(weather_csv, climate.timezone, climate.weather_time_convention)
        except (OSError, ValueError, KeyError):
            weather = None
    r = cross_check_pv(solar.annual_kwh.expected, solar.system_kw_dc, inputs["planes"],
                       climate.pvgis_annual_kwh_per_kw, climate.pvgis_sd_fraction, climate.lat, climate.lon,
                       losses_percent=inputs["losses_percent"], shading_fraction=inputs["shading_fraction"],
                       weather=weather, timezone=climate.timezone)
    return list(r.warnings), r
