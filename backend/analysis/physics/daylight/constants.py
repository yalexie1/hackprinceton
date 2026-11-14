"""Constants of A5 (daylight, glare, comfort). specs/physics/03-daylight-comfort.md.

Constants destined for backend/config.py (SPEC 12) are kept here until the lane owner moves them;
each cites its entry. Assumption ranges are design ranges from section 0.4, not measured facts.
"""
from __future__ import annotations

import math

# ---- reference heights, section 0.3 (config) ----
WORKPLANE_HEIGHT_M = 0.85      # 0.3: BS EN 17037 UK annex / BR 209 working plane [V as quoted]
EYE_HEIGHT_SEATED_M = 1.20     # 0.3: Wienold 2009 seated view position [V]
BODY_CENTRE_SEATED_M = 0.60    # 0.3: evaluation height only; ISO 7726 convention [U]

# ---- desk score, LCT-03 (design choice, config) ----
SCORE_WEIGHTS = {"daylight": 0.4, "glare": 0.3, "comfort": 0.3}
G_MAX = 0.20
PPD_MAX = 25.0
TARGET_LUX = 300.0             # DAY-09: DeskScore.daylight is DA_300

# ---- occupied hours, section 0.3 (design choice, config) ----
OCCUPIED_START_HOUR = 8        # 08:00 local
OCCUPIED_END_HOUR = 18         # 18:00 local, Monday to Friday

# ---- vision-window placement, section 0.2 (design choices) ----
VISION_SILL_M = 0.9            # 0.2: sill 0.9 m for a window read by vision
VISION_WINDOW_HEIGHT_M = 1.5   # design choice of A5: height of a vision window before it is widened
                               # (R0 window height); the width is area / height, capped at the edge
DEFAULT_CEILING_HEIGHT_M = 2.7 # design choice of A5 when Room.height_m is missing (warned)

# ---- glazing defaults when a measured opening has no window Surface (A9 placeholders) ----
DEFAULT_WINDOW_U = 4.5         # physics 02 DEF table expected value as used by A9 (window.u_value)
DEFAULT_WINDOW_SHGC = 0.5      # same (window.shgc)

# ---- inside surface coefficient, physics 02 ENV-06 (physics.md section 4) ----
H_I_W_M2K = 7.69               # ISO 6946 R_si = 0.13 m2K/W; range to 8.35. Not the 8.0 of CMF-04's example
H_I_RANGE_W_M2K = (7.69, 8.35)

# ---- DAY-02 overcast sky ----
EH_OVER_LZ = 7.0 * math.pi / 9.0                     # E_h / L_z
F_S0 = (3.0 * math.pi + 8.0) / (14.0 * math.pi)      # vertical sky component 0.39618

# ---- DAY-07 Perez 1990 Table 1 (bin lower bounds) and Table 4 ----
PEREZ_EPS_BOUNDS = (1.000, 1.065, 1.230, 1.500, 1.950, 2.800, 4.500, 6.200)
PEREZ_DIFFUSE = (   # a, b, c, d per bin 1..8
    (97.24, -0.46, 12.00, -8.91),
    (107.22, 1.15, 0.59, -3.95),
    (104.97, 2.96, -5.53, -8.77),
    (102.39, 5.59, -13.95, -13.90),
    (100.71, 5.94, -22.75, -23.74),
    (106.42, 3.83, -36.15, -28.83),
    (141.88, 1.90, -53.24, -14.03),
    (152.23, 0.35, -45.27, -7.98),
)
PEREZ_DIRECT = (
    (57.20, -4.55, -2.98, 117.12),
    (98.99, -3.46, -1.21, 12.38),
    (109.83, -4.90, -1.71, -8.81),
    (110.34, -5.84, -1.99, -4.56),
    (106.36, -3.97, -1.75, -6.16),
    (107.19, -1.25, -1.51, -26.73),
    (105.75, 0.77, -1.26, -34.44),
    (101.18, 1.58, -1.10, -8.29),
)
PEREZ_KAPPA = 1.041
SUN_MIN_ALTITUDE_DEG = 2.0     # DAY-07 design choice: below 2 deg all illuminances are zero
SOLAR_CONSTANT_W_M2 = 1361.0   # DAY-07 worked example: I0 = 1361 (1 + 0.033 cos(2 pi n / 365))

