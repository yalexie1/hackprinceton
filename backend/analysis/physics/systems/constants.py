"""Constants and default tables for A3 (systems, end uses, cost, emissions).

Every number cites the physics entry it comes from. They are kept local to this
subfolder (workplan 2.6): `backend/config.py` holds none of them today.
"""
from __future__ import annotations

# ---- unit conversions: physics 02 section 0, physics 04 TAR-05 ----
COP_PER_BTU_PER_WH = 0.293071        # EER, SEER, HSPF (Btu/(W.h)) to W/W; HVAC-01
# Homes take lighting and plug energy from the LGT-01 and LGT-02 annual formulas, which describe
# the existing lamp and appliance mix. `Systems.lighting_w_per_m2` and `plug_w_per_m2` scale those
# formulas relative to the reference densities below, the expected values of the registry's home
# placeholders (A10, tables.HOME_LPD_PLACEHOLDER and HOME_PPD_PLACEHOLDER). A measure that lowers a
# density (LGT_LED applies the LGT-01 lamp-mix factor) therefore lowers the energy. Moves to
# backend/config.py under A29.
HOME_LPD_REFERENCE_W_M2 = 7.0
HOME_PPD_REFERENCE_W_M2 = 5.0
KWH_PER_THERM = 29.3071070172         # TAR-05: 1 therm = 100 000 Btu_IT
MJ_PER_KWH = 3.6                      # TAR-05
KG_PER_LB = 0.45359237                # TAR-05
KWH_PER_MMBTU = 293.07107             # TAR-05
M3_PER_GALLON = 0.00378541            # physics 02 section 0
M2_PER_FT2 = 0.092903                 # physics 02 section 0

# ---- HVAC: physics 02 section 5 ----
SEER2_PER_SEER_DUCTED = 0.95          # HVAC-01 (also EER2 / EER)
HSPF2_PER_HSPF_DUCTED = 0.85          # HVAC-01
COOL_EIR_COEFFS = (0.69815, -0.015397, 0.00070)       # HVAC-02: g(theta) = a + b theta + c theta^2
COOL_CURVE_VALID_C = (18.0, 46.0)     # HVAC-02 validity; hours outside are clamped (counted, warned)
SEER_TEST_C = 27.78                   # HVAC-02: 82 F SEER test point
CD_DEFAULT = (0.05, 0.10, 0.25)       # HVAC-02: cycling degradation low / expected / high
SIZING_FACTOR = 1.2                   # HVAC-03: capacity = 1.2 x peak hourly load if unknown (S11)
SEASONAL_CLIMATE_BAND = 0.15          # HVAC-04 and HVAC-07: carry +-15 % on a seasonal result
HEAT_EIR_COEFFS = (1.168249, -0.030675, 0.000738)     # HVAC-05: g_h(theta)
HEAT_RATING_C = 8.33                  # HVAC-05: 47 F
HSPF_TO_COP47 = ((7.7, 3.05), (8.2, 3.35), (8.5, 3.50))   # HVAC-05, S14 Table 11; no extrapolation
HP_COLD_LIMIT_C = -5.0                # HVAC-05 validity
HP_COLD_HOURS_WARN = 50               # HVAC-05: warn above this many hours below -5 C
RTU_MIN_CAPACITY_W = 19000.0          # HVAC-07: units of 19 kW and above are rated by IEER
IEER_WEIGHTS = (0.020, 0.617, 0.238, 0.125)           # HVAC-07 (AHRI 340/360 via S16)
DSE_DUCTS_OUTSIDE = (0.800, 0.867, 0.933)             # HVAC-08 upper bound with DEF-06 leakage classes
CENTRAL_PLANT_BAND = 0.25             # HVAC-00 rule 3: central plant, efficiency range widened +-25 %

# ---- DHW: physics 02 section 6 ----
DHW_T_SET_C = 51.67                   # DHW-02: 125 F
DHW_T_MIX_C = 43.33                   # DHW-02: 110 F
DHW_GAL_PER_DAY = {                   # DHW-02, S10 Table 11: (constant, per bedroom), US gallons per day
    "clothes_washer": (2.35, 0.78),
    "dishwasher": (2.26, 0.75),
    "shower": (14.0, 4.67),
    "bath": (3.5, 1.17),
    "sink": (12.5, 4.16),
}
DHW_VOLUME_BAND = 0.30                # DHW-02: +-30 % on volume (tier B judgment)
DHW_ENERGY_BAND = 0.15                # DHW-03: +-15 % on E_dhw
WATER_RHO = 990.0                     # DHW-03, kg/m3 (tier B)
WATER_CP = 4180.0                     # DHW-03, J/(kg K) (tier B)

