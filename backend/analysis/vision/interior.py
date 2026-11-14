"""A7: read the interior panoramas for glazing, HVAC, water heater and lighting (SPEC 5.2).

One model call per panorama: its cube faces (up and the four sides; the floor face is left out)
go to ``ask_model`` with ``PROMPT``, and the reply must be one JSON object of the shape in
``REPLY_SCHEMA``. Each panorama's reply is parsed on its own; a reply that is not that object is
dropped whole (no assumption, no exception). The readings of all panoramas are then combined
into ``Assumption`` values with ``source="vision"``, each carrying the panoramas it rests on as
``EvidenceRef(kind="pano")`` and a confidence.

What is written, and the keys the rest of the lane reads (registry A10, geometry A9):

- Glazing: ``window.type`` (a DEF-03 type; the registry derives U and SHGC from it) and
  ``window.shading``. Always, whatever the wall graph holds: glazing performance is always an
  assumption (SPEC 5.1).
- Window count and size: only when the wall graph has no window opening at all (SPEC 5.1, 16;
  workplan A7): ``window.count`` and ``window.area_m2``, range plus or minus 30 percent
  (physics 02 DEF-03). Where the scan measured windows the reading is a cross-check only and is
  reported in the evidence note of ``window.type``, never as a size. With
  ``room_fallback=True`` a room without window openings in a model that has some gets
  ``window.<room_id>.area_m2`` (the form A9 places on that room's wall); off by default, see
  the module notes in the PR.
- HVAC: ``hvac.system_type`` (a ``Systems.hvac_type`` value, only when a type is seen),
  ``hvac.heating_fuel``, ``hvac.thermostat_type``, ``hvac.install_year`` (from the age band;
  DEF-05 rule: the vision reading of the unit's age replaces the vintage guess).
- Water heater: ``dhw.type``, ``dhw.fuel``.
- Lighting: ``lighting.fixture_type``; for offices also ``lighting.lpd``, the DEF-10 row the
  fixture type selects. Homes take lighting energy from LGT-01, so no density is written.

The live model call is the one network exception of the lane (workplan 3.2). It is a function
argument and is never exercised in tests; until sending sponsor imagery to an external provider
is approved (SPEC 16) the door does not pass a live one and the lane runs on vintage defaults.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

from backend.schema import Assumption, EvidenceRef, Flag, Pano, PropertyBundle, Ranged, Room

AskModel = Callable[[list[bytes], str], str]   # (images, prompt) -> reply text
GetBytes = Callable[[str], bytes]              # asset path -> bytes (data_layer.api.get_asset)

# Constants destined for backend/config.py (SPEC 12); kept local until the lane owner moves them.
MAX_PANOS = 12                       # model calls per property
VISION_MAX_CONFIDENCE = 0.8          # a panorama reading never beats this
WINDOW_SIZE_CONFIDENCE = 0.5         # count and size read from imagery
WINDOW_AREA_REL = 0.30               # physics 02 DEF-03: vision window area +/- 30 %
NOTE_MAX_CHARS = 200
SAME_VIEW_M = 6.0                    # panoramas of one room closer than this see the same windows

# ---------------------------------------------------------------- vocabularies

FRAMES = ("metal", "wood", "vinyl", "fiberglass", "unknown")
PANES = ("single", "double", "triple", "unknown")
TRI = ("yes", "no", "unknown")
SHADING = ("none", "interior_blinds", "curtains", "exterior_shade", "overhang", "tinted_film",
           "unknown")
HVAC_TYPES = ("central_ac_furnace", "heat_pump", "rooftop_unit", "room_ac", "central_plant",
              "none", "unknown")             # Systems.hvac_type
HVAC_CUES = ("ceiling_diffuser", "floor_register", "wall_register", "return_grille",
             "wall_unit", "window_unit", "mini_split_head", "fan_coil", "baseboard_heater",
             "radiator", "furnace", "air_handler", "outdoor_condenser", "rooftop_unit_visible",
             "chilled_water_piping", "thermostat")
THERMOSTATS = ("manual", "programmable", "smart", "none_seen")
FUELS = ("gas", "electricity", "unknown")
AGE_BANDS = ("before_1992", "1992_2005", "2006_2014", "2015_2022", "2023_or_later", "unknown")
DHW_TYPES = ("storage", "tankless", "heat_pump", "unknown")   # Systems.dhw_type
FIXTURES = ("led", "fluorescent_t8", "fluorescent_t12", "cfl", "incandescent", "halogen",
            "mixed", "unknown")

REPLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["windows", "hvac", "water_heater", "lighting"],
    "properties": {
        "windows": {
            "type": "object",
            "required": ["visible", "confidence"],
            "properties": {
                "visible": {"type": "boolean"},
                "count": {"type": ["integer", "null"], "minimum": 0},
                "total_area_m2": {"type": ["number", "null"], "minimum": 0},
                "frame": {"enum": list(FRAMES)},
                "panes": {"enum": list(PANES)},
                "low_e": {"enum": list(TRI)},
                "shading": {"enum": list(SHADING)},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "note": {"type": "string"},
            },
        },
        "hvac": {
            "type": "object",
            "required": ["confidence"],
            "properties": {
                "system_type": {"enum": list(HVAC_TYPES)},
                "cues": {"type": "array", "items": {"enum": list(HVAC_CUES)}},
                "thermostat": {"enum": list(THERMOSTATS)},
                "heating_fuel": {"enum": list(FUELS)},
                "age_band": {"enum": list(AGE_BANDS)},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "note": {"type": "string"},
            },
        },
        "water_heater": {
            "type": "object",
            "required": ["visible", "confidence"],
            "properties": {
                "visible": {"type": "boolean"},
                "type": {"enum": list(DHW_TYPES)},
                "fuel": {"enum": list(FUELS)},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "note": {"type": "string"},
            },
        },
        "lighting": {
            "type": "object",
            "required": ["confidence"],
            "properties": {
                "fixture_type": {"enum": list(FIXTURES)},
                "fixture_count": {"type": ["integer", "null"], "minimum": 0},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "note": {"type": "string"},
            },
        },
    },
}

PROMPT = """You are inspecting one interior panorama of a {building} for an energy audit.
The images are the faces of one cube panorama taken at the same point (panorama {pano_id}{room}):
the first looks up at the ceiling, the next four look horizontally around the room.

