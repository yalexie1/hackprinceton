"""WIN_REPLACE, WIN_FILM, WIN_SHADE (SPEC 6.2; physics 02 WIN-01, WIN-02, DEF-03).

Each measure changes only `u_value` or `shgc` of window surfaces. The zone model (A2) applies
the baseline interior shading F_int = 0.70 to every window, every hour (WIN-02), and reads
`Surface.shgc`. So a film or a shade is carried as an effective SHGC:

    shgc_after = shgc * F_measure

which gives `F_sh,gl = F_int * F_measure` inside WIN-01: the film or screen multiplies the
interior factor, it does not replace it. That is the arithmetic of the WIN-02 worked example
(film: 378.0 W x 0.70 = 264.6 W; screen: 378.0 x 0.30 = 113.4 W), whose text says "0.70 in
place of the interior factor" but whose numbers keep it.
"""
from __future__ import annotations

from typing import Optional

from backend.schema import (BaselineResult, BuildingModel, EvidenceRef, MeasureResult,
                            PropertyBundle, Ranged, Surface)

from .common import (EPS, anchors_for, assumption, assumption_evidence, facing_list,
                     from_vision, loss_surfaces, opening_evidence, scale, total_area)

# ---------------------------------------------------------------- constants (measure-local)

# DEF-03: WIN_REPLACE installs "double, low-e, non-metal frame" by default (S17 Table 69).
REPLACE_TYPE = "double_lowe_non_metal"
REPLACE_U = 2.16           # W/m2K (0.38 Btu/(h ft2 F))
REPLACE_SHGC = 0.44

# WIN-02 (S13 citing the MulTEA manual; tier B, single-sourced): exterior coefficients.
FILM_FACTOR = 0.70         # applied solar control film, C_ext
SCREEN_FACTOR = 0.30       # exterior solar screen, C_ext
# WIN-02 baseline interior factor the zone model already applies (S10); copied from
# physics/zone/constants.py INTERIOR_SHADING_BASELINE, which a measure may not import.
F_INT_BASELINE = 0.70
# WIN-02 interior devices (C1, C2), S13 citing ASHRAE HoF 2021 ch. 15 Table 14 (tier B), and the
# default covered fraction by family. Copied from physics/zone/constants.py.
INTERIOR = {
    "light_curtains": (0.84, 0.42), "medium_curtains": (0.94, 0.37), "dark_curtains": (0.98, 0.25),
    "light_shades": (0.82, 0.42), "medium_shades": (0.90, 0.38), "dark_shades": (0.98, 0.33),
    "light_blinds_closed": (0.78, 0.47), "medium_blinds_closed": (0.90, 0.41),
    "dark_blinds_closed": (0.98, 0.25), "light_blinds_half_open": (0.93, 0.38),
    "medium_blinds_half_open": (0.95, 0.26), "dark_blinds_half_open": (1.00, 0.19),
}
INTERIOR_COVER = {"curtains": 0.5, "shades": 0.5, "blinds": 1.0}

# The device WIN_SHADE proposes: an exterior solar screen (the house fixture's "exterior
# shading"). An interior key of INTERIOR also works (see shade_factor).
SHADE_DEVICE = "solar_screen"
# Windows WIN_SHADE treats: the sun side, true azimuth from east through south to west,
# inclusive. A design choice of this package, not a sourced figure.
SUN_SIDE_DEG = (90.0, 270.0)

NO_COST_WARNING = "no verified cost source; get a quote"   # physics 04 COST-01, section 9

# Assumption keys that record what is already fitted (written by vision or the user). Not yet in
# any fixture: proposed here for A7.
KEY_FILM = "window.film"
# What A7 (vision) writes: one categorical reading for the windows it saw. Its values that
# mean a shading device is already fitted, and the one that means film is.
KEY_VISION_SHADING = "window.shading"
VISION_SHADES = {"interior_blinds", "curtains", "exterior_shade", "overhang"}
VISION_FILM = "tinted_film"
KEY_EXT_SHADING = "window.exterior_shading"
KEY_INT_SHADING = "window.interior_shading"
_NONE = {"", "none", "no", "unknown", "false"}


def shade_factor(device: str, shgc: float) -> float:
    """F_measure for WIN_SHADE (WIN-02): the factor that multiplies SHGC so the zone model's
    F_int = 0.70 becomes the device's own factor. Exterior: C_ext. Interior: F_int(device) /
    0.70, from F_int = f_cov (C1 - C2 SHGC) + (1 - f_cov)."""
    if device == "solar_screen":
        return SCREEN_FACTOR
    if device == "solar_film":
        return FILM_FACTOR
    c1, c2 = INTERIOR[device]
    cov = next(v for k, v in INTERIOR_COVER.items() if k in device)
    return (cov * (c1 - c2 * shgc) + (1.0 - cov)) / F_INT_BASELINE


def _fitted(model: BuildingModel, key: str) -> Optional[str]:
    """The text of an assumption saying something is already fitted, or None."""
    a = assumption(model, key)
    if a is None:
        return None
    v = a.value
    if isinstance(v, bool):
        return a.label if v else None
    if isinstance(v, str):
        return None if v.strip().lower() in _NONE else v.replace("_", " ")
    return None


