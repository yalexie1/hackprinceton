"""A10: the assumption registry (SPEC 5.1 to 5.3; physics 02 section 8).

Pure functions. No network, no file access, no imports from sibling subfolders.

Pipeline used by `build_registry`:

1. facts: CoStar fields (year built with its event as evidence, storeys, gross building area,
   office occupancy from tenancies), Vexcel attributes, the observed assumptions handed in
   (vision), and the overrides (user);
2. vintage defaults by era, climate zone and building type, chosen using the merged facts
   (for example the year built, the roof material, the window type read by vision);
3. one merge by source strength: user > measured > costar > vexcel > vision >
   published_default > vintage_default;
4. `Systems` from the merged assumptions, and the feasibility flags (`unknown` until a cue).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Iterable, Literal, Mapping, Optional, Sequence, Union, get_args

from backend.schema import (
    Assumption,
    BuildingModel,
    EvidenceRef,
    Flag,
    PropertyBundle,
    Ranged,
    Source,
    Systems,
)

from . import tables as T

BuildingType = Literal["home", "office"]
OverrideValue = Union[float, int, str, bool]

SOURCE_ORDER: tuple[str, ...] = get_args(Source)   # strongest first, as in SPEC 5.1
SOURCE_RANK: dict[str, int] = {s: i for i, s in enumerate(SOURCE_ORDER)}
# Sources that count as data about this building (Systems.occupants is set only from these).
_BUILDING_SPECIFIC = {"user", "measured", "costar", "vexcel", "vision"}

DEFAULT_CONFIDENCE: dict[str, float] = {
    "user": 1.0, "measured": 0.95, "costar": 0.9, "vexcel": 0.8, "vision": 0.5,
    "published_default": 0.5, "vintage_default": 0.4,
}
# Confidence multipliers for a vintage default whose year is uncertain (judgment).
_CONF_YEAR_UNKNOWN = 0.5
_CONF_YEAR_WIDENED = 0.75

_KW_PER_TON = 3.51685
_CONSTRUCTION_COMPLETE = {"constructioncomplete", "construction_complete", "construction complete", "completed"}

_UNITS: dict[str, str] = {
    "building.year_built": "year", "building.stories": "storeys", "building.gross_area_m2": "m2",
    "building.floor_plate_m2": "m2", "occupancy.count": "people", "wall.u_value": "W/m2K",
    "roof.u_value": "W/m2K", "window.u_value": "W/m2K", "window.shgc": "-", "roof.absorptance": "-",
    "infiltration.ach50": "1/h at 50 Pa", "infiltration.leakage_75pa": "L/s.m2 at 75 Pa",
    "hvac.distribution_efficiency": "-", "hvac.heating_efficiency": "-", "dhw.uef": "-",
    "setpoint.heating": "C", "setpoint.cooling": "C", "lighting.lpd": "W/m2", "plug.ppd": "W/m2",
    "ventilation.outdoor_air_m3_s": "m3/s", "hvac.cooling_capacity_kw": "kW",
    "hvac.rtu_capacity_tons": "ton", "hvac.install_year": "year",
}

_HVAC_TYPES = set(get_args(Systems.model_fields["hvac_type"].annotation))
_FUELS = set(get_args(Systems.model_fields["heating_fuel"].annotation))
_DHW_TYPES = set(get_args(Systems.model_fields["dhw_type"].annotation))
_DHW_FUELS = set(get_args(Systems.model_fields["dhw_fuel"].annotation))
_SCHEDULES = {"home", "office", "office_vacant"}
_DUCT_LOCATIONS = {"conditioned", "attic", "garage", "crawlspace", "none", "unknown"}
_DHW_LOCATIONS = {"conditioned", "garage", "outdoor", "unknown"}
_COOLING_METRICS = {"SEER", "SEER2", "EER", "EER2", "IEER"}

FEASIBILITY_KEYS = ("electrical.service", "roof.structure")


# ---------------------------------------------------------------- helpers

def _r(x: float) -> float:
    return round(float(x), 4)


def _ranged(low: float, expected: float, high: float, unit: str) -> Ranged:
    lo, ex, hi = _r(low), _r(expected), _r(high)
    return Ranged(low=min(lo, ex), expected=ex, high=max(hi, ex), unit=unit)


def _point(value: float, unit: str) -> Ranged:
    return _ranged(value, value, value, unit)


def _spread(value: float, frac: float, unit: str) -> Ranged:
    return _ranged(value * (1 - frac), value, value * (1 + frac), unit)


def _a(key: str, label: str, value, source: str, confidence: float,
       evidence: Sequence[EvidenceRef] = (), user_editable: bool = True) -> Assumption:
    return Assumption(key=key, label=label, value=value, source=source,
                      confidence=max(0.0, min(1.0, round(confidence, 3))),
                      evidence=list(evidence), user_editable=user_editable)


def _table_ev(ref: str, note: str) -> EvidenceRef:
    return EvidenceRef(kind="default_table", ref=ref, note=note)


def is_stronger(a: str, b: str) -> bool:
    """True if source `a` is strictly stronger than source `b` (SPEC 5.1)."""
    return SOURCE_RANK[a] < SOURCE_RANK[b]


# ---------------------------------------------------------------- merge by source strength

def merge_assumptions(*groups: Iterable[Assumption]) -> list[Assumption]:
    """One assumption per key: the strongest source wins (SPEC 5.1).

    Between equal sources the later one wins, so a re-reading replaces an earlier one.
    The result is ordered by source strength, then by the order in which each key first
    appeared, like the `model#/assumptions` fixtures.
    """
    best: dict[str, Assumption] = {}
    first_seen: dict[str, int] = {}
    n = 0
    for group in groups:
        for a in group:
            first_seen.setdefault(a.key, n)
            n += 1
            cur = best.get(a.key)
            if cur is None or SOURCE_RANK[a.source] <= SOURCE_RANK[cur.source]:
                best[a.key] = a
    return sorted(best.values(), key=lambda a: (SOURCE_RANK[a.source], first_seen[a.key]))


def _by_key(assumptions: Iterable[Assumption]) -> dict[str, Assumption]:
    return {a.key: a for a in merge_assumptions(assumptions)}


def _num(a: Optional[Assumption]) -> Optional[Ranged]:
    return a.value if a is not None and isinstance(a.value, Ranged) else None


def _txt(a: Optional[Assumption]) -> Optional[str]:
    return a.value if a is not None and isinstance(a.value, str) else None


# ---------------------------------------------------------------- building context

def building_type(bundle: PropertyBundle) -> BuildingType:
    """Homes and apartment units use the home tables; offices and other commercial use the office tables."""
    use = bundle.summary.use_type
    if use in ("single_family", "multifamily_unit"):
        return "home"
    if use == "office":
        return "office"
    return "office" if bundle.summary.segment == "commercial" else "home"


def climate_zone(bundle: PropertyBundle) -> tuple[Optional[str], str]:
    """IECC zone used by the tables ("2A" or "3B"), and how it was found."""
    z = (bundle.climate.climate_zone or "").upper().replace("-CA", "").strip()
    for c in T.CLIMATES:
        if z.startswith(c):
            return c, f"climate zone {c}"
    state = bundle.summary.state
    if state == "TX":
        return "2A", "climate zone 2A taken from the state (TX)"
    if state == "CA":
        return "3B", "climate zone 3B taken from the state (CA)"
    return None, "climate zone unknown: both zones spanned"


def scanned_floor_area_m2(bundle: PropertyBundle) -> float:
    """Sum of the scanned room floor areas (the suite or home), never a CoStar area."""
    return float(sum(r.area_m2 for r in bundle.matterport.rooms if r.area_m2))


def count_bedrooms(bundle: PropertyBundle) -> int:
    """Bedrooms counted from Matterport room labels (DHW-02)."""
    return sum(1 for r in bundle.matterport.rooms if r.label and "bedroom" in r.label.lower())


def _gas_at_site(bundle: PropertyBundle) -> Optional[bool]:
    """True when the tariff carries a gas price. None when it does not: a missing price means
    the price is unknown, not that the site has no gas, so the caller keeps its default."""
    return True if bundle.tariff.gas_usd_per_kwh is not None else None


@dataclass(frozen=True)
class YearInfo:
    expected: Optional[int]
    low: Optional[int]
    high: Optional[int]
    widen: bool
    note: str


def _event_is_complete(event: Optional[str]) -> bool:
    return event is not None and event.strip().lower() in _CONSTRUCTION_COMPLETE


def year_info(bundle: PropertyBundle, facts: Mapping[str, Assumption]) -> YearInfo:
    """Vintage for the default tables, from the strongest `building.year_built` (physics 02 section 8)."""
    a = facts.get("building.year_built")
    v = _num(a)
    if v is None:
        return YearInfo(None, None, None, False, "year built unknown: low and high span every vintage row")
    widen = False
    note = f"year {round(v.expected)} ({a.source})"
    if a.source == "costar" and bundle.costar is not None:
        ev = bundle.costar.year_built_event
        if ev is not None and not _event_is_complete(ev):
            widen = True
            note += f", from the {ev} event: widened to the adjacent vintage rows"
    return YearInfo(round(v.expected), round(v.low), round(v.high), widen, note)


@dataclass(frozen=True)
class Selection:
    low: float
    expected: float
    high: float
    row_note: str
    ref: str
    confidence_factor: float


def select_rows(rows: Sequence[T.Row], yi: YearInfo) -> Selection:
    """Pick the vintage row; span rows when the year is uncertain or comes from a non-completion event."""
    if yi.expected is None:
        exp = statistics.median_low([r.expected for r in rows])
        return Selection(min(r.low for r in rows), exp, max(r.high for r in rows),
                         "all vintages", rows[0].ref, _CONF_YEAR_UNKNOWN)
    idx = next((i for i, r in enumerate(rows) if r.contains(yi.expected)), None)
    if idx is None:   # tables cover every year; defensive
        idx = 0 if (rows[0].start is not None and yi.expected < rows[0].start) else len(rows) - 1
    used = {i for i, r in enumerate(rows)
            if (r.start is None or r.start <= yi.high) and (r.end is None or r.end >= yi.low)}
    used.add(idx)
    factor = 1.0
    if yi.widen:
        used |= {max(idx - 1, 0), min(idx + 1, len(rows) - 1)}
        factor = _CONF_YEAR_WIDENED
    elif len(used) > 1:
        factor = _CONF_YEAR_WIDENED
    sel = [rows[i] for i in sorted(used)]
    return Selection(min(r.low for r in sel), rows[idx].expected, max(r.high for r in sel),
                     rows[idx].note, rows[idx].ref, factor)


def _climate_rows(table: Mapping[str, Sequence[T.Row]], climate: Optional[str]) -> Sequence[T.Row]:
    if climate in table:
        return table[climate]
    a, b = table["2A"], table["3B"]
    return [T.Row(x.start, x.end, min(x.low, y.low), (x.expected + y.expected) / 2, max(x.high, y.high),
                  x.ref, f"{x.note}; both climate zones") for x, y in zip(a, b)]


def _office_rows(first, second, s11_type, first_name: str, label: str,
                 avoid_no_requirement: bool = False) -> dict[str, list[T.Row]]:
    """DEF-11 element with two construction types: expected is the S11 type for the vintage, low
    and high span the other type. The Los Angeles 'no requirement' mass wall is a high bound only."""
    out: dict[str, list[T.Row]] = {}
    for c in T.CLIMATES:
        rows = []
        for (s, e, va), (_, _, vb) in zip(first, second):
            a, b = va[c][0], vb[c][0]
            t = next(tp for ts, te, tp in s11_type
                     if (ts is None or (s is not None and s >= ts)) and (te is None or s is None or s <= te))
            exp = a if t == first_name else b
            if avoid_no_requirement and exp == T.NO_REQUIREMENT_U:
                exp = a
            span = "before 1980" if s is None else (f"{s} to {e}" if e else f"after {s - 1}")
            rows.append(T.Row(s, e, min(a, b), exp, max(a, b), "DEF-11", f"{label}, {span}"))
        out[c] = rows
    return out


def _single_rows(table, label: str) -> dict[str, list[T.Row]]:
    out: dict[str, list[T.Row]] = {}
    for c in T.CLIMATES:
        rows = []
        for s, e, v in table:
            span = "before 1980" if s is None else (f"{s} to {e}" if e else f"after {s - 1}")
            rows.append(T.Row(s, e, v[c][0], v[c][0], v[c][0], "DEF-11", f"{label}, {span}"))
        out[c] = rows
    return out


# ---------------------------------------------------------------- facts: CoStar, Vexcel, overrides

def _tenant_occupants(bundle: PropertyBundle, area_m2: float):
    """Occupants of the scanned suite from CoStar tenancies, or None (SPEC 5.1, office occupancy)."""
    occ = bundle.costar.occupancy if bundle.costar else None
    if occ is None or not occ.tenancies:
        return None
    current = [t for t in occ.tenancies if t.move_out is None]
    if not current:
        return None
    # 1. the current tenancy whose area matches the scanned suite
    if area_m2 > 0:
        matches = [t for t in current if t.employees and t.area_m2
                   and max(t.area_m2, area_m2) / min(t.area_m2, area_m2) <= T.TENANT_AREA_MATCH_RATIO]
        if matches:
            t = min(matches, key=lambda t: abs(t.area_m2 - area_m2))
            ev = EvidenceRef(kind="costar_field", ref="CostarData.occupancy.tenancies",
                             note=f"employee count of the current tenant whose area ({t.area_m2:g} m2) "
                                  f"matches the scanned {area_m2:.1f} m2"
                                  + (f", floor {t.floor}" if t.floor else ""))
            return _spread(t.employees, T.TENANT_OCCUPANT_SPREAD, "people"), 0.8, ev
    # 2. building tenant density applied to the scanned area
    known = [t for t in current if t.employees and t.area_m2]
    if area_m2 > 0 and known:
        density = sum(t.employees for t in known) / sum(t.area_m2 for t in known)
        ev = EvidenceRef(kind="costar_field", ref="CostarData.occupancy.tenancies",
                         note=f"no tenancy matches the suite; current tenants' density {density:.4f} "
                              f"people/m2 applied to the scanned {area_m2:.1f} m2")
        return _spread(density * area_m2, T.TENANT_DENSITY_SPREAD, "people"), 0.6, ev
    # 3. a single current tenancy with employees and no area to compare
    with_emp = [t for t in current if t.employees]
    if len(with_emp) == 1:
        ev = EvidenceRef(kind="costar_field", ref="CostarData.occupancy.tenancies",
                         note="the only current tenant with an employee count")
        return _spread(with_emp[0].employees, T.TENANT_DENSITY_SPREAD, "people"), 0.5, ev
    return None


def costar_assumptions(bundle: PropertyBundle) -> list[Assumption]:
    """Assumptions with source `costar`. Never reads `rentable_area_m2` (SPEC 5.1)."""
    c = bundle.costar
    if c is None:
        return []
    out: list[Assumption] = []
    if c.year_built is not None:
        ev = c.year_built_event
        complete = _event_is_complete(ev)
        note = (f"from the {ev} event" if ev else "construction event not recorded") + \
            "; normalised field; kit field names are in the kit's models/ folder"
        evidence = [EvidenceRef(kind="costar_field", ref="CostarData.year_built", note=note)]
        if ev:
            evidence.append(EvidenceRef(kind="costar_field", ref="CostarData.year_built_event", note=ev))
        conf = 0.9 if (complete or ev is None) else 0.6
        out.append(_a("building.year_built", "Year built", _point(c.year_built, "year"), "costar", conf, evidence))
    if c.stories:
        out.append(_a("building.stories", "Storeys above grade", _point(c.stories, "storeys"), "costar", 0.9,
                      [EvidenceRef(kind="costar_field", ref="CostarData.stories")]))
    if c.building_area_m2:
        out.append(_a("building.gross_area_m2", "Gross building area", _point(c.building_area_m2, "m2"),
                      "costar", 0.9,
                      [EvidenceRef(kind="costar_field", ref="CostarData.building_area_m2",
                                   note="gross building area, used for the envelope and whole-building "
                                        "scaling; the rentable area is never used")]))
        if c.stories:
            out.append(_a("building.floor_plate_m2", "Floor plate (gross area / storeys)",
                          _point(c.building_area_m2 / c.stories, "m2"), "costar", 0.6,
                          [EvidenceRef(kind="costar_field", ref="CostarData.building_area_m2",
                                       note=f"gross building area / {c.stories} storeys")]))
    if c.building_class:
        out.append(_a("building.class", "Building class", c.building_class, "costar", 0.9,
                      [EvidenceRef(kind="costar_field", ref="CostarData.building_class")]))
    if building_type(bundle) == "office":
        t = _tenant_occupants(bundle, scanned_floor_area_m2(bundle))
        if t is not None:
            val, conf, ev = t
            out.append(_a("occupancy.count", "People working in the suite", val, "costar", conf, [ev]))
        elif _vacant(bundle):
            out.append(_a("occupancy.schedule", "Occupancy schedule", "office_vacant", "costar",
                          T.VACANT_CONFIDENCE,
                          [EvidenceRef(kind="costar_field", ref="CostarData.occupancy.tenancies",
                                       note="tenancy records exist but none is current: the building is "
                                            "modelled vacant (DEF-09 'other' row every day); savings then "
                                            "depend on who moves in")]))
    return out


def _vacant(bundle: PropertyBundle) -> bool:
    """SPEC 5.1: an office with tenancy records and no sitting tenant is vacant.

    D10 returns `OccupancyData(tenancies=[])` when a property has records but none is
    current, and `occupancy=None` when it has no records at all; only the first is
    evidence of vacancy. Ended tenancies passed with a `move_out` count the same way.
    """
    occ = bundle.costar.occupancy if bundle.costar else None
    return occ is not None and not any(t.move_out is None for t in occ.tenancies)


def _vexcel_attrs(bundle: PropertyBundle) -> dict:
    v = bundle.vexcel
    if v is None:
        return {}
    attrs = dict(v.attributes)
    prim = next((s for s in v.structures if s.primary), v.structures[0] if v.structures else None)
    if prim is not None:
        attrs.update(prim.attributes)
    return attrs


def vexcel_assumptions(bundle: PropertyBundle) -> list[Assumption]:
    """Roof material, shape and existing solar; rooftop units on an office (HVAC-00)."""
    attrs = _vexcel_attrs(bundle)
    out: list[Assumption] = []

    def ev(k):
        return [EvidenceRef(kind="vexcel_attr", ref=k)]

    k = "roof-characteristics.material.class"
    if isinstance(attrs.get(k), str):
        out.append(_a("roof.material", "Roof material", attrs[k], "vexcel", 0.8, ev(k)))
    k = "roof-characteristics.shape.value"
    if isinstance(attrs.get(k), str):
        out.append(_a("roof.shape", "Roof shape", attrs[k], "vexcel", 0.9, ev(k)))
    k = "roof-objects.solar.value"
    if isinstance(attrs.get(k), bool):
        out.append(_a("roof.existing_solar", "Solar panels already on the roof", attrs[k], "vexcel", 0.85, ev(k)))
    k = "roof-objects.ac-unit.count"
    n = attrs.get(k)
    # A count of zero is a detection limit, not proof of absence (HVAC-00), so it sets nothing.
    if building_type(bundle) == "office" and isinstance(n, (int, float)) and not isinstance(n, bool) and n > 0:
        out.append(_a("hvac.system_type", "HVAC system type", "rooftop_unit", "vexcel", 0.7,
                      [EvidenceRef(kind="vexcel_attr", ref=k, note=f"{n:g} as returned")]))
    return out


def _override_value(value: OverrideValue, unit: str):
    if isinstance(value, bool) or isinstance(value, str):
        return value
    return _point(float(value), unit)


def make_assumption(key: str, value: OverrideValue, source: str = "user",
                    existing: Optional[Assumption] = None, confidence: Optional[float] = None) -> Assumption:
    """A new assumption for `key`. A number becomes a collapsed range (low = expected = high)."""
    unit = (existing.value.unit if existing is not None and isinstance(existing.value, Ranged)
            else _UNITS.get(key, ""))
    if source == "user":
        evidence = [EvidenceRef(kind="user", ref=f"overrides.{key}")]
    else:
        evidence = list(existing.evidence) if existing is not None else []
    return _a(key, existing.label if existing is not None else key, _override_value(value, unit), source,
              DEFAULT_CONFIDENCE[source] if confidence is None else confidence, evidence,
              existing.user_editable if existing is not None else True)


def override_assumptions(overrides: Mapping[str, OverrideValue],
                         existing: Mapping[str, Assumption] | None = None) -> list[Assumption]:
    """Overrides as a plain map -> assumptions with source `user` and collapsed ranges."""
    existing = existing or {}
    return [make_assumption(k, v, "user", existing.get(k)) for k, v in overrides.items()]


def set_assumption(assumptions: Sequence[Assumption], key: str, value: OverrideValue,
                   source: str = "user") -> list[Assumption]:
    """Return a new list with `key` set. A number collapses the range to that value.

    The key is replaced whatever the strength of the old source: setting is explicit.
    The input list and its assumptions are not changed.
    """
    out = list(assumptions)
    idx = next((i for i, a in enumerate(out) if a.key == key), None)
    new = make_assumption(key, value, source, out[idx] if idx is not None else None)
    if idx is None:
        out.append(new)
    else:
        out[idx] = new
    return out


# ---------------------------------------------------------------- vintage defaults

def _vd(key, label, sel: Selection, unit: str, base_conf: float, extra: str = "",
        ref: Optional[str] = None) -> Assumption:
    note = sel.row_note + (f"; {extra}" if extra else "")
    return _a(key, label, _ranged(sel.low, sel.expected, sel.high, unit), "vintage_default",
              base_conf * sel.confidence_factor, [_table_ev(ref or sel.ref, note)])


def _fixed(key, label, row: T.Row, unit: str, conf: float, extra: str = "") -> Assumption:
    note = row.note + (f"; {extra}" if extra else "")
    return _a(key, label, _ranged(row.low, row.expected, row.high, unit), "vintage_default",
              0.0 if row.placeholder else conf, [_table_ev(row.ref, note)])


def _home_window_rows(climate: Optional[str]):
    """DEF-03 type rows -> numeric U and SHGC rows."""
    def rows_for(c):
        u_rows, g_rows = [], []
        for tr in T.HOME_WINDOW_TYPES[c]:
            ub, ue, uw = (T.WINDOW_TYPES[t][0] for t in (tr.best, tr.expected, tr.worst))
            gs = [T.WINDOW_TYPES[t][1] for t in (tr.best, tr.expected, tr.worst)]
            span = f"{tr.start or 'before'}-{tr.end or 'later'}"
            u_rows.append(T.Row(tr.start, tr.end, ub, ue, uw, "DEF-03",
                                f"{tr.best} / {tr.expected} / {tr.worst}, {span}"))
            g_rows.append(T.Row(tr.start, tr.end, min(gs), gs[1], max(gs), "DEF-03",
                                f"{tr.best} / {tr.expected} / {tr.worst}, {span}"))
        return u_rows, g_rows
    if climate in T.CLIMATES:
        return rows_for(climate)
    (ua, ga), (ub, gb) = rows_for("2A"), rows_for("3B")
    return (_climate_rows({"2A": ua, "3B": ub}, None), _climate_rows({"2A": ga, "3B": gb}, None))


def _expected_window_type(climate: Optional[str], yi: YearInfo) -> str:
    c = climate if climate in T.CLIMATES else "3B"
    rows = T.HOME_WINDOW_TYPES[c]
    if yi.expected is None:
        return statistics.median_low([r.expected for r in rows])
    return next((r.expected for r in rows if r.contains(yi.expected)), rows[-1].expected)


def _roof_absorptance(material: Optional[str], btype: BuildingType) -> tuple[T.Row, str]:
    key = T.ROOF_MATERIAL_ALIASES.get((material or "").strip().lower().replace("-", "_").replace(" ", "_"))
    if key is not None:
        return T.ROOF_ABSORPTANCE[key], ""
    if btype == "office":
        return T.ROOF_ABSORPTANCE["membrane"], "roof material unknown: unknown commercial roof"
    rows = list(T.ROOF_ABSORPTANCE.values())
    return (T.Row(None, None, min(r.low for r in rows), statistics.median_low([r.expected for r in rows]),
                  max(r.high for r in rows), "DEF-02", "roof material unknown: all materials spanned"),
            "")


def _occupancy_default(bundle: PropertyBundle, btype: BuildingType) -> Optional[Assumption]:
    if btype == "office":
        area = scanned_floor_area_m2(bundle)
        if area <= 0:
            return None
        n = area / T.OFFICE_M2_PER_PERSON
        return _a("occupancy.count", "People working in the suite",
                  _spread(n, T.OCCUPANT_DEFAULT_SPREAD, "people"), "vintage_default", 0.3,
                  [_table_ev("INF-05", f"no CoStar tenancy: scanned {area:.1f} m2 / 18.59 m2 per person "
                                       "(S11 Table 4); plus or minus 30 percent is a judgment")])
    kind = bundle.summary.use_type if bundle.summary.use_type in T.HOME_OCCUPANTS else "single_family"
    a, b = T.HOME_OCCUPANTS[kind]
    nbr = count_bedrooms(bundle)
    n = a * nbr + b
    return _a("occupancy.count", "Number of occupants", _spread(n, T.OCCUPANT_DEFAULT_SPREAD, "people"),
              "vintage_default", 0.3,
              [_table_ev("LGT-03", f"{a} x {nbr} bedrooms + {b} ({kind}); plus or minus 30 percent is a judgment")])


def _cooling_capacity_kw(facts: Mapping[str, Assumption]) -> Optional[float]:
    v = _num(facts.get("hvac.cooling_capacity_kw"))
    if v is not None:
        return v.expected
    v = _num(facts.get("hvac.rtu_capacity_tons"))
    if v is not None:
        return v.expected * _KW_PER_TON
    return None


def vintage_defaults(bundle: PropertyBundle, facts: Iterable[Assumption] = ()) -> list[Assumption]:
    """Defaults by era, climate zone and building type (physics 02 DEF-01 to DEF-11, INF-05, LGT-03).

    `facts` are the stronger assumptions already known; they choose the row (year built, roof
    material, HVAC type, window type, unit capacity) but are not returned.
    """
    f = _by_key(facts)
    btype = building_type(bundle)
    climate, cnote = climate_zone(bundle)
    yi = year_info(bundle, f)
    ctx = f"{cnote}; {yi.note}"
    out: list[Assumption] = []

    mat = _txt(f.get("roof.material"))
    row, extra = _roof_absorptance(mat, btype)
    out.append(_fixed("roof.absorptance", "Roof solar absorptance", row, "-", 0.5, extra))

    hvac_type = _txt(f.get("hvac.system_type"))
    if btype == "home":
        out.append(_vd("wall.u_value", "Exterior wall U-value",
                       select_rows(_climate_rows(T.HOME_WALL_U, climate), yi), "W/m2K", 0.5, ctx))
        out.append(_vd("roof.u_value", "Attic ceiling U-value",
                       select_rows(_climate_rows(T.HOME_ATTIC_U, climate), yi), "W/m2K", 0.4, ctx))
        u_rows, g_rows = _home_window_rows(climate)
        su, sg = select_rows(u_rows, yi), select_rows(g_rows, yi)
        out.append(_a("window.type", "Window type", _expected_window_type(climate, yi), "vintage_default",
                      0.4 * su.confidence_factor, [_table_ev("DEF-03", f"{su.row_note}; {ctx}")]))
        out.append(_vd("window.u_value", "Window U-value", su, "W/m2K", 0.4, ctx))
        out.append(_vd("window.shgc", "Window solar heat gain coefficient", sg, "-", 0.4, ctx))
        out.append(_vd("infiltration.ach50", "Air leakage at 50 Pa",
                       select_rows(_climate_rows(T.HOME_ACH50, climate), yi), "1/h at 50 Pa", 0.4, ctx))
        gas = _gas_at_site(bundle)
        # A missing gas price is unknown, not "no gas": keep the gas furnace default, which is
        # the HVAC-00 case for a home with gas, at a lower confidence (judgment).
        default_type = "central_ac_furnace"
        out.append(_a("hvac.system_type", "HVAC system type", default_type, "vintage_default",
                      0.4 if gas else 0.25,
                      [_table_ev("HVAC-00", "home with gas at the site: split AC with gas furnace" if gas
                                 else "gas at the site unknown (no gas price in the tariff): split AC with "
                                      "gas furnace assumed, at lower confidence")]))
        eff_type = hvac_type if hvac_type in _HVAC_TYPES and hvac_type != "unknown" else default_type
        fuel = "gas" if eff_type == "central_ac_furnace" else "electricity"
        out.append(_a("hvac.heating_fuel", "Heating fuel", fuel, "vintage_default", 0.4,
                      [_table_ev("HVAC-00", f"follows the system type {eff_type}")]))
        out.append(_vd("hvac.cooling_rating", "Air conditioner rating (SEER)",
                       select_rows(T.HOME_SEER, yi), "SEER", 0.4, yi.note))
        if eff_type == "heat_pump":
            out.append(_vd("hvac.heating_rating", "Heat pump rating (HSPF)",
                           select_rows(T.HOME_HSPF, yi), "HSPF", 0.4, yi.note))
        else:
            out.append(_vd("hvac.heating_rating", "Furnace AFUE", select_rows(T.HOME_AFUE, yi), "-", 0.4, yi.note))
        if eff_type in ("central_ac_furnace", "heat_pump"):
            out.append(_fixed("hvac.distribution_efficiency", "Duct distribution efficiency (upper bound)",
                              T.HOME_DSE_OUTSIDE, "-", 0.3))
            out.append(_a("hvac.duct_location", "Duct location", "attic", "vintage_default", 0.3,
                          [_table_ev("DEF-06", "ducted system, ducts assumed outside the conditioned space")]))
        # Same rule as the system type: no gas price is unknown gas, so the gas heater stays.
        dfuel = "gas" if gas or eff_type == "central_ac_furnace" else "electricity"
        out.append(_a("dhw.type", "Water heater type", "storage", "vintage_default", 0.4,
                      [_table_ev("DEF-07", "unknown storage heater")]))
        out.append(_a("dhw.fuel", "Water heater fuel", dfuel, "vintage_default", 0.4 if gas or dfuel != "gas" else 0.25,
                      [_table_ev("DEF-07", "gas at the site" if gas else
                                 "gas at the site unknown (no gas price in the tariff): gas assumed, at lower "
                                 "confidence" if dfuel == "gas" else
                                 f"gas at the site unknown and the system type {eff_type} is electric")]))
        out.append(_fixed("dhw.uef", "Water heater efficiency", T.DHW_UEF[dfuel], "-", 0.4))
        sp = T.SETPOINTS["home"]
        out.append(_a("setpoint.heating", "Heating setpoint", _spread_k(sp["heating"]), "vintage_default", 0.5,
                      [_table_ev("DEF-08", "home, all hours")]))
        out.append(_a("setpoint.cooling", "Cooling setpoint", _spread_k(sp["cooling"]), "vintage_default", 0.5,
                      [_table_ev("DEF-08", "home, all hours")]))
        out.append(_fixed("lighting.lpd", "Lighting power density", T.HOME_LPD_PLACEHOLDER, "W/m2", 0.0))
        out.append(_fixed("plug.ppd", "Plug power density", T.HOME_PPD_PLACEHOLDER, "W/m2", 0.0))
    else:
        walls = _office_rows(T.OFFICE_WALL_STEEL, T.OFFICE_WALL_MASS, T.OFFICE_WALL_S11_TYPE, "steel",
                             "office wall, S11 type expected, the other type as the bound",
                             avoid_no_requirement=True)
        out.append(_vd("wall.u_value", "Exterior wall U-value", select_rows(_climate_rows(walls, climate), yi),
                       "W/m2K", 0.4, ctx))
        roofs = _office_rows(T.OFFICE_ROOF_ABOVE_DECK, T.OFFICE_ROOF_ATTIC, T.OFFICE_ROOF_S11_TYPE,
                             "above_deck", "office roof, S11 type expected, the other type as the bound")
        out.append(_vd("roof.u_value", "Roof U-value", select_rows(_climate_rows(roofs, climate), yi),
                       "W/m2K", 0.4, ctx))
        out.append(_vd("window.u_value", "Window U-value",
                       select_rows(_climate_rows(_single_rows(T.OFFICE_WINDOW_U, "office window U"), climate), yi),
                       "W/m2K", 0.4, ctx))
        out.append(_vd("window.shgc", "Window solar heat gain coefficient",
                       select_rows(_climate_rows(_single_rows(T.OFFICE_WINDOW_SHGC, "office window SHGC"),
                                                 climate), yi), "-", 0.4, ctx))
        out.append(_vd("infiltration.leakage_75pa", "Envelope leakage at 75 Pa",
                       select_rows(T.OFFICE_LEAKAGE_75PA, yi), "L/s.m2 at 75 Pa", 0.4, yi.note))
        out.append(_a("hvac.system_type", "HVAC system type", "unknown", "vintage_default", 0.3,
                      [_table_ev("HVAC-00", "no packaged unit confirmed: type unknown, efficiency from the "
                                            "office default (packaged unit with gas furnace)")]))
        out.append(_a("hvac.heating_fuel", "Heating fuel", "gas", "vintage_default", 0.4,
                      [_table_ev("HVAC-00", "office default: gas furnace")]))
        out.append(_office_cooling(yi, _cooling_capacity_kw(f), hvac_type))
        out.append(_fixed("hvac.heating_efficiency", "Heating efficiency", T.OFFICE_HEATING_EFFICIENCY, "-", 0.4))
        out.append(_a("dhw.type", "Water heater type", "storage", "vintage_default", 0.4,
                      [_table_ev("DEF-07", "office: hot water is a minor end use and is not modelled (DHW-02)")]))
        out.append(_a("dhw.fuel", "Water heater fuel", "electricity", "vintage_default", 0.4,
                      [_table_ev("DEF-07", "office: electric storage assumed; not modelled (DHW-02)")]))
        out.append(_fixed("dhw.uef", "Water heater efficiency", T.DHW_UEF["electricity"], "-", 0.4))
        sp = T.SETPOINTS["office"]
        out.append(_a("setpoint.heating", "Heating setpoint (occupied)", _spread_k(sp["heating"]),
                      "vintage_default", 0.5, [_table_ev("DEF-08", "office, occupied hours")]))
        out.append(_a("setpoint.cooling", "Cooling setpoint (occupied)", _spread_k(sp["cooling"]),
                      "vintage_default", 0.5, [_table_ev("DEF-08", "office, occupied hours")]))
        out.append(_vd("lighting.lpd", "Lighting power density", select_rows(T.OFFICE_LPD, yi), "W/m2", 0.5,
                       yi.note))
        out.append(_vd("plug.ppd", "Plug power density", select_rows(T.OFFICE_PPD, yi), "W/m2", 0.5))

    occ = _occupancy_default(bundle, btype)
    if occ is not None:
        out.append(occ)
    out.extend(derived_assumptions({**{a.key: a for a in out}, **f}, btype))
    return out


def _spread_k(v: float) -> Ranged:
    return _ranged(v - T.SETPOINT_RANGE_K, v, v + T.SETPOINT_RANGE_K, "C")


def _office_cooling(yi: YearInfo, capacity_kw: Optional[float], hvac_type: Optional[str]) -> Assumption:
    rows = T.OFFICE_COOLING
    large = capacity_kw is not None and capacity_kw >= T.OFFICE_LARGE_UNIT_KW
    if yi.expected is None:
        cand = rows
        r = rows[len(rows) // 2]
        factor = _CONF_YEAR_UNKNOWN
    else:
        r = next((x for x in rows if x.contains(yi.expected)), rows[-1])
        cand = [r]
        factor = _CONF_YEAR_WIDENED if yi.widen else 1.0
    value, metric = r.large if large else r.small
    # Only rows with the same metric can share one range.
    same = [(x.large if large else x.small)[0] for x in cand if (x.large if large else x.small)[1] == metric]
    minus, plus = T.OFFICE_COOLING_MINUS, T.OFFICE_COOLING_PLUS
    note = r.note + ("; 19 kW or more: EER row" if large and metric == "EER" else "")
    if hvac_type == "central_plant":
        minus = plus = 0.25
        note += "; central plant: no plant model, range widened to -25 / +25 percent (HVAC-00 rule 3)"
    else:
        note += "; minus 10, plus 15 percent"
    val = _ranged(min(same) * (1 - minus), value, max(same) * (1 + plus), metric)
    return _a("hvac.cooling_rating", f"Cooling rating ({metric})", val, "vintage_default", 0.3 * factor,
              [_table_ev("DEF-05", note)])


def derived_assumptions(merged: Mapping[str, Assumption], btype: BuildingType) -> list[Assumption]:
    """Assumptions computed from other assumptions; each takes the source of what it was derived from."""
    out: list[Assumption] = []
    wt = merged.get("window.type")
    t = _txt(wt)
    if wt is not None and wt.source != "vintage_default" and t in T.WINDOW_TYPES:
        worst = T.WINDOW_SAME_PANES_WORST[t]
        u, g = T.WINDOW_TYPES[t][:2]
        uw, gw = T.WINDOW_TYPES[worst][:2]
        ev = [_table_ev("DEF-03", f"properties of {t} read as {wt.source}; high is {worst}")]
        out.append(_a("window.u_value", "Window U-value", _ranged(u, u, max(u, uw), "W/m2K"),
                      wt.source, wt.confidence, ev))
        out.append(_a("window.shgc", "Window solar heat gain coefficient",
                      _ranged(min(g, gw), g, max(g, gw), "-"), wt.source, wt.confidence, ev))
    if btype == "office":
        occ = merged.get("occupancy.count")
        n = _num(occ)
        if n is not None:
            q = T.OUTDOOR_AIR_M3_S_PER_PERSON
            out.append(_a("ventilation.outdoor_air_m3_s", "Design outdoor air flow",
                          _ranged(n.low * q, n.expected * q, n.high * q, "m3/s"), occ.source, occ.confidence,
                          [_table_ev("INF-05", f"occupants ({occ.source}) x 0.00944 m3/s per person")]))
    return out


# ---------------------------------------------------------------- the registry

def build_assumptions(bundle: PropertyBundle, observed: Iterable[Assumption] = (),
                      overrides: Mapping[str, OverrideValue] | None = None) -> list[Assumption]:
    """Every assumption for the model, merged by source strength (SPEC 5.1)."""
    overrides = overrides or {}
    base = list(costar_assumptions(bundle)) + list(vexcel_assumptions(bundle)) + list(observed)
    pre = _by_key(base)
    facts = merge_assumptions(base, override_assumptions(overrides, pre))
    defaults = vintage_defaults(bundle, facts)
    # Overrides are re-made against the merged set so a number override keeps the key's unit.
    merged_wo = _by_key(defaults + facts)
    users = override_assumptions(overrides, merged_wo)
    return merge_assumptions(defaults, facts, users)


def _metric_cop(r: Ranged, metric: str) -> Ranged:
    k = T.BTU_PER_WH_TO_COP
    if metric in ("SEER2", "EER2"):
        k = k / 0.95
    elif metric == "HSPF2":
        k = k / 0.85
    elif metric in ("COP", "AFUE", "-"):
        k = 1.0
    return _ranged(r.low * k, r.expected * k, r.high * k, "W/W" if k != 1.0 or metric == "COP" else "-")


def systems_from_assumptions(assumptions: Iterable[Assumption], btype: BuildingType,
                             base: Optional[Systems] = None) -> Systems:
    """`Systems` from the merged assumptions (physics 02 section 12 meanings).

    Fields no assumption speaks to keep the value of `base` (if given) or the contract default.
    """
    m = _by_key(assumptions)
    upd: dict = {}

    def rng(k):
        return _num(m.get(k))

    def txt(k, allowed):
        v = _txt(m.get(k))
        return v if v in allowed else None

    ht = txt("hvac.system_type", _HVAC_TYPES)
    if ht is None and "hvac.system_type" in m:
        ht = "unknown"
    if ht:
        upd["hvac_type"] = ht
    fuel = txt("hvac.heating_fuel", _FUELS)
    if fuel:
        upd["heating_fuel"] = fuel

    cr = rng("hvac.cooling_rating")
    if cr is not None:
        metric = cr.unit if cr.unit in _COOLING_METRICS else None
        upd["cooling_rating"] = cr
        upd["cooling_rating_metric"] = metric
        upd["cooling_cop"] = _metric_cop(cr, metric or "SEER")
    hr = rng("hvac.heating_rating")
    if hr is not None:
        metric = {"-": "AFUE", "AFUE": "AFUE", "HSPF": "HSPF", "HSPF2": "HSPF2", "COP": "COP"}.get(hr.unit)
        upd["heating_rating"] = hr
        upd["heating_rating_metric"] = metric
        upd["heating_efficiency"] = _metric_cop(hr, metric or "AFUE")
    he = rng("hvac.heating_efficiency")
    if he is not None:
        upd["heating_efficiency"] = he
    for key, fld in (("hvac.distribution_efficiency", "distribution_efficiency"),
                     ("dhw.uef", "dhw_efficiency"), ("lighting.lpd", "lighting_w_per_m2"),
                     ("plug.ppd", "plug_w_per_m2"), ("infiltration.ach50", "infiltration_ach50"),
                     ("infiltration.leakage_75pa", "envelope_leakage_l_s_m2_75pa"),
                     ("setpoint.heating", "heating_setpoint_c"), ("setpoint.cooling", "cooling_setpoint_c"),
                     ("ventilation.outdoor_air_m3_s", "outdoor_air_m3_s")):
        v = rng(key)
        if v is not None:
            upd[fld] = v
    for key, fld, allowed in (("dhw.type", "dhw_type", _DHW_TYPES), ("dhw.fuel", "dhw_fuel", _DHW_FUELS),
                              ("hvac.duct_location", "duct_location", _DUCT_LOCATIONS),
                              ("dhw.location", "dhw_location", _DHW_LOCATIONS),
                              ("occupancy.schedule", "occupancy_schedule", _SCHEDULES)):
        v = txt(key, allowed)
        if v:
            upd[fld] = v
    iy = rng("hvac.install_year")
    if iy is not None:
        upd["hvac_install_year"] = int(round(iy.expected))

    occ = m.get("occupancy.count")
    if occ is not None and occ.source in _BUILDING_SPECIFIC and isinstance(occ.value, Ranged):
        upd["occupants"] = occ.value
    elif base is None or "occupancy.count" in m:
        upd["occupants"] = None

    # Systems.infiltration_ach is a reported result; until the physics fills it, a placeholder.
    if btype == "home":
        a50 = upd.get("infiltration_ach50") or (base.infiltration_ach50 if base else None)
        if a50 is not None:
            d = T.HOME_ACH50_TO_NATURAL
            upd.setdefault("infiltration_ach", _ranged(a50.low / d, a50.expected / d, a50.high / d, "1/h"))
    else:
        lo, ex, hi = T.OFFICE_NATURAL_ACH_PLACEHOLDER
        if base is None:
            upd["infiltration_ach"] = _ranged(lo, ex, hi, "1/h")
        sp = T.SETPOINTS["office"]
        upd.setdefault("heating_setback_c", sp["setback"])
        upd.setdefault("cooling_setup_c", sp["setup"])
    if "occupancy_schedule" not in upd and base is None:
        upd["occupancy_schedule"] = btype

    if base is not None:
        return Systems.model_validate({**base.model_dump(), **upd})
    missing = [k for k in ("hvac_type", "heating_fuel", "cooling_cop", "heating_efficiency", "dhw_type",
                           "dhw_fuel", "dhw_efficiency", "lighting_w_per_m2", "plug_w_per_m2", "infiltration_ach")
               if k not in upd]
    if missing:
        raise ValueError(f"assumptions do not cover the required Systems fields: {missing}")
    return Systems(**upd)


def feasibility_flags(btype: BuildingType, assumptions: Iterable[Assumption] = (),
                      flags: Iterable[Flag] = ()) -> list[Flag]:
    """The model's feasibility flags. Each is `unknown` until a cue (a flag from vision or the
    user) sets it (SPEC 5.2). Flags handed in are kept as given."""
    given = list(flags)
    keys = {f.key for f in given}
    m = _by_key(assumptions)
    out: list[Flag] = []
    defaults = {
        "electrical.service": "No cue on the main electrical service yet: panel capacity for solar is unknown.",
        "roof.structure": "No cue on the roof structure yet: whether it carries a PV array is unknown.",
    }
    for k in FEASIBILITY_KEYS:
        f = next((x for x in given if x.key == k), None)
        out.append(f if f is not None else Flag(key=k, status="unknown", message=defaults[k]))
    out.extend(x for x in given if x.key not in FEASIBILITY_KEYS)
    ht = _txt(m.get("hvac.system_type"))
    if btype == "office" and (ht is None or ht == "unknown") and "hvac.system_type" not in keys:
        out.append(Flag(key="hvac.system_type", status="unknown",
                        message="No packaged rooftop unit is confirmed. The baseline uses the office default "
                                "efficiency; HVAC_RTU and HVAC_ECON are not evaluated (physics 02 HVAC-00).",
                        evidence=list(m["hvac.system_type"].evidence) if "hvac.system_type" in m else []))
    return out


@dataclass
class Registry:
    assumptions: list[Assumption]
    systems: Systems
    flags: list[Flag]
    building_type: BuildingType
    bedrooms: Optional[int] = None
    notes: list[str] = field(default_factory=list)


def build_registry(bundle: PropertyBundle, observed: Iterable[Assumption] = (),
                   flags: Iterable[Flag] = (),
                   overrides: Mapping[str, OverrideValue] | None = None) -> Registry:
    """Assumptions, Systems and flags for `build_building_model` (the door wires geometry in)."""
    btype = building_type(bundle)
    assumptions = build_assumptions(bundle, observed, overrides)
    systems = systems_from_assumptions(assumptions, btype)
    return Registry(assumptions=assumptions, systems=systems,
                    flags=feasibility_flags(btype, assumptions, flags), building_type=btype,
                    bedrooms=count_bedrooms(bundle) if btype == "home" else None)


def set_model_assumption(model: BuildingModel, key: str, value: OverrideValue,
                         source: str = "user") -> BuildingModel:
    """`set_assumption` on a model: returns a new model with the key set and `systems` re-derived.

    Derived assumptions (window U and SHGC from a window type, office outdoor air from the
    occupant count) follow, unless the user set them directly. Vintage defaults that depend on
    the changed key (for example the year built) need the bundle: rebuild with an override then.
    """
    btype: BuildingType = "home" if model.systems.occupancy_schedule == "home" else "office"
    new = set_assumption(model.assumptions, key, value, source)
    merged = {a.key: a for a in new}
    for d in derived_assumptions(merged, btype):
        cur = merged.get(d.key)
        if d.key == key:
            continue
        if cur is None or cur.source != "user" or d.source == "user":
            new = [d if a.key == d.key else a for a in new] if cur is not None else new + [d]
    systems = systems_from_assumptions(new, btype, base=model.systems)
    return model.model_copy(update={"assumptions": new, "systems": systems})