Report only what you can see. Use "unknown" (or false, or null) whenever the images do not show
it clearly; a wrong guess is worse than "unknown".

Reply with ONE JSON object and nothing else (no prose, no code fence), with exactly these keys:

{{
  "windows": {{
    "visible": true | false,                 // any exterior window in these images
    "count": integer | null,                 // windows seen in this room; in a large open
                                             // room only those within about 6 m of the camera
    "total_area_m2": number | null,          // their total glazed area, estimated from door
                                             // height (about 2.0 m) and ceiling height
    "frame": {frames},
    "panes": {panes},                        // count reflections in the glass, look at the
                                             // spacer bar and the sash depth
    "low_e": {tri},                          // a faint green or purple tint in the glass
    "shading": {shading},
    "confidence": number between 0 and 1,
    "note": short string saying what you saw
  }},
  "hvac": {{
    "system_type": {hvac_types},
        // central_ac_furnace: ducted registers with a furnace or air handler closet;
        // heat_pump: a heat pump outdoor unit or air handler label; room_ac: wall or window
        // units, mini-split heads; rooftop_unit: only if a packaged unit itself is visible
        // (ceiling diffusers alone are not enough, say unknown); central_plant: fan-coil units
        // or chilled-water piping; none: clearly no heating or cooling
    "cues": array of {hvac_cues},
    "thermostat": {thermostats},
    "heating_fuel": {fuels},                 // gas only with a flue, gas line or burner seen
    "age_band": {age_bands},                 // of the equipment, from its style or a label
    "confidence": number between 0 and 1,
    "note": short string
  }},
  "water_heater": {{
    "visible": true | false,
    "type": {dhw_types},                     // storage: a tank; tankless: a wall box with
                                             // a vent; heat_pump: a tank with a fan on top
    "fuel": {fuels},                         // gas: a flue pipe or gas valve; electricity:
                                             // a junction box and no flue
    "confidence": number between 0 and 1,
    "note": short string
  }},
  "lighting": {{
    "fixture_type": {fixtures},
    "fixture_count": integer | null,         // ceiling fixtures in view
    "confidence": number between 0 and 1,
    "note": short string
  }}
}}
"""


def _alts(values: Iterable[str]) -> str:
    return " | ".join(f'"{v}"' for v in values)


def build_prompt(pano: Pano, building: str, room_label: Optional[str] = None) -> str:
    """The prompt for one panorama. ``building`` is "home" or "office"."""
    room = f", in a room labelled {room_label!r}" if room_label else ""
    return PROMPT.format(
        building="office" if building == "office" else "home", pano_id=pano.id, room=room,
        frames=_alts(FRAMES), panes=_alts(PANES), tri=_alts(TRI), shading=_alts(SHADING),
        hvac_types=_alts(HVAC_TYPES), hvac_cues=_alts(HVAC_CUES), thermostats=_alts(THERMOSTATS),
        fuels=_alts(FUELS), age_bands=_alts(AGE_BANDS), dhw_types=_alts(DHW_TYPES),
        fixtures=_alts(FIXTURES))


# ---------------------------------------------------------------- parsing

@dataclass(frozen=True)
class Section:
    """One parsed section of a reply: its fields (only valid ones kept) and its confidence."""
    fields: dict[str, Any]
    confidence: float
    note: Optional[str]


@dataclass(frozen=True)
class PanoReading:
    pano_id: str
    windows: Optional[Section] = None
    hvac: Optional[Section] = None
    water_heater: Optional[Section] = None
    lighting: Optional[Section] = None


_SECTION_FIELDS: dict[str, dict[str, Any]] = {
    "windows": {"visible": bool, "count": "int", "total_area_m2": "num", "frame": FRAMES,
                "panes": PANES, "low_e": TRI, "shading": SHADING},
    "hvac": {"system_type": HVAC_TYPES, "cues": ("list", HVAC_CUES), "thermostat": THERMOSTATS,
             "heating_fuel": FUELS, "age_band": AGE_BANDS},
    "water_heater": {"visible": bool, "type": DHW_TYPES, "fuel": FUELS},
    "lighting": {"fixture_type": FIXTURES, "fixture_count": "int"},
}
_REQUIRED = {"windows": ("visible",), "water_heater": ("visible",)}


def _json_object(text: Any) -> Optional[dict]:
    if not isinstance(text, str):
        return None
    s = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", s, re.S | re.I)
    if fence:
        s = fence.group(1)
    try:
        obj = json.loads(s)
    except (ValueError, RecursionError):
        return None
    return obj if isinstance(obj, dict) else None


def _number(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def _field(v: Any, spec: Any) -> Any:
    """The value if it fits ``spec``, else None (dropped)."""
    if spec is bool:
        return v if isinstance(v, bool) else None
    if spec == "num":
        n = _number(v)
        return n if n is not None and n >= 0 else None
    if spec == "int":
        n = _number(v)
        return int(n) if n is not None and n >= 0 and n == int(n) else None
    if isinstance(spec, tuple) and spec and spec[0] == "list":
        if not isinstance(v, list):
            return None
        return [x for x in v if isinstance(x, str) and x in spec[1]]
    return v if isinstance(v, str) and v in spec else None


def _section(name: str, raw: Any) -> Optional[Section]:
    if not isinstance(raw, dict):
        return None
    conf = _number(raw.get("confidence"))
    if conf is None or not 0 <= conf <= 1:
        return None
    fields = {}
    for k, spec in _SECTION_FIELDS[name].items():
        v = _field(raw.get(k), spec)
        if v is not None:
            fields[k] = v
    if any(k not in fields for k in _REQUIRED.get(name, ())):
        return None
    note = raw.get("note")
    note = note.strip()[:NOTE_MAX_CHARS] if isinstance(note, str) and note.strip() else None
    return Section(fields, conf, note)


def parse_reply(pano_id: str, text: Any) -> Optional[PanoReading]:
    """One model reply -> a reading, or None when the reply is not the JSON object asked for.

    A reply must be one JSON object (a surrounding code fence is tolerated) with the four
    section keys. A section with a missing or out-of-range confidence is dropped; a field
    outside its vocabulary is dropped. Never raises.
    """
    try:
        obj = _json_object(text)
        if obj is None or not all(k in obj for k in _SECTION_FIELDS):
            return None
        secs = {k: _section(k, obj[k]) for k in _SECTION_FIELDS}
        if not any(secs.values()):
            return None
        return PanoReading(pano_id=pano_id, **secs)
    except Exception:            # defensive: a reply must never break the run
        return None


# ---------------------------------------------------------------- geometry helpers

def _inside(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    n, inside = len(poly), False
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def pano_room(pano: Pano, rooms: list[Room]) -> Optional[Room]:
    """The room whose outline holds the panorama; on a tie the one with the pano's label."""
    hits = [r for r in rooms if len(r.polygon) >= 3 and _inside(pano.x, pano.y, r.polygon)]
    if not hits:
        return None
    same = [r for r in hits if pano.label and r.label == pano.label]
    return (same or hits)[0]


