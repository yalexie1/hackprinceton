"""DEF tables (physics 02 section 9): ordering, conversions, coverage of every year."""
from __future__ import annotations

import pytest

from backend.analysis.model.registry import tables as T


@pytest.mark.parametrize("name", sorted(T.ALL_ROW_TABLES))
def test_rows_are_ordered_and_carry_a_source(name):
    for r in T.ALL_ROW_TABLES[name]:
        assert r.low <= r.expected <= r.high, (name, r)
        assert r.ref.startswith(("DEF-", "INF-", "LGT-")), (name, r)


@pytest.mark.parametrize("name", sorted(T.ALL_ROW_TABLES))
def test_imperial_values_convert_to_the_printed_si_values(name):
    for r in T.ALL_ROW_TABLES[name]:
        if r.ip is None:
            continue
        for si, ip in zip((r.low, r.expected, r.high), r.ip):
            # the printed SI values round the imperial ones; R-7 values are computed (tier B)
            assert si == pytest.approx(ip * r.ip_factor, abs=5e-3), (name, r)


@pytest.mark.parametrize("name", sorted(T.OFFICE_TYPE_TABLES))
def test_office_imperial_values_convert(name):
    for _, _, vals in T.OFFICE_TYPE_TABLES[name]:
        for si, ip in vals.values():
            assert si == pytest.approx(ip * T.U_IP_TO_SI, abs=5e-3), (name, si, ip)


def test_window_types_convert():
    for key, (u, shgc, (u_ip, _)) in T.WINDOW_TYPES.items():
        assert u == pytest.approx(u_ip * T.U_IP_TO_SI, abs=5e-3), key
        assert 0 < shgc < 1


def _covers(rows):
    for y in range(1800, 2101):
        assert sum(1 for r in rows if r.contains(y)) == 1, y


@pytest.mark.parametrize("name", sorted(k for k in T.ALL_ROW_TABLES
                                        if k not in ("ROOF_ABSORPTANCE", "DHW_UEF", "DSE", "OFFICE_HEATING",
                                                     "HOME_PLACEHOLDERS")))
def test_vintage_rows_cover_every_year_once(name):
    _covers(T.ALL_ROW_TABLES[name])


def test_type_rows_cover_every_year_once():
    for c in T.CLIMATES:
        _covers(T.HOME_WINDOW_TYPES[c])
    _covers(T.OFFICE_COOLING)


def test_placeholders_are_marked():
    assert T.HOME_LPD_PLACEHOLDER.placeholder and T.HOME_PPD_PLACEHOLDER.placeholder
