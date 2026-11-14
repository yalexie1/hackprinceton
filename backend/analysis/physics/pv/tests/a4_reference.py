"""Test helpers for A4: pvlib as the reference implementation (physics 01, 0.2 and PV-06).

pvlib builds the inputs the climate package will hand to A4 (sun position and
plane-of-array components, computed here only to drive the tests), and runs
``ModelChain`` with the settings PV-06 lists as the reference. Tests only; the
package itself does not import pvlib.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pvlib
from pvlib.location import Location
from pvlib.modelchain import ModelChain
from pvlib.pvsystem import PVSystem

from backend.analysis.physics.pv import PVHourly, pv_hourly_yield
from backend.analysis.physics.pv import constants as C

# Our temperature row names against pvlib's SAPM table keys.
PVLIB_SAPM_ROW = {
    "glass_glass_open_rack": "open_rack_glass_glass",
    "glass_glass_close_roof_mount": "close_mount_glass_glass",
    "glass_polymer_open_rack": "open_rack_glass_polymer",
    "glass_polymer_insulated_back": "insulated_back_glass_polymer",
}


def synthetic_clear_sky_year(lat, lon, altitude=90.0, tz="Etc/GMT+8", year=2026,
                             air_temp_c=20.0, wind_m_s=2.0):
    """The PV-06 worked-example weather: Haurwitz clear-sky GHI split by Erbs.

    Stamps are the hour midpoints (SOL-07) in local standard time; the solar
    position uses the air temperature for refraction, as ModelChain does, and
    Haurwitz and Erbs take the apparent zenith. With these details the PV-06
    printed totals reproduce exactly.
    """
    loc = Location(lat, lon, tz=tz, altitude=altitude)
    times = pd.date_range(f"{year}-01-01 00:30", periods=8760, freq="h", tz=tz)
    sp = loc.get_solarposition(times, temperature=air_temp_c)
    ghi = pvlib.clearsky.haurwitz(sp["apparent_zenith"])["ghi"]
    erbs = pvlib.irradiance.erbs(ghi, sp["apparent_zenith"], times)
    weather = pd.DataFrame({"ghi": ghi, "dni": erbs["dni"], "dhi": erbs["dhi"],
                            "temp_air": air_temp_c, "wind_speed": wind_m_s}, index=times)
    return loc, weather


def plane_inputs(loc, weather, tilt, azimuth, albedo=0.2):
    """IRR-04 and IRR-05/08/09 arrays by pvlib: what A4 receives from the climate package."""
    times = weather.index
    temp = weather["temp_air"] if "temp_air" in weather else 12.0
    sp = loc.get_solarposition(times, temperature=temp)
    dni_extra = pvlib.irradiance.get_extra_radiation(times)
    am = pvlib.atmosphere.get_relative_airmass(sp["apparent_zenith"], model="kasten1966")
    poa = pvlib.irradiance.get_total_irradiance(
        tilt, azimuth, sp["apparent_zenith"], sp["azimuth"],
        weather["dni"], weather["ghi"], weather["dhi"], dni_extra=dni_extra,
        airmass=am, albedo=albedo, model="perez")
    aoi = pvlib.irradiance.aoi(tilt, azimuth, sp["apparent_zenith"], sp["azimuth"])
    return {k: np.nan_to_num(np.asarray(v, dtype=float)) for k, v in {
        "poa_beam": poa["poa_direct"], "poa_sky_diffuse": poa["poa_sky_diffuse"],
        "poa_ground": poa["poa_ground_diffuse"], "incidence_deg": aoi}.items()}


def ours(loc, weather, tilt, azimuth, *, shading_percent=None,
         temperature_row=C.TEMPERATURE_ROW_EXPECTED, gamma_per_c=C.GAMMA_PDC_EXPECTED) -> PVHourly:
    p = plane_inputs(loc, weather, tilt, azimuth)
    losses = None
    if shading_percent is not None:
        losses = {**C.DEFAULT_LOSSES_PERCENT, "shading": shading_percent}
    return pv_hourly_yield(p["poa_beam"], p["poa_sky_diffuse"], p["poa_ground"],
                           p["incidence_deg"], weather["temp_air"].to_numpy(),
                           weather["wind_speed"].to_numpy(), temperature_row=temperature_row,
                           gamma_per_c=gamma_per_c, losses_percent=losses)


def modelchain(loc, weather, tilt, azimuth, pdc0_w, *, shading_percent=3.0,
               temperature_row=C.TEMPERATURE_ROW_EXPECTED, gamma_per_c=C.GAMMA_PDC_EXPECTED,
               dc_ac_ratio=C.DC_AC_RATIO, eta_nom=C.INVERTER_ETA_NOM):
    """ModelChain configured exactly as PV-06 states."""
    system = PVSystem(
        surface_tilt=tilt, surface_azimuth=azimuth, albedo=0.2,
        module_parameters={"pdc0": pdc0_w, "gamma_pdc": gamma_per_c},
        inverter_parameters={"pdc0": pdc0_w / dc_ac_ratio / eta_nom, "eta_inv_nom": eta_nom},
        temperature_model_parameters=pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"][
            PVLIB_SAPM_ROW[temperature_row]],
        losses_parameters={"shading": shading_percent})
    mc = ModelChain(system, loc, transposition_model="perez", airmass_model="kasten1966",
                    aoi_model="physical", spectral_model="no_loss", temperature_model="sapm",
                    dc_model="pvwatts", ac_model="pvwatts", losses_model="pvwatts")
    mc.run_model(weather)
    return mc