def rooms_with_window_openings(bundle: PropertyBundle) -> set[str]:
    """Rooms bounded by an edge that carries a ``window`` opening."""
    window_edges = {e.id for fl in bundle.matterport.floors for e in fl.edges
                    if any(o.type == "window" for o in e.openings)}
    return {r.id for r in bundle.matterport.rooms if window_edges & set(r.boundary_edge_ids)}


def model_has_window_openings(bundle: PropertyBundle) -> bool:
    return any(o.type == "window" for fl in bundle.matterport.floors for e in fl.edges
               for o in e.openings)


def building_kind(bundle: PropertyBundle) -> str:
    use = bundle.summary.use_type
    if use in ("single_family", "multifamily_unit"):
        return "home"
    if use == "office":
        return "office"
    return "office" if bundle.summary.segment == "commercial" else "home"


def select_panos(bundle: PropertyBundle, max_panos: int = MAX_PANOS) -> list[Pano]:
    """Panoramas to read: one per room first (rooms in bundle order), then the rest, capped."""
    rooms = bundle.matterport.rooms
    first, rest, seen = [], [], set()
    for p in bundle.matterport.panos:
        if not p.face_paths:
            continue
        r = pano_room(p, rooms)
        key = r.id if r else f"pano:{p.id}"
        (rest if key in seen else first).append(p)
        seen.add(key)
    return (first + rest)[:max(0, max_panos)]


