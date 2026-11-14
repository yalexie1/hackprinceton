"""Daylight, glare and thermal comfort at a point (work package A5).

Formulas: specs/physics/03-daylight-comfort.md, entries DAY-01 to DAY-10, GLR-01 to GLR-05,
CMF-01 to CMF-08 and LCT-01 to LCT-03. The entry point for desk layout (A23) is
`score_point(room, surfaces, x, y, sun, zone_temps, *, floor, ...)`; build a room once with
`prepare_room(...)` and pass it as `context=` when scoring many points.
"""
from .comfort import (config_factor_b3, glass_inside_surface_temperature, mean_radiant_temperature,
                      omega_corner, operative_temperature, pd_cool_wall, plane_factor_to_window,
                      pmv_ppd, ppd_from_pmv, projected_area_factor, radiant_asymmetry_window,
                      sky_vault_fraction, solar_gain_delta_mrt, window_angle_factor,
                      window_solid_angle)
from .daylight import (IRCWindow, average_daylight_factor, cie_overcast_luminance,
                       config_factor_b4, config_factor_horizontal_to_window, daylight_autonomy,
                       extraterrestrial_normal, externally_reflected_component,
                       indoor_illuminance_hourly, internally_reflected_component,
                       obstruction_luminance_factor, perez_luminous_efficacy, sky_component,
                       sky_window_factor, sky_window_factor_obstructed, target_daylight_factor)
from .geometry import (WindowRect, azimuth_in_model, azimuth_true, opening_centre, room_geometry,
                       room_windows, wrap180)
from .glare import (cos_sun_view, dgp_simplified, dgp_simplified_inverse, glare_hours,
                    glare_rating, glare_risk, sun_visible_through_window,
                    vertical_eye_illuminance, vertical_window_factors)
from .lighting import desk_score, lighting_energy_saved, lighting_power_fraction
from .point import (DESK_SCORE_KEYS, FORMULA_IDS, RoomContext, SunArrays, desk_score_fields,
                    occupied_mask_from_stamps, prepare_room, resolve_assumptions, score_point,
                    sun_arrays)

__all__ = [
    "config_factor_b3", "glass_inside_surface_temperature", "mean_radiant_temperature",
    "omega_corner", "operative_temperature", "pd_cool_wall", "plane_factor_to_window", "pmv_ppd",
    "ppd_from_pmv", "projected_area_factor", "radiant_asymmetry_window", "sky_vault_fraction",
    "solar_gain_delta_mrt", "window_angle_factor", "window_solid_angle",
    "IRCWindow", "average_daylight_factor", "cie_overcast_luminance", "config_factor_b4",
    "config_factor_horizontal_to_window", "daylight_autonomy", "extraterrestrial_normal",
    "externally_reflected_component", "indoor_illuminance_hourly",
    "internally_reflected_component", "obstruction_luminance_factor", "perez_luminous_efficacy",
    "sky_component", "sky_window_factor", "sky_window_factor_obstructed", "target_daylight_factor",
    "WindowRect", "azimuth_in_model", "azimuth_true", "opening_centre", "room_geometry",
    "room_windows", "wrap180",
    "cos_sun_view", "dgp_simplified", "dgp_simplified_inverse", "glare_hours", "glare_rating",
    "glare_risk", "sun_visible_through_window", "vertical_eye_illuminance",
    "vertical_window_factors",
    "desk_score", "lighting_energy_saved", "lighting_power_fraction",
    "DESK_SCORE_KEYS", "FORMULA_IDS", "RoomContext", "SunArrays", "desk_score_fields",
    "occupied_mask_from_stamps", "prepare_room", "resolve_assumptions", "score_point",
    "sun_arrays",
]
