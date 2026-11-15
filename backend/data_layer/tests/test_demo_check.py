"""Tests for the demo-day runbook command (package D-warm).

Only `main`'s process-level housekeeping is covered here: the per-property checks
are all live by design (`check_property` assembles against the sponsor APIs with
`refresh=True`), and `pytest backend -q` must make no network call, so every test
below injects a `check_property` double and never lets the real one run.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.data_layer import demo_check
from backend.data_layer.demo_check import Check


def test_main_removes_its_temporary_cache(monkeypatch):
    """`main` points `DATA_LAYER_CACHE_DIR` at a fresh temporary directory so a
    rehearsal cannot leave bundles in the real cache - but nothing ever deleted it.
    One cold run of the default set fills it with a full fetch of every property:
    about 75 MB for the 50-property manifest, left behind on a command teammates are
    told to run before each rehearsal."""
    seen: list[str] = []

    def fake_check_property(sid, **kwargs):
        cache_dir = os.environ["DATA_LAYER_CACHE_DIR"]
        seen.append(cache_dir)
        # Stand in for the ~1.5 MB a real cold check writes per property.
        (Path(cache_dir) / f"{sid}.json").write_text("{}")
        return [Check("bundle", "ok", "assembled")]

    monkeypatch.setattr(demo_check, "check_property", fake_check_property)

    assert demo_check.main(["SID_A"]) == 0
    assert len(seen) == 1
    assert not Path(seen[0]).exists()


def test_main_restores_a_cache_override_it_borrowed(monkeypatch, tmp_path):
    """The override is process-global. Leaving it pointing at a directory `main`
    just deleted would silently redirect anything that runs afterwards in the same
    process (another command in a script, the next test) at a path that no longer
    exists."""
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(
        demo_check, "check_property", lambda sid, **k: [Check("bundle", "ok", "")],
    )

    demo_check.main(["SID_A"])

    assert os.environ["DATA_LAYER_CACHE_DIR"] == str(tmp_path)
    assert tmp_path.exists()


def test_main_cleans_up_even_when_a_check_raises(monkeypatch):
    """A check that raises is not supposed to happen - `check_property` catches its
    own failures - but cleanup that only runs on the happy path is the kind that
    stops running exactly when a rehearsal is already going badly."""
    seen: list[str] = []

    def boom(sid, **kwargs):
        seen.append(os.environ["DATA_LAYER_CACHE_DIR"])
        raise RuntimeError("upstream exploded")

    monkeypatch.setattr(demo_check, "check_property", boom)

    with pytest.raises(RuntimeError):
        demo_check.main(["SID_A"])
    assert not Path(seen[0]).exists()


def test_keep_cache_leaves_the_real_cache_alone(monkeypatch, tmp_path):
    """`--keep-cache` makes no temporary directory, so there is nothing to clean up -
    and the real cache root must never be what gets deleted."""
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(
        demo_check, "check_property", lambda sid, **k: [Check("bundle", "ok", "")],
    )

    demo_check.main(["SID_A", "--keep-cache"])

    assert tmp_path.exists()
    assert os.environ["DATA_LAYER_CACHE_DIR"] == str(tmp_path)


def test_main_does_not_leave_live_mode_on_for_the_rest_of_the_process(monkeypatch):
    """`DATA_LAYER_LIVE=1` is how the whole lane decides to call sponsor APIs
    instead of replaying fixtures. `main` has to set it, but leaving it set turns
    anything that runs after it in the same process - the next command in a script,
    the next test - live without asking."""
    monkeypatch.delenv("DATA_LAYER_LIVE", raising=False)
    monkeypatch.setattr(
        demo_check, "check_property", lambda sid, **k: [Check("bundle", "ok", "")],
    )

    demo_check.main(["SID_A"])

    assert "DATA_LAYER_LIVE" not in os.environ


def test_golden_flag_selects_the_three_golden_sids(monkeypatch):
    """`--golden` is the two-minute mode: just the three `specs/examples/` fixtures,
    not the full 50-property manifest."""
    seen: list[str] = []
    monkeypatch.setattr(demo_check, "golden_sids", lambda: ["G1", "G2", "G3"])
    monkeypatch.setattr(demo_check, "demo_sids", lambda: ["D1"] * 50)
    monkeypatch.setattr(
        demo_check, "check_property",
        lambda sid, **k: (seen.append(sid), [Check("bundle", "ok", "")])[1],
    )

    demo_check.main(["--golden"])

    assert seen == ["G1", "G2", "G3"]


def test_no_args_still_defaults_to_the_full_demo_set(monkeypatch):
    """The default is unchanged by this change: no sids and no `--golden` still
    means the full 50-property manifest."""
    seen: list[str] = []
    monkeypatch.setattr(demo_check, "golden_sids", lambda: ["G1"])
    monkeypatch.setattr(demo_check, "demo_sids", lambda: ["D1", "D2"])
    monkeypatch.setattr(
        demo_check, "check_property",
        lambda sid, **k: (seen.append(sid), [Check("bundle", "ok", "")])[1],
    )

    demo_check.main([])

    assert seen == ["D1", "D2"]


def test_explicit_sids_win_over_golden(monkeypatch, capsys):
    """`--golden` combined with explicit sids must not silently drop either - the
    explicit sids win, exactly as they do against the full default, and the run
    says so rather than going quiet about which one it picked."""
    seen: list[str] = []
    monkeypatch.setattr(demo_check, "golden_sids", lambda: ["G1", "G2", "G3"])
    monkeypatch.setattr(
        demo_check, "check_property",
        lambda sid, **k: (seen.append(sid), [Check("bundle", "ok", "")])[1],
    )

    demo_check.main(["SID_A", "--golden"])

    assert seen == ["SID_A"]
    assert "golden" in capsys.readouterr().out.lower()
