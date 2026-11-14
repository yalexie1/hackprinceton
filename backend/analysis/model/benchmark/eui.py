"""BEN-01 to BEN-03: site energy use intensity against the EIA surveys (physics 02 section 13).

The table ``eui_tables.csv`` holds weighted percentiles of site EUI for comparable buildings,
built by ``build_eui_tables.py`` from the RECS 2020 and CBECS 2018 public-use microdata. This
module only reads it. Pure functions, no network, no import from another analysis package.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

TABLE = Path(__file__).resolve().parent / "eui_tables.csv"

KWH_TO_KBTU = 3.412142          # 1 kWh = 3412.142 Btu
M2_TO_FT2 = 10.763910           # 1 m2 = 10.76391 ft2
KWH_M2_TO_KBTU_FT2 = KWH_TO_KBTU / M2_TO_FT2      # 0.316998

QUANTILES = (5, 10, 25, 50, 75, 90, 95)
N_MIN = 50                      # [J] smallest sample a cut may rest on (BEN-02)
WARN_LOW, WARN_HIGH = 10, 90    # [J] plausibility band, percentiles (BEN-03)

BUILDING_TYPES = ("single_family", "multifamily", "office")
# CBECS 2018 climate groups of the ASHRAE 169-2021 thermal zones (EIA, "Definitions of CBECS
# climate zones"): 1A 1B 2A 2B / 3A 3B 3C / 4A 4B 4C / 5A 5B 5C / 6A 6B 7 8.
CBECS_GROUP = {"1": "hot_or_very_hot", "2": "hot_or_very_hot", "3": "warm", "4": "mixed_mild",
               "5": "cool", "6": "cold_or_very_cold", "7": "cold_or_very_cold", "8": "cold_or_very_cold"}
HOME_SIZE = [(0, 1000, "lt1000"), (1000, 1500, "1000_1499"), (1500, 2000, "1500_1999"),
             (2000, 2500, "2000_2499"), (2500, 3000, "2500_2999"), (3000, float("inf"), "ge3000")]
OFFICE_SIZE = [(0, 10000, "le10k"), (10000, 50000, "10k_50k"), (50000, 200000, "50k_200k"),
               (200000, float("inf"), "gt200k")]

SIZE_WORDS = {"lt1000": "under 1,000", "1000_1499": "1,000 to 1,499", "1500_1999": "1,500 to 1,999",
              "2000_2499": "2,000 to 2,499", "2500_2999": "2,500 to 2,999", "ge3000": "3,000 or more",
              "le10k": "under 10,000", "10k_50k": "10,000 to 49,999", "50k_200k": "50,000 to 199,999",
              "gt200k": "200,000 or more"}

SOURCES = {
    "RECS2020": "EIA, 2020 Residential Energy Consumption Survey, public-use microdata v7 "
                "(recs2020_public_v7.csv), weighted with NWEIGHT",
    "CBECS2018": "EIA, 2018 Commercial Buildings Energy Consumption Survey, public-use microdata "
                 "(cbecs2018_final_public.csv), principal building activity Office, weighted with FINALWT",
}


@dataclass(frozen=True)
class Band:
    """Percentiles of one quantity in the matched cut, kBtu/ft2 and kWh/m2 per year."""
    quantity: str                               # "total", "electricity" or "gas"
    model_kbtu_ft2: float
    model_kwh_m2: float
    percentiles_kbtu_ft2: dict[int, float]
    percentiles_kwh_m2: dict[int, float]
    position: str                               # e.g. "about the 62nd percentile", "below the 5th percentile"
    percentile: Optional[float]                 # interpolated rank, None outside 5..95
    verdict: str                                # "typical", "low", "high", "very_low", "very_high"


@dataclass(frozen=True)
class EuiBenchmark:
    status: str                                 # "checked" or "not_checked"
    reason: str = ""
    building_type: Optional[str] = None
    survey: Optional[str] = None
    source: Optional[str] = None
    cut: dict = field(default_factory=dict)     # survey keys actually used
    cut_note: str = ""                          # how the cut differs from the building, if it does
    n: int = 0                                  # sampled buildings in the cut
    fuel: Optional[str] = None                  # the building's fuel group: "electric" or "gas"
    floor_area_m2: Optional[float] = None
    eui_kwh_m2: Optional[float] = None
    eui_kbtu_ft2: Optional[float] = None
    eui_range_kwh_m2: Optional[tuple[float, float]] = None   # from the low and high of the baseline
    bands: list[Band] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=1)
def _rows() -> tuple[dict, ...]:
    with TABLE.open(newline="") as f:
        return tuple(csv.DictReader(f))


def _index() -> dict[tuple, dict]:
    return {(r["survey"], r["building_type"], r["climate"], r["fuel"], r["size"]): r for r in _rows()}


def normalise_building_type(value: Optional[str]) -> Optional[str]:
    """Map the contract's ``PropertySummary.use_type`` (and plain words) to a benchmark type."""
    if not value:
        return None
    v = value.strip().lower().replace("-", "_").replace(" ", "_")
    if v in ("single_family", "house", "home", "single_family_detached", "single_family_attached", "townhouse"):
        return "single_family"
    if v in ("multifamily", "multifamily_unit", "multi_family", "apartment", "condo"):
        return "multifamily"
    if v == "office":
        return "office"
    return None


