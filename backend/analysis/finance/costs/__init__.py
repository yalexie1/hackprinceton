"""S7 Plan, costs and incentives (A24). Reached through backend.analysis.api.

`cost_fields` is the entry point: for a measure and its property it returns the cost fields of
`FinancialBreakdown` (installed cost and its source, useful life, O&M change, incentives, net
upfront cash). A measure with no verified cost raises `NoCostData`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from backend.analysis.finance.costs.costs import (CPI_FACTORS, NoCostData, adjust_cost,
                                                  annual_om_change, cost_table, measure_cost,
                                                  quantity_of, useful_life)
from backend.analysis.finance.costs.incentives import (counts_toward_net_upfront, incentives_for,
                                                       net_upfront, registry, utility_of)
from backend.schema import Incentive, MeasureResult, PropertySummary, Ranged


@dataclass
class CostFields:
    installed_cost_usd: Ranged
    cost_source: str
    useful_life_years: int
    annual_om_change_usd: float
    incentives: list[Incentive]
    net_upfront_usd: Ranged
    notes: list[str] = field(default_factory=list)      # e.g. an unverified useful life


def cost_fields(measure: MeasureResult, summary: PropertySummary, quantity: Optional[float] = None,
                extra: Optional[dict] = None) -> CostFields:
    q = quantity if quantity is not None else quantity_of(measure)
    if q is None:
        raise NoCostData("no_quantity", f"{measure.measure_id}: the quantity to price is unknown")
    cost, source = measure_cost(measure.measure_id, q, summary.segment)
    years, status = useful_life(measure.measure_id, summary.segment)
    incentives = incentives_for(measure, summary, q, cost, extra)
    notes = [] if status == "verified" else [
        f"useful life of {years} years is {status} (physics 04 COST-02)"]
    return CostFields(cost, source, years, annual_om_change(measure.measure_id, q), incentives,
                      net_upfront(cost, incentives), notes)


__all__ = ["CPI_FACTORS", "CostFields", "NoCostData", "adjust_cost", "annual_om_change",
           "cost_fields", "cost_table", "counts_toward_net_upfront", "incentives_for",
           "measure_cost", "net_upfront", "quantity_of", "registry", "useful_life", "utility_of"]
