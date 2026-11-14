"""Climate inputs (work package A1): weather reader, solar position, irradiance.

Formulas: specs/physics/01-solar-pv.md, entries SOL-01 to SOL-07 and IRR-01 to IRR-10.
"""
from .hourly import ClimateHours, hourly_climate, load_climate, plane_irradiance
from .irradiance import (
    decompose_ghi_erbs,
    extraterrestrial_normal_irradiance,
    incidence_angle,
    plane_of_array_irradiance,
    poa_beam,
    poa_ground_reflected,
    relative_air_mass,
    sky_diffuse_haydavies,
    sky_diffuse_isotropic,
    sky_diffuse_perez,
)
from .solar_position import (
    declination_spencer,
    equation_of_time_spencer,
    hour_angle,
    interval_midpoints,
    solar_position,
    solar_position_simple,
    sun_vector,
)
from .weather import Weather, read_site_weather, read_weather

__all__ = [
    "ClimateHours", "hourly_climate", "load_climate", "plane_irradiance",
    "decompose_ghi_erbs", "extraterrestrial_normal_irradiance", "incidence_angle",
    "plane_of_array_irradiance", "poa_beam", "poa_ground_reflected", "relative_air_mass",
    "sky_diffuse_haydavies", "sky_diffuse_isotropic", "sky_diffuse_perez",
    "declination_spencer", "equation_of_time_spencer", "hour_angle", "interval_midpoints",
    "solar_position", "solar_position_simple", "sun_vector",
    "Weather", "read_site_weather", "read_weather",
]