# ---- GLR-02 DGPs classes (Wienold 2009 Table 5) ----
DGPS_SLOPE = 6.22e-5
DGPS_INTERCEPT = 0.184
DGP_GLARE_LIMIT = 0.40         # GLR-05: class B limit
GLARE_FACING_WARN = 0.05       # GLR-05: warn when the facing-the-window value exceeds this

# ---- CMF-06 radiant asymmetry ----
DT_PR_COOL_WALL_LIMIT_K = 10.0

# ---- CMF-07 SolarCal ----
F_EFF = {"seated": 0.696, "standing": 0.725}
ALPHA_LW = 0.95
H_R_W_M2K = 6.0
FP_ALTITUDES = (0, 15, 30, 45, 60, 75, 90)
FP_SHARPS = tuple(range(0, 181, 15))
FP_SEATED = (       # rows SHARP 0..180 step 15, columns altitude 0..90 step 15
    (0.290, 0.324, 0.305, 0.303, 0.262, 0.224, 0.177),
    (0.292, 0.328, 0.294, 0.288, 0.268, 0.227, 0.177),
    (0.288, 0.332, 0.298, 0.290, 0.264, 0.222, 0.177),
    (0.274, 0.326, 0.294, 0.289, 0.252, 0.214, 0.177),
    (0.254, 0.308, 0.280, 0.276, 0.241, 0.202, 0.177),
    (0.230, 0.282, 0.262, 0.260, 0.233, 0.193, 0.177),
    (0.216, 0.260, 0.248, 0.244, 0.220, 0.186, 0.177),
    (0.234, 0.258, 0.236, 0.227, 0.208, 0.180, 0.177),
    (0.262, 0.260, 0.224, 0.208, 0.196, 0.176, 0.177),
    (0.280, 0.260, 0.210, 0.192, 0.184, 0.170, 0.177),
    (0.298, 0.256, 0.194, 0.174, 0.168, 0.168, 0.177),
    (0.306, 0.250, 0.180, 0.156, 0.156, 0.166, 0.177),
    (0.300, 0.240, 0.168, 0.152, 0.152, 0.164, 0.177),
)

# ---- assumption keys, section 0.4: (low, expected, high) ----
# "low" is the daylight-unfavourable set and "high" the daylight-favourable set (section 0.4: do
# not mix signs inside one run), so for obstruction angle low = 30 and high = 0.
DAYLIGHT_ASSUMPTIONS = {
    "glazing.visible_transmittance": (0.40, 0.68, 0.80),
    "glazing.maintenance_factor": (0.70, 0.90, 1.00),
    "glazing.glazed_fraction": (0.65, 0.80, 0.90),
    "interior.reflectance_ceiling": (0.60, 0.70, 0.85),
    "interior.reflectance_walls": (0.30, 0.50, 0.70),
    "interior.reflectance_floor": (0.10, 0.20, 0.40),
    "interior.reflectance_glass": (0.10, 0.10, 0.10),
    "site.ground_reflectance": (0.10, 0.20, 0.30),
    "site.obstruction_angle_deg": (30.0, 10.0, 0.0),
    "site.obstruction_reflectance": (0.10, 0.20, 0.40),
}
COMFORT_ASSUMPTIONS = {        # expected values used in every run (A5 design choice, see README of PR)
    "comfort.met": 1.2,
    "comfort.clo_heating": 1.0,
    "comfort.clo_cooling": 0.5,
    "comfort.air_speed_m_s": 0.1,
    "comfort.rh_percent": 50.0,
    "comfort.shortwave_absorptivity": 0.70,
    "comfort.floor_reflectance_solar": 0.6,
    "comfort.body_exposed_fraction": 0.5,
}
CLO_SWITCH_T_OUT_C = 15.0      # CMF-08: heating clothing when T_out < 15 and no zone mode is given
