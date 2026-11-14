"""A25: every worked example of physics 04 ECO-01 to ECO-13, and the whole breakdown against
the priced example measures."""
import json
from pathlib import Path

import pytest

from backend import config
from backend.analysis.finance.economics import (
    airr, cash_scenario, cashflows, discounted_payback, default_escalation, economic_defaults,
    equivalent_escalation_rate, financial_breakdown, incentive_cashflows, irr, nominal_rate,
    npv_measure, present_values, real_rate, residual_value_linear, simple_payback, sir, spv, upv,
    upv_star)
from backend.schema import (EnergyUse, Incentive, MeasureResult, PropertyBundle, Ranged, RunResult)

EX = Path(__file__).resolve().parents[5] / "specs" / "examples"

# Example A of ECO-07 (reused in ECO-09 to ECO-11)
A = dict(net_upfront_usd=10000, savings_elec_usd=1500, savings_gas_usd=0, export_usd=0,
         om_saving_usd=100, d=0.03, e_elec=-0.005, e_gas=0, e_export=0, n=15)


def usd(low, expected, high):
    return Ranged(low=low, expected=expected, high=high, unit="USD")


# ---- ECO-01 to ECO-04 ----

def test_eco01_rates():
    assert real_rate(0.07, 0.04) == pytest.approx(0.02885, abs=1e-5)
    assert nominal_rate(0.03, 0.04) == pytest.approx(0.0712, abs=1e-5)
    assert real_rate(0.045, 0.0146) == pytest.approx(0.03, abs=1e-4)


def test_eco02_spv():
    assert 1000 * spv(0.03, 5) == pytest.approx(862.61, abs=0.01)


def test_eco03_upv():
    assert 100 * upv(0.03, 5) == pytest.approx(457.97, abs=0.01)
    assert upv(0.03, 15) == pytest.approx(11.938, abs=1e-3)
    assert upv(0.03, 20) == pytest.approx(14.877, abs=1e-3)
    assert upv(0.03, 25) == pytest.approx(17.413, abs=1e-3)
    assert upv(0.0, 7) == 7


def test_eco04_upv_star():
    assert 100 * upv_star(0.02, 0.03, 5) == pytest.approx(485.62, abs=0.01)
    assert upv_star(0.03, 0.03, 9) == 9                        # singular point
    assert upv_star(0.0, 0.03, 15) == pytest.approx(upv(0.03, 15))
    assert upv_star(-0.005, 0.03, 15) == pytest.approx(11.5030, abs=1e-4)


# ---- ECO-05, ECO-06 ----

def test_eco05_defaults_come_from_config_and_are_echoed():
    p = economic_defaults("los_angeles", "residential", useful_life_years=60)
    assert (p.discount_rate, p.nominal_discount_rate, p.inflation) == (
        config.DISCOUNT_RATE_REAL, config.DISCOUNT_RATE_NOMINAL, config.INFLATION)
    assert p.analysis_period_years == 40 == config.ANALYSIS_PERIOD_CAP_YEARS         # min(L, 40)
    assert economic_defaults("houston", "commercial", 15).analysis_period_years == 15
    assert "ECO-05" in p.source


def test_eco06_table_values_and_band():
    e, notes = default_escalation("houston", "commercial", "electricity", 20)
    assert e.expected == pytest.approx(0.0017) and notes == []
    assert (e.low, e.high) == (pytest.approx(0.0017 - 0.01), pytest.approx(0.0017 + 0.01))
    la, _ = default_escalation("los_angeles", "residential", "electricity", 25)
    assert la.expected == pytest.approx(-0.0018)


def test_eco06_between_columns_is_interpolated_and_flagged():
    e, notes = default_escalation("los_angeles", "residential", "electricity", 12)
    assert -0.0108 < e.expected < -0.0062 and notes and "interpolated" in notes[0]
    held, notes = default_escalation("los_angeles", "residential", "electricity", 5)
    assert held.expected == pytest.approx(-0.0108) and "held" in notes[0]


