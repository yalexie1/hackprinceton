"""Vintage default tables, transcribed from specs/physics/02-thermal-systems.md section 8 (DEF).

Every row carries the DEF entry it comes from and, where the physics file prints one, the
imperial value it was converted from, so a test can check the conversion and the ordering
low <= expected <= high (physics 02 section 9, "DEF tables").

Years are inclusive. `None` means open-ended. Climate keys are IECC zones: "2A" (Houston)
and "3B" (Los Angeles; the DOE reference buildings call it "3B-CA").

Values the physics file lists as unverified (section 10) are marked `placeholder=True` and
are carried as wide ranges with a low confidence; they are never presented as sourced.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Unit conversions, physics 02 section 0. Exact or to six figures.
U_IP_TO_SI = 5.678263          # Btu/(h.ft2.F) -> W/(m2.K)
BTU_PER_WH_TO_COP = 0.293071   # EER, SEER, HSPF -> W/W (HVAC-01)
W_FT2_TO_W_M2 = 10.7639

CLIMATES = ("2A", "3B")


@dataclass(frozen=True)
class Row:
    start: Optional[int]           # first year, inclusive; None = open
    end: Optional[int]             # last year, inclusive; None = open
    low: float
    expected: float
    high: float
    ref: str                       # DEF entry
    note: str = ""
    ip: Optional[tuple[float, float, float]] = None   # imperial values, if printed
    ip_factor: float = U_IP_TO_SI
    placeholder: bool = False

    def contains(self, year: int) -> bool:
        return (self.start is None or year >= self.start) and (self.end is None or year <= self.end)


def _u(lo, ex, hi, start, end, ref, note, ip=None):
    return Row(start, end, lo, ex, hi, ref, note, ip)


# ---------- DEF-01 home opaque envelope ----------

_WALL_COMMON = [
    _u(0.625, 2.021, 2.021, None, 1969, "DEF-01", "wood-frame wall, before 1970", (0.110, 0.356, 0.356)),
    _u(0.625, 0.782, 2.021, 1970, 1979, "DEF-01", "wood-frame wall, 1970 to 1979", (0.110, 0.138, 0.356)),
    _u(0.420, 0.625, 0.782, 1980, 1989, "DEF-01", "wood-frame wall, 1980 to 1989", (0.074, 0.110, 0.138)),
    _u(0.420, 0.625, 0.625, 1990, 1999, "DEF-01", "wood-frame wall, 1990 to 1999", (0.074, 0.110, 0.110)),
]
HOME_WALL_U: dict[str, list[Row]] = {
    "2A": _WALL_COMMON + [
        _u(0.420, 0.625, 0.625, 2000, None, "DEF-01", "wood-frame wall, 2000 and later, Texas", (0.074, 0.110, 0.110))],
    "3B": _WALL_COMMON + [
        _u(0.420, 0.420, 0.625, 2000, None, "DEF-01", "wood-frame wall, 2000 and later, California", (0.074, 0.074, 0.110))],
}

# Attic: the R-7 high value 0.61 is interpolated (physics 02 section 10, tier B).
_ATTIC = [
    _u(0.182, 0.403, 1.703, None, 1949, "DEF-01", "ceiling under a vented attic, before 1950", (0.032, 0.071, 0.300)),
    _u(0.182, 0.278, 1.703, 1950, 1959, "DEF-01", "ceiling under a vented attic, 1950 to 1959", (0.032, 0.049, 0.300)),
    _u(0.182, 0.403, 0.61, 1960, 1969, "DEF-01", "ceiling under a vented attic, 1960 to 1969; R-7 high interpolated (tier B)", (0.032, 0.071, 0.108)),
    _u(0.182, 0.278, 0.61, 1970, 1979, "DEF-01", "ceiling under a vented attic, 1970 to 1979; R-7 high interpolated (tier B)", (0.032, 0.049, 0.108)),
    _u(0.182, 0.278, 0.403, 1980, 1989, "DEF-01", "ceiling under a vented attic, 1980 to 1989", (0.032, 0.049, 0.071)),
    _u(0.148, 0.182, 0.278, 1990, None, "DEF-01", "ceiling under a vented attic, 1990 and later", (0.026, 0.032, 0.049)),
]
HOME_ATTIC_U: dict[str, list[Row]] = {"2A": _ATTIC, "3B": _ATTIC}

# ---------- DEF-02 solar absorptance, by roof material class ----------

ROOF_ABSORPTANCE: dict[str, Row] = {
    "shingle": Row(None, None, 0.75, 0.85, 0.92, "DEF-02", "asphalt shingle, colour unknown"),
    "concrete_tile": Row(None, None, 0.60, 0.75, 0.90, "DEF-02", "concrete or cement tile, colour unknown"),
    "tile": Row(None, None, 0.60, 0.75, 0.90, "DEF-02", "clay tile or slate, colour unknown"),
    "wood_shingle": Row(None, None, 0.80, 0.80, 0.90, "DEF-02", "wood shingle"),
    "membrane": Row(None, None, 0.40, 0.65, 0.90, "DEF-02", "low-slope membrane, metal or unknown commercial roof"),
}
# Vexcel material classes and vision words mapped onto the rows above.
ROOF_MATERIAL_ALIASES = {
    "shingle": "shingle", "asphalt": "shingle", "asphalt_shingle": "shingle", "composition": "shingle",
    "concrete": "concrete_tile", "concrete_tile": "concrete_tile", "cement_tile": "concrete_tile",
    "tile": "tile", "clay_tile": "tile", "slate": "tile",
    "wood": "wood_shingle", "wood_shingle": "wood_shingle", "shake": "wood_shingle",
    "membrane": "membrane", "metal": "membrane", "flat": "membrane", "built_up": "membrane",
    "gravel": "membrane", "tar_gravel": "membrane",
}

# ---------- DEF-03 windows ----------

WINDOW_TYPES: dict[str, tuple[float, float, tuple[float, float]]] = {
    # key: (U W/m2K, SHGC, (U imperial, unused))
    "single_clear_metal": (6.59, 0.76, (1.16, 0.0)),
    "single_clear_non_metal": (4.77, 0.63, (0.84, 0.0)),
    "double_clear_metal": (4.32, 0.67, (0.76, 0.0)),
    "double_clear_non_metal": (2.78, 0.56, (0.49, 0.0)),
    "double_lowe_non_metal": (2.16, 0.44, (0.38, 0.0)),
    "triple_lowe_non_metal": (1.65, 0.26, (0.29, 0.0)),
}
# The leakiest type with the same pane count: the high bound when vision reads the panes only.
WINDOW_SAME_PANES_WORST = {
    "single_clear_metal": "single_clear_metal",
    "single_clear_non_metal": "single_clear_metal",
    "double_clear_metal": "double_clear_metal",
    "double_clear_non_metal": "double_clear_metal",
    "double_lowe_non_metal": "double_clear_metal",
    "triple_lowe_non_metal": "triple_lowe_non_metal",
}


@dataclass(frozen=True)
class TypeRow:
    start: Optional[int]
    end: Optional[int]
    best: str
    expected: str
    worst: str
    ref: str = "DEF-03"

    def contains(self, year: int) -> bool:
        return (self.start is None or year >= self.start) and (self.end is None or year <= self.end)


HOME_WINDOW_TYPES: dict[str, list[TypeRow]] = {
    "2A": [
        TypeRow(None, 1959, "double_lowe_non_metal", "single_clear_non_metal", "single_clear_metal"),
        TypeRow(1960, 1979, "double_lowe_non_metal", "single_clear_non_metal", "single_clear_metal"),
        TypeRow(1980, 1999, "double_lowe_non_metal", "single_clear_non_metal", "single_clear_metal"),
        TypeRow(2000, 2009, "double_lowe_non_metal", "double_clear_metal", "single_clear_metal"),
        TypeRow(2010, None, "double_lowe_non_metal", "double_clear_metal", "single_clear_metal"),
    ],
    "3B": [
        TypeRow(None, 1959, "double_lowe_non_metal", "single_clear_non_metal", "single_clear_metal"),
        TypeRow(1960, 1979, "double_lowe_non_metal", "double_clear_metal", "single_clear_metal"),
        TypeRow(1980, 1999, "double_lowe_non_metal", "double_clear_metal", "single_clear_metal"),
        TypeRow(2000, 2009, "double_lowe_non_metal", "double_clear_non_metal", "double_clear_metal"),
        TypeRow(2010, None, "double_lowe_non_metal", "double_lowe_non_metal", "double_lowe_non_metal"),
    ],
}

# ---------- DEF-04 air leakage, homes, ACH50 ----------

HOME_ACH50: dict[str, list[Row]] = {
    "2A": [
        Row(None, 1959, 10, 25, 50, "DEF-04", "Houston, before 1960"),
        Row(1960, 1979, 8, 20, 40, "DEF-04", "Houston, 1960 to 1979"),
        Row(1980, 1989, 7, 20, 40, "DEF-04", "Houston, 1980 to 1989"),
        Row(1990, 1999, 5, 15, 25, "DEF-04", "Houston, 1990 to 1999"),
        Row(2000, None, 5, 15, 25, "DEF-04", "Houston, 2000 and later"),
    ],
    "3B": [
        Row(None, 1959, 6, 15, 30, "DEF-04", "Los Angeles, before 1960"),
        Row(1960, 1979, 5, 15, 25, "DEF-04", "Los Angeles, 1960 to 1979"),
        Row(1980, 1989, 4, 10, 20, "DEF-04", "Los Angeles, 1980 to 1989"),
        Row(1990, 1999, 3, 8, 15, "DEF-04", "Los Angeles, 1990 to 1999"),
        Row(2000, None, 3, 7, 15, "DEF-04", "Los Angeles, 2000 and later"),
    ],
}

# ---------- DEF-05 equipment efficiency ----------
# Homes, keyed by building year with the "equipment replaced" rule (tier B judgment): older than
# 2006 and nothing observed -> SEER 10 / 13 / 14. From 2006 the building year is the equipment
# year; the high bound is the current minimum, since a replacement can only be newer.
HOME_SEER: list[Row] = [
    Row(None, 2005, 10.0, 13.0, 14.0, "DEF-05", "building older than 2006, equipment year not observed"),
    Row(2006, 2014, 13.0, 13.0, 15.05, "DEF-05", "building 2006 to 2014, equipment of the building year"),
    Row(2015, 2022, 14.0, 14.0, 15.05, "DEF-05", "building 2015 to 2022, equipment of the building year"),
    Row(2023, None, 15.05, 15.05, 15.05, "DEF-05", "building 2023 or later: 14.3 SEER2 = 15.05 SEER"),
]
# Heat pump HSPF with the same rule; the pre-2006 row mirrors SEER 10 / 13 / 14 with the HSPF of
# the same rows (7.1 / 7.7 / 8.2). The mirroring is this package's judgment (tier B).
HOME_HSPF: list[Row] = [
    Row(None, 2005, 7.1, 7.7, 8.2, "DEF-05", "building older than 2006, heat pump year not observed; mirrors the SEER rule (judgment)"),
    Row(2006, 2014, 7.7, 7.7, 8.8, "DEF-05", "building 2006 to 2014"),
    Row(2015, 2022, 8.2, 8.2, 8.8, "DEF-05", "building 2015 to 2022"),
    Row(2023, None, 8.8, 8.8, 8.8, "DEF-05", "building 2023 or later: 7.5 HSPF2 = 8.8 HSPF"),
]
HOME_AFUE: list[Row] = [
    Row(None, 1991, 0.64, 0.78, 0.80, "DEF-05", "unknown furnace, building older than 1992"),
    Row(1992, None, 0.78, 0.80, 0.90, "DEF-05", "unknown furnace, building 1992 or later"),
]

# Offices (packaged unit with gas furnace). DEF-05 gives no row for 2005 to 2022; the 1980 to 2004
# values ("as above") are used there. Cooling carried -10 % / +15 %.
OFFICE_COOLING_MINUS = 0.10
OFFICE_COOLING_PLUS = 0.15
OFFICE_LARGE_UNIT_KW = 19.0   # DEF-05: SEER below 19 kW, EER for 19 to 40 kW


@dataclass(frozen=True)
class OfficeCoolingRow:
    start: Optional[int]
    end: Optional[int]
    small: tuple[float, str]       # value, metric under 19 kW
    large: tuple[float, str]       # value, metric 19 kW and over
    note: str
    ref: str = "DEF-05"

    def contains(self, year: int) -> bool:
        return (self.start is None or year >= self.start) and (self.end is None or year <= self.end)


OFFICE_COOLING: list[OfficeCoolingRow] = [
    OfficeCoolingRow(None, 1979, (11.06, "SEER"), (9.63, "EER"), "office before 1980, equipment since replaced"),
    OfficeCoolingRow(1980, 2004, (11.06, "SEER"), (9.63, "EER"), "office 1980 to 2004"),
    OfficeCoolingRow(2005, 2022, (11.06, "SEER"), (9.63, "EER"),
                     "office 2005 to 2022: DEF-05 has no row, the 1980 to 2004 values are used"),
    OfficeCoolingRow(2023, None, (14.6, "IEER"), (14.6, "IEER"), "office new or replaced from 2023, gas heat"),
]
OFFICE_HEATING_EFFICIENCY = Row(None, None, 0.80, 0.80, 0.80, "DEF-05", "office gas furnace, combustion efficiency 0.80")

# ---------- DEF-06 ducts, DEF-07 water heaters ----------

HOME_DSE_OUTSIDE = Row(None, None, 0.800, 0.867, 0.933, "DEF-06",
                       "ducts outside the conditioned space; an upper bound, HVAC-08")
DHW_UEF = {
    "gas": Row(None, None, 0.54, 0.58, 0.64, "DEF-07", "unknown gas storage heater"),
    "electricity": Row(None, None, 0.87, 0.92, 0.93, "DEF-07", "unknown electric storage heater"),
}

# ---------- DEF-08 setpoints ----------

SETPOINT_RANGE_K = 1.0
SETPOINTS = {
    "home": {"heating": 21.7, "cooling": 24.4, "setback": None, "setup": None},
    "office": {"heating": 21.0, "cooling": 24.0, "setback": 15.6, "setup": 26.7},
}

# ---------- DEF-10 lighting and plug power density (offices) ----------

OFFICE_LPD: list[Row] = [
    Row(None, 2003, 10.76, 19.48, 19.48, "DEF-10", "office built before 2004, lighting not yet upgraded",
        (1.0, 1.81, 1.81), W_FT2_TO_W_M2),
    Row(2004, None, 6.5, 10.76, 10.76, "DEF-10", "office built 2004 or later; 6.5 is a placeholder (tier A)",
        None, W_FT2_TO_W_M2),
]
OFFICE_PPD: list[Row] = [
    Row(None, None, 8.61, 10.76, 10.76, "DEF-10", "the source's two tables disagree; both are carried",
        (0.8, 1.0, 1.0), W_FT2_TO_W_M2),
]

# Homes take lighting and plug energy from LGT-01 and LGT-02 (floor area and bedrooms), not from a
# power density. Systems still needs a density; these are unsourced placeholders, wide, confidence 0.
HOME_LPD_PLACEHOLDER = Row(None, None, 4.0, 7.0, 11.0, "LGT-01",
                           "placeholder: homes use the LGT-01 energy formula; not a sourced density", placeholder=True)
HOME_PPD_PLACEHOLDER = Row(None, None, 3.0, 5.0, 8.0, "LGT-02",
                           "placeholder: homes use the LGT-02 energy formula; not a sourced density", placeholder=True)

# ---------- DEF-11 office envelope ----------


# (start, end): {climate: (value SI, value IP)}
OFFICE_WALL_STEEL = [
    (None, 1979, {"2A": (1.306, 0.230), "3B": (1.306, 0.230)}),
    (1980, 2004, {"2A": (0.852, 0.150), "3B": (1.249, 0.220)}),
    (2005, None, {"2A": (0.704, 0.124), "3B": (0.704, 0.124)}),
]
# DEF-11 has no mass wall before 1980; the 1980 to 2004 mass wall is the other-type bound there
# (as in the office_houston fixture).
OFFICE_WALL_MASS = [
    (None, 1979, {"2A": (1.931, 0.340), "3B": (5.678, 1.000)}),
    (1980, 2004, {"2A": (1.931, 0.340), "3B": (5.678, 1.000)}),
    (2005, None, {"2A": (3.293, 0.580), "3B": (0.857, 0.151)}),
]
# The 5.678 Los Angeles mass wall is the code's "no requirement" entry: high bound only.
NO_REQUIREMENT_U = 5.678
# S11 type by vintage: steel frame before 1980, mass wall afterwards.
OFFICE_WALL_S11_TYPE = [(None, 1979, "steel"), (1980, None, "mass")]

OFFICE_ROOF_ABOVE_DECK = [
    (None, 1979, {"2A": (0.568, 0.100), "3B": (0.568, 0.100)}),
    (1980, 2004, {"2A": (0.375, 0.066), "3B": (0.568, 0.100)}),
    (2005, None, {"2A": (0.358, 0.063), "3B": (0.358, 0.063)}),
]
OFFICE_ROOF_ATTIC = [
    (None, 1979, {"2A": (0.568, 0.100), "3B": (0.568, 0.100)}),
    (1980, 2004, {"2A": (0.375, 0.066), "3B": (0.568, 0.100)}),
    (2005, None, {"2A": (0.193, 0.034), "3B": (0.193, 0.034)}),
]
OFFICE_ROOF_S11_TYPE = [(None, 1979, "above_deck"), (1980, None, "attic")]

OFFICE_WINDOW_U = [
    (None, 1979, {"2A": (6.93, 1.22), "3B": (6.93, 1.22)}),
    (1980, 2004, {"2A": (6.93, 1.22), "3B": (6.93, 1.22)}),
    (2005, None, {"2A": (6.93, 1.22), "3B": (3.24, 0.57)}),
]
OFFICE_WINDOW_SHGC = [
    (None, 1979, {"2A": (0.54, None), "3B": (0.54, None)}),
    (1980, 2004, {"2A": (0.25, None), "3B": (0.44, None)}),
    (2005, None, {"2A": (0.25, None), "3B": (0.25, None)}),
]

# ---------- INF-05 office leakage and outdoor air ----------

OFFICE_LEAKAGE_75PA: list[Row] = [
    Row(None, 2003, 2.0, 7.5, 7.5, "INF-05", "built before 2004"),
    Row(2004, None, 2.0, 2.0, 2.0, "INF-05", "built 2004 or later"),
]
OFFICE_M2_PER_PERSON = 18.59          # INF-05, LGT-03 (S11 Table 4)
OUTDOOR_AIR_M3_S_PER_PERSON = 0.00944  # INF-05, 20 cfm

# LGT-03 occupant count for homes from bedrooms.
HOME_OCCUPANTS = {"single_family": (0.59, 0.87), "multifamily_unit": (0.92, 0.63)}

# Unsourced spreads (judgments of this package; candidates for backend/config.py):
OCCUPANT_DEFAULT_SPREAD = 0.30   # +/- on a default occupant count (A_f / 18.59 or bedrooms formula)
TENANT_OCCUPANT_SPREAD = 0.20    # +/- on a CoStar tenant's employee count (office fixture: 16 / 20 / 24)
TENANT_DENSITY_SPREAD = 0.30     # +/- when occupants are scaled from the building's tenant density
TENANT_AREA_MATCH_RATIO = 1.5    # a tenancy matches the scanned suite if areas agree within this factor

# Systems.infiltration_ach is a reported result (physics 02 section 12, note 1), filled later by the
# physics. Until then the registry carries a placeholder: homes ACH50 / 20 (rule of thumb, unsourced),
# offices 0.1 / 0.3 / 0.4 (unsourced, as in the fixtures).
HOME_ACH50_TO_NATURAL = 20.0
OFFICE_NATURAL_ACH_PLACEHOLDER = (0.1, 0.3, 0.4)

# All numeric vintage tables, for the table test.
ALL_ROW_TABLES: dict[str, list[Row]] = {
    "HOME_WALL_U.2A": HOME_WALL_U["2A"], "HOME_WALL_U.3B": HOME_WALL_U["3B"],
    "HOME_ATTIC_U": _ATTIC,
    "ROOF_ABSORPTANCE": list(ROOF_ABSORPTANCE.values()),
    "HOME_ACH50.2A": HOME_ACH50["2A"], "HOME_ACH50.3B": HOME_ACH50["3B"],
    "HOME_SEER": HOME_SEER, "HOME_HSPF": HOME_HSPF, "HOME_AFUE": HOME_AFUE,
    "DHW_UEF": list(DHW_UEF.values()), "DSE": [HOME_DSE_OUTSIDE],
    "OFFICE_LPD": OFFICE_LPD, "OFFICE_PPD": OFFICE_PPD, "OFFICE_LEAKAGE_75PA": OFFICE_LEAKAGE_75PA,
    "OFFICE_HEATING": [OFFICE_HEATING_EFFICIENCY],
    "HOME_PLACEHOLDERS": [HOME_LPD_PLACEHOLDER, HOME_PPD_PLACEHOLDER],
}
OFFICE_TYPE_TABLES = {
    "OFFICE_WALL_STEEL": OFFICE_WALL_STEEL, "OFFICE_WALL_MASS": OFFICE_WALL_MASS,
    "OFFICE_ROOF_ABOVE_DECK": OFFICE_ROOF_ABOVE_DECK, "OFFICE_ROOF_ATTIC": OFFICE_ROOF_ATTIC,
    "OFFICE_WINDOW_U": OFFICE_WINDOW_U,
}