# ---- lighting, plug, occupants: physics 02 section 7 ----
HOME_LIGHT_A, HOME_LIGHT_B = 0.542, 334.0              # LGT-01: kWh/yr = 0.542 A_ft2 + 334
HOME_MEL = (1185.4, 180.2, 0.3188)                     # LGT-02: kWh/yr = a + b N_br + c A_ft2
HOME_APPLIANCES = {                    # LGT-02, S10 Table 25: (constant, per bedroom) kWh/yr, all electric
    "refrigerator": (434.0, 0.0),
    "range": (250.0, 83.0),
    "dishwasher": (87.6, 29.2),
    "clothes_washer": (38.8, 12.9),
    "dryer": (538.2, 179.4),
}
HOME_APPLIANCE_FRACTIONS = {           # LGT-03, S10 Table 25: (sensible, latent)
    "refrigerator": (1.00, 0.00),
    "range": (0.40, 0.30),
    "dishwasher": (0.60, 0.15),
    "clothes_washer": (0.80, 0.00),
    "dryer": (0.15, 0.05),
}
PLUG_SENSIBLE = {"home": 0.93, "office": 1.00}         # LGT-03
PLUG_LATENT = {"home": 0.02, "office": 0.00}           # LGT-03
OCC_SENSIBLE_W = {"home": 64.5, "office": 73.3}        # LGT-03, S10 Table 48
OCC_LATENT_W = {"home": 48.1, "office": 58.6}          # LGT-03, S10 Table 48
HOME_OCC_SF = (0.59, 0.87)             # LGT-03 eq. (23): N_occ = 0.59 N_br + 0.87 (single-family)
HOME_PERSON_HOURS_PER_DAY = 16.5       # LGT-03, S10 Figure 25
OFFICE_M2_PER_PERSON = 18.59           # LGT-03, S11 Table 4
PLUG_SCALE_LIMITS = (0.5, 2.0)         # LGT-02: plug scaling by head count, limited (tier B design choice)
HOME_BEDROOMS_DEFAULT = 3              # this file's fallback when neither bedrooms nor occupants is known

# ---- DEF-09 schedules (S11 Table B-13; S13 home shares), hour 1 = 00:00 to 01:00 ----
OFFICE_SCHEDULES = {
    "occupancy": {
        "weekday": (0, 0, 0, 0, 0, 0, 0.1, 0.2, 0.95, 0.95, 0.95, 0.95, 0.5, 0.95, 0.95, 0.95, 0.95, 0.3,
                    0.1, 0.1, 0.05, 0.05, 0.05, 0.05),
        "saturday": (0, 0, 0, 0, 0, 0, 0.1, 0.1, 0.3, 0.3, 0.3, 0.3, 0.1, 0.1, 0.1, 0.1, 0.1, 0, 0, 0, 0, 0,
                     0, 0),
        "other": (0.0,) * 24,
    },
    "lighting": {
        "weekday": (0.05, 0.05, 0.05, 0.05, 0.05, 0.1, 0.1, 0.3, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9,
                    0.5, 0.3, 0.3, 0.2, 0.2, 0.1, 0.05),
        "saturday": (0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.1, 0.1, 0.3, 0.3, 0.3, 0.3, 0.15, 0.15, 0.15, 0.15,
                     0.15, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05),
        "other": (0.05,) * 24,
    },
    "equipment": {
        "weekday": (0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.9, 0.9, 0.9, 0.9, 0.8, 0.9, 0.9, 0.9, 0.9, 0.5,
                    0.4, 0.4, 0.4, 0.4, 0.4, 0.4),
        "saturday": (0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.4, 0.4, 0.5, 0.5, 0.5, 0.5, 0.35, 0.35, 0.35, 0.35, 0.35,
                     0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3),
        "other": (0.3,) * 24,
    },
}
HOME_SHARES = {
    "occupancy": (0.035, 0.035, 0.035, 0.035, 0.035, 0.059, 0.082, 0.055, 0.027, 0.014, 0.014, 0.014, 0.014,
                  0.014, 0.019, 0.027, 0.041, 0.055, 0.068, 0.082, 0.082, 0.070, 0.053, 0.035),
    "lighting": (0.012, 0.010, 0.010, 0.010, 0.011, 0.018, 0.030, 0.038, 0.041, 0.041, 0.039, 0.037, 0.036,
                 0.035, 0.037, 0.041, 0.050, 0.065, 0.086, 0.106, 0.110, 0.079, 0.040, 0.018),
    "equipment": (0.036, 0.036, 0.036, 0.036, 0.036, 0.036, 0.038, 0.041, 0.042, 0.042, 0.042, 0.042, 0.042,
                  0.042, 0.042, 0.044, 0.047, 0.050, 0.051, 0.050, 0.048, 0.044, 0.040, 0.037),
}
HOME_LIGHT_MONTHLY = (1.19, 1.11, 1.02, 0.93, 0.84, 0.80, 0.82, 0.88, 0.98, 1.07, 1.16, 1.20)   # DEF-09
DEFAULT_CALENDAR_START = "2017-01-01T00"   # non-leap year starting on a Sunday: 260 weekdays, 52 Saturdays,
                                           # 53 other days, the day count of the LGT-01 worked example

# ---- emissions: physics 04 EMI-01, EMI-02 ----
# eGRID2023 rev 2, total-output CO2e and non-baseload CO2e, lb/MWh (EMI-01 table)
EGRID_LB_PER_MWH = {
    "CAMX": (429.983, 961.2),
    "ERCT": (736.629, 1247.5),
    "US": (770.9, 1379.2),
}
GAS_CO2E_KG_PER_MMBTU = 53.06 + 1.0e-3 * 28 + 1.0e-4 * 265   # EMI-02, AR5 GWP (CH4 28, N2O 265)
