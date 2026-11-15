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

import argparse
import ast
import os
import random
import re
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


# ---------------------------------------------------------------------------
# The committed manifest (task 3)
#
# `select()` is pure on purpose - two teammates generating this manifest on
# different laptops must get the exact same 75 from the same index, or the
# "committed" part of "committed manifest" is a lie. That means it cannot look
# at local cache state itself. But the task 2 plan still wants the ten
# properties this machine already warmed (three `specs/examples/` fixtures plus
# seven others with a `bundle.json`) to win their buckets, because they are
# already proven and already paid for. Generation - a one-off development
# action whose *output* is what every reader shares - is the only place that
# can know both things at once, so `main --generate` is the one caller that
# passes `prefer=already_warm()` into `select()`. Every other caller of
# `select()` (tests, and any future caller) stays pure.
# ---------------------------------------------------------------------------

#: The three fixtures `specs/examples/` ships (house, office, office_houston) -
#: see their `property_summary.json` files. `demo_transfer.DEMO_SIDS` lists the
#: same three sids; it is duplicated here rather than imported for the same
#: reason `already_warm` duplicates `warm`'s primitive instead of importing it -
#: this module must stay free to be imported by whichever of the two needs the
#: other later, and a one-way dependency now would pick that direction by accident.
_GOLDEN_SIDS: frozenset[str] = frozenset({"zvKHR9DHNjJ", "ZSPaQbkGcJJ", "L3266YcPPvd"})


def _reason(summary: PropertySummary) -> str:
    """"<use_type>/<state>", suffixed "/golden" when `summary` is one of the three
    sids `specs/examples/` already ships a fixture for - those three are already
    proven to work regardless of what this laptop has cached."""
    base = f"{summary.use_type}/{summary.state}"
    return f"{base}/golden" if summary.sid in _GOLDEN_SIDS else base


def _generate() -> tuple[tuple[str, str], ...]:
    """What `--generate` writes: `select()` against the live index, with
    `already_warm()` as `prefer` so this machine's already-fetched properties win
    their bucket (see the section note above), each stamped with its reason.

    **Not reproducible on another laptop, by design.** `select()` itself is pure and
    stays that way, but `already_warm()` is machine-local - it reads whatever this
    cache root happens to hold - so regenerating on a second machine yields a
    different 75. The committed `DEMO_SET` literal, not this function, is the
    authoritative demo set; `--generate` is a one-off development action whose
    *output* is the thing teammates share.
    """
    chosen = select(prefer=already_warm())
    return tuple((summary.sid, _reason(summary)) for summary in chosen)


