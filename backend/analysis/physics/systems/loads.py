"""Lighting, plug loads, appliances and occupants with their heat gains: physics 02 LGT-01 to
LGT-03, schedules DEF-09, occupant defaults LGT-03.

The hourly internal gains (`internal_gains_hourly`) are what the zone model (A2) needs; the
door passes them there. This file does not import the zone model.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .constants import (DEFAULT_CALENDAR_START, HOME_APPLIANCE_FRACTIONS, HOME_APPLIANCES,
                        HOME_BEDROOMS_DEFAULT, HOME_LIGHT_A, HOME_LIGHT_B, HOME_LIGHT_MONTHLY,
                        HOME_MEL, HOME_OCC_SF, HOME_PERSON_HOURS_PER_DAY, HOME_SHARES, M2_PER_FT2,
                        OCC_LATENT_W, OCC_SENSIBLE_W, OFFICE_M2_PER_PERSON, OFFICE_SCHEDULES,
                        PLUG_LATENT, PLUG_SCALE_LIMITS, PLUG_SENSIBLE)

DAY_TYPES = ("weekday", "saturday", "other")


# ---------- calendar ----------

@dataclass(frozen=True)
class Calendar:
    """One entry per simulated hour, labelled by the hour's start in local standard time."""
    month: np.ndarray          # 1..12
    day_of_year: np.ndarray    # 1..365 (366)
    day_index: np.ndarray      # 0-based day counter from the first hour
    day_type: np.ndarray       # 0 weekday, 1 Saturday, 2 other (Sunday)
    hour: np.ndarray           # 0..23; schedule hour 1 is hour 0 here

    @property
    def n(self) -> int:
        return len(self.hour)


def calendar_from_hour_start(hour_start) -> Calendar:
    """Calendar from the start time of each hour (anything NumPy reads as datetime64; a
    timezone-aware pandas index is read in its own local time)."""
    if getattr(hour_start, "tz", None) is not None:
        hour_start = hour_start.tz_localize(None)
    t = np.asarray(hour_start, dtype="datetime64[h]")
    days = t.astype("datetime64[D]")
    month = (t.astype("datetime64[M]").astype(int) % 12) + 1
    doy = (days - days.astype("datetime64[Y]")).astype(int) + 1
    hour = (t - days).astype(int)
    weekday = (days.astype(int) + 3) % 7          # 1970-01-01 was a Thursday; Monday = 0
    day_type = np.where(weekday < 5, 0, np.where(weekday == 5, 1, 2))
    day_index = (days - days[0]).astype(int)
    return Calendar(month=month, day_of_year=doy, day_index=day_index, day_type=day_type, hour=hour)


def calendar_from_stamps(stamps, convention: str = "hour_end") -> Calendar:
    """Calendar from weather stamps. With `hour_end` (the weather convention, physics.md 3) the
    value stamped 01:00 is the hour 00:00 to 01:00, so one hour is subtracted."""
    if getattr(stamps, "tz", None) is not None:
        stamps = stamps.tz_localize(None)
    t = np.asarray(stamps, dtype="datetime64[h]")
    if convention == "hour_end":
        t = t - np.timedelta64(1, "h")
    elif convention == "hour_centre":
        t = np.asarray(np.asarray(stamps, dtype="datetime64[m]") - np.timedelta64(30, "m"), dtype="datetime64[h]")
    return calendar_from_hour_start(t)


def default_calendar(n_hours: int = 8760) -> Calendar:
    """A non-leap year starting on a Sunday (2017): 260 weekdays, 52 Saturdays, 53 other days."""
    start = np.datetime64(DEFAULT_CALENDAR_START, "h")
    return calendar_from_hour_start(start + np.arange(n_hours).astype("timedelta64[h]"))


# ---------- schedules (DEF-09) ----------

def building_kind(occupancy_schedule: str) -> str:
    """'home' or 'office' from `Systems.occupancy_schedule`."""
    return "home" if occupancy_schedule == "home" else "office"


def office_fraction(kind: str, cal: Calendar, vacant: bool = False) -> np.ndarray:
    """DEF-09 office schedule fraction per hour; `vacant` uses the 'other' row every day."""
    table = np.array([OFFICE_SCHEDULES[kind][d] for d in DAY_TYPES], dtype=float)
    day_type = np.full(cal.n, 2) if vacant else cal.day_type
    return table[day_type, cal.hour]


def home_share(kind: str, cal: Calendar) -> np.ndarray:
    """DEF-09 home hourly share of the day's total (each row sums to 1)."""
    return np.asarray(HOME_SHARES[kind], dtype=float)[cal.hour]


def equivalent_full_load_hours(kind: str, cal: Calendar, vacant: bool = False) -> float:
    """Sum of the office schedule over the calendar (LGT-01: 2939 h for lighting in 2017)."""
    return float(office_fraction(kind, cal, vacant).sum())


# ---------- LGT-01 lighting ----------

