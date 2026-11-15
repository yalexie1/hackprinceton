"""Tests for the live reach probe (package D-warm, task 1).

Every test monkeypatches `index.summaries()` rather than depending on a real
index: this worktree has no `data/cache/` kit mirror (it is git-ignored and lives
only in the main checkout), and `index.summaries()` returns empty with no mirror -
a test that relied on the real index would pass here for the wrong reason and
fail wherever a mirror happens to exist. `probe` is exercised with an injected
`post`, per `matterport.get_matterport_data_with_notes`'s own contract: an
injected poster bypasses the cache entirely, so these tests make no network call
and touch no cache file.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.data_layer import warm
from backend.schema import PropertySummary


def _summary(sid: str) -> PropertySummary:
    return PropertySummary(sid=sid, name=sid, segment="commercial", use_type="office")


@pytest.fixture(autouse=True)
def fake_index(monkeypatch):
    """Two indexed sids, in a stable order, for every test in this module."""
    monkeypatch.setattr(
        warm.index, "summaries",
        lambda: (_summary("SID_A"), _summary("SID_B")),
    )


def fake_post_ok(query: str, variables: dict) -> dict:
    return {"data": {"model": {"id": variables["id"]}}}


def fake_post_403(query: str, variables: dict) -> dict:
    return {"errors": [{"message": "403 Forbidden: invalid key/secret"}], "data": {"model": None}}


# ---------- uncached_sids ----------

def test_uncached_sids_skips_what_is_already_cached(tmp_path):
    root = tmp_path / "cache"
    (root / "SID_A").mkdir(parents=True)
    (root / "SID_A" / "bundle.json").write_text("{}")

    assert warm.uncached_sids(2, root=root) == ["SID_B"]


def test_uncached_sids_caps_at_n(tmp_path):
    root = tmp_path / "cache"
    assert warm.uncached_sids(1, root=root) == ["SID_A"]


def test_uncached_sids_defaults_to_the_real_cache_root_when_root_is_absent(monkeypatch, tmp_path):
    # No `root` given: falls back to `cache.cache_root()`, overridable the same way
    # the rest of the lane overrides it, via `DATA_LAYER_CACHE_DIR`.
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(tmp_path / "does-not-exist"))
    assert warm.uncached_sids(2) == ["SID_A", "SID_B"]


# ---------- probe ----------

def test_probe_reports_reachable_when_poster_returns_a_model(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(tmp_path / "does-not-exist"))
    out = warm.probe(1, post=fake_post_ok)
    assert out == [("SID_A", True, "ok")]


def test_probe_reports_unreachable_and_keeps_going_on_error(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(tmp_path / "does-not-exist"))
    out = warm.probe(2, post=fake_post_403)
    assert [r[1] for r in out] == [False, False]
    assert "403" in out[0][2]


def test_probe_forces_a_refresh_on_the_default_transport(monkeypatch):
    """`post is None` is the live path. Without `refresh=True`, a sid this probe
    already reached once would answer "reachable" straight from the Matterport
    payload cache on a later run - a gate that can pass without touching the
    network. This pins that `probe` always asks for a refresh on that path."""
    calls = []

    def fake_get_with_notes(sid, *, post=None, refresh=False):
        calls.append((sid, post, refresh))
        return (None, [])

    monkeypatch.setattr(warm.matterport, "get_matterport_data_with_notes", fake_get_with_notes)
    warm.probe(1)
    assert calls == [("SID_A", None, True)]


def test_probe_does_not_force_a_refresh_when_a_transport_is_injected(monkeypatch):
    """An injected `post` already bypasses the cache (`use_cache=post is None`), so
    `refresh` would be a no-op; pin it at `False` there so a reader is not misled
    into thinking it does something in that branch."""
    calls = []

    def fake_get_with_notes(sid, *, post=None, refresh=False):
        calls.append((sid, post, refresh))
        return (None, [])

    monkeypatch.setattr(warm.matterport, "get_matterport_data_with_notes", fake_get_with_notes)
    warm.probe(1, post=fake_post_ok)
    assert calls == [("SID_A", fake_post_ok, False)]
