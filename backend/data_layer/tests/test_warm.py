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


@pytest.fixture(autouse=True)
def no_live_obliques(monkeypatch):
    """`warm_one`'s oblique fetch defaults to `api.get_obliques`, which is live.
    Every test in this module that does not inject its own `obliques` would
    otherwise reach Vexcel, and `pytest backend -q` must make no network call. The
    stub answers with all four directions, i.e. the uneventful case; tests about
    the oblique behaviour itself inject their own."""
    monkeypatch.setattr(
        warm.api, "get_obliques",
        lambda sid, **kwargs: ({d: f"{sid}-{d}.jpg" for d in warm._OBLIQUE_DIRECTIONS}, []),
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


# ---------- main ----------

def test_main_probe_exits_nonzero_on_zero_results(monkeypatch, capsys):
    """`all()` over an empty sequence is `True`, so without a special case a kit
    mirror that is not reachable (`index.summaries()` empty) would make the gate
    exit 0 having checked nothing. Zero probed sids must be a failure."""
    monkeypatch.setattr(warm.index, "summaries", lambda: ())
    rc = warm.main(["--probe", "5"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "probed 0 sids" in err


# ---------- warm_one / warm_all (task 4) ----------
#
# These tests always inject both `assemble` and `verify` - `pytest backend -q` must
# make no network call, and the production defaults (`api.get_property_bundle(...,
# live=True, ...)` and `demo_check.check_property(..., run_analysis=True)`) do
# exactly that. `warm_all`'s manifest check is bypassed the same way: `demo_set.
# resolve()` walks the real `DEMO_SET` literal against `index.by_sid()`, which is
# `lru_cache`d process-wide, so patching it per test (rather than the index it reads
# from) is what keeps these tests independent of whatever ran before them in the
# same `pytest` invocation.

from backend.data_layer.demo_check import Check


def ok_assemble(sid, **kwargs):
    """Succeeds for any sid - stands in for `api.get_property_bundle`."""
    return object()


def raises_incomplete(sid, **kwargs):
    """Stands in for an `IncompleteBundle` from assembly - a real disqualification,
    never a crash."""
    from backend.data_layer.api import IncompleteBundle

    raise IncompleteBundle(f"{sid}: no georeference, so climate cannot be built", [])


def ok_verify(sid, **kwargs):
    return [Check("bundle", "ok", "assembled")]


def fail_then_ok(sid, **kwargs):
    """Fails for BAD1, succeeds for everything else - the shape of a bad target
    sid that a spare then replaces cleanly."""
    if sid == "BAD1":
        raise RuntimeError("BAD1: dead model")
    return object()


def always_fail(sid, **kwargs):
    raise RuntimeError(f"{sid}: always fails")


def test_default_verify_does_not_force_a_refresh(monkeypatch):
    """`warm_one`'s default verifier used to be `demo_check.check_property` taken
    as-is, which defaults to `refresh=True` - correct for `demo_check`'s own
    cold-timing purpose, but `warm_one` calls it right after `assemble` has already
    fetched the same property live, so that default would fetch every property
    twice: once in `assemble`, once again in `verify`. Over a 50-property pass
    against Matterport keys shared with every other team at the hackathon, that
    silently doubles the cost of an hour-long run. This pins that the default
    verify path asks `check_property` for `refresh=False`."""
    calls = []

    def fake_check_property(sid, *, refresh=True, **kwargs):
        calls.append(refresh)
        return [Check("bundle", "ok", "assembled")]

    monkeypatch.setattr(warm.demo_check, "check_property", fake_check_property)
    ok, _ = warm.warm_one("SID_A", assemble=ok_assemble)
    assert ok is True
    assert calls == [False]


def test_a_warn_does_not_disqualify_a_property():
    ok, detail = warm.warm_one(
        "SID_A", assemble=ok_assemble,
        verify=lambda s, **k: [Check("utility", "warn", "")],
    )
    assert ok is True


def test_a_failed_check_disqualifies():
    ok, detail = warm.warm_one(
        "SID_A", assemble=ok_assemble,
        verify=lambda s, **k: [Check("mask", "fail", "0.1 of footprint")],
    )
    assert ok is False and "mask" in detail


def test_incomplete_bundle_disqualifies_without_raising():
    ok, detail = warm.warm_one("SID_A", assemble=raises_incomplete)
    assert ok is False and "no georeference" in detail


def test_malformed_verify_result_disqualifies_without_raising():
    """`verify` returning *successfully* but with something that is not a
    `list[Check]` (here, an object with no `.status`) must disqualify the sid, not
    raise a bare `AttributeError` out of `warm_one` - that attribute access used to
    sit outside the function's only `try`, and would have aborted `warm_all`'s
    whole pass exactly like an un-caught `verify` exception."""

    class NotACheck:
        pass

    ok, detail = warm.warm_one(
        "SID_A", assemble=ok_assemble, verify=lambda s, **k: [NotACheck()],
    )
    assert ok is False


def test_a_failure_is_replaced_by_the_next_spare(monkeypatch):
    """Neither "BAD1" nor "SPARE1" is in the real committed manifest, so
    `demo_set.buckets()` maps both to `None` and the bucket-matching search below
    finds SPARE1 by that trivial match - this only pins that a single disqualified
    target with one available spare gets replaced at all. It does NOT exercise
    bucket-matching itself (both sids have no bucket to match); that is
    `test_replacement_only_draws_from_the_failed_targets_own_bucket` below, which
    puts real bucket keys in play via a monkeypatched manifest."""
    monkeypatch.setattr(warm.demo_set, "resolve", lambda: None)
    out = warm.warm_all(
        ["BAD1"], ["SPARE1"], assemble=fail_then_ok, verify=ok_verify,
        log=lambda *_: None,
    )
    assert out["warmed"] == ["SPARE1"]
    assert out["replaced"] == [("BAD1", "SPARE1")]


#: A tiny manifest with two buckets in play, used by the tests below to pin that a
#: replacement is drawn from the failed target's own bucket/state, never just the
#: next sid in the spare list regardless of bucket.
_TWO_BUCKET_MANIFEST = (
    ("BAD1", "office/TX"),
    ("WRONG_BUCKET_SPARE", "retail/CA"),
    ("RIGHT_BUCKET_SPARE", "office/TX"),
)


def test_replacement_only_draws_from_the_failed_targets_own_bucket(monkeypatch):
    """`fail_then_ok` would happily succeed on WRONG_BUCKET_SPARE if it were ever
    tried (it only fails for "BAD1") - so if this picked it, the FIFO bug this test
    guards against (drawing whichever spare is first regardless of bucket) would
    pass silently. Asserting the exact replacement pins that WRONG_BUCKET_SPARE
    (retail/CA) is skipped in favour of RIGHT_BUCKET_SPARE (office/TX), the one
    sharing BAD1's own bucket/state."""
    monkeypatch.setattr(warm.demo_set, "resolve", lambda: None)
    monkeypatch.setattr(warm.demo_set, "DEMO_SET", _TWO_BUCKET_MANIFEST)
    out = warm.warm_all(
        ["BAD1"], ["WRONG_BUCKET_SPARE", "RIGHT_BUCKET_SPARE"],
        assemble=fail_then_ok, verify=ok_verify, log=lambda *_: None,
    )
    assert out["warmed"] == ["RIGHT_BUCKET_SPARE"]
    assert out["replaced"] == [("BAD1", "RIGHT_BUCKET_SPARE")]


def test_no_same_bucket_spare_is_a_shortfall_not_a_cross_bucket_substitution(monkeypatch):
    """OTHER_BUCKET_SPARE (retail/CA) must never fill BAD1's office/TX slot, even
    though it is the only spare available - a short bucket is a real shortfall,
    reported by `SparesExhausted`, not something papered over by borrowing a
    different bucket's spare."""
    manifest = (
        ("BAD1", "office/TX"),
        ("OTHER_BUCKET_SPARE", "retail/CA"),
    )
    monkeypatch.setattr(warm.demo_set, "resolve", lambda: None)
    monkeypatch.setattr(warm.demo_set, "DEMO_SET", manifest)
    with pytest.raises(warm.SparesExhausted, match="0 of 1"):
        warm.warm_all(
            ["BAD1"], ["OTHER_BUCKET_SPARE"],
            assemble=always_fail, verify=ok_verify, log=lambda *_: None,
        )


def test_exhausted_spares_report_short_and_do_not_claim_fifty(monkeypatch):
    """The brief's own draft of this test asserted `match="48 of 50"` while passing
    only two target sids - self-contradictory. The shortfall message is
    parameterised on the actual target count, so with 2 targets and both failing
    (no spares to draw) the message names `0 of 2`, not a number borrowed from the
    real 50-property plan."""
    monkeypatch.setattr(warm.demo_set, "resolve", lambda: None)
    with pytest.raises(warm.SparesExhausted, match="0 of 2"):
        warm.warm_all(
            ["B1", "B2"], [], assemble=always_fail, verify=ok_verify,
            log=lambda *_: None,
        )


def test_warm_all_lets_manifest_stale_propagate_before_any_fetching(monkeypatch):
    """`resolve()` must run before any assembly - a stale manifest should surface in
    the first second, not after an hour. `assemble`/`verify` are never called when
    `resolve` raises."""
    called = []

    def boom():
        raise warm.demo_set.ManifestStale("SID_X: in DEMO_SET but not in the live index")

    monkeypatch.setattr(warm.demo_set, "resolve", boom)

    def tripwire(sid, **kwargs):
        called.append(sid)
        return object()

    with pytest.raises(warm.demo_set.ManifestStale):
        warm.warm_all(["B1"], ["S1"], assemble=tripwire, verify=ok_verify)
    assert called == []


def test_warm_all_logs_per_property_progress(monkeypatch):
    """A pass over fifty properties can run up to an hour; silence that long looks
    hung, so every sid tried (targets and spares) must produce a log line."""
    monkeypatch.setattr(warm.demo_set, "resolve", lambda: None)
    lines = []
    warm.warm_all(
        ["BAD1", "OK1"], ["SPARE1"], assemble=fail_then_ok, verify=ok_verify,
        log=lines.append,
    )
    assert any("BAD1" in line for line in lines)
    assert any("SPARE1" in line for line in lines)
    assert any("OK1" in line for line in lines)


# ---------- main --all (task 4) ----------
#
# `main --all` now does two things besides `warm_all`: a `probe(1)` credential
# preflight, and - afterwards - a manifest write-back through
# `demo_set.apply_replacements`, which rewrites `demo_set.py` on disk. Every test
# below patches both, so none of them touches the network or the committed source
# file.


@pytest.fixture
def reachable_preflight(monkeypatch):
    monkeypatch.setattr(warm, "probe", lambda n=1: [("SID_A", True, "ok")])


@pytest.fixture
def recorded_write_back(monkeypatch):
    """`demo_set.apply_replacements` replaced by a recorder - calling the real one
    would rewrite the committed `demo_set.py` during a test run."""
    written = []
    monkeypatch.setattr(
        warm.demo_set, "apply_replacements",
        lambda replacements, path=None: written.append(list(replacements)),
    )
    return written


def test_main_all_reports_warmed_and_replacements(
    monkeypatch, capsys, reachable_preflight, recorded_write_back
):
    """Wiring only - `warm_all` itself is exercised directly above. `main --all`
    must never call the real `warm_all` here, so this patches it out rather than
    letting it fall through to the live defaults."""
    monkeypatch.setattr(
        warm, "warm_all",
        lambda: {"warmed": ["A", "B"], "replaced": [("BAD1", "A")],
                 "notes": [("B", "3 of 4 obliques (east, north, south)")]},
    )
    rc = warm.main(["--all"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "warmed 2" in out
    assert "BAD1 -> A" in out
    assert "3 of 4 obliques" in out


def test_main_all_writes_the_replacements_back_into_the_manifest(
    monkeypatch, capsys, reachable_preflight, recorded_write_back
):
    """The critical gap: a pass's substitutions existed only in the operator's
    terminal. `demo_transfer pack` builds its archive from `demo_set.sids()`, so
    without this write-back the archive omits every spare that warmed and carries
    every target that failed - a judge would be offered a property proven not to
    assemble."""
    monkeypatch.setattr(
        warm, "warm_all",
        lambda: {"warmed": ["S1"], "replaced": [("BAD1", "S1")], "notes": []},
    )
    assert warm.main(["--all"]) == 0
    assert recorded_write_back == [[("BAD1", "S1")]]
    assert "rewrote demo_set.DEMO_SET" in capsys.readouterr().out


def test_main_all_leaves_the_manifest_alone_when_nothing_was_replaced(
    monkeypatch, capsys, reachable_preflight, recorded_write_back
):
    """A clean pass must not rewrite a committed source file for no reason - a
    no-op diff on `demo_set.py` after every run would make a real substitution
    harder to spot in review."""
    monkeypatch.setattr(
        warm, "warm_all",
        lambda: {"warmed": ["A"], "replaced": [], "notes": []},
    )
    assert warm.main(["--all"]) == 0
    assert recorded_write_back == []
    assert "manifest unchanged" in capsys.readouterr().out


def test_main_all_survives_a_write_back_that_refuses(
    monkeypatch, capsys, reachable_preflight
):
    """`apply_replacements` refuses a hop it cannot apply, and `_write_manifest`
    refuses a rewrite that would drop a required name. Either one raising *after* an
    hour of warming must not take the result report down with it - the printed
    replacements are then the operator's record."""
    def boom(replacements, path=None):
        raise ValueError("BAD1: not in the first 50 manifest entries")

    monkeypatch.setattr(warm.demo_set, "apply_replacements", boom)
    monkeypatch.setattr(
        warm, "warm_all",
        lambda: {"warmed": ["S1"], "replaced": [("BAD1", "S1")], "notes": []},
    )
    assert warm.main(["--all"]) == 0
    captured = capsys.readouterr()
    assert "BAD1 -> S1" in captured.out
    assert "could not rewrite the manifest" in captured.err


def test_main_all_exits_nonzero_on_manifest_stale(monkeypatch, capsys, reachable_preflight):
    def boom():
        raise warm.demo_set.ManifestStale("SID_X: in DEMO_SET but not in the live index")

    monkeypatch.setattr(warm, "warm_all", boom)
    rc = warm.main(["--all"])
    assert rc == 1
    assert "SID_X" in capsys.readouterr().err


def test_main_all_exits_nonzero_on_spares_exhausted(
    monkeypatch, capsys, reachable_preflight, recorded_write_back
):
    def boom():
        raise warm.SparesExhausted(48, 50)

    monkeypatch.setattr(warm, "warm_all", boom)
    rc = warm.main(["--all"])
    assert rc == 1
    assert "48 of 50" in capsys.readouterr().err


def test_main_all_prints_and_persists_the_partial_result_of_an_exhausted_pass(
    monkeypatch, capsys, reachable_preflight, recorded_write_back
):
    """An hour of work must not vanish into a one-line stderr message. The slots that
    filled are still the record of which properties are good, and the substitutions
    among them still have to reach the manifest - otherwise `demo_transfer pack`
    packs the failures and omits the spares exactly as it would after a silent
    success."""
    def boom():
        raise warm.SparesExhausted(
            1, 2,
            {"warmed": ["S1"], "replaced": [("BAD1", "S1")],
             "notes": [("S1", "obliques unavailable (HTTPError: 429)")]},
        )

    monkeypatch.setattr(warm, "warm_all", boom)
    assert warm.main(["--all"]) == 1
    captured = capsys.readouterr()
    assert "warmed 1 properties" in captured.out
    assert "BAD1 -> S1" in captured.out
    assert "429" in captured.out
    assert recorded_write_back == [[("BAD1", "S1")]]


# ---------- the credential preflight (review finding 8) ----------

def test_main_all_aborts_before_warming_when_the_preflight_cannot_reach(monkeypatch, capsys):
    """Without `.env` sourced every sid fails with `MatterportAuthMissing`, the pass
    runs its full length fetching nothing and ends `SparesExhausted: 0 of 50` - loud,
    but naming the wrong cause, an hour late. One probe names the real one."""
    monkeypatch.setattr(
        warm, "probe",
        lambda n=1: [("SID_A", False, "MatterportAuthMissing: no MATTERPORT_API_TOKEN")],
    )

    def tripwire():
        raise AssertionError("warm_all must not run after a failed preflight")

    monkeypatch.setattr(warm, "warm_all", tripwire)
    assert warm.main(["--all"]) == 1
    assert "MatterportAuthMissing" in capsys.readouterr().err


def test_an_empty_preflight_does_not_abort_the_pass(monkeypatch, capsys, recorded_write_back):
    """`probe` draws from `uncached_sids`, which is empty both when the kit mirror is
    missing *and* when every indexed sid is already warm. The second is a fine state
    to start a pass in, and the first is caught a moment later by `resolve()`, so an
    empty probe must not be read as an unreachable key."""
    monkeypatch.setattr(warm, "probe", lambda n=1: [])
    monkeypatch.setattr(
        warm, "warm_all", lambda: {"warmed": ["A"], "replaced": [], "notes": []},
    )
    assert warm.main(["--all"]) == 0
    assert "nothing uncached to reach-check" in capsys.readouterr().err


# ---------- obliques (review finding 2) ----------
#
# `api._with_imagery` deliberately fetches only the ortho during bundle assembly
# (the lead's decision, board 2026-11-14). `demo_transfer.check` nevertheless
# requires four of four obliques before a sid counts as complete, so without a
# separate fetch here a flawless hour-long pass would end with 50 bundles, 50
# orthophotos and 50 lines of "0 of 4 obliques" on every teammate's laptop.


def test_default_assemble_is_live_and_does_not_refresh(monkeypatch):
    """The production default had no test at all: every other test injects an
    `assemble` that swallows `**kwargs` without asserting them. If `live=True` were
    ever dropped, `api.get_property_bundle` falls back to `_fixture_bundle`, the
    hour-long run "warms" 50 replayed fixtures, every check passes and nothing says
    so. `refresh=False` matters the other way - taking the refreshing default would
    re-fetch a bundle this same pass already warmed. This pins both, the way
    `test_default_verify_does_not_force_a_refresh` already pins the verifier."""
    calls = []

    def recording_bundle(sid, **kwargs):
        calls.append((sid, kwargs))
        return object()

    monkeypatch.setattr(warm.api, "get_property_bundle", recording_bundle)
    ok, _ = warm.warm_one("SID_A", verify=ok_verify)
    assert ok is True
    assert calls == [("SID_A", {"live": True, "refresh": False})]


def test_default_oblique_fetch_is_live(monkeypatch):
    """`get_obliques`'s own `live` default reads `DATA_LAYER_LIVE` from the
    environment; a warming pass must not depend on that being set, or it quietly
    fetches nothing from disk-only mode while reporting success."""
    calls = []

    def recording_obliques(sid, **kwargs):
        calls.append((sid, kwargs))
        return {d: f"{d}.jpg" for d in warm._OBLIQUE_DIRECTIONS}, []

    monkeypatch.setattr(warm.api, "get_obliques", recording_obliques)
    ok, detail = warm.warm_one("SID_A", assemble=ok_assemble, verify=ok_verify)
    assert (ok, detail) == (True, "ok")
    assert calls == [("SID_A", {"live": True})]


def test_obliques_are_not_fetched_for_a_disqualified_property():
    """No point paying the most rate-limited endpoint in the lane for a property
    that is not going into the demo set."""
    calls = []

    def recording_obliques(sid, **kwargs):
        calls.append(sid)
        return {}, []

    ok, _ = warm.warm_one(
        "SID_A", assemble=raises_incomplete, obliques=recording_obliques,
    )
    assert ok is False and calls == []


def test_a_failed_oblique_fetch_is_a_note_not_a_disqualification():
    """429 is the expected failure at `oriented/extract`. The bundle is assembled and
    verified and the orthophoto is on disk; spending a spare to replace a property
    over one missing tab would be strictly worse than shipping the note."""
    def boom(sid, **kwargs):
        raise RuntimeError("429 Too Many Requests")

    ok, detail = warm.warm_one(
        "SID_A", assemble=ok_assemble, verify=ok_verify, obliques=boom,
    )
    assert ok is True
    assert "429" in detail and "obliques unavailable" in detail


def test_a_short_oblique_fetch_is_reported_by_direction():
    """`get_obliques` leaves out a direction that 403s, 404s or 429s rather than
    failing the three that worked, so "fewer than four" is an ordinary outcome - and
    it is exactly what `demo_transfer check` will later call `incomplete`, so the
    operator should learn it now rather than on a teammate's laptop."""
    ok, detail = warm.warm_one(
        "SID_A", assemble=ok_assemble, verify=ok_verify,
        obliques=lambda sid, **k: ({"north": "n.jpg", "south": "s.jpg"}, []),
    )
    assert ok is True
    assert "2 of 4 obliques (north, south)" in detail


def test_warm_all_collects_oblique_notes_without_dropping_the_property(monkeypatch):
    monkeypatch.setattr(warm.demo_set, "resolve", lambda: None)
    out = warm.warm_all(
        ["OK1"], [], assemble=ok_assemble, verify=ok_verify,
        obliques=lambda sid, **k: ({"north": "n.jpg"}, []),
        log=lambda *_: None,
    )
    assert out["warmed"] == ["OK1"]
    assert out["notes"] == [
        ("OK1", "1 of 4 obliques (north) - the Side angle tab will be short")
    ]


def test_a_complete_pass_records_no_notes(monkeypatch):
    monkeypatch.setattr(warm.demo_set, "resolve", lambda: None)
    out = warm.warm_all(
        ["OK1"], [], assemble=ok_assemble, verify=ok_verify, log=lambda *_: None,
    )
    assert out["notes"] == []


# ---------- SparesExhausted carries the partial result (review finding 3) ----------

def test_spares_exhausted_carries_the_warmed_and_replaced_record(monkeypatch):
    """The raise happens at the end of a pass that may have run for most of an hour.
    Discarding `warmed`/`replaced` left the operator of an unattended run with
    nothing but terminal scrollback they may not still have."""
    def fails_every_bad(sid, **kwargs):
        if sid.startswith("BAD"):
            raise RuntimeError(f"{sid}: dead model")
        return object()

    monkeypatch.setattr(warm.demo_set, "resolve", lambda: None)
    monkeypatch.setattr(
        warm.demo_set, "DEMO_SET",
        (("BAD1", "office/TX"), ("BAD2", "office/TX"), ("SPARE1", "office/TX")),
    )
    with pytest.raises(warm.SparesExhausted) as caught:
        warm.warm_all(
            ["BAD1", "BAD2"], ["SPARE1"], assemble=fails_every_bad, verify=ok_verify,
            log=lambda *_: None,
        )
    # BAD1 is replaced by SPARE1, which warms; BAD2 has no spare left, so the pass is
    # one short - and that partial record is exactly what must survive the raise.
    assert caught.value.result["warmed"] == ["SPARE1"]
    assert caught.value.result["replaced"] == [("BAD1", "SPARE1")]


def test_a_malformed_oblique_result_is_a_note_not_a_crash():
    """Unpacking the fetcher's result sits inside `_fetch_obliques`'s own `try` for
    the same reason `warm_one`'s `.status` reads do: a `TypeError` raised *after* a
    successful call has nothing wrapped around it in `warm_all` and would abort the
    whole pass."""
    ok, detail = warm.warm_one(
        "SID_A", assemble=ok_assemble, verify=ok_verify,
        obliques=lambda sid, **k: "not a two-tuple",
    )
    assert ok is True
    assert "obliques unavailable" in detail