#: The frozen output of `_generate()`, written back into this file by
#: `python -m backend.data_layer.demo_set --generate`. 75 `(sid, reason)` pairs,
#: the first 50 the target demo set and the last 25 spares in replacement order -
#: see `select()`'s docstring for what "replacement order" means. Every reader at
#: runtime reads only this literal; generating it is the only step that needs the
#: kit mirror, which is why `pytest backend -q` can exercise `resolve()` without one.
#
# DEMO_SET-GENERATED-BEGIN
DEMO_SET: tuple[tuple[str, str], ...] = (
    ("L3266YcPPvd", "office/TX/golden"),
    ("NLpW1UAp1HJ", "office/TX"),
    ("ThfCq6T7tLX", "office/TX"),
    ("ebSqaFMntwv", "office/TX"),
    ("7uM5JKssTED", "office/TX"),
    ("ydzXab1mZt5", "office/TX"),
    ("4HiyM1Eqfce", "office/TX"),
    ("4VqcKP8VSXX", "office/TX"),
    ("ZSPaQbkGcJJ", "office/CA/golden"),
    ("jfiEvosX974", "office/CA"),
    ("A2dg4xeLX4j", "office/CA"),
    ("XVPPwqqbFdB", "office/CA"),
    ("kpdF1dt7jo2", "office/CA"),
    ("K6X5Tk8UBn9", "office/CA"),
    ("tsaz3uu9Nk9", "office/CA"),
    ("BoqDzrD8JLh", "retail/TX"),
    ("zKgykpJUQ69", "retail/TX"),
    ("nYvgTdxFHsT", "retail/TX"),
    ("qUemqJ6WYv8", "retail/TX"),
    ("KT7w4e1moiZ", "retail/TX"),
    ("7LuW15YPx4r", "retail/CA"),
    ("9JVEYsUzXcy", "retail/CA"),
    ("2wKwkYGbkPc", "retail/CA"),
    ("7uN3XX6U5Un", "retail/CA"),
    ("VHxVaDxPiub", "retail/CA"),
    ("PmUgz1kP1xu", "multifamily_unit/TX"),
    ("5UXkjV5TyQa", "multifamily_unit/TX"),
    ("TK8wtSvDWia", "multifamily_unit/TX"),
    ("5yDW81CsybP", "multifamily_unit/TX"),
    ("EKTSt6W4aWv", "multifamily_unit/TX"),
    ("AmmeKd2ddDh", "multifamily_unit/CA"),
    ("YnQBU9JUQWC", "multifamily_unit/CA"),
    ("2u5aEeXan5U", "multifamily_unit/CA"),
    ("itLHNpaCLeb", "multifamily_unit/CA"),
    ("b9kNytWmz5k", "multifamily_unit/CA"),
    ("XFTP8epsP4E", "single_family/TX"),
    ("8VF48HG3wMH", "single_family/TX"),
    ("ktcrR9s3PVL", "single_family/TX"),
    ("iqNJy5KMKGW", "single_family/TX"),
    ("NhdS6VJypGE", "single_family/TX"),
    ("zvKHR9DHNjJ", "single_family/CA/golden"),
    ("tUQSvpRoXLj", "single_family/CA"),
    ("VJ8SigddfDf", "single_family/CA"),
    ("burWoXUMoTf", "single_family/CA"),
    ("ChKhSEUvPKE", "single_family/CA"),
    ("bJg9wSAeFAe", "other/TX"),
    ("5FyvmAZAhRg", "other/TX"),
    ("wdjyrTtBBHT", "other/TX"),
    ("2tv5N4fK91i", "other/CA"),
    ("M4PzRXV6bFG", "other/CA"),
    ("XSC8HVkwJH2", "office/TX"),
    ("jtfVRiouTPW", "office/TX"),
    ("1J9YKR5rPqk", "office/TX"),
    ("EJdgXvCPTr3", "office/CA"),
    ("122gc4639J7", "office/CA"),
    ("pMe3VYvpCCU", "office/CA"),
    ("59U6s4YUbrP", "office/CA"),
    ("kSVfr4gKUhM", "retail/TX"),
    ("gjMWcj8oz4B", "retail/TX"),
    ("ZwxqzRQzs2r", "retail/TX"),
    ("C3JYiY97kaX", "retail/CA"),
    ("43hNG6RhgjM", "retail/CA"),
    ("TSpwHx7D8yC", "multifamily_unit/TX"),
    ("44ABXz8TMfA", "multifamily_unit/TX"),
    ("HdRHXqSHohe", "multifamily_unit/TX"),
    ("dtHoajDQgmY", "multifamily_unit/CA"),
    ("2Aaw7drsvrT", "multifamily_unit/CA"),
    ("ddKZEats5Np", "single_family/TX"),
    ("Xxfv2EZsgFB", "single_family/TX"),
    ("C1BgHc2TDsC", "single_family/TX"),
    ("DhTEXLfCtiH", "single_family/CA"),
    ("PTz2GeBccjR", "single_family/CA"),
    ("9oebYSRx5QD", "other/TX"),
    ("5RYmbtMAuEV", "other/CA"),
    ("5V9hTd7N5dg", "other/CA"),
)
# DEMO_SET-GENERATED-END