def _zone(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    c = code.strip().upper().replace("ZONE", "").replace(" ", "")
    return c if c[:1] in "12345678" else None


def _size(sqft: Optional[float], classes) -> Optional[str]:
    if sqft is None or sqft <= 0:
        return None
    return next(label for lo, hi, label in classes if lo <= sqft < hi)


def _candidates(building_type: str, zone: str, fuel: str, size: Optional[str]):
    """Cuts in the order they are tried (BEN-02). Each: (keys, note)."""
    if building_type == "office":
        survey, climate, digit = "CBECS2018", CBECS_GROUP.get(zone[0]), None
    else:
        survey, climate, digit = "RECS2020", zone, f"digit:{zone[0]}"
    out = []
    climates = [(climate, "")] + ([(digit, f"climate zone {zone[0]} (all of {zone[0]}A/B/C) instead of {zone}")]
                                  if digit else [])
    climates.append(("*", "national instead of the climate zone"))
    for fuel_key, fuel_note in ((fuel, ""), ("*", "all fuel groups instead of the building's")):
        for clim, clim_note in climates:
            for size_key, size_note in (((size, ""),) if size else ()) + (("*", "all sizes"),):
                notes = [n for n in (clim_note, fuel_note, size_note if size else "") if n]
                out.append(((survey, building_type, clim, fuel_key, size_key), "; ".join(notes)))
    return out


def _band(quantity: str, model_kbtu: float, row: dict) -> Band:
    pct = {q: float(row[f"{quantity}_p{q}"]) for q in QUANTILES}
    xs = [pct[q] for q in QUANTILES]
    if model_kbtu < xs[0]:
        position, rank = "below the 5th percentile", None
    elif model_kbtu > xs[-1]:
        position, rank = "above the 95th percentile", None
    else:
        rank = None
        for (q0, x0), (q1, x1) in zip(zip(QUANTILES, xs), zip(QUANTILES[1:], xs[1:])):
            if x0 <= model_kbtu <= x1:
                rank = q0 + (q1 - q0) * ((model_kbtu - x0) / (x1 - x0) if x1 > x0 else 0.5)
                break
        position = f"about the {_ordinal(round(rank))} percentile"
    if model_kbtu < pct[WARN_LOW]:
        verdict = "very_low" if model_kbtu < pct[5] else "low"
    elif model_kbtu > pct[WARN_HIGH]:
        verdict = "very_high" if model_kbtu > pct[95] else "high"
    else:
        verdict = "typical"
    return Band(quantity, round(model_kbtu, 2), round(model_kbtu / KWH_M2_TO_KBTU_FT2, 1),
                pct, {q: round(v / KWH_M2_TO_KBTU_FT2, 1) for q, v in pct.items()},
                position, None if rank is None else round(rank, 1), verdict)


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


_LABEL = {"total": "Site energy use intensity", "electricity": "Electricity use intensity",
          "gas": "Gas use intensity"}
_WHO = {"single_family": "single-family homes", "multifamily": "apartments", "office": "offices"}


def benchmark_eui(electricity_kwh: float, gas_kwh: float, floor_area_m2: Optional[float],
                  building_type: Optional[str], climate_zone: Optional[str], *,
                  building_area_m2: Optional[float] = None,
                  electricity_range_kwh: Optional[tuple[float, float]] = None,
                  gas_range_kwh: Optional[tuple[float, float]] = None) -> EuiBenchmark:
    """BEN-01 to BEN-03. Place the modelled annual site energy in the survey distribution.

    ``floor_area_m2`` is the conditioned floor area the baseline covers. ``building_area_m2`` is
    the gross area of the whole building (offices: CoStar), used only to pick the CBECS size
    class; for homes the modelled area picks the RECS size class. ``climate_zone`` is the IECC
    zone, e.g. "3B". Any missing input returns ``status="not_checked"`` with the reason.
    """
    btype = normalise_building_type(building_type)
    zone = _zone(climate_zone)
    missing = []
    if btype is None:
        missing.append(f"building type {building_type!r} has no survey benchmark (single-family, "
                       "multifamily and office do)")
    if zone is None:
        missing.append("no climate zone")
    if not floor_area_m2 or floor_area_m2 <= 0:
        missing.append("no conditioned floor area")
    if electricity_kwh is None or electricity_kwh < 0 or (gas_kwh or 0) < 0:
        missing.append("no annual energy")
    if missing:
        reason = "; ".join(missing)
        return EuiBenchmark(status="not_checked", reason=reason, building_type=btype,
                            warnings=[f"Energy use was not benchmarked against comparable buildings: {reason}."])

    gas_kwh = gas_kwh or 0.0
    fuel = "gas" if gas_kwh > 0 else "electric"
    area_ft2 = floor_area_m2 * M2_TO_FT2
    if btype == "office":
        size = _size(building_area_m2 * M2_TO_FT2 if building_area_m2 else None, OFFICE_SIZE)
    else:
        size = _size(area_ft2, HOME_SIZE)
    index = _index()
    row, note = None, ""
    for keys, n in _candidates(btype, zone, fuel, size):
        r = index.get(keys)
        if r is not None and int(r["n"]) >= N_MIN:
            row, note = r, n
            break
    if row is None:                                   # cannot happen with the shipped table
        return EuiBenchmark(status="not_checked", reason="no survey cut with enough buildings",
                            building_type=btype, warnings=["Energy use was not benchmarked: no survey cut "
                                                           "with enough buildings."])

    total_kwh = electricity_kwh + gas_kwh
    eui = total_kwh / floor_area_m2
    to_kbtu = KWH_TO_KBTU / area_ft2
    bands = [_band("total", total_kwh * to_kbtu, row)]
    if row["fuel"] == "gas":                          # an all-electric cut: electricity is the total
        bands.append(_band("electricity", electricity_kwh * to_kbtu, row))
        bands.append(_band("gas", gas_kwh * to_kbtu, row))
    rng = None
    if electricity_range_kwh and gas_range_kwh:
        rng = (round((electricity_range_kwh[0] + gas_range_kwh[0]) / floor_area_m2, 1),
               round((electricity_range_kwh[1] + gas_range_kwh[1]) / floor_area_m2, 1))

    survey = row["survey"]
    cut = {"climate": row["climate"], "fuel": row["fuel"], "size": row["size"]}
    peers = _peer_words(btype, row)
    cut_note = (f" Compared with {note}, because the closer cut has fewer than {N_MIN} surveyed buildings."
                if note else "")
    warnings = []
    for b in bands:
        if b.verdict == "typical":
            continue
        lo, hi = b.percentiles_kwh_m2[WARN_LOW], b.percentiles_kwh_m2[WARN_HIGH]
        side = "below" if b.verdict.endswith("low") else "above"
        hint = _HINTS.get((btype, b.quantity, side)) or _HINTS[(b.quantity, side)]
        inside = ""
        if rng and b.quantity == "total" and rng[0] <= hi and rng[1] >= lo:
            inside = f" The model's own range ({rng[0]:.0f} to {rng[1]:.0f} kWh/m2) reaches into that band."
        warnings.append(
            f"{_LABEL[b.quantity]} of {b.model_kwh_m2:.0f} kWh/m2 a year ({b.model_kbtu_ft2:.1f} kBtu/ft2) is "
            f"{b.position} of {peers} ({survey}); 80 percent of them use {lo:.0f} to {hi:.0f} kWh/m2. "
            f"Check the model before relying on it: {hint}.{inside}{cut_note}")
    return EuiBenchmark(
        status="checked", building_type=btype, survey=survey, source=SOURCES[survey], cut=cut,
        cut_note=cut_note.strip(), n=int(row["n"]), fuel=fuel, floor_area_m2=floor_area_m2,
        eui_kwh_m2=round(eui, 1), eui_kbtu_ft2=round(eui * KWH_M2_TO_KBTU_FT2, 2),
        eui_range_kwh_m2=rng, bands=bands, warnings=warnings)


_HINTS = {
    ("total", "below"): "floor area too large, or an end use missing or too small",
    ("total", "above"): "floor area too small, or heating, cooling or plug loads too large",
    ("electricity", "below"): "lighting, plug or cooling electricity may be too small",
    ("electricity", "above"): "cooling, lighting or plug electricity may be too large",
    ("gas", "below"): "gas heating or water heating may be too small",
    ("gas", "above"): "gas heating or water heating may be too large, or the furnace efficiency too low",
    # An office's modelled gas is a lower bound by construction, not a fault to look for: one zone
    # per unit (physics 02, 5R1C), so the heat of the core, lights and equipment offsets the
    # perimeter's heat loss; no office water heating (DHW-02 covers homes); and a suite in the
    # middle of a building has no roof or ground floor, unlike the whole buildings CBECS surveys.
    ("office", "gas", "below"): ("this office's gas is a lower bound. The model treats the space as one "
                                 "zone, so the heat of the core, the lights and the equipment offsets the "
                                 "perimeter's heat loss; it does not model office water heating; and a "
                                 "suite with no roof or ground floor loses less heat than the whole "
                                 "buildings surveyed. Gas savings in the plan are understated, and the "
                                 "utility bills would calibrate it"),
}


def _peer_words(btype: str, row: dict) -> str:
    fuel = {"gas": "gas-using ", "electric": "all-electric ", "*": ""}[row["fuel"]]
    words = fuel + _WHO[btype]
    if row["size"] != "*":
        words += f" of {SIZE_WORDS[row['size']]} ft2"
    clim = row["climate"]
    if clim == "*":
        words += " nationally"
    elif clim.startswith("digit:"):
        words += f" in climate zone {clim[6:]}"
    elif btype == "office":
        words += f" in the CBECS '{clim.replace('_', ' ')}' climate group"
    else:
        words += f" in climate zone {clim}"
    return words
