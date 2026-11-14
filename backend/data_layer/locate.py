"""Which building on the parcel this bundle is about (package D16).

The lead's rule, from the board on 2026-11-14: take the structure that contains the
**CoStar address point**; when candidates differ, prefer the footprint that best
matches CoStar's floor plate, `building_area_m2 / stories`; with no CoStar point, fall
back to the Matterport georeference; and emit a record whenever the candidates
disagree.

Writing it turned up a bigger fault than the one it was asked to fix.

**A point query returns one feature per capture collection, and the first is not the
newest.** `property/extract` at a single point came back with 5 features for the
golden house, 4 for the Los Angeles office and 6 for the Houston office. They are not
neighbouring parcels - every one of their parcel rings contains the query point. They
are the same parcel as seen by different Vexcel captures, distinguished by
`metadata.collection` and `metadata.ortho-date-estimate`. D3 kept `features[0]`, which
at the Los Angeles office is `us-ca-losangeles-2023` (imagery 2022-12-20) while a
2025-12-06 capture sat in the same response, unread. [V] 2026-11-14

So the bundle has been modelling an arbitrary capture of an arbitrary structure. Two
consequences that were live on the demo path:

| property | `features[0]` kept | this rule picks | why |
|---|---|---|---|
| house | 190.4 m2, 2 AC units, imagery 2022-12 | 191.3 m2, 0 AC units, imagery 2025-12 | same house in 5 captures; take the newest |
| LA office | 2,207 m2, a building the address point is **not inside** | 1,566 m2, imagery 2025-12 | 17 storeys over 24,148 m2 is a 1,420 m2 plate; 1,566 is within 10 % |
| Houston office | 4,320 m2 | 1,104 m2, imagery 2023-01 | a 944 m2 plate; and SAM 3's mask measured ~1,080 m2 |

The Houston row is the one that convinced me: D8's roof mask, which comes from
imagery and knows nothing about either number, measured 0.25 of the 4,320 m2 footprint
- about 1,080 m2, which is 98 % of the 1,104 m2 structure this rule chooses. Two
independent sources, the storey count and the mask, both say the kept structure was
wrong, in the same direction, on two different properties.

**Why the floor plate decides and not the newest capture.** They conflict: Houston's
newest capture (`us-tx-houston-2026`, imagery 2025-12-31) reports one 4,164 m2
structure over the address, 341 % above the plate, while a 2023 capture reports
1,104 m2. Choosing the right building from an older capture beats the wrong building
from a newer one, because every roof number downstream - PV capacity (A14), roof
planes (A11), the envelope (A2) - scales with the footprint, whereas the cost of a
two-year-old capture is a slightly stale roof condition. The capture date is reported
so a reader can see which they got.

**The capture decides within a building, not between buildings.** Where several
captures see the same structure the areas agree to about 1 % - the golden house is
190.4, 190.0, 191.7, 190.5, 191.3 m2 across five - so a plate comparison between them
is choosing on noise. `PLATE_BAND` is what stops that: everything within 10
percentage points of the best deviation is treated as equally good a match, and the
newest capture wins among them. On the house that is the difference between quoting
2 rooftop AC units from 2022 and 0 from 2025 - and those counts really do vary by
capture (2, 1, 1, 1, 0), which is worth knowing before anyone sizes an HVAC measure
off one.

**What this does not claim.** The plate is `building_area_m2 / stories`, which assumes
the storeys are stacked on one footprint; for a tower on a podium it names the tower,
which is the right answer for a roof and the wrong one for a floor area. It is a
*discriminator between candidates*, never a measurement - the chosen footprint is
still Vexcel's, and the house's plate is 25 % off every capture of it because CoStar's
area excludes the garage while the footprint includes the eaves. It has to separate
candidates that differ by 2x, and it does.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.schema import CostarData, FetchRecord

#: Candidates within this many percentage points of the best plate deviation count as
#: equally good, and the newest capture wins among them. Set from the measured spread:
#: captures of one building agree to about 1 % on area, and the buildings this has to
#: tell apart differ by 50 % or more. Anything in between is reported, not resolved.
PLATE_BAND = 0.10

#: Two candidates whose roof centroids are closer together than this are taken to be
#: the same building seen twice, not two buildings. Measured: the five captures of the
#: golden house put its centroid within 3 m every time, and the two captures of the
#: Los Angeles office's north building within 9 m, while the two *distinct* buildings
#: on that parcel are 70 m apart. This only changes the wording of a record - never
#: which structure is chosen - so a wrong call here misleads a reader rather than the
#: model.
SAME_BUILDING_M = 25.0

#: Captures with `metadata.is-ortho-image` false are derived from an oblique and are
#: measurably worse: the two in the golden set gave 9,162 m2 for a 1,420 m2 plate and
#: 3,802 m2 for a 944 m2 one, both with no AC count and no roof condition at all. They
#: stay as candidates - an oblique capture is still data - but lose every tie.
ORTHO_PREFERRED = True


@dataclass
class Candidate:
    """One structure as seen by one capture."""
    feature: int                     # index into the response's `features`
    structure: int                   # index into that feature's `structures`
    area_m2: Optional[float]
    primary: bool
    collection: Optional[str]
    captured: Optional[str]          # `metadata.ortho-date-estimate`, ISO
    is_ortho: bool
    contains: bool                   # footprint encloses the locator point
    centre: Optional[tuple[float, float]] = None   # roof centroid, (lat, lon)
    solar: Optional[bool] = None     # `roof-objects.solar.value`, which decides PV_ROOF

    @property
    def label(self) -> str:
        return (f"{self.area_m2:,.0f} m2 from {self.collection or 'an unnamed collection'}"
                f" ({(self.captured or 'undated')[:10]})" if self.area_m2 is not None
                else f"an area-less structure from {self.collection}")


def floor_plate_m2(costar: Optional[CostarData]) -> Optional[float]:
    """CoStar's gross area divided by its storeys, or `None`.

    `rentable_area_m2` is deliberately not a fallback: it is a leasing number that
    excludes cores and common area, so it would bias the plate low by a different
    amount per building and make the comparison between candidates meaningless.
    """
    if costar is None or not costar.building_area_m2 or not costar.stories:
        return None
    if costar.stories < 1:
        return None
    return costar.building_area_m2 / costar.stories


def newest_feature(features: list[dict]) -> int:
    """The index of the newest capture, for when there is no structure to choose by.

    A parcel with no structure in any capture is still a parcel - it has a polygon and
    attributes, and `elements/detect` needs the polygon - so this keeps the best
    available feature rather than letting the caller return nothing. That mattered:
    dropping it turned "a parcel with no building" into "no parcel", which also broke
    the cache's own provenance note.
    """
    if not features:
        return 0
    ranked = sorted(
        range(len(features)),
        key=lambda i: (
            not bool(_props(features[i]).get("metadata.is-ortho-image")),
            -_date_rank(_props(features[i]).get("metadata.ortho-date-estimate")),
            i,
        ),
    )
    return ranked[0]


def _flag(value) -> Optional[bool]:
    """A Vexcel boolean attribute, keeping absent distinct from false."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() not in ("false", "0", "no", "none", "")