def sids(n: int = 50) -> tuple[str, ...]:
    """The first `n` sids of `DEMO_SET` - defaults to the target fifty, the part of
    the manifest Task 4 warms before falling back to `spares()`."""
    return tuple(sid for sid, _ in DEMO_SET[:n])


def spares() -> tuple[str, ...]:
    """The 25 sids beyond the target fifty, in replacement order."""
    return tuple(sid for sid, _ in DEMO_SET[50:])


def buckets() -> dict[str, str]:
    """`sid` -> its "<use_type>/<state>" bucket key, from the manifest's own `reason`
    field with any "/golden" suffix stripped.

    `select()`'s guarantee that "a spare is adjacent to the target slot of its own
    bucket and state" is a *positional* invariant inside the 75-entry tuple - true
    of the manifest's row order, not something a caller holding only a bare sid
    (`warm.warm_all`, replacing one disqualified target) can recover by itself.
    This is the accessor that closes that gap: a failed target's bucket key, looked
    up here, is exactly what its replacement must match - drawing from a different
    bucket's spares would silently skew the 15/10/10/10/5 quota the whole plan is
    built around.
    """
    return {
        sid: reason[: -len("/golden")] if reason.endswith("/golden") else reason
        for sid, reason in DEMO_SET
    }


#: How many entries of `DEMO_SET` are the target set; the rest are spares.
_TARGET_N = 50


def with_replacements(
    entries: tuple[tuple[str, str], ...],
    replacements: Iterable[tuple[str, str]],
    *,
    target_n: int = _TARGET_N,
) -> tuple[tuple[str, str], ...]:
    """`entries` with every `(disqualified_sid, replacement_sid)` hop applied, as a
    swap between the target block and the spare block. Pure - it writes nothing.

    Each hop moves the replacement into the exact target slot the disqualified sid
    occupied, and demotes the disqualified sid into the exact spare slot the
    replacement vacated. A swap, not an insert-and-append, because `select()`'s
    "a spare is adjacent to the target slot of its own bucket and state" guarantee
    is positional: appending would push every later spare one place along and quietly
    break that adjacency for the next run, while both blocks' lengths (50 and 25)
    must stay exactly what every reader of `sids()`/`spares()` assumes.

    Chains are applied in order, so `[(BAD, S1), (S1, S2)]` - a spare that itself
    failed and was replaced again - ends with S2 in the target slot and both BAD and
    S1 demoted, each in the spare slot its own successor vacated.

    Whole `(sid, reason)` rows move, never bare sids: a property's
    `"<use_type>/<state>"` bucket does not change by being promoted or demoted, and
    the `/golden` suffix must follow its own sid rather than its slot. Keeping the
    rows intact is what makes both of those true by construction.

    Raises `ValueError` naming the sid when a hop does not describe a
    target-to-spare move (the disqualified sid is not currently a target, or the
    replacement is not currently a spare) - a hop that cannot be applied means the
    caller's record and the manifest disagree, and writing a half-applied manifest
    over a committed one is strictly worse than refusing.
    """
    rows = list(entries)
    for old, new in replacements:
        try:
            i = next(j for j in range(min(target_n, len(rows))) if rows[j][0] == old)
        except StopIteration:
            raise ValueError(
                f"{old}: recorded as a disqualified target but it is not in the "
                f"first {target_n} manifest entries"
            ) from None
        try:
            k = next(j for j in range(target_n, len(rows)) if rows[j][0] == new)
        except StopIteration:
            raise ValueError(
                f"{new}: recorded as a replacement but it is not in the manifest's "
                "spare block"
            ) from None
        rows[i], rows[k] = rows[k], rows[i]
    return tuple(rows)