def _faces(pano: Pano) -> list[str]:
    """Up and the four sides; the floor face (the sixth) shows nothing this package reads."""
    return pano.face_paths[:5] if len(pano.face_paths) >= 6 else list(pano.face_paths)


# ---------------------------------------------------------------- the model calls

@dataclass
class VisionResult:
    assumptions: list[Assumption]
    flags: list[Flag] = field(default_factory=list)          # A8 fills these
    warnings: list[str] = field(default_factory=list)
    readings: dict[str, PanoReading] = field(default_factory=dict)


def read_panoramas(bundle: PropertyBundle, ask_model: AskModel, get_bytes: GetBytes,
                   max_panos: int = MAX_PANOS) -> tuple[dict[str, PanoReading], list[str]]:
    """Call the model once per selected panorama. Returns the readings that parsed, and warnings."""
    readings: dict[str, PanoReading] = {}
    warnings: list[str] = []
    kind = building_kind(bundle)
    for pano in select_panos(bundle, max_panos):
        images: list[bytes] = []
        for path in _faces(pano):
            try:
                b = get_bytes(path)
            except Exception as exc:          # a missing asset skips the face, not the run
                warnings.append(f"{pano.id}: face {path} not read ({type(exc).__name__})")
                continue
            if isinstance(b, (bytes, bytearray)) and b:
                images.append(bytes(b))
        if not images:
            warnings.append(f"{pano.id}: no face image; not sent to the model")
            continue
        room = pano_room(pano, bundle.matterport.rooms)
        prompt = build_prompt(pano, kind, (room.label if room else None) or pano.label)
        try:
            reply = ask_model(images, prompt)
        except Exception as exc:
            warnings.append(f"{pano.id}: model call failed ({type(exc).__name__}); no reading")
            continue
        reading = parse_reply(pano.id, reply)
        if reading is None:
            warnings.append(f"{pano.id}: reply is not the JSON object asked for; ignored")
            continue
        readings[pano.id] = reading
    return readings, warnings


# ---------------------------------------------------------------- readings -> assumptions

WINDOW_TYPE_BY_CUES = {
    # (panes, frame class, low-e) -> DEF-03 type; frame class "unknown" takes the non-metal row,
    # whose same-pane worst case (metal) the registry uses as the high bound.
    ("single", "metal"): "single_clear_metal",
    ("single", "non_metal"): "single_clear_non_metal",
    ("single", "unknown"): "single_clear_non_metal",
    ("double", "metal"): "double_clear_metal",
    ("double", "non_metal"): "double_clear_non_metal",
    ("double", "unknown"): "double_clear_non_metal",
    ("triple", "metal"): "triple_lowe_non_metal",
    ("triple", "non_metal"): "triple_lowe_non_metal",
    ("triple", "unknown"): "triple_lowe_non_metal",
}

