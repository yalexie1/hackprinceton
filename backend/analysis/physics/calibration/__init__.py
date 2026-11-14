"""Bill calibration and measurement and verification (work package A6).

Formulas: specs/physics/04-economics-emissions-mv.md MV-02 (change-point and degree-day models),
MV-03 (fit statistics), MV-04 (calibration tolerances), MV-05 (fractional savings uncertainty) and
MV-06 (the calibration procedure). The simulation and `set_assumption` are passed in; nothing here
imports the door or another package of the lane.
"""
from .calibrate import (CANDIDATES, CalibrationResult, FuelSplit, Move, calibrate_to_bills)
from .changepoint import (ChangePointModel, DegreeDayModel, choose_degree_day, degree_days, fit_change_point,
                          fit_degree_day, fit_degree_day_at, monthly_mean_temps, predict)
from .stats import TOLERANCES, FitStats, calibration_ok, fit_statistics, model_acceptable
from .uncertainty import (SavingsUncertainty, fractional_savings_uncertainty, guarantee_level,
                          savings_uncertainty, t_value, y_factor_monthly)

__all__ = [
    "CANDIDATES", "CalibrationResult", "FuelSplit", "Move", "calibrate_to_bills",
    "ChangePointModel", "DegreeDayModel", "choose_degree_day", "degree_days", "fit_change_point",
    "fit_degree_day", "fit_degree_day_at", "monthly_mean_temps", "predict",
    "TOLERANCES", "FitStats", "calibration_ok", "fit_statistics", "model_acceptable",
    "SavingsUncertainty", "fractional_savings_uncertainty", "guarantee_level", "savings_uncertainty",
    "t_value", "y_factor_monthly",
]
