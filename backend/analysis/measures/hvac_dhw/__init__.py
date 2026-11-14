"""S6 Measures HVAC_ECON, HVAC_DUCT, DHW_HPWH (A21). Registered by backend.analysis.api.

MEASURES maps each MeasureId to (check, change, describe, formula_ids), ready for
`engine.register(mid, check=..., change=..., describe=..., formula_ids=...)`.
"""
from backend.analysis.measures.hvac_dhw.hvac_dhw import (
    DUCT_FORMULAS, DUCT_REASON, ECON_FORMULAS, ECONOMIZER_LIMIT_C, HPWH_FORMULAS, HPWH_UEF,
    duct_change, duct_check, duct_describe, econ_change, econ_check, econ_describe,
    hpwh_change, hpwh_check, hpwh_describe, rooftop_units)

MEASURES = {
    "HVAC_ECON": (econ_check, econ_change, econ_describe, ECON_FORMULAS),
    "HVAC_DUCT": (duct_check, duct_change, duct_describe, DUCT_FORMULAS),
    "DHW_HPWH": (hpwh_check, hpwh_change, hpwh_describe, HPWH_FORMULAS),
}

__all__ = ["MEASURES", "DUCT_FORMULAS", "DUCT_REASON", "ECON_FORMULAS", "ECONOMIZER_LIMIT_C",
           "HPWH_FORMULAS", "HPWH_UEF", "duct_change", "duct_check", "duct_describe", "econ_change",
           "econ_check", "econ_describe", "hpwh_change", "hpwh_check", "hpwh_describe",
           "rooftop_units"]