def lighting_power(lpd_w_m2: float, area_m2: float, fraction):
    """LGT-01: P_light(h) = LPD A_f f_light(h), W."""
    return lpd_w_m2 * area_m2 * np.asarray(fraction, dtype=float)


def home_lighting_base(floor_area_m2: float) -> float:
    """LGT-01: E_light,base = 0.542 A_ft2 + 334 kWh/yr (benchmark lamp mix; the home baseline)."""
    return HOME_LIGHT_A * floor_area_m2 / M2_PER_FT2 + HOME_LIGHT_B


def home_lighting_factor(f_inc: float, f_cfl: float, f_led: float, f_lf: float,
                         er_led: float = 0.30) -> float:
    """LGT-01 lamp-mix factor on E_light,base, with the smart replacement factor SAF."""
    saf = 1.1 * f_inc ** 4 - 1.9 * f_inc ** 3 + 1.5 * f_inc ** 2 - 0.7 * f_inc + 1.0
    mix = (f_inc + 0.34) + (f_cfl - 0.21) * 0.27 + f_led * er_led + (f_lf - 0.13) * 0.17
    return mix * saf * 0.9 + 0.1


def home_lighting_energy(floor_area_m2: float, f_inc: float, f_cfl: float, f_led: float, f_lf: float,
                         er_led: float = 0.30) -> float:
    """LGT-01: E_light = E_light,base x factor, kWh/yr."""
    return home_lighting_base(floor_area_m2) * home_lighting_factor(f_inc, f_cfl, f_led, f_lf, er_led)


def home_lighting_hourly_kwh(annual_kwh: float, cal: Calendar) -> np.ndarray:
    """LGT-01: P(h) = E share_day(h) m_month / 365. The monthly multipliers are normalised over the
    calendar's days so that the hours add to `annual_kwh` exactly (their 365-day mean is 0.9995)."""
    w = home_share("lighting", cal) * np.asarray(HOME_LIGHT_MONTHLY)[cal.month - 1]
    return annual_kwh * w / w.sum()


def _home_daily_spread(annual_kwh: float, kind: str, cal: Calendar) -> np.ndarray:
    w = home_share(kind, cal)
    return annual_kwh * w / w.sum()


# ---------- LGT-02 plug and appliances ----------

def plug_power(ppd_w_m2: float, area_m2: float, fraction):
    """LGT-02: P_plug(h) = PPD A_f f_equip(h), W."""
    return ppd_w_m2 * area_m2 * np.asarray(fraction, dtype=float)


def home_misc_energy(bedrooms: float, floor_area_m2: float) -> float:
    """LGT-02: E_mel = 1185.4 + 180.2 N_br + 0.3188 A_ft2, kWh/yr."""
    a, b, c = HOME_MEL
    return a + b * bedrooms + c * floor_area_m2 / M2_PER_FT2


def home_appliance_energy(bedrooms: float) -> dict[str, float]:
    """LGT-02: major appliances, kWh/yr each (electric range and dryer, as in the source table)."""
    return {k: a + b * bedrooms for k, (a, b) in HOME_APPLIANCES.items()}


def plug_density_scale(occupants: float, floor_area_m2: float) -> float:
    """LGT-02: (N_occ / A_f) / (1 / 18.59), limited to 0.5 to 2.0 (design choice, tier B)."""
    lo, hi = PLUG_SCALE_LIMITS
    return float(np.clip((occupants / floor_area_m2) * OFFICE_M2_PER_PERSON, lo, hi))


# ---------- LGT-03 occupants and gains ----------

def home_occupants_default(bedrooms: float) -> float:
    """LGT-03 eq. (23), single-family: N_occ = 0.59 N_br + 0.87."""
    a, b = HOME_OCC_SF
    return a * bedrooms + b


def office_occupants_default(floor_area_m2: float) -> float:
    """LGT-03, S11 Table 4: N_occ = A_f / 18.59."""
    return floor_area_m2 / OFFICE_M2_PER_PERSON


def bedrooms_for_home(bedrooms: int | None, occupants: float | None) -> tuple[float, str | None]:
    """Bedroom count for DHW-02 and LGT-02: the model's count; else inverted from the occupant
    count through LGT-03 eq. (23); else this file's fallback of 3, with a warning."""
    if bedrooms is not None:
        return float(bedrooms), None
    if occupants is not None:
        a, b = HOME_OCC_SF
        n = max((occupants - b) / a, 0.0)
        return n, f"bedrooms unknown: {n:.2f} inferred from {occupants:g} occupants (LGT-03 eq. 23)"
    return float(HOME_BEDROOMS_DEFAULT), (f"bedrooms and occupants unknown: {HOME_BEDROOMS_DEFAULT} "
                                          "bedrooms assumed for hot water and plug loads")


def occupant_presence(kind: str, cal: Calendar, vacant: bool = False) -> np.ndarray:
    """LGT-03 occ(h): office schedule fraction; home hourly share x 16.5 person-hours per day."""
    if kind == "home":
        return home_share("occupancy", cal) * HOME_PERSON_HOURS_PER_DAY
    return office_fraction("occupancy", cal, vacant)


