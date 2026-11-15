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
from pathlib import Path

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


# ---------------------------------------------------------------------------
# `_write_manifest` - the function that rewrites this module's own source.
#
# It has already corrupted itself once: a sentinel-boundary bug silently deleted
# `sids`, `spares`, `ManifestStale`, `resolve`, `_format_entries` and the sentinel
# constants themselves, and the only reason that was caught was an unrelated
# `ImportError` surfacing on the next full test run - `_write_manifest` itself
# raised nothing. These tests exercise the rewrite directly, against a throwaway
# fake module file rather than the real `demo_set.py`, so they can both prove the
# round trip is byte-exact outside the sentinels and prove the corrupting case
# (a rewrite that would drop a required name) is now a loud `RuntimeError`
# instead of a silent write.
# ---------------------------------------------------------------------------

def _fake_module(demo_set_body: str = '    ("OLDSID1234", "old/TX"),\n') -> str:
    """A minimal stand-in for `demo_set.py`'s own shape: a line before the
    sentinel block, the block itself, a line after. `demo_set._REQUIRED_NAMES`
    are stubbed so a well-formed rewrite passes `_assert_still_whole`."""
    return (
        "X = 1\n"
        + demo_set._MANIFEST_BEGIN
        + "\n"
        + "DEMO_SET = (\n"
        + demo_set_body
        + ")\n"
        + demo_set._MANIFEST_END
        + "\n"
        "def sids(): ...\n"
        "def spares(): ...\n"
        "def resolve(): ...\n"
        "class ManifestStale(RuntimeError): ...\n"
        "Y = 2\n"
    )


def test_write_manifest_replaces_only_the_interior(tmp_path):
    path = tmp_path / "fake_demo_set.py"
    path.write_text(_fake_module())

    demo_set._write_manifest((("NEWSID12345", "retail/CA"),), path=path)

    new_text = path.read_text()
    assert '("NEWSID12345", "retail/CA"),' in new_text
    assert "OLDSID1234" not in new_text
    # Everything outside the sentinel-bounded interior survives byte-for-byte.
    assert new_text.startswith("X = 1\n" + demo_set._MANIFEST_BEGIN + "\n")
    assert new_text.endswith(
        demo_set._MANIFEST_END + "\n"
        "def sids(): ...\n"
        "def spares(): ...\n"
        "def resolve(): ...\n"
        "class ManifestStale(RuntimeError): ...\n"
        "Y = 2\n"
    )


def test_write_manifest_is_valid_python_afterwards(tmp_path):
    path = tmp_path / "fake_demo_set.py"
    path.write_text(_fake_module())

    demo_set._write_manifest((("NEWSID12345", "retail/CA"),), path=path)

    compile(path.read_text(), str(path), "exec")   # raises SyntaxError if broken


def test_write_manifest_rejects_a_rewrite_that_would_drop_required_names(tmp_path):
    """The exact failure class task 3's review caught: a sentinel match landing
    in the wrong place and taking `sids`/`spares`/`resolve`/`ManifestStale` with
    it. Built here by a fake module whose sentinel-bounded interior is immediately
    followed by nothing - `_assert_still_whole` must refuse to write rather than
    silently producing a module with no required names, and the source file on
    disk must be untouched."""
    original = (
        "X = 1\n"
        + demo_set._MANIFEST_BEGIN
        + "\nDEMO_SET = ()\n"
        + demo_set._MANIFEST_END
        + "\n"
        # Deliberately no sids/spares/resolve/ManifestStale below.
    )
    path = tmp_path / "fake_demo_set.py"
    path.write_text(original)

    with pytest.raises(RuntimeError, match="sids"):
        demo_set._write_manifest((("NEWSID12345", "retail/CA"),), path=path)

    assert path.read_text() == original   # refused before a single byte was written


def test_manifest_sentinels_appear_exactly_once_in_source():
    """Pins the fix for the review's third finding: the sentinel markers are built
    by concatenation specifically so the contiguous marker text cannot also occur
    inside their own definitions or anywhere else in this module. If it ever does,
    `text.index` in `_write_manifest` stops being an unambiguous boundary search."""
    source = Path(demo_set.__file__).read_text()
    assert source.count(demo_set._MANIFEST_BEGIN) == 1
    assert source.count(demo_set._MANIFEST_END) == 1