AGE_BAND_YEARS = {   # hvac.install_year low / expected / high, the DEF-05 table's bins
    "before_1992": (1975.0, 1985.0, 1991.0),
    "1992_2005": (1992.0, 1999.0, 2005.0),
    "2006_2014": (2006.0, 2010.0, 2014.0),
    "2015_2022": (2015.0, 2018.0, 2022.0),
    "2023_or_later": (2023.0, 2024.0, 2026.0),
}

# DEF-10 office rows, selected by fixture type (W/m2 low, expected, high)
OFFICE_LPD_OLD = (10.76, 19.48, 19.48)       # lighting not yet upgraded
OFFICE_LPD_NEW = (6.5, 10.76, 10.76)         # 2005 or later; 6.5 is the "already LED" placeholder
LPD_BY_FIXTURE = {
    "led": (OFFICE_LPD_NEW, "LED fixtures: the 2005-or-later row"),
    "fluorescent_t8": (OFFICE_LPD_OLD, "fluorescent fixtures: the not-yet-upgraded row"),
    "fluorescent_t12": (OFFICE_LPD_OLD, "fluorescent fixtures: the not-yet-upgraded row"),
    "cfl": (OFFICE_LPD_OLD, "compact fluorescent: the not-yet-upgraded row"),
    "incandescent": (OFFICE_LPD_OLD, "incandescent: the not-yet-upgraded row"),
    "halogen": (OFFICE_LPD_OLD, "halogen: the not-yet-upgraded row"),
    "mixed": ((OFFICE_LPD_NEW[0], OFFICE_LPD_NEW[1], OFFICE_LPD_OLD[1]),
              "mixed fixtures: spans both rows"),
}


@dataclass
class _Vote:
    """Confidence-weighted vote over panoramas for one categorical value."""
    weights: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    best_conf: dict[str, float] = field(default_factory=dict)
    panos: dict[str, list[tuple[str, Optional[str]]]] = field(default_factory=lambda: defaultdict(list))

    def add(self, value: str, conf: float, pano_id: str, note: Optional[str]) -> None:
        self.weights[value] += conf
        self.best_conf[value] = max(conf, self.best_conf.get(value, 0.0))
        self.panos[value].append((pano_id, note))

    def winner(self) -> Optional[tuple[str, float, list[tuple[str, Optional[str]]]]]:
        total = sum(self.weights.values())
        if not self.weights or total <= 0:
            return None
        value = max(self.weights, key=lambda v: (self.weights[v], v))
        share = self.weights[value] / total
        conf = min(VISION_MAX_CONFIDENCE, round(self.best_conf[value] * share, 3))
        return value, conf, self.panos[value]


def _pano_ev(panos: list[tuple[str, Optional[str]]]) -> list[EvidenceRef]:
    seen, out = set(), []
    for pid, note in panos:
        if pid not in seen:
            seen.add(pid)
            out.append(EvidenceRef(kind="pano", ref=pid, note=note))
    return out


def _vision(key: str, label: str, value: Any, conf: float,
            evidence: list[EvidenceRef]) -> Assumption:
    return Assumption(key=key, label=label, value=value, source="vision",
                      confidence=max(0.0, min(1.0, conf)), evidence=evidence)


def _categorical(readings: Iterable[PanoReading], section: str, fld: str,
                 skip: tuple[str, ...] = ("unknown",),
                 when: Callable[[Section], bool] = lambda s: True) -> Optional[tuple]:
    vote = _Vote()
    for r in readings:
        s = getattr(r, section)
        if s is None or not when(s):
            continue
        v = s.fields.get(fld)
        if isinstance(v, str) and v not in skip:
            vote.add(v, s.confidence, r.pano_id, s.note)
    return vote.winner()


def _frame_class(frame: Optional[str]) -> str:
    if frame == "metal":
        return "metal"
    if frame in ("wood", "vinyl", "fiberglass"):
        return "non_metal"
    return "unknown"


def _window_type(s: Section) -> Optional[str]:
    panes = s.fields.get("panes")
    if panes not in ("single", "double", "triple"):
        return None
    fc = _frame_class(s.fields.get("frame"))
    t = WINDOW_TYPE_BY_CUES[(panes, fc)]
    if panes == "double" and fc == "non_metal" and s.fields.get("low_e") == "yes":
        t = "double_lowe_non_metal"
    return t