def test_eco06_equivalent_rate_from_an_index():
    index = {2026 + t: 1.02 ** t for t in range(0, 31)}
    assert equivalent_escalation_rate(index, 2026, 0.03, 20) == pytest.approx(0.02, abs=1e-9)
    flat = {2026 + t: 1.0 for t in range(0, 31)}
    assert equivalent_escalation_rate(flat, 2026, 0.03, 20) == pytest.approx(0.0, abs=1e-9)


# ---- ECO-07, ECO-08 ----

def test_eco07_example_a():
    pv_s, pv_i = present_values(**A)
    assert pv_s == pytest.approx(18448.32, abs=0.01)
    assert npv_measure(**A) == pytest.approx(8448.32, abs=0.01)
    flows = cashflows(A["net_upfront_usd"], 1500, 0, 0, 100, -0.005, 0, 0, 15)
    assert len(flows) == 16
    assert sum(cf / 1.03 ** t for t, cf in enumerate(flows)) == pytest.approx(8448.32, abs=0.01)


def test_eco08_residual_and_example_2():
    assert residual_value_linear(30000, 25, 15) == 12000
    assert 12000 * spv(0.03, 15) == pytest.approx(7702, abs=1)
    assert residual_value_linear(30000, 25, 25) == 0.0
    kw = dict(net_upfront_usd=30000, savings_elec_usd=2400, savings_gas_usd=0, export_usd=0, om_saving_usd=0,
              d=0.03, e_elec=0, e_gas=0, e_export=0, n=20, replacements=[(13, 3000)],
              residual_usd=residual_value_linear(30000, 25, 20))
    assert npv_measure(**kw) == pytest.approx(6985.14, abs=0.01)
    pv_s, pv_i = present_values(**kw)
    assert sir(pv_s, pv_i) == pytest.approx(1.243, abs=1e-3)
    flows = cashflows(30000, 2400, 0, 0, 0, 0, 0, 0, 20, replacements=[(13, 3000)], residual_usd=6000)
    assert sum(cf / 1.03 ** t for t, cf in enumerate(flows)) == pytest.approx(6985.14, abs=0.01)


# ---- ECO-09, ECO-10 ----

def test_eco09_sir():
    pv_s, pv_i = present_values(**A)
    assert sir(pv_s, pv_i) == pytest.approx(1.845, abs=1e-3)
    assert sir(71043, 27240) == pytest.approx(2.608, abs=1e-3)
    assert sir(100, 0) is None and sir(100, -5) is None


def test_eco10_airr_and_irr():
    assert airr(1.84483, 0.03, 15) == pytest.approx(0.0729, abs=1e-4)
    assert airr(2.61, 0.03, 20) == pytest.approx(0.0806, abs=1e-4)
    flows = cashflows(10000, 1500, 0, 0, 100, -0.005, 0, 0, 15)
    assert irr(flows) == pytest.approx(0.1312, abs=1e-4)
    assert airr(0.0, 0.03, 15) is None


def test_irr_is_none_when_not_unique_or_not_repaid():
    assert irr([-100, 10, -50, 200]) is None                         # a negative year after the outlay
    assert irr([-100, 5, 5, 5]) is None                              # undiscounted savings never repay
    assert irr([100, 10]) is None


# ---- ECO-11 ----

def test_eco11_paybacks():
    assert simple_payback(10000, 1600) == pytest.approx(6.25)
    flows = cashflows(10000, 1500, 0, 0, 100, -0.005, 0, 0, 15)
    assert discounted_payback(flows, 0.03) == pytest.approx(7.17, abs=0.01)
    assert discounted_payback(flows, 0.0) == pytest.approx(6.36, abs=0.01)


def test_zero_savings_gives_no_payback_not_a_division_error():
    assert simple_payback(10000, 0) is None and simple_payback(10000, -3) is None
    assert simple_payback(0, 0) == 0.0
    flows = cashflows(10000, 0, 0, 0, 0, 0, 0, 0, 15)
    assert discounted_payback(flows, 0.03) is None and irr(flows) is None


