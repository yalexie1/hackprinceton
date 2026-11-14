"""Payload cache and fetch records (package D4).

Two jobs, both of which were spread across the other modules before this file
existed, or not done at all.

**1. Cache the raw payloads.** Every source module used to hit the network on every
call. The sponsor keys are shared with every other team at the hackathon and the
Matterport limit is documented at 10 req/s, so a demo that re-assembles a bundle
three times should not query Matterport three times. The two cache writes that did
exist - the bundle in `api.py` and the weather CSV in `external.py` - were plain
`write_text`, so an interrupted run left a half-written file that later read as a
hit. Everything here is written to a temporary name and then `os.replace`d, which is
atomic on a POSIX filesystem.

**2. Name every normal missing outcome in one place.** `specs/data-integration.md`
section 6.4 lists ten outcomes that are all *normal* - a parcel Vexcel has never
flown, an office with no defurnished view, a residential listing with a hidden
address. `FetchRecord.status` has five values, so distinctness has to come from
`what` and `detail`, and ten strings scattered across four modules is how two of
them end up identical and a reader can no longer tell which thing was missing.
`MISSING_OUTCOMES` is the table, and a test asserts the `what` values are unique.

Three rules worth knowing before using this:

- **A caller that injects a transport bypasses the cache.** D5 shipped this bug
  once: its bundle cache was consulted *before* the live-or-offline decision, so on
  any machine where someone had run a live assembly the tests silently ran against
  cached data instead of the fixtures, and still passed. An injected getter means the
  caller is in control of what comes back, so the cache stays out of the way.
- **No URL is ever persisted.** Matterport's response carries signed URLs for
  panoramas and floor plans; they expire, so a cached one is a trap rather than a
  shortcut. `write_json` replaces every `http(s)` string with `URL_REDACTED` and says
  how many it removed. Whatever downloads bytes re-queries for a fresh URL, which is
  what `matterport.py` has always documented.
- **Absent and null stay different.** The scrubber rebuilds containers key by key
  and never inserts a key that was not there, because `{"ac-unit": {"count": null}}`
  (flown, nothing found) and `{}` (never flown) mean different things to the analysis
  lane and JSON is perfectly capable of keeping them apart.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

from backend.schema import FetchRecord

_ROOT = Path(__file__).resolve().parents[2]

#: Bumping this invalidates every entry written by an older version. Cheaper than a
#: migration, and a stale entry read with new parsing rules is a silent wrong answer.
CACHE_VERSION = 1

#: What replaces a URL in a cached payload. Not an empty string: a reader should be
#: able to tell "there was a URL here and we deliberately dropped it" from "this
#: field was blank".
URL_REDACTED = "<url-not-cached>"

_URL = re.compile(r"^\s*(https?|wss?)://", re.IGNORECASE)
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def cache_root() -> Path:
    """`data/cache/`, or `DATA_LAYER_CACHE_DIR`. Git-ignored either way: this holds
    sponsor payloads, which are hackathon-licensed and this repository is public."""
    override = os.environ.get("DATA_LAYER_CACHE_DIR")
    return Path(override) if override else _ROOT / "data" / "cache"


# ---------- keys ----------

def key(source: str, identifier: str, query: Optional[dict] = None) -> str:
    """A stable key over the source, the identifier **and the query shape**.

    The query shape has to be in the key. Vexcel's `include=precomputed` and
    `include=precomputed,calculated` return different key sets for the same point -
    that is finding 4.3 - so letting them share an entry would serve a caller asking
    for roof height a payload that has none, and nothing would report an error.
    """
    blob = json.dumps(
        {"v": CACHE_VERSION, "source": source, "id": identifier, "query": query or {}},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _safe(part: str) -> str:
    """A path component that cannot escape the cache or collide after cleaning.

    A WKT point is a legal Vexcel identifier and contains spaces, brackets and a
    minus sign; `..` is a legal-looking identifier and must not walk upwards.
    """
    cleaned = _UNSAFE.sub("-", part).strip("-")
    return cleaned[:60] or "unnamed"


def path_for(
    source: str, identifier: str, query: Optional[dict] = None, *, suffix: str = ".json"
) -> Path:
    """`data/cache/<source>/<identifier>/<key><suffix>`.

    The identifier stays in the path, unhashed, because a human debugging the lane
    should be able to find the Matterport payload for a model without computing a
    hash. The key disambiguates the query shape.
    """
    return cache_root() / _safe(source) / _safe(identifier) / f"{key(source, identifier, query)}{suffix}"


# ---------- URLs ----------

class SignedUrlInCache(ValueError):
    """A URL reached a cache write that refuses to scrub. Carries where it was."""


def scrub_urls(payload: Any, _path: str = "") -> tuple[Any, list[str]]:
    """Return `(payload with every URL replaced, the paths they were at)`.

    Containers are rebuilt key by key and no key is invented, so a field that was
    absent stays absent and a field that was `null` stays `null`.
    """
    found: list[str] = []
    if isinstance(payload, dict):
        out_d = {}
        for k, v in payload.items():
            sub, paths = scrub_urls(v, f"{_path}.{k}" if _path else str(k))
            out_d[k] = sub
            found += paths
        return out_d, found
    if isinstance(payload, list):
        out_l = []
        for i, v in enumerate(payload):
            sub, paths = scrub_urls(v, f"{_path}[{i}]")
            out_l.append(sub)
            found += paths
        return out_l, found
    if isinstance(payload, str) and _URL.match(payload):
        return URL_REDACTED, [_path or "<root>"]
    return payload, found


# ---------- reading and writing ----------

def read_json(source: str, identifier: str, query: Optional[dict] = None) -> Optional[Any]:
    """The cached payload, or `None` on a miss.

    A truncated or unparseable entry is a **miss**, not a crash. It should not be
    reachable - writes are atomic - but a disk that filled mid-write should cost a
    refetch, not the run.
    """
    path = path_for(source, identifier, query)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None


def write_json(
    source: str, identifier: str, payload: Any, query: Optional[dict] = None, *,
    strict: bool = False,
) -> tuple[Path, list[str]]:
    """Write a payload atomically, with every URL replaced. Returns the path and the
    paths the URLs were at, so a caller can put the count in a `FetchRecord`.

    `strict=True` raises instead of scrubbing, for a caller that would rather fail
    than silently lose a field it needed. Either way no URL reaches the disk.
    """
    scrubbed, urls = scrub_urls(payload)
    if urls and strict:
        raise SignedUrlInCache(f"{source}/{identifier}: URLs at {urls[:5]}")
    return _atomic_write(
        path_for(source, identifier, query),
        json.dumps(scrubbed, separators=(",", ":")).encode(),
    ), urls


def write_bytes(source: str, identifier: str, data: bytes, query: Optional[dict] = None, *,
                suffix: str = ".bin") -> Path:
    """Asset bytes, atomically. `get_asset` serves these; it never returns a URL."""
    return _atomic_write(path_for(source, identifier, query, suffix=suffix), data)


def _atomic_write(path: Path, data: bytes) -> Path:
    """Write to a temporary name beside the target, then `os.replace` onto it.

    This is the whole reason an interrupted write cannot read as a hit: a reader sees
    either the old entry or the new one, never half of either. The temporary name
    carries the process id so two processes caching the same payload do not fight.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def write_text(source: str, identifier: str, text: str, query: Optional[dict] = None, *,
               suffix: str = ".csv") -> Path:
    return _atomic_write(path_for(source, identifier, query, suffix=suffix), text.encode())


