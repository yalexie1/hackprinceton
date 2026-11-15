"""Shared pytest setup for every backend test.

The retired measures (engine.catalogue.RETIRED_MEASURES) are off in the product but their physics is
still tested, so every test here runs with them enabled. A test that checks the product default
removes the variable itself (see measures/engine/tests/test_retired.py)."""
import pytest

from backend.analysis.measures.engine import RETIRED_ENV


@pytest.fixture(autouse=True)
def _retired_measures_enabled_in_tests(monkeypatch):
    monkeypatch.setenv(RETIRED_ENV, "1")
