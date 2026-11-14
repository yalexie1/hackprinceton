"""Tests of the agent lane never serve (or write) the developer's recorded live runs."""
import pytest


@pytest.fixture(autouse=True)
def no_recorded_demo_runs(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("AGENT_DEMO_DIR", str(tmp_path_factory.mktemp("demo")))
