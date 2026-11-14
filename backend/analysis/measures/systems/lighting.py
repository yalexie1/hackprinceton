"""LGT_LED: LED retrofit (SPEC 6.2; physics 02 LGT-01, LGT-03, DEF-10).

Offices: the lighting power density drops to the DEF-10 target, 6.5 W/m2, a placeholder with
no opened source (physics 02 section 10, tier A), carried with a wide range (SPEC 6.2).
Homes: LGT-01 with every lamp LED (F_led = 1, SAF = 1) against the benchmark-mix baseline
E_light,base: E_light = E_light,base x factor, applied to `lighting_w_per_m2` as that factor.
The heating and cooling interaction is the simulation's (LGT-03: no separate factor).
"""
from __future__ import annotations

from typing import Optional

from backend.schema import BaselineResult, BuildingModel, MeasureResult, PropertyBundle, Ranged

from ._common import anchor, evidence_of, floor_area_m2, number_value, scaled, set_assumption, text_value

MEASURE_ID = "LGT_LED"
FORMULA_IDS = ("LGT-01", "LGT-03")

# ---- offices (DEF-10). Destined for config / the measure library. ----
LED_LPD_W_M2 = 6.5            # DEF-10 placeholder for "already LED" and the LGT_LED target (tier A)
LED_LPD_HIGH_W_M2 = 10.76     # DEF-10 / S11 Table A-2: the 90.1-2004 density, the top of the wide range
LED_LPD_LOW_W_M2 = 6.5        # no density below the placeholder is sourced, so the range is one-sided

# ---- homes (LGT-01). ----
ER_LED_CURRENT = 15.0 / 90.0  # LGT-01: incandescent-to-LED efficacy ratio for current lamps (source 0.30)


def home_led_factor(er_led: float = ER_LED_CURRENT) -> float:
    """LGT-01 lamp-mix factor with F_led = 1 (F_inc = F_cfl = F_lf = 0, SAF = 1), relative to
    E_light,base. 0.6051 at the source's ER 0.30 (worked example), 0.4851 at 15/90."""
    mix = (0.0 + 0.34) + (0.0 - 0.21) * 0.27 + 1.0 * er_led + (0.0 - 0.13) * 0.17
    return mix * 1.0 * 0.9 + 0.1


# Fixture count, when no count is recorded (assumption lighting.fixture_count or
# lighting.lamp_count): placeholders with no opened source, destined for config.
OFFICE_M2_PER_TROFFER = 8.0   # one 2x4 troffer per 8 m2 of open-plan floor (judgment)
HOME_M2_PER_LAMP = 2.75       # one lamp per 2.75 m2 of home floor (judgment)

_LED_WORDS = ("led",)


def _is_home(model: BuildingModel) -> bool:
    return model.systems.occupancy_schedule == "home"


def check(bundle: PropertyBundle, model: BuildingModel) -> Optional[tuple[str, str]]:
    lamp = text_value(model, "lighting.lamp_type")
    if lamp in _LED_WORDS:
        return ("already_done", "the lamps are already LED.")
    if not _is_home(model) and model.systems.lighting_w_per_m2.expected <= LED_LPD_W_M2:
        return ("already_done", f"the lighting power density is already at or below the LED target of "
                                f"{LED_LPD_W_M2:g} W/m2 (physics 02 DEF-10).")
    return None


def _after_lpd(model: BuildingModel) -> Ranged:
    cur = model.systems.lighting_w_per_m2
    if _is_home(model):
        return scaled(cur, home_led_factor())
    # paired percentile by percentile and never above the existing density
    lo = min(LED_LPD_LOW_W_M2, cur.low)
    ex = min(LED_LPD_W_M2, cur.expected)
    hi = min(LED_LPD_HIGH_W_M2, cur.high)
    return Ranged(low=min(lo, ex), expected=ex, high=max(hi, ex), unit=cur.unit)


def change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel:
    out = model.model_copy(deep=True)
    after = _after_lpd(out)
    out.systems = out.systems.model_copy(update={"lighting_w_per_m2": after})
    set_assumption(out, "lighting.lpd", after, f"{MEASURE_ID}: lighting power after the LED retrofit")
    return out


def _count(model: BuildingModel) -> tuple[int, bool]:
    """(count, estimated)."""
    key = "lighting.lamp_count" if _is_home(model) else "lighting.fixture_count"
    n = number_value(model, key)
    if n:
        return int(round(n)), False
    per = HOME_M2_PER_LAMP if _is_home(model) else OFFICE_M2_PER_TROFFER
    return max(1, int(round(floor_area_m2(model) / per))), True


def describe(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
             before: BaselineResult, options: dict) -> MeasureResult:
    n, estimated = _count(model)
    evidence = evidence_of(model, ("lighting.fixture_type", "lighting.lamp_type", "lighting.lamp_count",
                                   "lighting.fixture_count"))
    lamp = text_value(model, "lighting.lamp_type")
    warnings: list[str] = []
    if _is_home(model):
        params: dict = {"lamps": n}
        title = "LED lamps throughout"
        description = "Replace the remaining incandescent and halogen lamps with LED."
        label = "Ceiling fixtures"
        warnings.append(f"Uses the LED efficacy ratio 15/90 = 0.17 for current lamps instead of the source's "
                        f"0.30 (physics 02 LGT-01): home lighting falls to {home_led_factor():.4f} of the "
                        f"benchmark-mix baseline.")
        if estimated:
            warnings.append(f"Lamp count estimated at one lamp per {HOME_M2_PER_LAMP:g} m2 of floor, "
                            "not counted from the panoramas.")
    else:
        params = {"fixtures": n, "lpd_after_w_m2": changed.systems.lighting_w_per_m2.expected}
        title = "LED retrofit of ceiling troffers"
        kind = f"{lamp} " if lamp and lamp != "unknown" else ""
        description = f"Replace the {n} {kind}2x4 troffers with LED luminaires."
        label = f"{lamp.capitalize()} troffers" if lamp and lamp != "unknown" else "Ceiling troffers"
        warnings.append(f"Rests on the lighting power after retrofit, {LED_LPD_W_M2:g} W/m2, a placeholder "
                        "with no opened source (physics 02 DEF-10).")
        if estimated:
            warnings.append(f"Fixture count estimated at one 2x4 troffer per {OFFICE_M2_PER_TROFFER:g} m2 of "
                            "floor, not counted from the panoramas.")
    return MeasureResult(
        measure_id=MEASURE_ID, title=title, applicable=True, description=description,
        params=params, anchors=anchor(bundle, model, label, evidence, "ceiling"),
        evidence=evidence, formula_ids=list(FORMULA_IDS), warnings=warnings)
