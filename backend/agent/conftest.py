"""Tests of the agent lane never serve (or write) the developer's recorded live runs."""
import os

import pytest


@pytest.fixture(autouse=True)
def no_recorded_demo_runs(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("AGENT_DEMO_DIR", str(tmp_path_factory.mktemp("demo")))


@pytest.fixture(autouse=True)
def keep_the_data_layer_flag(monkeypatch):
    """A live run switches the data layer to live data by setting an environment variable; a test must not
    leave it set for the tests of other lanes."""
    before = os.environ.get("DATA_LAYER_LIVE")
    yield
    if before is None:
        os.environ.pop("DATA_LAYER_LIVE", None)
    else:
        os.environ["DATA_LAYER_LIVE"] = before