def _vision_shading(model: BuildingModel) -> Optional[str]:
    """A7's reading of the windows' shading, lower case, or None."""
    a = assumption(model, KEY_VISION_SHADING)
    if a is None or not isinstance(a.value, str):
        return None
    return a.value.strip().lower()


def _windows(model: BuildingModel) -> list[Surface]:
    return loss_surfaces(model, "window")


def _glazed(model: BuildingModel) -> list[Surface]:
    return [s for s in _windows(model) if s.shgc is not None]


def _sun_side(model: BuildingModel) -> list[Surface]:
    lo, hi = SUN_SIDE_DEG
    return [s for s in _glazed(model)
            if s.azimuth_deg is not None and lo - EPS <= s.azimuth_deg % 360.0 <= hi + EPS]


def _to_replace(model: BuildingModel) -> list[Surface]:
    return [s for s in _windows(model) if s.u_value.expected > REPLACE_U + EPS]


def _set(model: BuildingModel, ids: set[str], **fields) -> BuildingModel:
    """A deep copy with `fields(surface)` applied to the window surfaces in ids."""
    out = model.model_copy(deep=True)
    for s in out.surfaces:
        if s.id in ids and s.kind == "window":
            for name, fn in fields.items():
                setattr(s, name, fn(s))
    return out


def _n(count: int, word: str) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")


def _common_warnings(windows: list[Surface]) -> list[str]:
    if from_vision(windows):
        return ["Some window areas were read from panoramas, not measured (plus or minus 30 percent, "
                "physics 02 DEF-03)."]
    return []


def _evidence(model: BuildingModel, windows: list[Surface], table: str, note: str) -> list[EvidenceRef]:
    ev = opening_evidence(windows)
    if from_vision(windows):
        for e in assumption_evidence(model, ["window.area_m2"]):
            if e.kind != "matterport_field" and e not in ev:
                ev.append(e)
    for e in assumption_evidence(model, ["window.type", "window.u_value", "window.shgc"]):
        if e not in ev:
            ev.append(e)
    ev.append(EvidenceRef(kind="default_table", ref=table, note=note))
    return ev


# ---------------------------------------------------------------- WIN_REPLACE

REPLACE_FORMULA_IDS = ("DEF-03", "ENV-03", "WIN-01", "ZON-04", "EMI-01")


def replace_check(bundle: PropertyBundle, model: BuildingModel) -> Optional[tuple[str, str]]:
    if not _windows(model):
        return ("feasibility", "The model has no window to replace.")
    if not _to_replace(model):
        return ("already_done", f"every window is already double low-e or better "
                                f"(U {REPLACE_U} W/m2K or lower).")
    return None


def replace_change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel:
    ids = {s.id for s in _to_replace(model)}
    return _set(model, ids,
                u_value=lambda s: Ranged(low=REPLACE_U, expected=REPLACE_U, high=REPLACE_U, unit=s.u_value.unit),
                shgc=lambda s: Ranged(low=REPLACE_SHGC, expected=REPLACE_SHGC, high=REPLACE_SHGC,
                                      unit=s.shgc.unit if s.shgc is not None else "-"))


def replace_describe(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
                     before: BaselineResult, options: dict) -> MeasureResult:
    wins = _to_replace(model)
    area = total_area(wins)
    old_u = max(s.u_value.expected for s in wins)
    warnings = _common_warnings(wins)
    lower = [s for s in wins if s.shgc is not None and s.shgc.expected < REPLACE_SHGC - EPS]
    if lower:
        warnings.append(f"The default new glass has SHGC {REPLACE_SHGC}, above the present "
                        f"{min(s.shgc.expected for s in lower):g} on {_n(len(lower), 'window')}: solar gain "
                        f"rises there. A lower-SHGC low-e product changes the result.")
    warnings.append("New windows are the DEF-03 default, double low-e with a non-metal frame "
                    f"(U {REPLACE_U}, SHGC {REPLACE_SHGC}); the rating of the product actually "
                    "quoted replaces it.")
    return MeasureResult(
        measure_id="WIN_REPLACE", title="Window replacement", applicable=True,
        description=(f"Replace {_n(len(wins), 'window')}, {area:g} m2 on the {facing_list(wins)} walls, "
                     f"with double low-e units: U from {old_u:g} to {REPLACE_U} W/m2K."),
        params={"glazing_area_m2": area, "window_surface_ids": [s.id for s in wins],
                "window_type_after": REPLACE_TYPE, "u_after_w_m2k": REPLACE_U, "shgc_after": REPLACE_SHGC},
        anchors=anchors_for(bundle, wins, "windows" if len(wins) > 1 else "window"),
        evidence=_evidence(model, wins, "DEF-03", f"{REPLACE_TYPE.replace('_', ' ')}: U {REPLACE_U}, "
                                                  f"SHGC {REPLACE_SHGC} (S17 Table 69)"),
        formula_ids=list(REPLACE_FORMULA_IDS), warnings=warnings)


# ---------------------------------------------------------------- WIN_FILM