def apply_replacements(
    replacements: Iterable[tuple[str, str]], path: Optional[Path] = None
) -> tuple[tuple[str, str], ...]:
    """Persist `warm.warm_all`'s replacements into the committed manifest, so the
    first 50 entries are the 50 properties that actually warmed.

    Without this step a warm pass's substitutions live only in the operator's
    terminal: `demo_transfer pack` would build the archive from `sids()` - omitting
    every spare that warmed and including every target that failed - `demo_transfer
    check` would report those failures as `not_warmed` forever, and the demo would
    offer a judge a property proven not to assemble. `--generate` cannot repair that
    either: it re-selects from scratch against this machine's live `already_warm()`,
    producing a *different* 75 rather than the corrected one.

    Goes through `_write_manifest`, so the `_assert_still_whole` AST guard and the
    atomic `os.replace` apply unchanged - this is not a second writer.

    **A slot that no spare could fill keeps its failed target.** That case has no
    hop to apply - `warm_all` records a replacement only when it actually drew a
    spare - so the sid stays where it is and the target block stays 50 long. The
    alternative, demoting it to leave 49 targets and 26 spares, would break the
    fixed split every reader of `sids()`/`spares()` assumes in order to hide a
    shortfall that `SparesExhausted` is there to shout about. The operator sees the
    non-zero exit and the named shortfall; the manifest is not the place to bury it.

    The in-process `DEMO_SET` literal is deliberately *not* rebound: this module's
    source on disk is the manifest, and a caller that needs the new one re-imports.
    Returns the entries written so a caller can report them without re-reading.
    """
    entries = with_replacements(DEMO_SET, replacements)
    _write_manifest(entries, path)
    return entries


class ManifestStale(RuntimeError):
    """A sid `DEMO_SET` carries is no longer in `index.by_sid()` - the kit mirror
    was re-mirrored or trimmed since the manifest was generated. `resolve()` raises
    this by name rather than letting a bare `KeyError` escape, because "which sid"
    is exactly what whoever re-runs `--generate` needs to know."""


def resolve() -> list[PropertySummary]:
    """Every `DEMO_SET` sid looked up in `index.by_sid()`, in manifest order.

    Raises `ManifestStale` naming the first sid the index no longer has, instead of
    letting that lookup's `KeyError` escape - a stale manifest should fail loudly and
    by name, not with a traceback that makes the caller go find which sid it was."""
    table = index.by_sid()
    out: list[PropertySummary] = []
    for sid, _ in DEMO_SET:
        try:
            out.append(table[sid])
        except KeyError:
            raise ManifestStale(
                f"{sid}: in DEMO_SET but not in the live index - re-run "
                "`python -m backend.data_layer.demo_set --generate`"
            ) from None
    return out


def _format_entries(entries: Iterable[tuple[str, str]]) -> str:
    return "\n".join(f'    ("{sid}", "{reason}"),' for sid, reason in entries)


#: The sentinel comments bracketing the `DEMO_SET` literal above. Matched as plain
#: strings, not a regex over surrounding code: the previous attempt at this used a
#: regex anchored only on `DEMO_SET: tuple[...] = (` and the next bare `)\n`, which
#: for an *empty* placeholder tuple (no entries between the parens) skipped straight
#: past that empty pair and matched the next unrelated `)` at column zero later in
#: this very file - deleting everything in between.
#:
#: Built by concatenation rather than as one literal string, on purpose: writing
#: the marker text as a single contiguous literal here would itself contain the
#: full sentinel, so `text.index(...)` against this module's own source would
#: have *two* candidates - the real comment above `DEMO_SET`, and this
#: assignment's own string - and would only find the right one because the real
#: comment happens to come first in the file today. That ordering dependency is
#: exactly the fragility a review of the previous version flagged. Splitting the
#: marker across a `+` (and never spelling it out contiguously anywhere else in
#: this module, including in comments like this one) means the full text appears
#: exactly once in the source: the real comment line. `test_manifest_sentinels_
#: appear_exactly_once_in_source` pins this.
_MANIFEST_BEGIN = "# DEMO_SET" + "-GENERATED-BEGIN"
_MANIFEST_END = "# DEMO_SET" + "-GENERATED-END"