def _glazing(readings: list[PanoReading], cross_check: Optional[str]) -> list[Assumption]:
    out: list[Assumption] = []
    vote = _Vote()
    for r in readings:
        s = r.windows
        if s is None or not s.fields.get("visible"):
            continue
        t = _window_type(s)
        if t is not None:
            frame_known = _frame_class(s.fields.get("frame")) != "unknown"
            vote.add(t, s.confidence * (1.0 if frame_known else 0.75), r.pano_id, s.note)
    w = vote.winner()
    if w:
        t, conf, panos = w
        ev = _pano_ev(panos) + [EvidenceRef(
            kind="default_table", ref="DEF-03",
            note=f"U and SHGC of the type read by vision ({t})"
                 + (f"; {cross_check}" if cross_check else ""))]
        out.append(_vision("window.type", "Window type", t, conf, ev))
    sh = _categorical(readings, "windows", "shading",
                      when=lambda s: bool(s.fields.get("visible")))
    if sh:
        v, conf, panos = sh
        out.append(_vision("window.shading", "Window shading", v, conf, _pano_ev(panos)))
    return out


def _view_groups(readings: list[PanoReading], panos: dict[str, Pano],
                 pano_rooms: dict[str, Optional[str]]) -> dict[str, list[PanoReading]]:
    """Panoramas that see the same windows: same room and chained within ``SAME_VIEW_M``.

    A large open floor plate read from several far-apart points sees different windows from
    each; two panoramas a few metres apart in one room see the same ones.
    """
    by_room: dict[str, list[PanoReading]] = defaultdict(list)
    for r in readings:
        rid = pano_rooms.get(r.pano_id)
        by_room[rid if rid else f"pano:{r.pano_id}"].append(r)
    out: dict[str, list[PanoReading]] = {}
    for rid, rs in by_room.items():
        clusters: list[list[PanoReading]] = []
        for r in rs:
            p = panos.get(r.pano_id)
            near = [c for c in clusters if p is not None and any(
                (q := panos.get(o.pano_id)) is not None
                and ((p.x - q.x) ** 2 + (p.y - q.y) ** 2) ** 0.5 < SAME_VIEW_M for o in c)]
            merged = [r] + [o for c in near for o in c]
            clusters = [c for c in clusters if c not in near] + [merged]
        for i, c in enumerate(clusters):
            out[rid if len(clusters) == 1 else f"{rid}#{i}"] = c
    return out


def _window_sizes(readings: list[PanoReading], panos: dict[str, Pano],
                  pano_rooms: dict[str, Optional[str]]
                  ) -> dict[str, tuple[Optional[int], Optional[float], float, list[tuple[str, Optional[str]]]]]:
    """Per view group (``_view_groups``): the largest count and area any of its panoramas saw.

    Panoramas of one group see the same windows, so a group takes the maximum, not the sum.
    """
    seen = [r for r in readings if r.windows is not None and r.windows.fields.get("visible")]
    groups = _view_groups(seen, panos, pano_rooms)
    out = {}
    for g, rs in groups.items():
        counts = [r.windows.fields["count"] for r in rs if "count" in r.windows.fields]
        areas = [r.windows.fields["total_area_m2"] for r in rs
                 if r.windows.fields.get("total_area_m2", 0) > 0]
        count = max(counts) if counts else None
        area = max(areas) if areas else None
        conf = max(r.windows.confidence for r in rs)
        out[g] = (count, area, conf, [(r.pano_id, r.windows.note) for r in rs])
    return out


def _spread(x: float, rel: float, unit: str, nd: int = 2) -> Ranged:
    return Ranged(low=round(x * (1 - rel), nd), expected=round(x, nd), high=round(x * (1 + rel), nd),
                  unit=unit)


_OPENINGS_EV = "floors.edges.openings"


