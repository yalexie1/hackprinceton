"""A18 systems measures: HVAC_HP, HVAC_RTU, LGT_LED (SPEC 6.2; physics 02 HVAC, LGT).

Plain functions over contract types, following the plug-in protocol of
`backend/analysis/measures/engine/engine.py`. The door registers them in one loop:

    from backend.analysis.measures import engine, systems
    for mid, (check, change, describe, formula_ids) in systems.MEASURES.items():
        engine.register(mid, change=change, describe=describe, check=check, formula_ids=formula_ids)

Each card lists the physics entries the measure itself uses; the simulation's entries and the
finance entries are added by the engine and S7. Pricing quantities in `params`:
HVAC_HP and HVAC_RTU `capacity_tons`, LGT_LED `lamps` (home) or `fixtures` (office), as
`backend/analysis/finance/costs/costs.py` reads them.
"""
from __future__ import annotations

from . import heat_pump, lighting, rooftop
from .heat_pump import check as hp_check, change as hp_change, describe as hp_describe  # noqa: F401
from .lighting import check as led_check, change as led_change, describe as led_describe  # noqa: F401
from .rooftop import check as rtu_check, change as rtu_change, describe as rtu_describe  # noqa: F401

# MeasureId -> (check, change, describe, formula_ids)
MEASURES = {
    heat_pump.MEASURE_ID: (heat_pump.check, heat_pump.change, heat_pump.describe, heat_pump.FORMULA_IDS),
    rooftop.MEASURE_ID: (rooftop.check, rooftop.change, rooftop.describe, rooftop.FORMULA_IDS),
    lighting.MEASURE_ID: (lighting.check, lighting.change, lighting.describe, lighting.FORMULA_IDS),
}

__all__ = ["MEASURES", "heat_pump", "lighting", "rooftop",
           "hp_check", "hp_change", "hp_describe", "rtu_check", "rtu_change", "rtu_describe",
           "led_check", "led_change", "led_describe"]
