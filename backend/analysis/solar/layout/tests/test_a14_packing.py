"""A14: LAY-01 packing and LAY-02 flat-roof rows against the physics 01 worked examples."""
from __future__ import annotations

import math
import random
import socket

import pytest
from shapely.geometry import Polygon, box

from backend.analysis.solar.layout import Module, pack_modules
from backend.analysis.solar.layout.packing import flat_grids, pack_grid, pitched_grids


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network call attempted")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


M = Module()


def test_lay01_rectangle_worked_example():
    r = box(0, 0, 9.0856, 4.5428)
    portrait, landscape = (len(pack_grid(r, g)) for g in pitched_grids(M))
    assert (portrait, landscape) == (14, 15)
    assert len(pack_modules(r, 1.722, 1.134)) == 15


def test_lay01_l_shape_worked_example():
    poly = Polygon([(0, 0), (9, 0), (9, 2.5), (5, 2.5), (5, 4.5), (0, 4.5)])
    assert [len(pack_grid(poly, g)) for g in pitched_grids(M)] == [11, 12]


def test_lay01_cells_inside_and_disjoint():
    poly = Polygon([(0, 0), (9, 0), (9, 2.5), (5, 2.5), (5, 4.5), (0, 4.5)])
    cells = pack_modules(poly, 1.722, 1.134)
    for i, c in enumerate(cells):
        assert poly.buffer(1e-6).contains(c)
        for d in cells[i + 1:]:
            assert c.intersection(d).area < 1e-9


def test_lay01_closed_form_on_random_rectangles():
    rng = random.Random(7)
    g = M.gap_m
    for _ in range(50):
        w, h = rng.uniform(0.5, 30), rng.uniform(0.5, 15)
        expect = max(math.floor((w + g) / (a + g)) * math.floor((h + g) / (b + g))
                     for a, b in ((M.short_m, M.long_m), (M.long_m, M.short_m)))
        assert len(pack_modules(box(0, 0, w, h), M.long_m, M.short_m)) == expect


def test_lay01_grid_search_on_notched_rectangle():
    """A rectangle with a notch far from the packed area forces the grid search."""
    w, h = 9.0856, 4.5428
    notched = Polygon([(0, 0), (w, 0), (w, h), (w - 0.01, h), (w - 0.01, h - 0.001), (0, h - 0.001)])
    # the notch removes a sliver 1 mm deep: the search must still find 15 landscape
    assert len(pack_modules(notched, 1.722, 1.134)) == 15


def test_lay02_flat_rows_pitch():
    grids = flat_grids(M)
    portrait = grids[0]
    assert portrait.pv == pytest.approx(1.722 / 0.70)
    assert portrait.ch == pytest.approx(1.722 * math.cos(math.radians(15)))
    # 20 m deep roof: rows at pitch 2.46 m, last row needs its footprint
    cells = pack_grid(box(0, 0, 10, 20), portrait)
    rows = math.floor((20 - portrait.ch) / portrait.pv) + 1
    cols = math.floor((10 + M.gap_m) / (M.short_m + M.gap_m))
    assert len(cells) == rows * cols
