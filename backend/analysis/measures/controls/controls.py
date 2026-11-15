"""A22 measures LGT_CTRL, PLUG_MGMT and CTRL_TSTAT (SPEC 6.2; workplan 4.2 row A22).

Plain functions over contract types, following the plug-in protocol of
`backend/analysis/measures/engine/engine.py`: `check`, `change`, `describe` per measure. This
module imports neither the engine nor a sibling measure package.

Each measure rests on one parameter that physics 02 section 10 leaves unsourced (SPEC 6.2, the
limits under the table): the lighting-control saving fraction, the plug-load floor and the
setback depth. Each is carried as an `Assumption` with a wide range, written into the changed
model, listed in `params`, and the card carries a warning that the result rests on it.

How the change reaches the simulation. `BuildingModel` has no field for a lighting control
factor or for the hourly equipment schedule (physics 02 LGT-01, LGT-02 describe the measures as
multipliers on `f_light(h)` and `f_equip(h)`). So LGT_CTRL and PLUG_MGMT are applied as the
equivalent reduction of `Systems.lighting_w_per_m2` and `Systems.plug_w_per_m2`: the annual
lighting and plug energy is exact; the hours in which the plug saving falls are spread over the
whole schedule instead of the unoccupied hours only, which shifts the interaction with heating
and cooling (LGT-03) slightly. CTRL_TSTAT sets `Systems.heating_setback_c` and
`Systems.cooling_setup_c` (physics 02 section 12), which the zone model reads (ZON-04, DEF-08).
"""
from __future__ import annotations

import math
import os
from typing import Optional

from backend.schema import (Anchor, Assumption, BaselineResult, BuildingModel, EvidenceRef,
                            MeasureResult, PropertyBundle, Ranged)

# ---------------------------------------------------------------- constants (workplan 2.6: local)

TITLES = {"LGT_CTRL": "Occupancy and daylight controls",   # SPEC 6.2 table
          "PLUG_MGMT": "Plug load management",
          "CTRL_TSTAT": "Smart thermostat and setback"}

FORMULA_IDS = {"LGT_CTRL": ("LGT-01", "LGT-03"),
               "PLUG_MGMT": ("LGT-02", "LGT-03", "DEF-09"),
               "CTRL_TSTAT": ("ZON-04", "DEF-08")}

OFFICE_SCHEDULES = ("office", "office_vacant")   # Systems.occupancy_schedule keys (physics 02 DEF-09)

# LGT_CTRL: share of lighting energy that occupancy and daylight controls remove.
# UNSOURCED (physics 02 section 10, "savings fractions for lighting controls"); judgment, wide range.
LGT_CTRL_FRACTION = (0.10, 0.20, 0.30)   # low, expected, high

# PLUG_MGMT: equipment schedule floor reached in unoccupied hours.
# UNSOURCED (physics 02 section 10, "the plug-load floor for PLUG_MGMT"); judgment, wide range.
# Listed as (most saving, expected, least saving).
PLUG_FLOOR = (0.15, 0.25, 0.35)

# DEF-09 small-office schedules (S11 Table B-13), hour 1 = midnight to 01:00.
_OCC = {"weekday": (0, 0, 0, 0, 0, 0, .1, .2, .95, .95, .95, .95, .5, .95, .95, .95, .95, .3, .1, .1,
                    .05, .05, .05, .05),
        "saturday": (0, 0, 0, 0, 0, 0, .1, .1, .3, .3, .3, .3, .1, .1, .1, .1, .1, 0, 0, 0, 0, 0, 0, 0),
        "other": (0,) * 24}
_EQUIP = {"weekday": (.4, .4, .4, .4, .4, .4, .4, .4, .9, .9, .9, .9, .8, .9, .9, .9, .9, .5, .4, .4,
                      .4, .4, .4, .4),
          "saturday": (.3, .3, .3, .3, .3, .3, .4, .4, .5, .5, .5, .5, .35, .35, .35, .35, .35, .3, .3,
                       .3, .3, .3, .3, .3),
          "other": (.3,) * 24}
# Day counts of the LGT-01 worked example (260 weekdays, 52 Saturdays, 53 other days).
_DAYS = {"weekday": 260, "saturday": 52, "other": 53}

