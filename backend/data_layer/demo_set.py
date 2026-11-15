"""Deterministic demo-set selection (task 2 of the demo-warm-50 plan).

Task 1 proved the shared Matterport key can still reach sids nobody has fetched.
This module decides *which* 50 of them are worth warming before a demo, plus 25
spares, so a cold cache during the demo is never the first thing a judge sees.

**The weighting is fixed by the plan, not discovered here.** 15 office, 10
retail, 10 multifamily_unit, 10 single_family, 5 other - 50 total. That is a
deliberate inversion of the kit's own shape: measured 2026-11-14, the 14,932
scans collapse to 5,098 properties averaging 2.93 scans each (one complex
carries 32), and of those properties multifamily_unit is 3,010, single_family
1,581, office 264, other 183 and retail only 58. A demo drawn from the kit's
natural distribution would be almost entirely apartments; `QUOTAS` instead
spends more than half the set on office and retail, the use types the analysis
lane's templates are built around, because that is what a judge will actually
be shown.

**One scan per property, always.** The 32-scan complex above is exactly why
`select` calls `index.collapse` before bucketing - without it, one property
could fill a third of its bucket's whole quota with the same building photographed
from different units.

**Only two states exist in this kit, TX and CA, and the thinnest bucket (retail)
measures 36 TX / 22 CA** - already lopsided before any selection runs. Splitting
a bucket's quota evenly is therefore sometimes impossible (an odd quota has no
even split, and a 50/50 split can still outrun the thinner side), so `_split_by_state`
always gives a bucket's one extra seat (or, when short, its one extra demand) to
whichever state's pool is larger. Hardcoding "CA is the big pool" or "TX is the
big pool" would be true for retail and false in general, so the pool sizes are
measured per bucket, per call, from whatever rows were actually passed in.

**Over-provisioning covers the fetch failures Task 1 showed are normal.** Not
every sid Task 4 tries to warm will answer - a 403, a dead model, a transient
network error are all things `warm.probe` already treats as ordinary outcomes,
not exceptions. Asking for exactly 50 and warming exactly those 50 means one
failure anywhere silently shrinks the demo below its planned size with nobody
the wiser. Each bucket's quota is instead scaled by 1.5 (rounded) before
selection, and the extra third - 25 properties total - rides along as spares,
ordered so the next spare for a given bucket and state is adjacent to the
target slot it would replace.

**Selection is reproducible from the seed and the index alone.** `random.Random(seed)`
makes the exact same 75 come back for the exact same input rows every time this
runs, which matters because Task 3 freezes this output into a committed manifest -
a selection that could change between runs would make that manifest a snapshot of
nothing in particular.
"""
from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional

from backend.schema import PropertySummary

from . import cache, index

#: Arbitrary and fixed. Changing it reshuffles the whole demo set, so it only
#: moves if the plan explicitly wants a new draw.
SEED = 1337

#: Fixed by the plan, not discovered from the kit's own shape - see the module
#: docstring. Keys are every `UseType` this selection cares about; `unknown` rows
#: are never picked because they have no quota to fill.
QUOTAS: dict[str, int] = {
    "office": 15,
    "retail": 10,
    "multifamily_unit": 10,
    "single_family": 10,
    "other": 5,
}

#: Target quota x this = how many candidates a bucket must actually hold,
#: rounded. Spares are the difference.
_OVERPROVISION = 1.5

_STATES = ("TX", "CA")


class SelectionShort(RuntimeError):
    """Not enough candidates to fill the plan: either there is nothing to select
    from (no kit mirror and no rows supplied), or one bucket's pool - after
    collapsing to one scan per property - is smaller than its 1.5x-scaled quota."""


def already_warm(root: Optional[Path] = None) -> set[str]:
    """Sids under `root` (default the cache root) that already carry a `bundle.json`.

    Same "has a bundle.json" primitive as `warm.uncached_sids`, duplicated here
    rather than imported from `warm.py`: Task 4 makes `warm` import *this* module
    (to feed it the selected set), and importing the other way round here would
    make that a circular import. Task 4 is where the two get reconciled - see the
    task 2 report.
    """
    base = Path(root) if root is not None else cache.cache_root()
    # `Path.glob` on a directory that does not exist yet (a fresh checkout's
    # `data/cache/`) returns nothing rather than raising, so there is no separate
    # case to handle here.
    return {p.parent.name for p in base.glob("*/bundle.json")}


