"""UNC-02: one-at-a-time runs combined in quadrature, for several outputs at once."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Mapping


@dataclass(frozen=True)
class SensitivityRow:
    """One input's effect on one output (UNC-02, UNC-03)."""
    key: str
    output: str
    y_low_run: float
    y_high_run: float
    swing: float


def quadrature(y0: float, runs: Mapping[str, tuple[float, float]],
               groups: Mapping[str, str] | None = None) -> tuple[float, float]:
    """UNC-02. `runs[key] = (y at input low, y at input high)`. Inputs in one group add linearly,
    groups add in quadrature. Returns (y_low, y_high); y_low <= y0 <= y_high by construction."""
    groups = groups or {}
    lo_g: dict[str, float] = {}
    hi_g: dict[str, float] = {}
    for key, (ylo, yhi) in runs.items():
        g = groups.get(key, key)
        d1, d2 = ylo - y0, yhi - y0
        lo_g[g] = lo_g.get(g, 0.0) + min(d1, d2, 0.0)
        hi_g[g] = hi_g.get(g, 0.0) + max(d1, d2, 0.0)
    return (y0 - math.sqrt(sum(v * v for v in lo_g.values())),
            y0 + math.sqrt(sum(v * v for v in hi_g.values())))


def propagate(f: Callable[[dict], Mapping[str, float]], base: dict,
              ends: Mapping[str, tuple[object, object]],
              groups: Mapping[str, str] | None = None):
    """UNC-02 over every output of `f`. `base` holds the expected inputs; `ends[key] = (low, high)`
    for each input varied. Returns ({output: (low, expected, high)}, [SensitivityRow])."""
    y0 = dict(f(base))
    runs: dict[str, dict[str, tuple[float, float]]] = {k: {} for k in y0}
    rows: list[SensitivityRow] = []
    for key, (lo, hi) in ends.items():
        ylo = f({**base, key: lo})
        yhi = f({**base, key: hi})
        for out in y0:
            runs[out][key] = (ylo[out], yhi[out])
            rows.append(SensitivityRow(key, out, ylo[out], yhi[out], abs(yhi[out] - ylo[out])))
    result = {}
    for out, v0 in y0.items():
        lo, hi = quadrature(v0, runs[out], groups)
        result[out] = (lo, v0, hi)
    return result, rows