# CTRL_TSTAT setpoints in unoccupied hours, C.
# Office: the DEF-08 unoccupied values (S11 Table B-13), as the fixtures propose.
# Home: DEF-08 has no home setback. The depth is UNSOURCED (physics 02 DEF-08 and section 10).
# Each is (low, expected, high); only `expected` enters the simulation.
TSTAT_SETBACK = {"office": {"heat": (13.9, 15.6, 17.2), "cool": (25.6, 26.7, 28.9)},
                 "home": {"heat": (15.6, 17.8, 19.4), "cool": (26.7, 27.8, 29.4)}}
SMART_THERMOSTATS = ("smart", "connected", "learning")   # hvac.thermostat_type values = already done

# CTRL_TSTAT on homes is switched OFF by default. The home baseline holds one setpoint all year
# (zone constants SETPOINTS["home"], no setback), while the measure sets back on the unsourced
# HOME_SETBACK_HOURS (about 63 % of the week), so the saving compares an ideal schedule against a
# household that never turns the heat down: on the golden house it read about a third of the gas.
# Offices are unaffected (their baseline already has the DEF-08/DEF-09 setback schedule).
# Set LETO_HOME_TSTAT=1 (or true/yes/on) to switch the home measure back on.
HOME_TSTAT_ENV = "LETO_HOME_TSTAT"


def home_tstat_enabled() -> bool:
    """Whether CTRL_TSTAT is offered to homes (off unless LETO_HOME_TSTAT is set truthy)."""
    return os.environ.get(HOME_TSTAT_ENV, "").strip().lower() in ("1", "true", "yes", "on")

# Quantities finance prices (backend/analysis/finance/costs, _PARAM_KEYS):
M2_PER_FIXTURE = 8.0         # LGT_CTRL "fixtures": one 4-ft troffer per 8 m2, the fixtures' luminaire
                             # count (48 on 383 m2, 112 on 898 m2); design choice, unsourced
M2_PER_THERMOSTAT = 232.26   # CTRL_TSTAT "thermostats" in offices: one zone per 2500 ft2 (2 and 4 in
                             # the fixtures); design choice, unsourced
M2_PER_PERSON = 18.59        # PLUG_MGMT "workstations" without a head count (physics 02 LGT-03, S11)

LOW_CONFIDENCE = 0.3         # confidence of an unsourced measure parameter


# ---------------------------------------------------------------- helpers

def _assumption(model: BuildingModel, key: str) -> Optional[Assumption]:
    return next((a for a in model.assumptions if a.key == key), None)


def _text(model: BuildingModel, key: str) -> Optional[str]:
    a = _assumption(model, key)
    return a.value.strip().lower() if a is not None and isinstance(a.value, str) else None


def _upsert(assumptions: list[Assumption], new: Assumption) -> list[Assumption]:
    return [a for a in assumptions if a.key != new.key] + [new]


def _is_office(model: BuildingModel) -> bool:
    return model.systems.occupancy_schedule in OFFICE_SCHEDULES


def _area(model: BuildingModel) -> float:
    return sum(z.floor_area_m2 for z in model.zones if z.conditioned)


def _scale(r: Ranged, lo: float, exp: float, hi: float) -> Ranged:
    """r with each end multiplied by its own factor; lo <= exp <= hi keeps the order."""
    return Ranged(low=r.low * lo, expected=r.expected * exp, high=r.high * hi, unit=r.unit)


def _r(t: tuple[float, float, float], unit: str) -> Ranged:
    return Ranged(low=t[0], expected=t[1], high=t[2], unit=unit)


def _unsourced(key: str, label: str, value: Ranged, entry: str) -> Assumption:
    return Assumption(key=key, label=f"{label} (unsourced: physics 02 section 10, {entry})", value=value,
                      source="published_default", confidence=LOW_CONFIDENCE,
                      evidence=[EvidenceRef(kind="default_table", ref=entry,
                                            note="no source opened; judgment with a wide range")])


def _rests_on(label: str, value: Ranged) -> str:
    return (f"Rests on an unsourced assumption (SPEC 6.2): {label} {value.expected:g} "
            f"(range {value.low:g} to {value.high:g} {value.unit}).")


