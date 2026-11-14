"""A8: feasibility cues from the panoramas: wall material, outlet type, main panel (SPEC 5.2, 6.3
step 7).

The cues ride on A7's one call per panorama: the reply carries an optional ``feasibility``
section (``SCHEMA`` here, merged into ``interior.REPLY_SCHEMA``; ``PROMPT_PART`` is appended to
``interior.PROMPT``). One call per panorama reads everything, so A8 adds no model call. The
section is optional, so a reply without it still gives A7's assumptions.

What is written:

- Flag ``electrical.service`` (registry A10 and the measure engine use this key; it blocks
  ``PV_ROOF``). From the strongest cue:
  a readable main panel (breaker rating under 100 A or a fuse box: ``likely_upgrade``; 100 A to
  under 200 A: ``unknown`` with a cost range, the panel may need a derated main or an upgrade
  for the PV backfeed; 200 A or more, or a commercial switchgear room: ``likely_ok``); without
  a panel, two-prong outlets: ``likely_upgrade``; only grounded outlets: ``unknown`` with a cost
  range; nothing seen: ``unknown`` without a cost. A flag is written only when at least one
  reply carried the feasibility section; otherwise the registry's own ``unknown`` stands.
- Flag ``dhw.space`` (blocks ``DHW_HPWH``): a water heater in a small closet inside the
  conditioned space gives ``blocked``, as in the house fixture; one in a garage, basement or
  utility room gives ``likely_ok``; nothing seen gives no flag.
- Assumption ``electrical.service_amps`` (A, the house fixture's key): the panel rating read, or
  a wide range from the outlet cue.
- Assumption ``wall.material`` (a string) with a construction-era note, and
  ``electrical.outlet_type`` with a wiring-age note. Both are cues: they set a value with a
  range and confidence and ``source="vision"``, never a hard fact.

Wall material also adds a conduit routing cost to an electrical flag that already carries one
(masonry, plaster or concrete walls are harder to fish wire through).

Costs: physics 04 COST-01 has no electrical service upgrade row. ``SERVICE_UPGRADE_USD`` is a
project judgement of 3,000 USD central (100 A to 200 A residential service), widened by the
COST-00 range rule (0.75 x, 1.5 x); ``SERVICE_MAYBE_USD`` is the house fixture's range for an
uncertain upgrade. Both are flagged as judgements in the flag message and the PR.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Optional

from backend.schema import Assumption, EvidenceRef, Flag, Ranged

VISION_MAX_CONFIDENCE = 0.8           # same cap as A7
OUTLET_AMPS_CONFIDENCE = 0.3          # house fixture: amps from an outlet cue
GROUNDED_AMPS_CONFIDENCE = 0.2

# ---------------------------------------------------------------- vocabularies

WALL_MATERIALS = ("drywall", "plaster", "masonry", "concrete", "wood_panelling", "unknown")
OUTLETS = ("two_prong", "three_prong", "gfci")
PANEL_TYPES = ("breaker_panel", "fuse_box", "switchgear_room", "unknown")
DHW_SPACES = ("small_closet_conditioned", "large_room_conditioned", "garage", "basement",
              "utility_room_unconditioned", "outdoor", "unknown")

SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["confidence"],
    "properties": {
        "wall_material": {"enum": list(WALL_MATERIALS)},
        "outlets": {"type": "array", "items": {"enum": list(OUTLETS)}},
        "panel_visible": {"type": "boolean"},
        "panel_type": {"enum": list(PANEL_TYPES)},
        "main_breaker_amps": {"type": ["integer", "null"], "minimum": 0},
        "water_heater_space": {"enum": list(DHW_SPACES)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "note": {"type": "string"},
    },
}

# parse spec in A7's ``_field`` vocabulary
FIELDS: dict[str, Any] = {
    "wall_material": WALL_MATERIALS, "outlets": ("list", OUTLETS), "panel_visible": bool,
    "panel_type": PANEL_TYPES, "main_breaker_amps": "int", "water_heater_space": DHW_SPACES,
}


def _alts(values: Iterable[str]) -> str:
    return " | ".join(f'"{v}"' for v in values)


# Appended inside the reply object of A7's prompt (doubled braces: it goes through str.format).
PROMPT_PART = """,
  "feasibility": {{
    "wall_material": """ + _alts(WALL_MATERIALS) + """,
        // drywall: flat painted board with taped seams; plaster: hard, slightly wavy, often
        // with cracks or picture rails; masonry: exposed brick or block; wood_panelling: boards
    "outlets": array of """ + _alts(OUTLETS) + """,
        // every receptacle type you can see: two_prong has two slots and no round ground hole;
        // gfci has test and reset buttons; empty array if no outlet is visible
    "panel_visible": true | false,           // the main electrical panel or meter room
    "panel_type": """ + _alts(PANEL_TYPES) + """,
        // fuse_box: screw-in or cartridge fuses; switchgear_room: a commercial electrical room
    "main_breaker_amps": integer | null,     // only if the main breaker's rating is legible
    "water_heater_space": """ + _alts(DHW_SPACES) + """,
        // where the water heater stands; small_closet_conditioned: a closet inside the heated
        // and cooled rooms with little air around the tank
    "confidence": number between 0 and 1,
    "note": short string saying what you saw
  }}"""

# ---------------------------------------------------------------- costs and cues

# Added cost of a likely service upgrade, USD. [J] 3,000 USD central with the COST-00 range rule;
# physics 04 has no COST row for an electrical service upgrade.
SERVICE_UPGRADE_USD = (2250.0, 3000.0, 4500.0)
# An upgrade that may or may not be needed: the house fixture's range (low 0).
SERVICE_MAYBE_USD = (0.0, 1500.0, 4500.0)
# Extra conduit routing cost on hard walls, USD [J].
ROUTING_ADDER_USD = {"plaster": (0.0, 300.0, 1000.0), "masonry": (0.0, 500.0, 1500.0),
                     "concrete": (0.0, 500.0, 1500.0)}
COST_SOURCE = ("project judgement: physics 04 has no COST row for a service upgrade; 3,000 USD "
               "central with the COST-00 range rule (0.75 x, 1.5 x)")
MAYBE_SOURCE = "project judgement, the house example's range for an uncertain upgrade"

AMPS_FROM_OUTLETS = (60.0, 100.0, 200.0)          # two-prong only: the house fixture's range
AMPS_FROM_GROUNDED = (100.0, 150.0, 200.0)        # three-prong or GFCI only

ERA_NOTE = {
    "plaster": "plaster walls: usually built before about 1950",
    "masonry": "exposed masonry: era not implied; hard to route conduit",
    "concrete": "concrete walls: era not implied; hard to route conduit",
    "wood_panelling": "wood panelling: common from the 1950s to the 1970s",
    "drywall": "drywall: usually after about 1950; easy to route conduit",
}
OUTLET_NOTE = {
    "two_prong": "two-prong outlets: ungrounded wiring, typically before the early 1960s",
    "three_prong": "three-prong outlets: grounded wiring",
    "gfci": "GFCI outlets: wiring updated at least in places",
    "mixed": "two-prong and grounded outlets: original wiring partly updated",
}
DHW_OK = {"garage", "basement", "utility_room_unconditioned", "outdoor", "large_room_conditioned"}


# ---------------------------------------------------------------- helpers

def _cap(c: float) -> float:
    return max(0.0, min(VISION_MAX_CONFIDENCE, round(c, 3)))


def _ev(pids: Iterable[tuple[str, Optional[str]]], extra: Optional[str] = None) -> list[EvidenceRef]:
    seen, out = set(), []
    for pid, note in pids:
        if pid in seen:
            continue
        seen.add(pid)
        n = "; ".join(x for x in (note, extra) if x) or None
        out.append(EvidenceRef(kind="pano", ref=pid, note=n))
    return out


def _usd(t: tuple[float, float, float]) -> Ranged:
    return Ranged(low=t[0], expected=t[1], high=t[2], unit="USD")


def _add(a: Ranged, b: tuple[float, float, float]) -> Ranged:
    return Ranged(low=a.low + b[0], expected=a.expected + b[1], high=a.high + b[2], unit="USD")


def _vote(items: list[tuple[str, float, str, Optional[str]]]):
    """Confidence-weighted vote: (value, confidence scaled by its share, panos)."""
    w: dict[str, float] = defaultdict(float)
    best: dict[str, float] = {}
    panos: dict[str, list] = defaultdict(list)
    for v, c, pid, note in items:
        w[v] += c
        best[v] = max(best.get(v, 0.0), c)
        panos[v].append((pid, note))
    total = sum(w.values())
    if not w or total <= 0:
        return None
    v = max(w, key=lambda k: (w[k], k))
    return v, _cap(best[v] * w[v] / total), panos[v]


# ---------------------------------------------------------------- readings -> flags

def _sections(readings: Iterable[Any]) -> list[tuple[str, Any]]:
    return [(r.pano_id, r.feasibility) for r in readings if getattr(r, "feasibility", None)]


def _wall(secs) -> Optional[tuple[str, float, list]]:
    return _vote([(s.fields["wall_material"], s.confidence, pid, s.note) for pid, s in secs
                  if s.fields.get("wall_material") not in (None, "unknown")])


def _electrical(secs, kind: str, wall: Optional[str]) -> tuple[Flag, list[Assumption]]:
    out: list[Assumption] = []
    n = len(secs)

    def amps(lo, ex, hi, conf, ev):
        out.append(Assumption(key="electrical.service_amps", label="Main electrical service size",
                              value=Ranged(low=lo, expected=ex, high=hi, unit="A"), source="vision",
                              confidence=_cap(conf), evidence=ev))

    def flag(status, msg, ev, cost=None, src=None):
        if cost is not None and wall in ROUTING_ADDER_USD:
            cost = _add(cost, ROUTING_ADDER_USD[wall])
            msg += f" Includes conduit routing through {wall} walls."
        if cost is not None:
            msg += f" Added cost: {src}."
        return Flag(key="electrical.service", status=status, message=msg, added_cost_usd=cost,
                    evidence=ev)

    # 1. a panel: direct evidence, the most confident reading wins
    panels = [(pid, s) for pid, s in secs if s.fields.get("panel_visible")
              and s.fields.get("panel_type", "unknown") != "unknown"]
    if panels:
        pid, s = max(panels, key=lambda x: (x[1].confidence, x[0]))
        ptype, a = s.fields["panel_type"], s.fields.get("main_breaker_amps")
        ev = _ev([(pid, s.note)], f"panel: {ptype}" + (f", {a} A main" if a else ""))
        if ptype == "switchgear_room":
            return flag("likely_ok", "A building electrical room is visible; a rooftop array is "
                        "small against a commercial service.", ev), out
        if ptype == "fuse_box":
            amps(30.0, 60.0, 100.0, s.confidence, ev)
            return flag("likely_upgrade", "A fuse box is the main panel: a service upgrade is likely "
                        "needed for solar.", ev, _usd(SERVICE_UPGRADE_USD), COST_SOURCE), out
        if a and 0 < a <= 400:
            amps(float(a), float(a), float(a), s.confidence, ev)
            if a < 100:
                return flag("likely_upgrade", f"The main breaker reads {a} A: a service upgrade is "
                            "likely needed for solar.", ev, _usd(SERVICE_UPGRADE_USD), COST_SOURCE), out
            if a < 200:
                return flag("unknown", f"The main breaker reads {a} A: a small array may fit under "
                            "the busbar rule, a larger one needs a derated main or an upgrade.", ev,
                            _usd(SERVICE_MAYBE_USD), MAYBE_SOURCE), out
            return flag("likely_ok", f"The main breaker reads {a} A: room for a rooftop array.", ev), out
        amps(*AMPS_FROM_GROUNDED, min(s.confidence, OUTLET_AMPS_CONFIDENCE), ev)
        return flag("unknown", "A breaker panel is visible but its rating is not legible.", ev,
                    _usd(SERVICE_MAYBE_USD), MAYBE_SOURCE), out

    # 2. outlets
    two = [(pid, s.note) for pid, s in secs if "two_prong" in s.fields.get("outlets", [])]
    grounded = [(pid, s.note) for pid, s in secs
                if {"three_prong", "gfci"} & set(s.fields.get("outlets", []))]
    if two:
        ev = _ev(two, "two-prong outlets; panel not visible")
        c = max(s.confidence for pid, s in secs if "two_prong" in s.fields.get("outlets", []))
        amps(*AMPS_FROM_OUTLETS, min(c, OUTLET_AMPS_CONFIDENCE), ev)
        return flag("likely_upgrade", "Main panel not visible in any panorama; two-prong outlets "
                    "seen, so the wiring and service are likely original: a service upgrade is "
                    "likely needed for solar.", ev, _usd(SERVICE_UPGRADE_USD), COST_SOURCE), out
    if grounded:
        ev = _ev(grounded, "grounded outlets only; panel not visible")
        c = max(s.confidence for pid, s in secs if {"three_prong", "gfci"} & set(s.fields.get("outlets", [])))
        amps(*AMPS_FROM_GROUNDED, min(c, GROUNDED_AMPS_CONFIDENCE), ev)
        return flag("unknown", "Main panel not visible; only grounded outlets seen, which says "
                    "little about the service size.", ev, _usd(SERVICE_MAYBE_USD), MAYBE_SOURCE), out

    # 3. nothing seen
    return Flag(key="electrical.service", status="unknown",
                message=f"Neither the main panel nor an outlet is visible in the {n} panoramas read: "
                        "panel capacity for solar is unknown."), out


def _dhw_space(secs) -> Optional[Flag]:
    w = _vote([(s.fields["water_heater_space"], s.confidence, pid, s.note) for pid, s in secs
               if s.fields.get("water_heater_space") not in (None, "unknown")])
    if not w:
        return None
    v, _, panos = w
    ev = _ev(panos, f"water heater space: {v}")
    if v == "small_closet_conditioned":
        return Flag(key="dhw.space", status="blocked", evidence=ev,
                    message="The water heater sits in a small closet inside the conditioned space: "
                            "a heat pump water heater needs more air volume and is assumed to be "
                            "outside the conditioned space (SPEC 6.2).")
    if v in DHW_OK:
        return Flag(key="dhw.space", status="likely_ok", evidence=ev,
                    message=f"The water heater stands in a {v.replace('_', ' ')}, with room for a "
                            "heat pump unit.")
    return None


def feasibility_from_readings(readings: dict[str, Any], kind: str = "home"
                              ) -> tuple[list[Assumption], list[Flag]]:
    """Per-panorama feasibility sections -> (vision assumptions, feasibility flags). Pure.

    No reply carried the section: nothing (the registry's ``unknown`` flags stand).
    """
    secs = _sections(readings[k] for k in sorted(readings))
    if not secs:
        return [], []
    assumptions: list[Assumption] = []
    wall = _wall(secs)
    if wall:
        v, conf, panos = wall
        assumptions.append(Assumption(key="wall.material", label="Interior wall material", value=v,
                                      source="vision", confidence=conf,
                                      evidence=_ev(panos, ERA_NOTE.get(v))))
    outlet_items = []
    for pid, s in secs:
        o = set(s.fields.get("outlets", []))
        if o:
            v = "two_prong" if o == {"two_prong"} else "mixed" if "two_prong" in o else (
                "gfci" if o == {"gfci"} else "three_prong")
            outlet_items.append((v, s.confidence, pid, s.note))
    ow = _vote(outlet_items)
    if ow:
        v, conf, panos = ow
        assumptions.append(Assumption(key="electrical.outlet_type", label="Outlet type", value=v,
                                      source="vision", confidence=conf,
                                      evidence=_ev(panos, OUTLET_NOTE[v])))
    flag, amps = _electrical(secs, kind, wall[0] if wall else None)
    flags = [flag]
    dhw = _dhw_space(secs)
    if dhw is not None:
        flags.append(dhw)
    return assumptions + amps, flags