def _props(feature: dict) -> dict:
    return feature.get("properties") or {}


def candidates(features: list[dict], lat: float, lon: float) -> list[Candidate]:
    """Every structure in every capture, flagged with whether it encloses the point."""
    from . import screening

    out: list[Candidate] = []
    for fi, feature in enumerate(features):
        props = _props(feature)
        for si, structure in enumerate(props.get("structures") or []):
            out.append(Candidate(
                feature=fi, structure=si,
                area_m2=structure.get("footprint.area"),
                primary=bool(structure.get("primary-structure")),
                collection=props.get("metadata.collection"),
                captured=props.get("metadata.ortho-date-estimate"),
                is_ortho=bool(props.get("metadata.is-ortho-image")),
                contains=screening.contains(structure.get("footprint.wkt"), lat, lon),
                centre=screening._centroid(structure),
                solar=_flag(structure.get("roof-objects.solar.value")),
            ))
    return out


def _deviation(candidate: Candidate, plate: float) -> float:
    if not candidate.area_m2:
        return float("inf")
    return abs(candidate.area_m2 - plate) / plate


def _newest_key(candidate: Candidate) -> tuple:
    """Sort key for "the best capture of this building", newest first.

    Ortho before oblique, then the newest imagery date, then the larger footprint -
    the last only so two captures that tie cannot swap between runs.
    """
    return (
        not (candidate.is_ortho or not ORTHO_PREFERRED),
        -(_date_rank(candidate.captured)),
        -(candidate.area_m2 or 0.0),
    )