#: Every name a reader of this module is allowed to assume exists. The previous
#: version of `_write_manifest` wrote straight to disk with no check at all, and a
#: wrong sentinel-boundary match silently deleted five of these names - discovered
#: only later, by an unrelated test's `ImportError`. `_assert_still_whole` parses
#: the candidate rewrite and refuses to write unless every one of these survives.
_REQUIRED_NAMES = frozenset({"DEMO_SET", "sids", "spares", "resolve", "ManifestStale"})


def _top_level_names(tree: ast.Module) -> set[str]:
    """Every name bound at module scope by a `def`, `class`, or plain assignment -
    enough to answer "did the rewrite drop a name a caller imports", without
    executing the candidate text (which would re-trigger whatever just went wrong
    in a half-written module, and risks import side effects this check must not
    have)."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _assert_still_whole(new_text: str, path: Path) -> None:
    """Refuse `new_text` unless it both parses and still defines every name in
    `_REQUIRED_NAMES`. A syntax error is the easy case; the dangerous one - the one
    that actually bit this module once - is a rewrite that stays syntactically
    valid Python while quietly missing a sentinel's real match and deleting
    everything between two *unintended* boundaries. Checking for the specific
    names this module promises callers, rather than trusting that a non-empty diff
    means a correct one, is what turns that failure mode into a loud `RuntimeError`
    instead of a silent `ImportError` three test files later."""
    try:
        tree = ast.parse(new_text, filename=str(path))
    except SyntaxError as exc:
        raise RuntimeError(f"--generate produced invalid Python for {path}: {exc}") from exc
    missing = _REQUIRED_NAMES - _top_level_names(tree)
    if missing:
        raise RuntimeError(
            f"--generate's rewrite of {path} would drop {sorted(missing)} - "
            "refusing to write anything"
        )


def _write_manifest(entries: tuple[tuple[str, str], ...], path: Optional[Path] = None) -> None:
    """Rewrite this module's own `DEMO_SET` literal in place, replacing everything
    strictly between the `_MANIFEST_BEGIN`/`_MANIFEST_END` sentinel lines (exclusive)
    with a fresh `DEMO_SET = (...)` block. Everything outside those sentinels -
    docstrings, the comment introducing the block, every other function - survives
    byte-for-byte.

    `path` defaults to this module's own file; a test passes a throwaway file
    instead so it can exercise the sentinel search and the `_assert_still_whole`
    guard without touching the real `demo_set.py`.

    Nothing reaches disk until `_assert_still_whole` has parsed the candidate
    result and confirmed it is still a module a caller can import from - see that
    function's docstring for why. The write itself goes to a temporary file and is
    `os.replace`d into place, the same atomic-write discipline `cache.py` already
    uses elsewhere in this lane, so a process killed mid-write cannot leave a
    half-written `demo_set.py` behind."""
    path = path if path is not None else Path(__file__)
    text = path.read_text()
    begin = text.index(_MANIFEST_BEGIN) + len(_MANIFEST_BEGIN)
    end = text.index(_MANIFEST_END, begin)
    body = (
        "\nDEMO_SET: tuple[tuple[str, str], ...] = (\n"
        + _format_entries(entries)
        + "\n)\n"
    )
    new_text = text[:begin] + body + text[end:]
    _assert_still_whole(new_text, path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(new_text)
    os.replace(tmp, path)


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--generate",
        action="store_true",
        help="regenerate the committed DEMO_SET literal from the live index. The "
             "committed literal is authoritative: generation prefers whatever this "
             "laptop has already warmed, so running --generate on another machine "
             "will not reproduce it.",
    )
    args = parser.parse_args(argv)
    if not args.generate:
        parser.print_help()
        return

    entries = _generate()
    _write_manifest(entries)
    golden = sum(1 for _, reason in entries if reason.endswith("/golden"))
    print(f"wrote {len(entries)} entries ({golden} /golden) to {Path(__file__)}")


if __name__ == "__main__":
    main()