def _windows_from_vision(bundle: PropertyBundle, readings: list[PanoReading],
                         pano_rooms: dict[str, Optional[str]], read_all: bool,
                         room_fallback: bool) -> tuple[list[Assumption], Optional[str]]:
    """Window count and size, only where the wall graph has no window openings.

    Returns the assumptions and, where the scan measured windows, a cross-check sentence.
    """
    panos = {p.id: p for p in bundle.matterport.panos}
    sizes = _window_sizes(readings, panos, pano_rooms)
    seen_area = sum(a for (_, a, _, _) in sizes.values() if a)
    seen_count = sum(c for (c, _, _, _) in sizes.values() if c)
    if model_has_window_openings(bundle):
        measured = [o for fl in bundle.matterport.floors for e in fl.edges for o in e.openings
                    if o.type == "window"]
        m_area = sum((o.width_m or 0) * (o.height_m or 0) for o in measured)
        cross = (f"cross-check only, the scan measured {len(measured)} window openings "
                 f"({m_area:.1f} m2); vision saw {seen_count} ({seen_area:.1f} m2) in the "
                 f"panoramas read")
        out: list[Assumption] = []
        if room_fallback:
            measured_rooms = rooms_with_window_openings(bundle)
            per_room: dict[str, list] = defaultdict(lambda: [0.0, 0.0, []])
            for g, (_, area, conf, ps) in sizes.items():
                rid = g.split("#")[0]
                if rid.startswith("pano:") or rid in measured_rooms or not area:
                    continue
                per_room[rid][0] += area
                per_room[rid][1] = max(per_room[rid][1], conf)
                per_room[rid][2] += ps
            for g, (area, conf, ps) in sorted(per_room.items()):
                ev = _pano_ev(ps) + [EvidenceRef(
                    kind="matterport_field", ref=_OPENINGS_EV,
                    note="no window opening on this room's edges, so this one room uses the "
                         "vision fallback: plus or minus 30 percent (physics 02 DEF-03)")]
                out.append(_vision(f"window.{g}.area_m2", f"Window area of room {g} (vision fallback)",
                                   _spread(area, WINDOW_AREA_REL, "m2"),
                                   min(WINDOW_SIZE_CONFIDENCE, conf), ev))
        return out, cross
    if not sizes:
        return [], None
    seen_panos = [p for (_, _, _, ps) in sizes.values() for p in ps]
    conf = min(WINDOW_SIZE_CONFIDENCE,
               max(c for (_, _, c, _) in sizes.values()))
    note = ("the scan has no window openings, so windows come from vision: plus or minus 30 "
            "percent (physics 02 DEF-03); panoramas of one room within 6 m of each other count once")
    if not read_all:
        note += "; not every panorama was read, so the total may be low"
    tail = [EvidenceRef(kind="matterport_field", ref=_OPENINGS_EV, note=note)]
    out = []
    if seen_count:
        out.append(_vision("window.count", "Window count read from the panoramas",
                           _spread(float(seen_count), WINDOW_AREA_REL, "count", 1), conf,
                           _pano_ev(seen_panos) + tail))
    if seen_area > 0:
        out.append(_vision("window.area_m2", "Window area read from the panoramas",
                           _spread(seen_area, WINDOW_AREA_REL, "m2"), conf,
                           _pano_ev(seen_panos) + tail))
    return out, None


def _hvac(readings: list[PanoReading]) -> list[Assumption]:
    out: list[Assumption] = []

    def cue_note(pids: list[tuple[str, Optional[str]]]) -> list[EvidenceRef]:
        by_id = {r.pano_id: r for r in readings}
        evs = []
        for pid, note in pids:
            cues = by_id[pid].hvac.fields.get("cues") if by_id[pid].hvac else None
            extra = f"cues: {', '.join(cues)}" if cues else None
            evs.append((pid, "; ".join(x for x in (note, extra) if x) or None))
        return _pano_ev(evs)

    st = _categorical(readings, "hvac", "system_type")
    if st:
        v, conf, panos = st
        out.append(_vision("hvac.system_type", "HVAC system type", v, conf, cue_note(panos)))
    fuel = _categorical(readings, "hvac", "heating_fuel")
    if fuel:
        v, conf, panos = fuel
        out.append(_vision("hvac.heating_fuel", "Heating fuel", v, conf, _pano_ev(panos)))
    th = _categorical(readings, "hvac", "thermostat", skip=("none_seen",))
    if th:
        v, conf, panos = th
        out.append(_vision("hvac.thermostat_type", "Thermostat type", v, conf, _pano_ev(panos)))
    age = _categorical(readings, "hvac", "age_band")
    if age:
        v, conf, panos = age
        lo, ex, hi = AGE_BAND_YEARS[v]
        ev = _pano_ev(panos) + [EvidenceRef(kind="default_table", ref="DEF-05",
                                            note=f"equipment age band {v} read by vision")]
        out.append(_vision("hvac.install_year", "Year the HVAC equipment was installed",
                           Ranged(low=lo, expected=ex, high=hi, unit="year"), conf, ev))
    return out


