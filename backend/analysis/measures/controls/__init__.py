"""S6 Measures LGT_CTRL, PLUG_MGMT, CTRL_TSTAT (A22). Plug-ins for the A16 engine; the door
registers them:

    for mid, (check, change, describe, formula_ids) in controls.MEASURES.items():
        engine.register(mid, change=change, describe=describe, check=check, formula_ids=formula_ids)
"""
from backend.analysis.measures.controls.controls import (
    FORMULA_IDS, ctrl_tstat_change, ctrl_tstat_check, ctrl_tstat_describe, lgt_ctrl_change,
    lgt_ctrl_check, lgt_ctrl_describe, plug_mgmt_change, plug_mgmt_check, plug_mgmt_describe,
    plug_saving_share)

MEASURES = {
    "LGT_CTRL": (lgt_ctrl_check, lgt_ctrl_change, lgt_ctrl_describe, FORMULA_IDS["LGT_CTRL"]),
    "PLUG_MGMT": (plug_mgmt_check, plug_mgmt_change, plug_mgmt_describe, FORMULA_IDS["PLUG_MGMT"]),
    "CTRL_TSTAT": (ctrl_tstat_check, ctrl_tstat_change, ctrl_tstat_describe, FORMULA_IDS["CTRL_TSTAT"]),
}

__all__ = ["MEASURES", "FORMULA_IDS", "plug_saving_share",
           "lgt_ctrl_check", "lgt_ctrl_change", "lgt_ctrl_describe",
           "plug_mgmt_check", "plug_mgmt_change", "plug_mgmt_describe",
           "ctrl_tstat_check", "ctrl_tstat_change", "ctrl_tstat_describe"]
