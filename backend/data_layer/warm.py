"""Live reach probe (task 1 of the demo-warm-50 plan).

The plan pre-warms 50 varied properties into the local cache so a demo is instant,
and the weighting that picks those 50 depends on drawing from the *whole* indexed
pool, not just the ones already cached. Today that pool is 42 already-cached scans
plus whatever the shared Matterport key can still reach. If the key cannot reach
anything new, the pool collapses back to those 42 and the plan is not deliverable
as specified - so this module proves reachability first, cheaply, before Task 2
spends any effort on selection.

`probe` draws its sample from `uncached_sids`, not from the index at large: a sid
with an assembled bundle already proves nothing about whether the key can still
reach it. That alone is not enough to guarantee a live call, though - see the
`refresh` note on `probe` below: without it, a sid this probe already reached
once answers "reachable" from the Matterport payload cache on every later run,
which is not what Task 1 is for.

**Honouring the shared rate limit.** `MIN_INTERVAL_S` (0.25 s) is a key shared with
every other team at the hackathon, so this module never posts GraphQL directly -
every reachability check goes through
`matterport.get_matterport_data_with_notes`, which already throttles and already
turns a response with both `errors` and a populated model into a documented
success. `probe` does not re-decide that; it just reports what that call decided.

**One bad sid does not end the probe.** `get_matterport_data_with_notes` raises
`LookupError` only when `data.model` is unusable (a dead sid, an auth failure, a
network error surfaces the same way through whatever `post` does). `probe` catches
per sid and keeps going, because the whole point of probing several sids is that a
single 403 should not hide whether the other four are reachable.

**Zero results is a failure, not a vacuous pass.** `probe` has nothing to iterate
when `index.summaries()` is empty, and `all()` over an empty sequence is `True` -
so a gate built on that line alone would exit 0 having checked nothing. `main`
special-cases an empty result list and exits 1.

**`DATA_LAYER_CACHE_DIR` does not redirect the CoStar kit.** It only overrides
`cache.cache_root()` (where fetched payloads and bundles land). The kit mirror
`index.summaries()` reads from is `costar.kit_dir()`, which resolves
`<repo>/data/cache/costar/kit` from this module's own repo root and is overridden
only by `COSTAR_KIT_DIR`. Running this gate from a git worktree - which has no
`data/cache/` of its own - needs **both** env vars set, or `index.summaries()`
comes back empty, `uncached_sids` comes back empty, and `probe` silently checks
nothing. That is exactly the trap behind the zero-results case above.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Optional

from . import api, demo_check, demo_set, index, matterport
from .demo_check import Check
from .matterport import Poster

#: `assemble`/`verify` signatures `warm_one` calls by default and that an injected
#: replacement in a test must match closely enough to stand in for.
Assembler = Callable[..., object]
Verifier = Callable[..., list[Check]]


def uncached_sids(n: int, *, root: Optional[Path] = None) -> list[str]:
    """Up to `n` indexed sids with no `bundle.json` yet under the cache root.

    "Cached" here means the assembled bundle `api.py` writes to
    `<root>/<sid>/bundle.json` - the same marker `demo_transfer.py` uses to decide
    what a laptop already has - not the raw Matterport payload cache, because the
    question this answers is "does warming this sid still do useful work", and a
    bundle already on disk is the one case where it would not.

    Delegates the "has a `bundle.json`" check to `demo_set.already_warm` - task 2
    had to duplicate that primitive here because `warm.py` did not yet import
    `demo_set` and the other direction would have been circular. Task 4 makes this
    module import `demo_set` anyway (for `sids`/`spares`/`resolve`), so the
    duplication is reconciled here; `demo_set.already_warm` keeps its own
    docstring and is still called directly by `demo_set._generate`, which this
    module does not touch.
    """
    warmed = demo_set.already_warm(root)
    out: list[str] = []
    for summary in index.summaries():
        if summary.sid in warmed:
            continue
        out.append(summary.sid)
        if len(out) >= n:
            break
    return out


def probe(n: int = 5, *, post: Optional[Poster] = None) -> list[tuple[str, bool, str]]:
    """Reach-check `n` uncached sids. One `(sid, reachable, detail)` per sid.

    Never raises on an individual sid: a 403 or a dead model is recorded, not
    thrown, so the caller sees every result even when some are unreachable.

    On the default transport (`post is None`), `get_matterport_data_with_notes`
    passes `use_cache=True` - its cache is keyed by sid alone, with no notion of
    "uncached for this plan's purposes," so a sid this probe reached once would
    answer "reachable" from disk on every later run without the key being asked
    anything. That defeats the one thing this module exists to prove, so the live
    path forces `refresh=True`: skip the read, always call Matterport, write the
    fresh response over whatever was there. An injected `post` already bypasses
    the cache entirely (`use_cache=post is None`), so `refresh` is a no-op there
    and is left `False` for it.
    """
    results: list[tuple[str, bool, str]] = []
    for sid in uncached_sids(n):
        try:
            matterport.get_matterport_data_with_notes(sid, post=post, refresh=post is None)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            results.append((sid, False, str(exc)))
        else:
            results.append((sid, True, "ok"))
    return results


def _verify_without_refetch(sid: str, **kwargs) -> list[Check]:
    """The default `verify` for `warm_one`: `demo_check.check_property` with
    `refresh=False`.

    `check_property`'s *own* default (`refresh=True`) is correct for `demo_check`'s
    purpose - it measures cold worst-case fetch timings, which is the number worth
    knowing before a demo. But `warm_one` calls `verify` immediately after `assemble`
    has already fetched this same property live; taking that default here would
    fetch every property twice, doubling the cost of a pass that can already run up
    to an hour against Matterport keys shared with every other team at the
    hackathon. `refresh=False` serves the "bundle" check from the bundle `assemble`
    just wrote instead of fetching it again.
    """
    return demo_check.check_property(sid, refresh=False, **kwargs)


def warm_one(
    sid: str, *, assemble: Optional[Assembler] = None, verify: Optional[Verifier] = None
) -> tuple[bool, str]:
    """Assemble `sid` live and verify it. `(True, detail)` on success; `(False, reason)`
    on any disqualification - this never raises, because `warm_all` calls it once per
    property across a pass that may already have run for most of an hour, and one bad
    sid (a dead model, an `IncompleteBundle` with no georeference, a failed check) must
    not abort the rest.

    `assemble` defaults to `api.get_property_bundle`, called with `live=True` - the
    offline default returns a replayed fixture, which would make every property in a
    real pass "succeed" against data nobody fetched. `refresh=False` because a bundle
    already warmed earlier in this same pass (or by a previous run) should not be
    re-fetched for nothing; the point of warming is that the second read is free.

    `verify` defaults to `_verify_without_refetch` (see its docstring), called with
    `run_analysis=True` per the plan - a warmed property is meant to drive a demo end
    to end, not just sit in cache. Only a `fail` status disqualifies; a `warn` (an
    unresolved utility, a thin scan) is normal even on the golden three and must not
    throw away a property over it.

    Everything after `assemble` succeeds - calling `verify`, reading `.status` off
    each result, reading `.name`/`.detail` off the first failure - stays inside one
    `try`, not just the `verify(...)` call itself. A `verify` that returns
    successfully but malformed (not a `list[Check]`, or an item missing an attribute)
    would otherwise raise a bare `TypeError`/`AttributeError` *after* the call
    returned, which `warm_all` has nothing wrapped around - that exception would
    abort the whole pass exactly as badly as an un-caught `verify` exception would,
    which defeats the entire point of this function never raising.
    """
    assemble = assemble if assemble is not None else api.get_property_bundle
    verify = verify if verify is not None else _verify_without_refetch

    try:
        assemble(sid, live=True, refresh=False)
    except Exception as exc:  # noqa: BLE001 - a disqualification, not a crash
        return False, str(exc)

    try:
        checks = verify(sid, run_analysis=True)
        fails = [c for c in checks if c.status == "fail"]
        if fails:
            return False, f"{fails[0].name}: {fails[0].detail}"
    except Exception as exc:  # noqa: BLE001 - same: reported, not raised
        return False, str(exc)

    return True, "ok"


class SparesExhausted(RuntimeError):
    """Raised by `warm_all` when the spare pool ran out before the target count could
    be met. Carries the shortfall by name - `"<warmed> of <len(target)>"` - rather
    than a bare "ran out", because a pass that silently warmed fewer than planned is
    exactly the failure mode over-provisioning (see `demo_set`'s module docstring)
    exists to catch."""

    def __init__(self, warmed: int, target: int):
        self.warmed = warmed
        self.target = target
        super().__init__(
            f"spares exhausted: only {warmed} of {target} warmed"
        )


def warm_all(
    sids: Optional[list[str]] = None,
    spares: Optional[list[str]] = None,
    *,
    assemble: Optional[Assembler] = None,
    verify: Optional[Verifier] = None,
    log: Callable[[str], None] = print,
) -> dict:
    """Warm every sid in `sids` (default `demo_set.sids()`), replacing any
    disqualification with the next *same-bucket* sid from `spares` (default
    `demo_set.spares()`, already in replacement order - see `demo_set.select`'s
    docstring).

    **A replacement must come from the failed target's own bucket and state.**
    `demo_set.select`'s "a spare is adjacent to the target slot of its own bucket
    and state" guarantee is positional - true of the 75-entry tuple's row order,
    not of a flat FIFO pop over bare sids. Popping the spare pool's *head*
    regardless of bucket would hand (say) an `office/TX` spare to a failed
    `multifamily_unit/TX` target the moment failures land out of bucket order -
    plausible, since Task 1 established failures are order-independent - silently
    inflating one bucket and starving another while `{"warmed": [...]}` still
    reports fifty names and looks like success. `demo_set.buckets()` is the
    accessor that recovers each bare sid's `"<use_type>/<state>"` key from the
    manifest, so the replacement search can filter the spare pool down to sids
    that share the *original* target's bucket (every hop of a chain fills the
    same slot, so the bucket is fixed per target, not re-derived per hop).

    If no same-bucket spare remains, that target's slot is short - full stop, not
    a silent substitution from a different bucket. It counts toward the
    `SparesExhausted` shortfall below exactly like a target with no spares left
    at all.

    `demo_set.resolve()` runs first and its `ManifestStale` is let through unchanged:
    a sid the manifest carries but the live index no longer has must surface in the
    first second, not after an hour spent warming the other forty-nine.

    Returns `{"warmed": [...], "replaced": [(disqualified_sid, next_sid), ...]}`.
    `replaced` records every hop of a chain, not just the first: if a spare itself
    fails and a second spare is drawn, both hops appear, so a reader can see exactly
    which sid a warmed slot actually came from.

    Logs one line per sid tried (not per target slot), because a pass over fifty
    properties at a measured 2 s to 76 s each runs up to an hour, and a silent process
    that long looks hung.

    Raises `SparesExhausted` if some target slot cannot be filled - either the
    whole spare pool ran dry, or what remains of it shares no bucket with that
    slot's original target - before every target slot is filled. A shrunk demo
    set should be loud, not discovered by counting bundles afterwards.
    """
    demo_set.resolve()

    target = list(sids) if sids is not None else list(demo_set.sids())
    spare_pool = list(spares) if spares is not None else list(demo_set.spares())
    bucket_of = demo_set.buckets()

    warmed: list[str] = []
    replaced: list[tuple[str, str]] = []

    for i, original in enumerate(target, start=1):
        # `None` for a sid outside the committed manifest (every test fixture, and
        # any future caller passing ad-hoc sids): two such sids compare equal under
        # `==`, so the search below still finds a match rather than refusing one
        # for a reason it cannot name.
        bucket = bucket_of.get(original)
        current = original
        ok, detail = warm_one(current, assemble=assemble, verify=verify)
        while not ok:
            log(f"[{i}/{len(target)}] {current}: disqualified ({detail}) - "
                f"drawing a same-bucket spare")
            match_at = next(
                (j for j, s in enumerate(spare_pool) if bucket_of.get(s) == bucket),
                None,
            )
            if match_at is None:
                break
            replacement = spare_pool.pop(match_at)
            replaced.append((current, replacement))
            current = replacement
            ok, detail = warm_one(current, assemble=assemble, verify=verify)

        if ok:
            warmed.append(current)
            log(f"[{i}/{len(target)}] {current}: warmed ({detail})")
        else:
            log(f"[{i}/{len(target)}] {current}: disqualified ({detail}) - "
                f"no same-bucket spare left")

    if len(warmed) < len(target):
        raise SparesExhausted(len(warmed), len(target))

    return {"warmed": warmed, "replaced": replaced}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--probe", type=int, metavar="N",
        help="reach-check N uncached sids against the live Matterport key",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="warm and verify the full 50-property demo set, replacing failures "
             "from the 25 spares (up to an hour against the live keys)",
    )
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    if args.all:
        try:
            result = warm_all()
        except (demo_set.ManifestStale, SparesExhausted) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"\nwarmed {len(result['warmed'])} properties")
        if result["replaced"]:
            print("replacements:")
            for old, new in result["replaced"]:
                print(f"  {old} -> {new}")
        return 0

    if args.probe is not None:
        results = probe(args.probe)
        if not results:
            print(
                "probed 0 sids - index.summaries() returned nothing, most likely "
                "because the CoStar kit mirror is not reachable (both "
                "DATA_LAYER_CACHE_DIR and COSTAR_KIT_DIR need to point at it; see "
                "the module docstring). Treating this as a failure: a gate that "
                "checks nothing has not proven anything.",
                file=sys.stderr,
            )
            return 1
        for sid, reachable, detail in results:
            print(f"{sid}: {'reachable' if reachable else 'UNREACHABLE'} ({detail})")
        if len(results) < args.probe:
            print(
                f"note: only {len(results)} of the requested {args.probe} sids were "
                "available to probe (the uncached pool is smaller than N) - not "
                "treated as a failure on its own.",
                file=sys.stderr,
            )
        return 0 if all(reachable for _, reachable, _ in results) else 1

    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