def _water_heater(readings: list[PanoReading]) -> list[Assumption]:
    out: list[Assumption] = []
    seen = lambda s: bool(s.fields.get("visible"))        # noqa: E731
    t = _categorical(readings, "water_heater", "type", when=seen)
    if t:
        v, conf, panos = t
        out.append(_vision("dhw.type", "Water heater type", v, conf, _pano_ev(panos)))
    f = _categorical(readings, "water_heater", "fuel", when=seen)
    if f:
        v, conf, panos = f
        out.append(_vision("dhw.fuel", "Water heater fuel", v, conf, _pano_ev(panos)))
    return out


def _lighting(readings: list[PanoReading], kind: str) -> list[Assumption]:
    out: list[Assumption] = []
    w = _categorical(readings, "lighting", "fixture_type")
    if not w:
        return out
    v, conf, panos = w
    by_id = {r.pano_id: r for r in readings}
    evs = []
    for pid, note in panos:
        n = by_id[pid].lighting.fields.get("fixture_count")
        evs.append((pid, "; ".join(x for x in (note, f"{n} fixtures in view" if n is not None else None)
                                   if x) or None))
    ev = _pano_ev(evs)
    out.append(_vision("lighting.fixture_type", "Lighting fixture type", v, conf, ev))
    if kind == "office" and v in LPD_BY_FIXTURE:
        (lo, ex, hi), why = LPD_BY_FIXTURE[v]
        out.append(_vision("lighting.lpd", "Lighting power density", Ranged(low=lo, expected=ex,
                           high=hi, unit="W/m2"), conf,
                           ev + [EvidenceRef(kind="default_table", ref="DEF-10", note=why)]))
    return out


def assumptions_from_readings(bundle: PropertyBundle, readings: dict[str, PanoReading], *,
                              read_all: bool = True, room_fallback: bool = False) -> list[Assumption]:
    """Combine per-panorama readings into vision assumptions (pure, no model call)."""
    rs = [readings[k] for k in sorted(readings)]
    if not rs:
        return []
    panos = {p.id: p for p in bundle.matterport.panos}
    pano_rooms = {pid: (r.id if (r := pano_room(panos[pid], bundle.matterport.rooms)) else None)
                  for pid in readings if pid in panos}
    sizes, cross = _windows_from_vision(bundle, rs, pano_rooms, read_all, room_fallback)
    return (_glazing(rs, cross) + sizes + _hvac(rs) + _water_heater(rs)
            + _lighting(rs, building_kind(bundle)))


def read_interior(bundle: PropertyBundle, ask_model: Optional[AskModel],
                  get_bytes: Optional[GetBytes], *, max_panos: int = MAX_PANOS,
                  room_fallback: bool = False) -> VisionResult:
    """Read the panoramas and return assumptions, flags (none until A8) and warnings.

    ``ask_model`` None (the default until imagery may be sent out, SPEC 16) returns nothing:
    the lane then runs on vintage defaults.
    """
    if ask_model is None or get_bytes is None:
        return VisionResult([], [], ["no vision model supplied; vintage defaults apply"])
    try:
        selected = select_panos(bundle, max_panos)
        readings, warnings = read_panoramas(bundle, ask_model, get_bytes, max_panos)
        read_all = len(selected) == sum(1 for p in bundle.matterport.panos if p.face_paths)
        assumptions = assumptions_from_readings(bundle, readings, read_all=read_all,
                                                room_fallback=room_fallback)
    except Exception as exc:     # defensive: vision is optional, it must never stop a run
        return VisionResult([], [], [f"vision reading failed ({type(exc).__name__}); "
                                     f"vintage defaults apply"])
    return VisionResult(assumptions, [], warnings, readings)


def observe_interior(bundle: PropertyBundle, ask_model: Optional[AskModel] = None,
                     get_bytes: Optional[GetBytes] = None, *, max_panos: int = MAX_PANOS,
                     room_fallback: bool = False) -> tuple[list[Assumption], list[Flag]]:
    """S3 See, interior (workplan 3.2 ``observe_interior``), with the model call passed in."""
    r = read_interior(bundle, ask_model, get_bytes, max_panos=max_panos,
                      room_fallback=room_fallback)
    return r.assumptions, r.flags
