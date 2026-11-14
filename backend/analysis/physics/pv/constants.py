"""Constants of the PV production chain (physics 01, section 3).

These are configuration values. They live here until the scaffold and
configuration packages (A0, A29) move them into ``backend/config.py``; the
names below are meant to be kept when they move.
"""

# PV-01: plain-glass cover, PVW5 section 8, SAM15 eq. 9.13 to 9.15.
GLASS_REFRACTIVE_INDEX = 1.526
GLASS_EXTINCTION_PER_M = 4.0
GLASS_THICKNESS_M = 0.002

# PV-02: Sandia module temperature model, KING04 Table 1: (a, b in s/m, dT in degC).
SAPM_TEMPERATURE_ROWS: dict[str, tuple[float, float, float]] = {
    "glass_glass_open_rack": (-3.47, -0.0594, 3.0),
    "glass_glass_close_roof_mount": (-2.98, -0.0471, 1.0),
    "glass_polymer_open_rack": (-3.56, -0.0750, 3.0),
    "glass_polymer_insulated_back": (-2.81, -0.0455, 0.0),
}
# Which row is the expected value and which are the bounds, for a module
# parallel to a pitched roof (PV-02 table, PV-09 step 4).
TEMPERATURE_ROW_EXPECTED = "glass_glass_close_roof_mount"
TEMPERATURE_ROW_HOT = "glass_polymer_insulated_back"
TEMPERATURE_ROW_COOL = "glass_polymer_open_rack"
# Tilted racks on flat roofs (PV-02 table).
TEMPERATURE_ROW_FLAT_RACK = "glass_polymer_open_rack"

# PV-03: power temperature coefficients, PVW5 Table 3 (1/degC).
GAMMA_PDC_EXPECTED = -0.0035  # premium module
GAMMA_PDC_LOW_YIELD = -0.0047  # standard module, low-yield bound
GAMMA_PDC_THIN_FILM = -0.0020

# PV-04: PVWatts v5 default losses in percent, PVW5 Table 6, as used in this project.
DEFAULT_LOSSES_PERCENT: dict[str, float] = {
    "soiling": 2.0,
    "shading": 3.0,  # 0 for a panel whose shading was computed by ray casting (SHD)
    "snow": 0.0,
    "mismatch": 2.0,
    "wiring": 2.0,
    "connections": 0.5,
    "lid": 1.5,
    "nameplate_rating": 1.0,
    "age": 0.0,  # handled by PV-07
    "availability": 3.0,
}
# PVW5 states the 3 % shading default stands for distant horizon obstructions.
DEFAULT_SHADING_LOSS_PERCENT = 3.0

# PV-05: PVWatts inverter, PVW5 eq. 10 and 11.
INVERTER_ETA_NOM = 0.96
INVERTER_ETA_REF = 0.9637
DC_AC_RATIO = 1.2  # GAG16 Table 1; PVW5's own default is 1.1

# PV-07: degradation, JK12 (median 0.5 %/yr, mean 0.8 %/yr).
DEGRADATION_RATE_EXPECTED = 0.005
DEGRADATION_RATE_LOW_YIELD = 0.008

# PV-08 defaults are tagged [U] in physics 01 section 8: typical values, not from
# a cited data sheet. Carried as assumptions; replace with the quoted product.
MODULE_W_UNVERIFIED = 430.0
MODULE_LENGTH_M_UNVERIFIED = 1.722
MODULE_WIDTH_M_UNVERIFIED = 1.134

# PV-09 step 6: one-sided 10 % / 90 % point of a normal distribution.
Z_10_90 = 1.2816

HOURS_PER_YEAR = 8760
