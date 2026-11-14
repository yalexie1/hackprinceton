"""Building systems and the S5 baseline totals (work package A3).

HVAC, water heating, lighting, plug loads and appliances with their heat gains, energy cost from
the tariff, emissions, and low / expected / high. Formulas: specs/physics/02-thermal-systems.md
HVAC-00 to HVAC-08, DHW-01 to DHW-03, LGT-01 to LGT-03, DEF-05 to DEF-10; and
specs/physics/04-economics-emissions-mv.md TAR-01, TAR-04, TAR-05, EMI-01 to EMI-03, UNC-01, UNC-02.

Hourly zone loads come in as arrays (`HourlyLoads`); the zone model is not imported here.
"""
from .baseline import (END_USES, HourlyLoads, SystemsBaseline, baseline_result, internal_gains_hourly,
                       systems_baseline)
from .cost import (annual_bill_flat, annual_co2_kg, bill_savings, egrid_subregion, gas_emission_factor,
                   grid_emission_factor, kwh_to_mj, kwh_to_therms, mmbtu_to_kwh, therms_to_kwh,
                   usd_per_therm_to_usd_per_kwh)
from .dhw import daily_hot_water_gallons, daily_hot_water_volume, dhw_energy, mains_temperature
from .hvac import (apply_distribution_efficiency, cooling_eir_modifier, cooling_power_single_stage,
                   cop47_from_hspf, eer_a_from_seer, fuel_heating_energy, heat_pump_heating_power,
                   heating_eir_modifier, ieer_from_points, rating_to_cop, seasonal_cooling_energy)
from .loads import (Calendar, calendar_from_hour_start, calendar_from_stamps, default_calendar,
                    end_use_profiles, home_appliance_energy, home_lighting_base, home_lighting_energy,
                    home_lighting_factor, home_misc_energy, home_occupants_default, internal_gains,
                    lighting_power, office_occupants_default, plug_density_scale, plug_power)
from .uncertainty import SensitivityRow, propagate, quadrature

__all__ = [
    "END_USES", "HourlyLoads", "SystemsBaseline", "baseline_result", "internal_gains_hourly", "systems_baseline",
    "annual_bill_flat", "annual_co2_kg", "bill_savings", "egrid_subregion", "gas_emission_factor",
    "grid_emission_factor", "kwh_to_mj", "kwh_to_therms", "mmbtu_to_kwh", "therms_to_kwh",
    "usd_per_therm_to_usd_per_kwh",
    "daily_hot_water_gallons", "daily_hot_water_volume", "dhw_energy", "mains_temperature",
    "apply_distribution_efficiency", "cooling_eir_modifier", "cooling_power_single_stage", "cop47_from_hspf",
    "eer_a_from_seer", "fuel_heating_energy", "heat_pump_heating_power", "heating_eir_modifier",
    "ieer_from_points", "rating_to_cop", "seasonal_cooling_energy",
    "Calendar", "calendar_from_hour_start", "calendar_from_stamps", "default_calendar", "end_use_profiles",
    "home_appliance_energy", "home_lighting_base", "home_lighting_energy", "home_lighting_factor",
    "home_misc_energy", "home_occupants_default", "internal_gains", "lighting_power", "office_occupants_default",
    "plug_density_scale", "plug_power",
    "SensitivityRow", "propagate", "quadrature",
]