def _scaled_quota(quota: int) -> int:
    """The 1.5x-scaled, rounded size a bucket's pool must reach."""
    return round(quota * _OVERPROVISION)


def _split_by_state(total: int, tx_pool: int, ca_pool: int) -> dict[str, int]:
    """Split `total` across TX and CA. An odd `total` has no even split, so its
    one extra seat goes to whichever state's pool (measured, not assumed) is
    larger - the thinner pool is the one that would run out first."""
    half, remainder = divmod(total, 2)
    tx = ca = half
    if remainder:
        if tx_pool >= ca_pool:
            tx += 1
        else:
            ca += 1
    return {"TX": tx, "CA": ca}


def _ordered_candidates(
    rng: random.Random, rows: list[PropertySummary], prefer: set[str]
) -> list[PropertySummary]:
    """Preferred rows first (so they always land inside a bucket's quota, however
    small), then the rest in a seeded-random order."""
    preferred = [r for r in rows if r.sid in prefer]
    rest = [r for r in rows if r.sid not in prefer]
    rng.shuffle(rest)
    return preferred + rest


def select(
    seed: int = SEED,
    rows: Optional[Iterable[PropertySummary]] = None,
    prefer: Optional[set[str]] = None,
) -> list[PropertySummary]:
    """75 summaries: the first 50 are the target demo set, the last 25 are spares
    in replacement order (a spare is adjacent to the target slot of its own
    bucket and state, so "the 3rd office/TX spare replaces the 3rd office/TX
    target that failed to warm" is a well-defined operation for Task 4).

    `rows` defaults to `index.summaries()`; pass real rows in tests so this never
    depends on a kit mirror being present. `prefer` should be `already_warm()` in
    production, so sids that already carry a `bundle.json` win their bucket
    instead of being re-picked by chance and re-warmed for nothing.

    Raises `SelectionShort` when there is nothing to select from at all (no kit
    mirror, and no rows given), or when one bucket's pool, after collapsing to
    one scan per property, cannot fill its 1.5x-scaled quota in a state - a
    short bucket should be reported by name, not silently rounded down.
    """
    source = tuple(index.summaries() if rows is None else rows)
    if not source:
        raise SelectionShort(
            "no kit mirror: index.summaries() returned nothing and no rows were "
            "given to select from"
        )

    prefer = prefer or set()
    collapsed = index.collapse(source, prefer=prefer)

    pools: dict[str, dict[str, list[PropertySummary]]] = defaultdict(lambda: defaultdict(list))
    for summary in collapsed:
        if summary.use_type not in QUOTAS or summary.state not in _STATES:
            continue
        pools[summary.use_type][summary.state].append(summary)

    rng = random.Random(seed)
    target: list[PropertySummary] = []
    spares: list[PropertySummary] = []

    for use_type, quota in QUOTAS.items():
        state_rows = pools.get(use_type, {})
        tx_rows = state_rows.get("TX", [])
        ca_rows = state_rows.get("CA", [])
        scaled = _scaled_quota(quota)
        target_split = _split_by_state(quota, len(tx_rows), len(ca_rows))
        total_split = _split_by_state(scaled, len(tx_rows), len(ca_rows))

        for state, available in (("TX", tx_rows), ("CA", ca_rows)):
            need = total_split[state]
            if len(available) < need:
                raise SelectionShort(
                    f"{use_type}/{state}: needs {need} properties ({quota} x "
                    f"{_OVERPROVISION} scaled) but only {len(available)} are "
                    "available after collapsing to one scan per property"
                )
            ordered = _ordered_candidates(rng, available, prefer)
            chosen = ordered[:need]
            keep = min(target_split[state], need)
            target.extend(chosen[:keep])
            spares.extend(chosen[keep:need])

    return target + spares
