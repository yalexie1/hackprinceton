"""A31 benchmarks: does the model look like real buildings? (physics 02 BEN, physics 01 PV-10)

- ``check_baseline``: site energy use intensity against RECS 2020 (homes) and CBECS 2018 (offices).
- ``check_pv``: the PV design's specific yield against PVGIS at the same orientation.

Both return ``(warnings, result)`` and never raise on missing inputs. Pure functions, no network.
Imported only by ``backend/analysis/api.py``.
"""
from .checks import check_baseline, check_pv, pv_inputs
from .eui import Band, EuiBenchmark, benchmark_eui
from .pv import Plane, PvCrossCheck, cross_check_pv, read_weather_csv

__all__ = ["Band", "EuiBenchmark", "Plane", "PvCrossCheck", "benchmark_eui", "check_baseline", "check_pv",
           "cross_check_pv", "pv_inputs", "read_weather_csv"]