def test_a_later_replacement_that_undoes_the_payback_moves_it():
    flows = cashflows(1000, 400, 0, 0, 0, 0, 0, 0, 10, replacements=[(4, 2000)])
    plain = cashflows(1000, 400, 0, 0, 0, 0, 0, 0, 10)
    assert discounted_payback(flows, 0.0) > discounted_payback(plain, 0.0)


# ---- ECO-13 ----

def inc(kind, amount=3000, status="verified", eligibility="confirmed"):
    return Incentive(name=kind, kind=kind, amount_usd=usd(amount / 2, amount, amount * 2), status=status,
                     eligibility=eligibility, citation="c")


def test_eco13_incentive_timing():
    upfront, later = incentive_cashflows([inc("upfront_rebate", 500), inc("tax_credit"),
                                          inc("rebate_after_install", 100), inc("tax_deduction", 1000),
                                          inc("performance_payment"),
                                          inc("tax_credit", status="unverified"),
                                          inc("tax_credit", status="expired", eligibility="not_eligible")], None)
    assert upfront == 500 and later == [(1, 3000), (1, 100)]                  # deduction omitted: no tax rate
    assert 3000 * spv(0.03, 1) == pytest.approx(2912.62, abs=0.01)
    _, with_rate = incentive_cashflows([inc("tax_deduction", 1000)], 0.25)
    assert with_rate == [(1, 250.0)]
    _, high = incentive_cashflows([inc("tax_credit")], None, level="high")
    assert high == [(1, 6000)]


# ---- ECO-12: the cash scenario ----

def test_cash_scenario():
    s = cash_scenario(usd(800, 866.81, 900))
    assert s.kind == "cash" and s.eligible and s.financed_usd == 0 and s.annual_payment_usd == 0
    assert s.rate is None and s.term_years is None and s.program_sir is None
    assert s.net_cashflow_year1_usd.expected == 866.81 and s.notes


# ---- the whole breakdown ----

def house_pv():
    run = RunResult.model_validate_json((EX / "house" / "run_result.json").read_text())
    bundle = PropertyBundle.model_validate_json((EX / "house" / "property_bundle.json").read_text())
    m = next(x for x in run.measures if x.measure_id == "PV_ROOF")
    return run, bundle, m


def breakdown(m, run, bundle, **kw):
    f = m.finance
    return financial_breakdown(
        installed_cost_usd=f.installed_cost_usd, cost_source=f.cost_source, net_upfront_usd=f.net_upfront_usd,
        incentives=f.incentives, useful_life_years=f.useful_life_years,
        annual_om_change_usd=f.annual_om_change_usd, savings=m.savings, tariff=bundle.tariff,
        state=run.property.state, segment=run.property.segment,
        degradation_rate=(m.solar.degradation_rate if m.solar else 0.0) or 0.0, **kw)


def test_breakdown_reproduces_the_house_pv_example():
    run, bundle, m = house_pv()
    got, want = breakdown(m, run, bundle), m.finance
    assert got.npv_usd.expected == pytest.approx(want.npv_usd.expected, abs=0.5)
    assert got.sir == pytest.approx(want.sir, abs=2e-3)
    assert got.airr == pytest.approx(want.airr, abs=1e-3)
    assert got.irr == pytest.approx(want.irr, abs=2e-3)
    assert got.discounted_payback_years == pytest.approx(want.discounted_payback_years, abs=0.1)
    assert got.npv_sensitivity_usd == pytest.approx(want.npv_sensitivity_usd, abs=1.0)