def atomic_write_path(path: Path, data: bytes) -> Path:
    """Atomic write to a caller's own path, for the files whose location is part of
    the contract rather than ours - `ClimateSite.weather_path` is in the bundle, so
    the weather CSV cannot live under a hashed key."""
    return _atomic_write(path, data)


def cached_json(
    source: str,
    identifier: str,
    fetch: Callable[[], Any],
    query: Optional[dict] = None,
    *,
    use_cache: bool = True,
    refresh: bool = False,
) -> tuple[Any, bool]:
    """`(payload, served_from_cache)`.

    `use_cache=False` is the escape hatch a caller with an injected transport must
    use. It skips the read **and** the write: a test that stubs a response has no
    business leaving that response on disk for the next test to find.
    """
    if not use_cache:
        return fetch(), False
    if not refresh:
        hit = read_json(source, identifier, query)
        if hit is not None:
            return hit, True
    payload = fetch()
    write_json(source, identifier, payload, query)
    return payload, False


# ---------- the normal missing outcomes ----------

#: Every outcome from `specs/data-integration.md` section 6.4 that is **normal** -
#: the lane reports it and carries on. Each entry is `(layer, what, status, detail)`.
#: The `what` values are unique, which is the point: `status` has five values and ten
#: outcomes, so a reader can only tell them apart by `what`.
MISSING_OUTCOMES: dict[str, tuple[str, str, str, str]] = {
    "vexcel.no_parcel": (
        "vexcel", "property/extract:no-parcel", "missing",
        "Vexcel has no parcel at this point (HTTP 404); urban coverage is not global",
    ),
    "vexcel.outside_coverage": (
        "vexcel", "property/extract:outside-coverage", "missing",
        "the point is outside the licensed coverage (HTTP 403); the key is valid, "
        "the area is not included",
    ),
    "vexcel.no_features": (
        "vexcel", "property/extract:no-features", "missing",
        "HTTP 200 with an empty feature list; the parcel is known but carries no "
        "attributes",
    ),
    "vexcel.rate_limited": (
        "vexcel", "property/extract:rate-limited", "error",
        "Vexcel returned HTTP 429; the key is shared with every team, so back off and retry",
    ),
    "vexcel.no_building_type": (
        "vexcel", "property/extract:building-type", "missing",
        "building-type.class is absent; it is null on residential lots, so do not "
        "depend on it for the home flow",
    ),
    "matterport.matterpak_locked": (
        "matterport", "model:matterpak", "locked",
        "MatterPak is not included in this model's plan; geometry still comes from "
        "the room and wall graph",
    ),
    "matterport.no_splat": (
        "matterport", "model:splat", "missing",
        "no Gaussian splat for this model; all nine models of the Houston office "
        "return 404 for the splat asset",
    ),
    "matterport.no_defurnished": (
        "matterport", "model:defurnished", "missing",
        "no defurnished view; none of the nine office models has one, so this is "
        "the normal case for commercial scans",
    ),
    "matterport.rooms_without_dimensions": (
        "matterport", "model:room-dimensions", "missing",
        "one or more rooms have no dimensions; area must come from the wall graph "
        "for those rooms",
    ),
    "costar.no_model_id": (
        "costar", "kit:matterport-model-id", "missing",
        "the CoStar row has an empty MatterportModelId (51 commercial, 1 "
        "residential), so there is no scan to join to",
    ),
    "costar.hidden_address": (
        "costar", "kit:residential-address", "missing",
        "the residential listing hides its address (4 listings); the property is "
        "real but cannot be geocoded from the kit",
    ),
    "costar.non_public_listing": (
        "costar", "kit:listing-visibility", "locked",
        "the listing is not public (228 listings); its record exists but may not be "
        "shown",
    ),
}


def record(outcome: str, detail_suffix: str = "") -> FetchRecord:
    """The `FetchRecord` for one of the named normal outcomes.

    Raises `KeyError` on an unknown name, deliberately: a typo should fail loudly
    here rather than produce a record whose `what` nothing else in the lane uses.
    """
    layer, what, status, detail = MISSING_OUTCOMES[outcome]
    return FetchRecord(
        layer=layer, what=what, status=status,
        detail=f"{detail}; {detail_suffix}" if detail_suffix else detail,
    )


def cache_note(layer: str, what: str, *, hit: bool, urls_dropped: int = 0) -> FetchRecord:
    """A record saying where a payload came from, so provenance distinguishes a fresh
    fetch from a replay. A cache hit is `ok`: the data is real, it is just not new."""
    detail = "served from the cache" if hit else "fetched live and cached"
    if urls_dropped:
        detail += f"; {urls_dropped} URL(s) dropped before writing"
    return FetchRecord(layer=layer, what=what, status="ok", detail=detail)