def _date_rank(iso: Optional[str]) -> float:
    """An ISO date as a sortable number; an undated capture sorts oldest."""
    if not iso:
        return 0.0
    digits = "".join(c for c in str(iso)[:10] if c.isdigit())
    return float(digits) if digits else 0.0


def choose(
    features: list[dict],
    *,
    at: Optional[tuple[float, float]] = None,
    plate_m2: Optional[float] = None,
    locator: str = "address",
) -> tuple[Optional[Candidate], list[FetchRecord]]:
    """Which capture and structure to use, with the records that explain it.

    `at` is the locator point - the CoStar address, or the georeference when CoStar has
    none. Returns `(None, records)` only when there is no structure anywhere in the
    response.
    """
    notes: list[FetchRecord] = []
    if not features:
        return None, [FetchRecord(layer="vexcel", what="property/extract:structures",
                                  status="missing", detail="no features in the response")]

    if at is None:
        # No locator at all. The newest capture's own primary structure is the best
        # available answer and is still strictly better than `features[0]`.
        everything = candidates(features, 0.0, 0.0)
        pick = _without_a_point(everything, plate_m2)
        if pick is not None:
            notes.append(FetchRecord(
                layer="vexcel", what="property/extract:structure", status="fallback",
                detail=(f"no locator point, so the newest capture's primary structure: "
                        f"{pick.label}; {_spread(everything)}"),
            ))
        return pick, notes

    lat, lon = at
    everything = candidates(features, lat, lon)
    if not everything:
        return None, [FetchRecord(
            layer="vexcel", what="property/extract:structures", status="missing",
            detail=f"{len(features)} capture(s) at the point, none with a structure")]

    enclosing = [c for c in everything if c.contains]
    pool = enclosing
    if not pool:
        # The locator is on the parcel but inside no building - open ground, or a
        # footprint that has moved between captures. Widen rather than give up, and
        # say so: the answer is no longer "the building at this address".
        pool = everything
        notes.append(FetchRecord(
            layer="vexcel", what="property/extract:containment", status="fallback",
            detail=(f"no structure in any of the {len(features)} capture(s) encloses the "
                    f"{locator} point, so every structure on the parcel is a candidate"),
        ))

    if plate_m2:
        best = min(_deviation(c, plate_m2) for c in pool)
        band = [c for c in pool if _deviation(c, plate_m2) <= best + PLATE_BAND]
        pick = sorted(band, key=_newest_key)[0]
        rejected = [c for c in pool if c not in band]
        notes.append(FetchRecord(
            layer="vexcel", what="property/extract:structure",
            status="ok" if len(pool) == 1 else "fallback",
            detail=(
                f"{len(pool)} candidate structure(s) over the {locator} point across "
                f"{len(features)} capture(s); chose {pick.label}, "
                f"{_deviation(pick, plate_m2):.0%} from the {plate_m2:,.0f} m2 CoStar floor "
                f"plate" + (f"; rejected " + ", ".join(
                    f"{c.label} at {_deviation(c, plate_m2):.0%}" for c in rejected[:4])
                    if rejected else
                    f"; {len(band) - 1} other capture(s) of it were within "
                    f"{PLATE_BAND:.0%} and lost on date" if len(band) > 1 else "")
            )[:500],
        ))
        notes += _same_building_notes(pick, rejected)
        return pick, notes

    # No plate. Vexcel's own flag is all that is left to prefer, then the newest.
    pick = sorted(pool, key=lambda c: (not c.primary,) + _newest_key(c))[0]
    notes.append(FetchRecord(
        layer="vexcel", what="property/extract:structure", status="fallback",
        detail=(f"no CoStar floor plate to compare footprints against, so the newest "
                f"capture's primary structure over the {locator} point: {pick.label}; "
                f"{_spread(pool)}")[:500],
    ))
    return pick, notes