def _inside(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    hit = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def _poly_area(poly: list[tuple[float, float]]) -> float:
    return abs(sum(poly[i - 1][0] * p[1] - p[0] * poly[i - 1][1] for i, p in enumerate(poly))) / 2


def _room_of(bundle: PropertyBundle, x: float, y: float) -> Optional[str]:
    return next((r.id for r in bundle.matterport.rooms if r.polygon and _inside(x, y, r.polygon)), None)


def _anchor_at_pano(bundle: PropertyBundle, pano_id: str, label: str) -> Optional[Anchor]:
    p = next((p for p in bundle.matterport.panos if p.id == pano_id), None)
    if p is None:
        return None
    return Anchor(room_id=_room_of(bundle, p.x, p.y), pano_id=p.id, x=p.x, y=p.y, z=p.z, label=label)


def _main_room_anchor(bundle: PropertyBundle, label: str, z: Optional[float] = None) -> list[Anchor]:
    """The first pano in the largest room (the open office where the desks and fixtures are)."""
    rooms = sorted((r for r in bundle.matterport.rooms if r.polygon), key=lambda r: -_poly_area(r.polygon))
    for room in rooms:
        for p in bundle.matterport.panos:
            if _inside(p.x, p.y, room.polygon):
                return [Anchor(room_id=room.id, pano_id=p.id, x=p.x, y=p.y, z=p.z if z is None else z,
                               label=label)]
    return []


def _evidence_with(model: BuildingModel, word: str) -> list[EvidenceRef]:
    """Pano evidence in the model whose note mentions `word` (e.g. a thermostat seen by vision)."""
    out: list[EvidenceRef] = []
    for item in list(model.assumptions) + list(model.flags):
        for e in item.evidence:
            if e.kind == "pano" and e.note and word in e.note.lower() and e not in out:
                out.append(e)
    return out


# ---------------------------------------------------------------- LGT_CTRL

def lgt_ctrl_check(bundle: PropertyBundle, model: BuildingModel) -> Optional[tuple[str, str]]:
    if not _is_office(model):
        return ("not_supported", "Lighting controls are modelled for offices only (physics 02 LGT-01).")
    ctl = _text(model, "lighting.control_type")
    if ctl not in (None, "none", "manual", "unknown"):
        return ("already_done", f"the lighting already has {ctl.replace('_', ' ')} controls.")
    return None


def lgt_ctrl_change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel:
    lo, exp, hi = LGT_CTRL_FRACTION
    out = model.model_copy(deep=True)
    out.systems.lighting_w_per_m2 = _scale(model.systems.lighting_w_per_m2, 1 - hi, 1 - exp, 1 - lo)
    out.assumptions = _upsert(out.assumptions, _unsourced(
        "lighting.control_saving_fraction", "Lighting energy removed by occupancy and daylight controls",
        _r(LGT_CTRL_FRACTION, "fraction"), "LGT-01"))
    out.assumptions = _upsert(out.assumptions, Assumption(
        key="lighting.control_type", label="Lighting controls", value="occupancy_daylight",
        source="published_default", confidence=LOW_CONFIDENCE))
    return out


def _fixtures(model: BuildingModel) -> int:
    a = _assumption(model, "lighting.fixture_count")
    if a is not None and isinstance(a.value, Ranged):
        return max(1, round(a.value.expected))
    return max(1, round(_area(model) / M2_PER_FIXTURE))


def lgt_ctrl_describe(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
                      before: BaselineResult, options: dict) -> MeasureResult:
    frac = _r(LGT_CTRL_FRACTION, "fraction")
    s = changed.systems.lighting_w_per_m2
    return MeasureResult(
        measure_id="LGT_CTRL", title=TITLES["LGT_CTRL"], applicable=True,
        description="Occupancy sensors and daylight dimming on the existing light fixtures.",
        params={"fixtures": _fixtures(model), "control_saving_fraction": frac.expected,
                "control_saving_fraction_range": [frac.low, frac.high],
                "lpd_before_w_m2": model.systems.lighting_w_per_m2.expected,
                "lpd_effective_after_w_m2": round(s.expected, 3)},
        anchors=_main_room_anchor(bundle, "Light fixtures to put on sensors"),
        evidence=[EvidenceRef(kind="default_table", ref="LGT-01",
                              note="control factor on f_light(h), applied as the equivalent lighting "
                                   "power density"),
                  EvidenceRef(kind="default_table", ref="DEF-09", note="small-office lighting schedule")],
        formula_ids=list(FORMULA_IDS["LGT_CTRL"]),
        warnings=[_rests_on("lighting control saving fraction", frac),
                  "The daylight part (physics 03 LCT-01, LCT-02) is not computed separately; it is "
                  "inside the one control fraction."])


# ---------------------------------------------------------------- PLUG_MGMT

def plug_saving_share(floor: float, schedule: str = "office") -> float:
    """Share of annual plug energy removed when f_equip(h) drops to `floor` in unoccupied hours
    (DEF-09 occupancy 0). A vacant suite runs the "other" row every day."""
    days = {"other": 365} if schedule == "office_vacant" else _DAYS
    total = saved = 0.0
    for day, n in days.items():
        for occ, eq in zip(_OCC[day], _EQUIP[day]):
            total += n * eq
            if occ == 0 and eq > floor:
                saved += n * (eq - floor)
    return saved / total if total else 0.0


def plug_mgmt_check(bundle: PropertyBundle, model: BuildingModel) -> Optional[tuple[str, str]]:
    if not _is_office(model):
        return ("not_supported", "Plug load management is modelled for offices only (physics 02 LGT-02).")
    ctl = _text(model, "plug.control_type")
    if ctl not in (None, "none", "unknown"):
        return ("already_done", f"plug loads are already managed ({ctl.replace('_', ' ')}).")
    return None


def _plug_shares(model: BuildingModel) -> tuple[float, float, float]:
    sch = model.systems.occupancy_schedule
    return tuple(plug_saving_share(f, sch) for f in PLUG_FLOOR)   # most saving first


def plug_mgmt_change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel:
    most, exp, least = _plug_shares(model)
    out = model.model_copy(deep=True)
    out.systems.plug_w_per_m2 = _scale(model.systems.plug_w_per_m2, 1 - most, 1 - exp, 1 - least)
    out.assumptions = _upsert(out.assumptions, _unsourced(
        "plug.unoccupied_floor", "Equipment schedule floor in unoccupied hours",
        _r(PLUG_FLOOR, "fraction"), "LGT-02"))
    out.assumptions = _upsert(out.assumptions, Assumption(
        key="plug.control_type", label="Plug load controls", value="scheduled_shutoff",
        source="published_default", confidence=LOW_CONFIDENCE))
    return out


def _workstations(bundle: PropertyBundle, model: BuildingModel) -> int:
    if model.systems.occupants is not None:
        return max(1, round(model.systems.occupants.expected))
    occ = bundle.costar.occupancy if bundle.costar else None
    if occ is not None and occ.employees_total:
        return occ.employees_total
    return max(1, round(_area(model) / M2_PER_PERSON))


def plug_mgmt_describe(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
                       before: BaselineResult, options: dict) -> MeasureResult:
    floor = _r(PLUG_FLOOR, "fraction")
    most, exp, least = _plug_shares(model)
    return MeasureResult(
        measure_id="PLUG_MGMT", title=TITLES["PLUG_MGMT"], applicable=True,
        description="Advanced power strips and scheduled shut-off for workstations.",
        params={"workstations": _workstations(bundle, model), "unoccupied_floor": floor.expected,
                "unoccupied_floor_range": [floor.low, floor.high],
                "plug_saving_share": round(exp, 4), "plug_saving_share_range": [round(least, 4), round(most, 4)],
                "ppd_before_w_m2": model.systems.plug_w_per_m2.expected,
                "ppd_effective_after_w_m2": round(changed.systems.plug_w_per_m2.expected, 3)},
        anchors=_main_room_anchor(bundle, "Workstation outlets", z=0.4),
        evidence=[EvidenceRef(kind="default_table", ref="DEF-09",
                              note="equipment schedule 0.40 on weekday nights, 0.30 on weekends")],
        formula_ids=list(FORMULA_IDS["PLUG_MGMT"]),
        warnings=["no verified cost source; get a quote",
                  _rests_on("unoccupied plug-load floor", floor),
                  "The saving is applied as the equivalent plug power density, so it is spread over "
                  "all hours rather than the unoccupied hours only (BuildingModel has no schedule field)."])


# ---------------------------------------------------------------- CTRL_TSTAT

def ctrl_tstat_check(bundle: PropertyBundle, model: BuildingModel) -> Optional[tuple[str, str]]:
    sysm = model.systems
    if sysm.hvac_type == "none" and sysm.heating_fuel == "none":
        return ("feasibility", "There is no heating or cooling system for a thermostat to control.")
    kind = _text(model, "hvac.thermostat_type")
    if kind in SMART_THERMOSTATS:
        return ("already_done", f"a {kind} thermostat is installed.")
    if not _is_office(model) and not home_tstat_enabled():
        return ("not_supported", "Home thermostat savings are not offered yet: the home baseline assumes "
                                 "the heat is never turned down, which would overstate the saving.")
    return None


def _setback(model: BuildingModel) -> dict:
    return TSTAT_SETBACK["office" if _is_office(model) else "home"]


def ctrl_tstat_change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel:
    sb = _setback(model)
    out = model.model_copy(deep=True)
    out.systems.heating_setback_c = sb["heat"][1]
    out.systems.cooling_setup_c = sb["cool"][1]
    out.assumptions = _upsert(out.assumptions, _unsourced(
        "setpoint.heating_setback", "Heating setpoint in unoccupied hours", _r(sb["heat"], "C"), "DEF-08"))
    out.assumptions = _upsert(out.assumptions, _unsourced(
        "setpoint.cooling_setup", "Cooling setpoint in unoccupied hours", _r(sb["cool"], "C"), "DEF-08"))
    out.assumptions = _upsert(out.assumptions, Assumption(
        key="hvac.thermostat_type", label="Thermostat type", value="smart",
        source="published_default", confidence=LOW_CONFIDENCE))
    return out


def _effective_setback(model: BuildingModel) -> tuple[float, float]:
    """The unoccupied setpoints the zone model runs today (Systems, else the DEF-08 office values)."""
    s, d = model.systems, TSTAT_SETBACK["office"]
    return (s.heating_setback_c if s.heating_setback_c is not None else d["heat"][1],
            s.cooling_setup_c if s.cooling_setup_c is not None else d["cool"][1])


def _thermostats(bundle: PropertyBundle, model: BuildingModel) -> int:
    a = _assumption(model, "hvac.thermostat_count")
    if a is not None and isinstance(a.value, Ranged):
        return max(1, round(a.value.expected))
    if _is_office(model):
        return max(1, math.ceil(_area(model) / M2_PER_THERMOSTAT - 1e-9))
    return 1


def ctrl_tstat_describe(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
                        before: BaselineResult, options: dict) -> MeasureResult:
    sb = _setback(model)
    heat, cool = _r(sb["heat"], "C"), _r(sb["cool"], "C")
    office = _is_office(model)
    seen = _evidence_with(model, "thermostat")
    anchors: list[Anchor] = []
    if seen:
        a = _anchor_at_pano(bundle, seen[0].ref, "Wall thermostat")
        anchors = [a] if a else []
    if not anchors and bundle.matterport.panos:
        # no thermostat seen: the pano nearest the middle of the scanned panos
        ps = bundle.matterport.panos
        cx, cy = sum(p.x for p in ps) / len(ps), sum(p.y for p in ps) / len(ps)
        p = min(ps, key=lambda p: (p.x - cx) ** 2 + (p.y - cy) ** 2)
        anchors = [Anchor(room_id=_room_of(bundle, p.x, p.y), pano_id=p.id, x=p.x, y=p.y, z=p.z,
                          label="Wall thermostat")]
    evidence = list(seen) + [EvidenceRef(kind="default_table", ref="DEF-08",
                                         note="unoccupied setpoints of the office schedule" if office
                                         else "home setpoints have no setback by default")]
    warnings = [_rests_on("unoccupied heating setpoint", heat), _rests_on("unoccupied cooling setpoint", cool)]
    if office and _effective_setback(model) == (heat.expected, cool.expected):
        warnings.insert(0, "No saving at the proposed setpoints: they equal the unoccupied setback the "
                           "baseline schedule already has. The setback depth is a measure parameter with "
                           "no sourced default.")
    if not office:
        warnings.append("The zone model applies Systems.heating_setback_c and cooling_setup_c on the "
                        "office schedule only (DEF-08, DEF-09); no home setback hours are defined, so a "
                        "home saving may read zero until the physics adds them.")
    n = _thermostats(bundle, model)
    return MeasureResult(
        measure_id="CTRL_TSTAT", title=TITLES["CTRL_TSTAT"], applicable=True,
        description=(f"Connected thermostats with an unoccupied setback ({n} zone{'s' if n > 1 else ''})."
                     if office else "A connected thermostat with a night and away setback."),
        params={"heating_setback_c": heat.expected, "cooling_setup_c": cool.expected, "thermostats": n,
                "heating_setback_range_c": [heat.low, heat.high],
                "cooling_setup_range_c": [cool.low, cool.high]},
        anchors=anchors, evidence=evidence, formula_ids=list(FORMULA_IDS["CTRL_TSTAT"]), warnings=warnings)