def test_breakdown_echoes_config_and_is_ordered():
    run, bundle, m = house_pv()
    got = breakdown(m, run, bundle)
    assert got.discount_rate == config.DISCOUNT_RATE_REAL and got.analysis_period_years == 25
    assert got.electricity_escalation == pytest.approx(-0.0018) and got.gas_escalation == pytest.approx(-0.0047)
    assert got.npv_usd.low <= got.npv_usd.expected <= got.npv_usd.high
    assert got.simple_payback_years.low <= got.simple_payback_years.expected <= got.simple_payback_years.high
    assert got.simple_payback_years.expected == pytest.approx(10.42, abs=0.01)
    assert got.financing[0].kind == "cash" and got.financing[0].net_cashflow_year1_usd.expected == pytest.approx(866.81, abs=0.01)
    assert (got.sir > 1) == (got.npv_usd.expected > 0)
    assert breakdown(m, run, bundle) == got                      # deterministic


def test_user_discount_rate_is_echoed_and_changes_npv():
    run, bundle, m = house_pv()
    base = breakdown(m, run, bundle)
    higher = breakdown(m, run, bundle, discount_rate=0.07)
    assert higher.discount_rate == 0.07 and higher.npv_usd.expected < base.npv_usd.expected


def test_zero_savings_breakdown():
    run, bundle, m = house_pv()
    zero = Ranged(low=0, expected=0, high=0, unit="USD")
    none = m.savings.model_copy(update={"cost_usd": zero})
    got = breakdown(m.model_copy(update={"savings": none}), run, bundle)
    assert got.simple_payback_years is None and got.discounted_payback_years is None
    assert got.irr is None and got.airr is None and got.sir is not None and got.sir < 1
    assert got.npv_usd.expected < 0


@pytest.mark.parametrize("flavor", ["house", "office", "office_houston"])
def test_every_priced_example_measure_has_consistent_breakdowns(flavor):
    run = RunResult.model_validate_json((EX / flavor / "run_result.json").read_text())
    bundle = PropertyBundle.model_validate_json((EX / flavor / "property_bundle.json").read_text())
    n = 0
    for m in run.measures:
        if not m.finance or not m.savings or m.savings.cost_usd.expected <= 0:
            continue
        got = breakdown(m, run, bundle)
        assert got.npv_usd.low <= got.npv_usd.expected <= got.npv_usd.high
        assert got.analysis_period_years == min(m.finance.useful_life_years, 40)
        if got.sir is not None:
            assert (got.sir > 1) == (got.npv_usd.expected > 0), m.measure_id
        n += 1
    assert n >= 3


# ---- UNC-02: the range of an output ----

def test_unc02_worked_example():
    from backend.analysis.finance.economics import propagate
    f = lambda v: v["a"] * v["b"]
    low, high = propagate(f, {"a": 10000, "b": 0.133}, {"a": (8000, 13000), "b": (0.118, 0.160)})
    assert low == pytest.approx(1024.6, abs=0.1) and high == pytest.approx(1811.8, abs=0.1)


def test_npv_range_is_the_quadrature_of_one_at_a_time_runs():
    run, bundle, m = house_pv()
    got = breakdown(m, run, bundle)
    f = m.finance
    e = (1 + got.electricity_escalation) * (1 - m.solar.degradation_rate) - 1

    def npv(savings, cost):
        return npv_measure(cost, savings, 0, 0, -f.annual_om_change_usd, 0.03, e, got.gas_escalation, e, 25)
    y0 = npv(m.savings.cost_usd.expected, f.net_upfront_usd.expected)
    s_lo, s_hi = npv(m.savings.cost_usd.low, f.net_upfront_usd.expected), npv(m.savings.cost_usd.high, f.net_upfront_usd.expected)
    c_lo, c_hi = npv(m.savings.cost_usd.expected, f.net_upfront_usd.high), npv(m.savings.cost_usd.expected, f.net_upfront_usd.low)
    assert got.npv_usd.low == pytest.approx(y0 - ((y0 - s_lo) ** 2 + (y0 - c_lo) ** 2) ** 0.5, abs=0.5)
    assert got.npv_usd.high == pytest.approx(y0 + ((s_hi - y0) ** 2 + (c_hi - y0) ** 2) ** 0.5, abs=0.5)