# ---------------------------------------------------------------------------
# `with_replacements` / `apply_replacements` - the warm pass's write-back.
#
# Without it a warm pass's substitutions lived only in the operator's terminal:
# `demo_transfer pack` builds its archive from `sids()`, so the archive would omit
# every spare that actually warmed and carry every target that failed, and
# `demo_transfer check` would report those failures as `not_warmed` forever. These
# tests use a synthetic 3-target/3-spare manifest so the ordering and the reason
# strings can be asserted exactly, without the real 75-entry literal.
# ---------------------------------------------------------------------------

_SYNTHETIC = (
    ("T1", "office/TX/golden"),
    ("T2", "office/TX"),
    ("T3", "retail/CA"),
    ("S1", "office/TX"),
    ("S2", "retail/CA"),
    ("S3", "office/TX/golden"),
)


def test_with_replacements_swaps_the_slot_and_keeps_both_block_sizes():
    """A promoted spare takes the failed target's exact slot and the failed target
    takes the spare's exact slot - a swap, not an insert-and-append, so the 50/25
    split and the positional spare adjacency `select()` builds both survive."""
    out = demo_set.with_replacements(_SYNTHETIC, [("T2", "S1")], target_n=3)
    assert out == (
        ("T1", "office/TX/golden"),
        ("S1", "office/TX"),
        ("T3", "retail/CA"),
        ("T2", "office/TX"),
        ("S2", "retail/CA"),
        ("S3", "office/TX/golden"),
    )


def test_with_replacements_carries_each_sids_own_reason_including_golden():
    """A sid's `<use_type>/<state>` does not change by being promoted or demoted, and
    `/golden` belongs to the sid, not to the slot - whole rows move, so both hold by
    construction."""
    out = demo_set.with_replacements(_SYNTHETIC, [("T1", "S3")], target_n=3)
    assert out[0] == ("S3", "office/TX/golden")
    assert out[5] == ("T1", "office/TX/golden")


def test_with_replacements_applies_a_chain_demoting_every_failed_sid():
    """A spare that itself failed and was replaced again: `warm_all` records both
    hops, and both failed sids must end up in the spare block with the final
    survivor in the target slot."""
    out = demo_set.with_replacements(_SYNTHETIC, [("T2", "S1"), ("S1", "S3")], target_n=3)
    assert [sid for sid, _ in out[:3]] == ["T1", "S3", "T3"]
    assert sorted(sid for sid, _ in out[3:]) == ["S1", "S2", "T2"]


def test_with_replacements_refuses_a_hop_it_cannot_apply():
    """A hop whose sids are not where the manifest says they are means the caller's
    record and the manifest disagree; writing a half-applied manifest over a
    committed one is strictly worse than refusing."""
    with pytest.raises(ValueError, match="NOPE"):
        demo_set.with_replacements(_SYNTHETIC, [("NOPE", "S1")], target_n=3)
    with pytest.raises(ValueError, match="T3"):
        # T3 is a target, not a spare - it cannot be promoted into T2's slot.
        demo_set.with_replacements(_SYNTHETIC, [("T2", "T3")], target_n=3)


def test_with_replacements_is_pure():
    before = tuple(_SYNTHETIC)
    demo_set.with_replacements(_SYNTHETIC, [("T2", "S1")], target_n=3)
    assert _SYNTHETIC == before


def test_apply_replacements_writes_through_the_guarded_writer(tmp_path, monkeypatch):
    """`apply_replacements` must not be a second writer: it goes through
    `_write_manifest`, so the `_assert_still_whole` AST guard and the atomic
    `os.replace` apply unchanged. Written to a throwaway fake module, never the real
    `demo_set.py`."""
    path = tmp_path / "fake_demo_set.py"
    path.write_text(_fake_module())
    manifest = tuple(("T%d" % i, "office/TX") for i in range(1, 51)) + (
        ("S1", "retail/CA"),
    )
    monkeypatch.setattr(demo_set, "DEMO_SET", manifest)

    written = demo_set.apply_replacements([("T7", "S1")], path=path)

    assert written[6] == ("S1", "retail/CA")
    assert written[50] == ("T7", "office/TX")
    text = path.read_text()
    assert '("S1", "retail/CA"),' in text
    compile(text, str(path), "exec")   # the guard's own invariant, end to end


def test_apply_replacements_refuses_rather_than_writing_a_half_applied_manifest(
    tmp_path, monkeypatch
):
    path = tmp_path / "fake_demo_set.py"
    original = _fake_module()
    path.write_text(original)
    monkeypatch.setattr(demo_set, "DEMO_SET", _SYNTHETIC)

    with pytest.raises(ValueError):
        demo_set.apply_replacements([("T2", "S1")], path=path)   # target_n is 50 here
    assert path.read_text() == original
