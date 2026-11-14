"""Constants of the zone model (A2). Every value cites its entry in
specs/physics/02-thermal-systems.md. Values marked "config candidate" are defaults the lane may
later move to backend/config.py (owned by A0); they live here until then.
"""
from __future__ import annotations

# ---- ENV-01, ENV-06: surface resistances, m2K/W (ISO 6946 via S5 section 4.1) ----
R_SI = {"horizontal": 0.13, "up": 0.10, "down": 0.17}
R_SE = 0.04
# ASHRAE films used in US tables (S6): exterior R-0.17, interior wall R-0.68 (ENV-06)
R_SI_ASHRAE_WALL = 0.68 * 0.176110
R_SE_ASHRAE = 0.17 * 0.176110

# ---- ENV-03: additional resistance for a construction bordering an unheated space (S9 Table 2) ----
R_ADJ_UNCONDITIONED = 0.3

# ---- ENV-04: slab on grade ----
GROUND_CONDUCTIVITY = 1.5          # W/(m K), clay (S7); 2.0 is the high case
GROUND_CONDUCTIVITY_HIGH = 2.0
SLAB_R_SI = 0.17
SLAB_R_SE = 0.04
WALL_THICKNESS_DEFAULT_M = 0.15    # ENV-04: framed wall when WallEdge.thickness_m is absent
SLAB_F_FACTOR = 1.263              # W/(m K), unheated uninsulated slab (S6 Table 4.4.7), the low case

# ---- ENV-05, WIN-01: sky radiation ----
EMITTANCE_DEFAULT = 0.90           # DEF-02, S10
H_R_PER_EMITTANCE = 5.0            # ENV-05: h_r = 4 eps sigma T^3, "about 5 eps"; worked examples use 5 eps
DT_SKY_K = 11.0                    # ENV-05: S1 clause 11.4.6, when the weather file has no sky temperature
SIGMA = 5.67e-8

# ---- DEF-02: absorptance used when a Surface carries none (expected values; config candidate) ----
ABSORPTANCE_WALL_DEFAULT = 0.60          # exterior walls, S10
ABSORPTANCE_ROOF_DEFAULT = 0.65          # "low-slope membrane, metal, or unknown roof", S13

# ---- ZON-01: ISO 13790 5R1C constants (S1 clause 7.2.2.2, 12.2.2, Table 12) ----
LAMBDA_AT = 4.5      # A_tot / A_f
H_IS = 3.45          # W/(m2 K)
H_MS = 9.1           # W/(m2 K)
RHO_C_AIR = 1200.0   # J/(m3 K), S1 clause 9.3.1 (ZON-01, INF-01)
MASS_CLASSES = {     # (C_m per m2 floor, J/(m2 K); A_m per m2 floor)
    "very_light": (80_000.0, 2.5),
    "light": (110_000.0, 2.5),
    "medium": (165_000.0, 2.5),
    "heavy": (260_000.0, 3.0),
    "very_heavy": (370_000.0, 3.5),
}
H_VE_FLOOR = 1e-6    # ZON-03: floor on H_ve, W/K

# ---- ZON-04: year run (implementation rule of the entry, not the standard) ----
THETA_M_START_C = 20.0
WARMUP_HOURS = 14 * 24
HEATING_OFF_C = -50.0
COOLING_OFF_C = 80.0

# ---- ZON-06: monthly utilisation factor reference values (S1 Table 9, monthly method) ----
A_0 = 1.0
TAU_0_H = 15.0

# ---- INF-02, INF-03: houses ----
LEAKAGE_EXPONENT = 0.65            # 0.60 to 0.70 range
AIR_DENSITY = 1.2                  # kg/m3
STACK_COEFF = {1: 0.000145, 2: 0.000290, 3: 0.000435}    # (L/s)^2 / (cm^4 K)
WIND_COEFF = {                     # shelter class -> by stories 1, 2, 3; (L/s)^2/(cm^4 (m/s)^2)
    1: (0.000319, 0.000420, 0.000494),
    2: (0.000246, 0.000325, 0.000382),
    3: (0.000174, 0.000231, 0.000271),
    4: (0.000104, 0.000137, 0.000161),
    5: (0.000032, 0.000042, 0.000049),
}
SHELTER_CLASS_DEFAULT = 4

# ---- INF-05: offices (S11, single-sourced, tier B) ----
OFFICE_M2_PER_PERSON = 18.59
OUTDOOR_AIR_PER_PERSON_M3_S = 0.00944
OFFICE_LEAKAGE_75PA_PRE2004 = 7.5   # L/(s m2) at 75 Pa
OFFICE_INFILTRATION_HVAC_ON_FRACTION = 0.25

# ---- INF-07: latent load (tier B constants) ----
H_FG = 2.50e6                       # J/kg
W_INDOOR = 0.0093                   # kg/kg, 24 degC and 50 % RH at sea level

# ---- WIN-01, WIN-02 ----
F_W = 0.90                          # S1 clause 11.4.2
INTERIOR_SHADING_BASELINE = 0.70    # WIN-02: S10, homes; offices use the same value (config candidate)
INTERIOR_SHADING = {                # (C1, C2), S13 citing ASHRAE HoF 2021 ch. 15 Table 14 (tier B)
    "light_curtains": (0.84, 0.42), "medium_curtains": (0.94, 0.37), "dark_curtains": (0.98, 0.25),
    "light_shades": (0.82, 0.42), "medium_shades": (0.90, 0.38), "dark_shades": (0.98, 0.33),
    "light_blinds_closed": (0.78, 0.47), "medium_blinds_closed": (0.90, 0.41),
    "dark_blinds_closed": (0.98, 0.25), "light_blinds_half_open": (0.93, 0.38),
    "medium_blinds_half_open": (0.95, 0.26), "dark_blinds_half_open": (1.00, 0.19),
}
INTERIOR_COVER_DEFAULT = {"curtains": 0.5, "shades": 0.5, "blinds": 1.0}
EXTERIOR_SHADING = {"solar_screen": 0.30, "solar_film": 0.70}   # tier B, single-sourced

# ---- DEF-08: setpoints (S10 section 4.2; S11 Table B-13) ----
SETPOINTS = {
    "home": {"heat": 21.7, "cool": 24.4},
    "office": {"heat": 21.0, "cool": 24.0, "heat_setback": 15.6, "cool_setup": 26.7},
}

# ---- DEF-09: office HVAC-on hours, hour 1 = 00:00 to 01:00 (S11 Table B-13) ----
OFFICE_HVAC_ON_HOURS = {"weekday": range(7, 23), "saturday": range(7, 19), "other": range(0)}