def internal_gains(lighting_w, plug_w, occupants: float, occ, building_type: str,
                   appliance_w: dict | None = None) -> dict:
    """LGT-03: sensible = 1.00 P_light + f_sens,plug P_plug + N_occ occ q_sens (+ appliances);
    latent = N_occ occ q_lat (+ plug and appliance latent parts). W, scalars or arrays."""
    kind = "home" if building_type == "home" else "office"
    occ = np.asarray(occ, dtype=float)
    sens = (np.asarray(lighting_w, dtype=float) + PLUG_SENSIBLE[kind] * np.asarray(plug_w, dtype=float)
            + occupants * occ * OCC_SENSIBLE_W[kind])
    lat = occupants * occ * OCC_LATENT_W[kind] + PLUG_LATENT[kind] * np.asarray(plug_w, dtype=float)
    for k, p in (appliance_w or {}).items():
        fs, fl = HOME_APPLIANCE_FRACTIONS[k]
        sens = sens + fs * np.asarray(p, dtype=float)
        lat = lat + fl * np.asarray(p, dtype=float)
    return {"sensible_w": sens if np.ndim(sens) else float(sens),
            "latent_w": lat if np.ndim(lat) else float(lat)}


# ---------- hourly end-use profiles ----------

@dataclass(frozen=True)
class EndUseProfiles:
    """Hourly electricity of the non-HVAC end uses (kWh per hour = W averaged over the hour / 1000)
    and the gains they and the occupants give the zone."""
    lighting_kwh: np.ndarray
    plug_kwh: np.ndarray
    appliances_kwh: np.ndarray
    occupants: float
    occupants_source: str        # "systems" or "schedule_default"
    sensible_gain_w: np.ndarray
    latent_gain_w: np.ndarray
    bedrooms: float | None
    warnings: tuple[str, ...]


def end_use_profiles(*, occupancy_schedule: str, floor_area_m2: float, cal: Calendar,
                     lpd_w_m2: float, ppd_w_m2: float, occupants: float | None,
                     bedrooms: int | None = None, lpd_scale: float = 1.0,
                     ppd_scale: float = 1.0) -> EndUseProfiles:
    """Lighting, plug, appliance and occupant profiles for one set of inputs.

    Offices: LGT-01 and LGT-02 from the power densities and DEF-09 fractions; plug density scaled
    by head count (LGT-02) only when `occupants` comes from `Systems.occupants`.
    Homes: LGT-01 and LGT-02 annual formulas spread with DEF-09 shares; `lpd_scale` and
    `ppd_scale` (the registry's range relative to its expected value) scale the annual figures.
    `occupants=None` runs on the schedule default (LGT-03)."""
    kind = building_kind(occupancy_schedule)
    vacant = occupancy_schedule == "office_vacant"
    warnings: list[str] = []
    if kind == "office":
        n_occ = occupants if occupants is not None else office_occupants_default(floor_area_m2)
        if vacant and occupants is None:
            n_occ = 0.0
        scale = plug_density_scale(n_occ, floor_area_m2) if (occupants is not None and n_occ > 0) else 1.0
        light_w = lighting_power(lpd_w_m2, floor_area_m2, office_fraction("lighting", cal, vacant))
        plug_w = plug_power(ppd_w_m2 * scale, floor_area_m2, office_fraction("equipment", cal, vacant))
        appl = np.zeros(cal.n)
        appl_w: dict = {}
        n_br = None
    else:
        n_br, w = bedrooms_for_home(bedrooms, occupants)
        if w:
            warnings.append(w)
        n_occ = occupants if occupants is not None else home_occupants_default(n_br)
        light_w = 1000.0 * home_lighting_hourly_kwh(home_lighting_base(floor_area_m2) * lpd_scale, cal)
        plug_w = 1000.0 * _home_daily_spread(home_misc_energy(n_br, floor_area_m2) * ppd_scale, "equipment", cal)
        appl_w = {k: 1000.0 * _home_daily_spread(e, "equipment", cal)
                  for k, e in home_appliance_energy(n_br).items()}
        appl = sum(appl_w.values()) / 1000.0
    gains = internal_gains(light_w, plug_w, n_occ, occupant_presence(kind, cal, vacant), kind, appl_w)
    # annual formulas are per 365-day year; on a leap-year calendar the hourly spread keeps the annual total
    return EndUseProfiles(
        lighting_kwh=np.asarray(light_w) / 1000.0, plug_kwh=np.asarray(plug_w) / 1000.0,
        appliances_kwh=np.asarray(appl, dtype=float) * np.ones(cal.n), occupants=float(n_occ),
        occupants_source="systems" if occupants is not None else "schedule_default",
        sensible_gain_w=np.asarray(gains["sensible_w"]), latent_gain_w=np.asarray(gains["latent_w"]),
        bedrooms=n_br, warnings=tuple(warnings))