FILM_FORMULA_IDS = ("WIN-02", "ZON-04", "EMI-01")


def film_check(bundle: PropertyBundle, model: BuildingModel) -> Optional[tuple[str, str]]:
    if not _windows(model):
        return ("feasibility", "The model has no window to film.")
    if not _glazed(model):
        return ("feasibility", "No window in the model has a solar heat gain coefficient.")
    done = _fitted(model, KEY_FILM)
    if done:
        return ("already_done", f"solar control film is already fitted ({done}).")
    if _vision_shading(model) == VISION_FILM:
        return ("already_done", "tinted film is already on the windows (seen in the panoramas).")
    return None


def film_change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel:
    ids = {s.id for s in _glazed(model)}
    return _set(model, ids, shgc=lambda s: scale(s.shgc, FILM_FACTOR, FILM_FACTOR, FILM_FACTOR))


def film_describe(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
                  before: BaselineResult, options: dict) -> MeasureResult:
    wins = _glazed(model)
    area = total_area(wins)
    warnings = _common_warnings(wins) + [
        f"The film factor {FILM_FACTOR} is single-sourced (physics 02 WIN-02, section 10 tier B); the "
        "film maker's rated SHGC for this glass replaces it.",
        "The film stays on all year, so it also cuts useful winter solar gain; the saving is net of that.",
        NO_COST_WARNING]
    return MeasureResult(
        measure_id="WIN_FILM", title="Solar control window film", applicable=True,
        description=(f"Film on the {facing_list(wins)} glazing, {area:g} m2, to cut solar heat gain: "
                     f"SHGC times {FILM_FACTOR}."),
        params={"glazing_area_m2": area, "window_surface_ids": [s.id for s in wins],
                "film_factor": FILM_FACTOR},
        anchors=anchors_for(bundle, wins, "glazing"),
        evidence=_evidence(model, wins, "WIN-02", f"applied solar film, C_ext = {FILM_FACTOR}, multiplied "
                                                  f"with the interior factor {F_INT_BASELINE}"),
        formula_ids=list(FILM_FORMULA_IDS), warnings=warnings)


# ---------------------------------------------------------------- WIN_SHADE

SHADE_FORMULA_IDS = ("WIN-02", "ZON-04", "EMI-01")


def shade_check(bundle: PropertyBundle, model: BuildingModel) -> Optional[tuple[str, str]]:
    if not _windows(model):
        return ("feasibility", "The model has no window to shade.")
    for key in (KEY_EXT_SHADING, KEY_INT_SHADING):
        done = _fitted(model, key)
        if done:
            return ("already_done", f"{done} fitted on the windows.")
    seen = _vision_shading(model)
    if seen in VISION_SHADES:
        return ("already_done", f"{seen.replace('_', ' ')} fitted on the windows (seen in the panoramas).")
    if not _sun_side(model):
        return ("feasibility", "No window faces east, south or west, where shading pays.")
    return None


def shade_change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel:
    ids = {s.id for s in _sun_side(model)}
    f = lambda g: shade_factor(SHADE_DEVICE, g)   # noqa: E731
    return _set(model, ids, shgc=lambda s: scale(s.shgc, f(s.shgc.low), f(s.shgc.expected), f(s.shgc.high)))


def shade_describe(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
                   before: BaselineResult, options: dict) -> MeasureResult:
    wins = _sun_side(model)
    area = total_area(wins)
    exterior = SHADE_DEVICE in ("solar_screen", "solar_film")
    device = "exterior solar screens" if SHADE_DEVICE == "solar_screen" else SHADE_DEVICE.replace("_", " ")
    factor = round(shade_factor(SHADE_DEVICE, wins[0].shgc.expected), 4)
    facing = facing_list(wins)
    warnings = _common_warnings(wins) + [
        (f"The screen factor {SCREEN_FACTOR} is single-sourced (physics 02 WIN-02, section 10 tier B)."
         if SHADE_DEVICE == "solar_screen" else
         "Interior shading coefficients come from S13 citing ASHRAE (physics 02 WIN-02, tier B)."),
        "The shades are modelled in place all year, so winter solar gain is lost too: an upper bound on "
        "the winter penalty for operable shades.",
        NO_COST_WARNING]
    return MeasureResult(
        measure_id="WIN_SHADE", title=f"{'Exterior' if exterior else 'Interior'} shading on the {facing} windows",
        applicable=True,
        description=f"{device.capitalize()} over {_n(len(wins), facing + ' window')}, {area:g} m2.",
        params={"window_surface_ids": [s.id for s in wins], "glazing_area_m2": area,
                "device": SHADE_DEVICE, "shading_factor": factor},
        anchors=anchors_for(bundle, wins, "windows" if len(wins) > 1 else "window"),
        evidence=_evidence(model, wins, "WIN-02",
                           f"{device}: factor {factor} on SHGC, multiplied with the interior factor "
                           f"{F_INT_BASELINE}" if exterior else f"{device}: F_int replaces {F_INT_BASELINE}"),
        formula_ids=list(SHADE_FORMULA_IDS), warnings=warnings)
