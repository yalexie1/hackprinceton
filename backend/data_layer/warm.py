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
from typing import Optional

from . import cache, index, matterport
from .matterport import Poster


def uncached_sids(n: int, *, root: Optional[Path] = None) -> list[str]:
    """Up to `n` indexed sids with no `bundle.json` yet under the cache root.

    "Cached" here means the assembled bundle `api.py` writes to
    `<root>/<sid>/bundle.json` - the same marker `demo_transfer.py` uses to decide
    what a laptop already has - not the raw Matterport payload cache, because the
    question this answers is "does warming this sid still do useful work", and a
    bundle already on disk is the one case where it would not.
    """
    base = Path(root) if root is not None else cache.cache_root()
    out: list[str] = []
    for summary in index.summaries():
        if (base / summary.sid / "bundle.json").is_file():
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


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--probe", type=int, metavar="N",
        help="reach-check N uncached sids against the live Matterport key",
    )
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

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
