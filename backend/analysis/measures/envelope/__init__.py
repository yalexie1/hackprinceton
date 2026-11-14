"""S6 envelope measures ENV_ATTIC, ENV_AIRSEAL, ROOF_COOL (A17).

Plain functions over contract types, following the plug-in protocol of
`backend/analysis/measures/engine/engine.py`. The door registers them in one loop:

    from backend.analysis.measures import engine, envelope
    for mid, m in envelope.MEASURES.items():
        engine.register(mid, check=m.check, change=m.change, describe=m.describe,
                        formula_ids=m.formula_ids)
"""
from __future__ import annotations

from typing import Callable, NamedTuple, Optional

from . import airseal, attic, roof_cool
from .airseal import (check as airseal_check, change as airseal_change,  # noqa: F401
                      describe as airseal_describe)
from .attic import (check as attic_check, change as attic_change,  # noqa: F401
                    describe as attic_describe)
from .roof_cool import (check as roof_cool_check, change as roof_cool_change,  # noqa: F401
                        describe as roof_cool_describe)


class EnvelopeMeasure(NamedTuple):
    check: Optional[Callable]
    change: Callable
    describe: Callable
    formula_ids: tuple[str, ...]


MEASURES: dict[str, EnvelopeMeasure] = {
    "ENV_ATTIC": EnvelopeMeasure(attic.check, attic.change, attic.describe, attic.FORMULA_IDS),
    "ENV_AIRSEAL": EnvelopeMeasure(airseal.check, airseal.change, airseal.describe, ()),  # INF ids vary by flow; on the card
    "ROOF_COOL": EnvelopeMeasure(roof_cool.check, roof_cool.change, roof_cool.describe, roof_cool.FORMULA_IDS),
}

__all__ = ["MEASURES", "EnvelopeMeasure", "attic_check", "attic_change", "attic_describe",
           "airseal_check", "airseal_change", "airseal_describe", "roof_cool_check",
           "roof_cool_change", "roof_cool_describe"]
