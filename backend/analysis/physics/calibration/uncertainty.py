"""Savings and fractional savings uncertainty (physics 04, MV-05).

FSU = t * 1.26 * CV(RMSE) * sqrt((1 + 2/n) * (1/m)) / F           (uncorrelated residuals: monthly data)
with lag-1 autocorrelation rho:  sqrt((n/n') * (1 + 2/n') * (1/m)),  n' = n (1 - rho) / (1 + rho)

Source: BPA-EMP section 5.5 (reproducing ASHRAE Guideline 14 Annex B). t is Student's t, two-sided,
with n - p degrees of freedom. For a calibrated simulation (MV-06 step 6) the CV(RMSE) is the one of
the calibrated model against the bills with p equal to the number of assumptions the calibration
moved [J: Guideline 14's formula is written for a regression baseline; counting each tuned input as
a fitted parameter is this project's conservative reading].
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from scipy import stats as _st

ACCEPT_FSU_68 = 0.50     # "less than 50% of the annual reported savings, at a confidence level of 68%"


def t_value(confidence: float, dof: int) -> float:
    """Two-sided Student's t for `confidence` (0.68 -> the 0.84 quantile) and `dof` degrees of freedom."""
    if not 0 < confidence < 1:
        raise ValueError("confidence must be in (0, 1)")
    if dof < 1:
        raise ValueError("need at least one degree of freedom (n > p)")
    return float(_st.t.ppf(0.5 + confidence / 2.0, dof))


def y_factor_monthly(m: int) -> float:
    """BPA-EMP 5.5.1 refinement of the 1.26 constant for monthly data: Y = -0.00022 m^2 + 0.03306 m + 0.94054."""
    return -0.00022 * m * m + 0.03306 * m + 0.94054


def fractional_savings_uncertainty(cv_rmse: float, n: int, m: int, p: int, savings_fraction: float,
                                   confidence: float = 0.68, rho: float = 0.0, y: float = 1.26) -> float:
    """MV-05. `cv_rmse` as a fraction, computed with n - p in the denominator; `savings_fraction`
    F = E_save / E_baseline. Returns the half-width of the confidence interval over the savings."""
    if savings_fraction <= 0:
        return math.inf
    if not -1 < rho < 1:
        raise ValueError("rho must be in (-1, 1)")
    t = t_value(confidence, n - p)
    if rho == 0.0:
        root = math.sqrt((1.0 + 2.0 / n) * (1.0 / m))
    else:
        n_eff = n * (1.0 - rho) / (1.0 + rho)
        root = math.sqrt((n / n_eff) * (1.0 + 2.0 / n_eff) * (1.0 / m))
    return t * y * cv_rmse * root / savings_fraction


def guarantee_level(expected_savings: float, fsu_90: float) -> float:
    """MV-05 drafting rule [J]: guaranteed savings at most E_save * (1 - FSU_90), never below zero."""
    return max(0.0, expected_savings * (1.0 - fsu_90))


@dataclass(frozen=True)
class SavingsUncertainty:
    savings_kwh: float
    savings_fraction: float
    fsu_68: float
    fsu_90: float
    half_width_68_kwh: float
    half_width_90_kwh: float
    acceptable: bool               # FSU at 68 % at most 50 % (BPA-EMP 5.5, Guideline 14)
    guarantee_kwh: float           # MV-05 drafting rule
    note: str


def savings_uncertainty(cv_rmse: float, n: int, p: int, savings_kwh: float, baseline_kwh: float,
                        m: int = 12) -> SavingsUncertainty:
    """FSU at 68 % and 90 % for an expected annual saving, before the retrofit (F is the predicted
    savings fraction) or after it (F from the measured savings). `cv_rmse` must already carry the
    n - p denominator."""
    f = savings_kwh / baseline_kwh if baseline_kwh > 0 else 0.0
    f68 = fractional_savings_uncertainty(cv_rmse, n, m, p, f, 0.68)
    f90 = fractional_savings_uncertainty(cv_rmse, n, m, p, f, 0.90)
    ok = f68 <= ACCEPT_FSU_68
    hw68 = f68 * savings_kwh if math.isfinite(f68) else math.inf
    hw90 = f90 * savings_kwh if math.isfinite(f90) else math.inf
    if f <= 0:
        note = "no saving is expected, so its uncertainty is undefined"
    elif ok:
        note = (f"savings of {savings_kwh:,.0f} kWh ({f:.1%} of the baseline) can be verified on the bills: "
                f"+/- {hw68:,.0f} kWh at 68 % confidence, +/- {hw90:,.0f} kWh at 90 %")
    else:
        note = (f"savings of {savings_kwh:,.0f} kWh ({f:.1%} of the baseline) are too small to verify on the "
                f"bills: the uncertainty at 68 % confidence is {f68:.0%} of the saving (the limit is 50 %)")
    return SavingsUncertainty(savings_kwh=savings_kwh, savings_fraction=f, fsu_68=f68, fsu_90=f90,
                              half_width_68_kwh=hw68, half_width_90_kwh=hw90, acceptable=ok,
                              guarantee_kwh=guarantee_level(savings_kwh, f90) if math.isfinite(f90) else 0.0,
                              note=note)