def _without_a_point(pool: list[Candidate], plate_m2: Optional[float]) -> Optional[Candidate]:
    if not pool:
        return None
    if plate_m2:
        best = min(_deviation(c, plate_m2) for c in pool)
        pool = [c for c in pool if _deviation(c, plate_m2) <= best + PLATE_BAND]
        return sorted(pool, key=_newest_key)[0]
    return sorted(pool, key=lambda c: (not c.primary,) + _newest_key(c))[0]


def same_building(a: Candidate, b: Candidate) -> bool:
    """Whether two candidates are the same building seen by two captures."""
    from . import screening

    if a.centre is None or b.centre is None:
        return False
    return screening._metres(a.centre, b.centre) <= SAME_BUILDING_M


def _same_building_notes(pick: Candidate, rejected: list[Candidate]) -> list[FetchRecord]:
    """One record when other captures outline the *same* building at a different size.

    This is the podium case, and it is not a tie between two buildings - it is one
    building whose extent the captures disagree about. At the Los Angeles office the
    2024 capture outlines 2,938 m2 and the 2025 capture 1,566 m2, 9 m apart at the
    centroid and 87 % nested; the plate (1,420 m2 over 17 storeys) says the smaller is
    the tower, and `vexcel.py` already records that Vexcel tends to outline a podium
    rather than a tower. At the Houston office four captures outline 3,700 to 4,320 m2
    against the chosen 1,104 m2 - and D8's roof mask, which is derived from imagery and
    knows about neither number, measured 1,064 m2.

    **The solar flag can differ between the two**, which is consistent with panels on a
    podium deck and none on the tower, and it decides whether `PV_ROOF` runs at all.

    Collapsed into one record: Houston produced four near-identical ones, and four
    sentences saying the same thing is how a real warning gets skimmed past.
    """
    kin = [c for c in rejected
           if same_building(pick, c) and c.area_m2 and pick.area_m2
           and not (0.8 <= c.area_m2 / pick.area_m2 <= 1.25)]
    if not kin:
        return []

    biggest = max(kin, key=lambda c: c.area_m2)
    disagree = [c for c in kin
                if c.solar is not None and pick.solar is not None and c.solar != pick.solar]
    return [FetchRecord(
        layer="vexcel", what="property/extract:extent", status="fallback",
        detail=(
            f"{len(kin)} other capture(s) outline what looks like the same building at "
            f"{min(c.area_m2 for c in kin):,.0f} to {biggest.area_m2:,.0f} m2 against the "
            f"chosen {pick.area_m2:,.0f} m2 (up to {biggest.area_m2 / pick.area_m2:.1f}x, "
            f"largest from {biggest.collection}); the floor plate chose the smaller, which "
            f"on a tower is the tower rather than the podium it stands on"
            + (f". **{len(disagree)} of them report rooftop solar where the chosen capture "
               f"does not** ({', '.join(c.collection or '?' for c in disagree[:3])}), and "
               f"that decides whether PV_ROOF runs or skips as already_done"
               if disagree else "")
        )[:500],
    )]


def _spread(pool: list[Candidate]) -> str:
    """What else was on offer, so a surprising choice can be checked by a reader."""
    areas = sorted({round(c.area_m2) for c in pool if c.area_m2})
    if len(areas) < 2:
        return f"the only footprint on offer was {areas[0] if areas else 'none'} m2"
    return (f"{len(pool)} candidates spanning {areas[0]:,} to {areas[-1]:,} m2 "
            f"over {len({c.collection for c in pool})} capture(s)")
