"""Tests for the deterministic demo-set selection (package D-warm, task 2).

Every test passes `rows=` explicitly rather than depending on a real index:
this worktree has no `data/cache/` kit mirror, so `index.summaries()` returns
empty here - a test that relied on it would pass or fail for the wrong reason
depending on which checkout ran it. The fixture below is built generously (30
candidates per bucket per state) so the only tests that are meant to exercise
a shortage (`THIN_RETAIL`) say so by name.
"""
from __future__ import annotations

import re
from collections import Counter

import pytest

from backend.data_layer import demo_set, index
from backend.data_layer.demo_set import (
    DEMO_SET,
    QUOTAS,
    ManifestStale,
    SelectionShort,
    already_warm,
    resolve,
    select,
    sids,
    spares,
)
from backend.schema import PropertySummary


def _row(sid: str, use_type: str, state: str) -> PropertySummary:
    segment = "residential" if use_type in ("single_family", "multifamily_unit") else "commercial"
    return PropertySummary(sid=sid, name=sid, segment=segment, use_type=use_type, state=state)


def _bucket(use_type: str, per_state: int) -> list[PropertySummary]:
    rows = []
    for state in ("TX", "CA"):
        for i in range(per_state):
            rows.append(_row(f"{use_type.upper()}_{state}_{i}", use_type, state))
    return rows


#: Comfortably more than any bucket's 1.5x-scaled quota (the largest is office
#: at 22-23), so these tests exercise the happy path, not a shortage.
FAKE: list[PropertySummary] = [row for use_type in QUOTAS for row in _bucket(use_type, 30)]

#: Same as FAKE, but retail has only 3 candidates per state - short of the 15
#: (10 x 1.5) retail needs overall.
THIN_RETAIL: list[PropertySummary] = [
    row for use_type in QUOTAS
    for row in (_bucket(use_type, 30) if use_type != "retail" else _bucket("retail", 3))
]


def test_select_is_deterministic():
    assert [s.sid for s in select(rows=FAKE)] == [s.sid for s in select(rows=FAKE)]


def test_select_returns_fifty_plus_twenty_five_spares():
    out = select(rows=FAKE)
    assert len(out) == 75


def test_first_fifty_match_the_quotas():
    head = select(rows=FAKE)[:50]
    counts = Counter(s.use_type for s in head)
    assert counts == {
        "office": 15, "retail": 10, "multifamily_unit": 10,
        "single_family": 10, "other": 5,
    }


def test_every_bucket_spans_both_metros():
    head = select(rows=FAKE)[:50]
    for ut in QUOTAS:
        states = {s.state for s in head if s.use_type == ut}
        assert states == {"TX", "CA"}


def test_one_scan_per_property():
    out = select(rows=FAKE)
    keys = [index.property_key(s) for s in out]
    assert len(keys) == len(set(keys))


def test_already_warm_properties_win_their_bucket():
    # SID_WARM and SID_COLD are both office/TX; only SID_WARM is cached.
    rows = list(FAKE) + [_row("SID_WARM", "office", "TX"), _row("SID_COLD", "office", "TX")]
    head = select(rows=rows, prefer={"SID_WARM"})[:50]
    assert "SID_WARM" in [s.sid for s in head]


def test_already_warm_reads_the_cache_root(tmp_path):
    root = tmp_path / "cache"
    (root / "SID_WARM").mkdir(parents=True)
    (root / "SID_WARM" / "bundle.json").write_text("{}")
    (root / "SID_COLD").mkdir(parents=True)  # no bundle.json - not warm

    assert already_warm(root=root) == {"SID_WARM"}


def test_already_warm_is_empty_when_the_cache_root_does_not_exist(tmp_path):
    assert already_warm(root=tmp_path / "does-not-exist") == set()


def test_no_kit_mirror_raises_rather_than_returning_short():   # Review Focus 1
    with pytest.raises(SelectionShort, match="no kit mirror"):
        select(rows=())


def test_a_bucket_short_of_its_quota_names_the_bucket():       # Review Focus 2
    with pytest.raises(SelectionShort, match="retail"):
        select(rows=THIN_RETAIL)


# ---------------------------------------------------------------------------
# The committed manifest (task 3)
# ---------------------------------------------------------------------------

def test_manifest_holds_seventy_five_entries():
    assert len(DEMO_SET) == 75


def test_manifest_carries_ids_and_reasons_only():
    for sid, reason in DEMO_SET:
        assert re.fullmatch(r"[A-Za-z0-9]{11}", sid)
        assert re.fullmatch(r"[a-z_]+/(TX|CA)(/golden)?", reason)


def test_sids_defaults_to_the_target_fifty():
    assert len(sids()) == 50
    assert sids()[0] == DEMO_SET[0][0]


def test_spares_is_the_trailing_twenty_five():
    assert spares() == tuple(sid for sid, _ in DEMO_SET[50:])


def test_resolve_names_a_sid_the_index_no_longer_has(monkeypatch):   # Review Focus 4
    monkeypatch.setattr(demo_set, "DEMO_SET", (("MISSINGSID1", "office/TX"),))
    monkeypatch.setattr(index, "by_sid", lambda: {})
    with pytest.raises(ManifestStale, match="MISSINGSID1"):
        resolve()
