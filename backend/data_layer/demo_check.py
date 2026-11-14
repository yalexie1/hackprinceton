"""Demo-day runbook checks: assemble each demo property live and fail loudly.

Requested by the lead. The point is to find on a laptop, in advance, the things that
would otherwise be found on stage — and every check here exists because something in
this project actually went wrong that way:

| check | why it is here |
|---|---|
| existing rooftop solar | `PV_ROOF` skips as `already_done`, so the live plan silently loses a measure the golden example shows. The Los Angeles office has panels. |
| electricity price | required by the contract; without it assembly raises |
| gas price | a missing one made `baseline.py` read a 1920s house as all-electric |
| utility resolved | an unnamed utility means **unconfirmed**, not LADWP, and the LADWP rebates and CPUC clauses key on it |
| comps for value uplift | `plan_value_uplift` returns `None` below ten, and the window that gives Los Angeles offices twelve gives them one if it is tightened |
| sitting tenants | an empty list means the vacant schedule; `None` means no data, and the two must not be confused |
| roof mask agreement | the mask is a **lower bound** on a commercial roof: 0.47 to 0.78 of the footprint, against 0.95 on the house |
| scan richness | a one-room, sixteen-panorama scan makes a poor 3D tour |
| provenance errors | an `error` record is a real fault; `missing` is often normal |
| fetch time | upstream latency has been measured between 2 s and 76 s on the same call |

**Nothing here writes to `data/cache`.** The run points `DATA_LAYER_CACHE_DIR` at a
temporary directory, which is why `api._cache_dir()` and `external.weather_path` were
made to honour it. That also means every fetch is cold, so the timings are the
worst case rather than the demo's warm case - which is the number worth knowing.

Usage:

    python -m backend.data_layer.demo_check                     # the golden three
    python -m backend.data_layer.demo_check SID [SID ...]       # named properties
    python -m backend.data_layer.demo_check --analysis          # also run the plan
    python -m backend.data_layer.demo_check --keep-cache        # use the real cache

Exit status is 1 if any check **failed**, 0 if the worst was a warning, so it can gate
a demo rehearsal.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Literal, Optional

Status = Literal["ok", "warn", "fail"]

#: Cold-fetch budget for one bundle. Upstream latency has been measured from 2.2 s to
#: 76 s on identical calls, so this is deliberately generous: it is here to catch a
#: hung service, not to police normal variance.
SLOW_BUNDLE_S = 45.0

#: Below this a scan makes a thin 3D tour. The current golden office has 8 rooms and
#: 36 panoramas; the proposed replacement has 17 and 339.
MIN_ROOMS = 3
MIN_PANOS = 10

#: `plan_value_uplift` returns `None` below this. Imported from the analysis lane when
#: available so the two cannot drift.
DEFAULT_MIN_COMPS = 10

#: The mask-to-footprint band seen on real commercial roofs. Outside it, the D8
#: cross-check disagrees with the Vexcel footprint enough to be worth a look.
MASK_RATIO_LOW = 0.30
MASK_RATIO_HIGH = 1.10


@dataclass
class Check:
    name: str
    status: Status
    detail: str


def _min_comps() -> int:
    try:
        from backend.analysis.finance.value.value import MIN_COMPS

        return int(MIN_COMPS)
    except Exception:
        return DEFAULT_MIN_COMPS


def check_property(sid: str, *, run_analysis: bool = False) -> list[Check]:
    """Every check for one property, in the order a reader wants them."""
    from backend.data_layer import api, imagery, vexcel

    out: list[Check] = []

    started = time.time()
    try:
        bundle = api.get_property_bundle(sid, live=True, refresh=True)
    except Exception as exc:
        return [Check("bundle", "fail", f"{type(exc).__name__}: {str(exc)[:160]}")]
    elapsed = time.time() - started

    out.append(Check("bundle", "ok", f"assembled in {elapsed:.1f} s (cold)"))
    out.append(Check(
        "fetch time",
        "warn" if elapsed > SLOW_BUNDLE_S else "ok",
        f"{elapsed:.1f} s cold against a {SLOW_BUNDLE_S:.0f} s budget"
        + ("; upstream was slow, re-run before reading anything into it" if elapsed > SLOW_BUNDLE_S else ""),
    ))

    # ---- provenance
    errors = [n for n in bundle.provenance if n.status == "error"]
    out.append(Check(
        "provenance", "fail" if errors else "ok",
        f"{len(errors)} error record(s): {[n.what for n in errors]}" if errors
        else f"{len(bundle.provenance)} records, none in error",
    ))

    # ---- tariff
    tariff = bundle.tariff
    out.append(Check(
        "electricity price", "ok" if tariff.electricity_usd_per_kwh else "fail",
        f"{tariff.electricity_usd_per_kwh:.4f} USD/kWh" if tariff.electricity_usd_per_kwh
        else "absent, and it is a required contract field",
    ))
    out.append(Check(
        "gas price", "ok" if tariff.gas_usd_per_kwh else "warn",
        f"{tariff.gas_usd_per_kwh:.6f} USD/kWh" if tariff.gas_usd_per_kwh
        else "absent: baseline.py then reads the building as all-electric and prices gas at zero",
    ))
    named = tariff.utility and "state average" not in tariff.utility
    out.append(Check(
        "utility", "ok" if named else "warn",
        f"{tariff.utility}" + ("" if named else " - unconfirmed, which is NOT LADWP; "
                               "the LADWP rebates and the CPUC clauses key on this"),
    ))
    out.append(Check(
        "export regime", "ok" if tariff.export_regime else "warn",
        str(tariff.export_regime or "unset, so PV export value has no rule"),
    ))

    # ---- the scan
    rooms = len(bundle.matterport.rooms)
    panos = len(bundle.matterport.panos)
    thin = rooms < MIN_ROOMS or panos < MIN_PANOS
    out.append(Check(
        "scan", "warn" if thin else "ok",
        f"{rooms} rooms, {panos} panoramas"
        + (f" - thin for a 3D tour (want {MIN_ROOMS}+ and {MIN_PANOS}+)" if thin else ""),
    ))

    # ---- Vexcel and the roof
    structure = vexcel.primary_structure(bundle.vexcel) if bundle.vexcel else None
    if structure is None:
        out.append(Check("roof", "fail", "no Vexcel primary structure, so no roof data at all"))
    else:
        attrs = structure.attributes
        solar = attrs.get("roof-objects.solar.value")
        has_solar = bool(solar) and str(solar).casefold() not in ("false", "0", "none")
        out.append(Check(
            "existing solar", "fail" if has_solar else "ok",
            "panels already on the roof: PV_ROOF will skip as already_done and the live "
            "plan will differ from the golden example" if has_solar
            else "none detected, so PV_ROOF is live",
        ))
        footprint = structure.footprint_area_m2
        out.append(Check(
            "roof footprint", "ok" if footprint else "warn",
            f"{footprint:,.0f} m2 {attrs.get('roof-characteristics.shape.value')}"
            f"/{attrs.get('roof-characteristics.material.class.value')}" if footprint
            else "no footprint area",
        ))
        out.append(_mask_check(bundle, footprint, sid, imagery))
        out.append(_roof_source_check(bundle, structure))

    # ---- CoStar, occupancy and market
    costar = bundle.costar
    if costar is None:
        out.append(Check("costar", "fail", "no CoStar record, so no vintage, area or market"))
    else:
        out.append(Check(
            "costar", "ok",
            f"{costar.property_type} built {costar.year_built}, {costar.stories} storeys, "
            f"class {costar.building_class}",
        ))
        out.append(_occupancy_check(costar))
        out.append(_market_check(costar))

    if run_analysis:
        out += _analysis_checks(bundle)
    return out


def _mask_check(bundle, footprint: Optional[float], sid: str, imagery) -> Check:
    """The D8 cross-check. A commercial mask is a **lower bound**: measured 0.47 to
    0.78 of the footprint against 0.95 on the golden house, because a big flat roof
    with plant and setbacks masks less completely."""
    parcel = bundle.vexcel.parcel_wkt if bundle.vexcel else None
    if not parcel or not footprint:
        return Check("roof mask", "warn", "no parcel polygon, so no mask cross-check")
    try:
        area, _ = imagery.roof_area_m2(parcel, sid=sid)
    except Exception as exc:
        return Check("roof mask", "warn", f"detection failed: {type(exc).__name__}")
    if area is None:
        return Check("roof mask", "warn",
                     "SAM 3 found no decodable roof mask, so there is no cross-check")
    ratio = area / footprint
    inside = MASK_RATIO_LOW <= ratio <= MASK_RATIO_HIGH
    return Check(
        "roof mask", "ok" if inside else "warn",
        f"{area:,.0f} m2, {ratio:.2f} of the footprint"
        + ("" if inside else f" - outside the {MASK_RATIO_LOW}-{MASK_RATIO_HIGH} band seen on "
                             f"real roofs, so the two sources disagree"),
    )


def _roof_source_check(bundle, structure) -> Check:
    """Does the bundle's roof agree with the building at the property's address?

    The bundle asks Vexcel for the parcel **at the Matterport georeference**. An area
    query, then taking the smallest structure whose footprint *encloses* the point,
    can name a different building - and on all three commercial golden properties it
    does. At the Los Angeles office the two differ on the solar flag itself, which
    decides whether `PV_ROOF` fires. Measured 2026-11-14:

    | property | bundle | enclosing |
    |---|---|---|
    | house | 190 m2, no solar | 190 m2, no solar - agree |
    | LA office | 2,207 m2, **no solar** | 2,938 m2, **solar** |
    | Houston office | 4,320 m2 | 1,104 m2 |
    | Culver Connect | 4,454 m2 | 2,567 m2 |

    So which roof the demo models is query-mode dependent. This check does not decide
    which is right - that needs resolving with the sponsor - it refuses to let the
    disagreement go unnoticed.
    """
    from backend.data_layer import index, screening

    # **The CoStar address geocode, not `bundle.summary`.** The summary's lat/lon comes
    # from the Matterport georeference, which is what the bundle already used to pick
    # its parcel - comparing against it compares the georeference with itself. The
    # index's coordinates come from the CoStar property record, so the two locators are
    # independent, which is the only way this check means anything. They are 45 m apart
    # at the Los Angeles office.
    indexed = index.by_sid().get(bundle.summary.sid)
    if indexed is None or indexed.lat is None or indexed.lon is None:
        return Check("roof source", "warn",
                     "no CoStar address coordinates, so the bundle's roof cannot be "
                     "cross-checked against an independent locator")
    try:
        enclosing, _ = screening.containing_structure(indexed.lat, indexed.lon)
    except Exception as exc:
        return Check("roof source", "warn", f"cross-check failed: {type(exc).__name__}")
    if enclosing is None:
        return Check("roof source", "warn",
                     "no structure encloses the address point, so the bundle's roof cannot "
                     "be confirmed as this building's")

    theirs = enclosing.get("footprint.area")
    ours = structure.footprint_area_m2
    solar_ours = _truthy(structure.attributes.get("roof-objects.solar.value"))
    solar_theirs = _truthy(enclosing.get("roof-objects.solar.value"))
    same_area = ours and theirs and abs(ours - theirs) / max(ours, theirs) < 0.02

    from backend.data_layer import screening as _s

    apart = _s._metres((bundle.summary.lat or indexed.lat, bundle.summary.lon or indexed.lon),
                       (indexed.lat, indexed.lon))
    if solar_ours != solar_theirs:
        return Check("roof source", "fail",
                     f"the two Vexcel query modes disagree about **solar**: the bundle's "
                     f"structure ({ours:,.0f} m2) says {solar_ours}, the structure enclosing "
                     f"the address ({theirs:,.0f} m2) says {solar_theirs}. The two locators are "
                     f"{apart:.0f} m apart. This decides whether PV_ROOF fires, so resolve it "
                     f"before the demo")
    if not same_area:
        return Check("roof source", "warn",
                     f"the bundle's structure is {ours:,.0f} m2 but the one enclosing the "
                     f"address is {theirs:,.0f} m2; the solar flag agrees, so the roof *area* "
                     f"is the uncertain part")
    return Check("roof source", "ok",
                 f"bundle and address agree on the building ({ours:,.0f} m2)")


def _truthy(value) -> bool:
    return bool(value) and str(value).casefold() not in ("false", "0", "none")


def _occupancy_check(costar) -> Check:
    """`tenancies == []` is the vacant case and drives the `office_vacant` schedule;
    `occupancy is None` is no data and keeps the defaults. Not the same thing."""
    occupancy = costar.occupancy
    if occupancy is None:
        return Check("occupancy", "warn",
                     "no tenancy data: the registry will use occupied defaults")
    if not occupancy.tenancies:
        return Check("occupancy", "warn",
                     "records exist but no sitting tenant, so the building is modelled vacant")
    return Check("occupancy", "ok",
                 f"{len(occupancy.tenancies)} sitting tenants, "
                 f"{occupancy.employees_total} employees, "
                 f"{occupancy.occupied_area_m2:,.0f} m2 occupied"
                 if occupancy.occupied_area_m2 else
                 f"{len(occupancy.tenancies)} sitting tenants")


def _market_check(costar) -> Check:
    minimum = _min_comps()
    market = costar.market
    if market is None or market.cap_rate is None:
        return Check("market", "warn",
                     f"no cap rate, so Plan.value_uplift will be None "
                     f"(residential properties have no commercial comps, which is correct)")
    if market.comp_count < minimum:
        return Check("market", "fail",
                     f"only {market.comp_count} comps against a minimum of {minimum}: "
                     f"value uplift will silently not appear")
    return Check("market", "ok",
                 f"cap rate {market.cap_rate.expected:.4f} over {market.comp_count} comps")


def _analysis_checks(bundle) -> list[Check]:
    """The analysis door, end to end. Slow - a real plan was measured at 20 to 35 s a
    property - so this is behind `--analysis`."""
    out: list[Check] = []
    try:
        from backend.analysis import api as analysis
    except Exception as exc:
        return [Check("analysis", "warn", f"not importable: {type(exc).__name__}")]

    started = time.time()
    try:
        model = analysis.build_building_model(bundle)
        out.append(Check("model", "ok",
                         f"{len(model.zones)} zones, {len(model.surfaces)} surfaces, "
                         f"{len(model.assumptions)} assumptions in {time.time() - started:.1f} s"))
    except Exception as exc:
        return out + [Check("model", "fail", f"{type(exc).__name__}: {str(exc)[:160]}")]

    started = time.time()
    try:
        baseline = analysis.run_baseline(bundle, model)
        total = getattr(baseline, "annual_cost_usd", None)
        out.append(Check("baseline", "ok",
                         f"built in {time.time() - started:.1f} s"
                         + (f", {total.expected:,.0f} USD/yr" if total else "")))
    except Exception as exc:
        out.append(Check("baseline", "fail", f"{type(exc).__name__}: {str(exc)[:160]}"))
    return out


# ---------- running ----------

def golden_sids() -> list[str]:
    """The demo properties, read from `specs/examples/` rather than hard-coded, since
    folders get repointed."""
    from backend.data_layer import api

    return [api._load(folder, "property_summary.json")["sid"] for folder in api._folders()]


_SYMBOL = {"ok": "ok  ", "warn": "WARN", "fail": "FAIL"}


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    run_analysis = "--analysis" in argv
    keep_cache = "--keep-cache" in argv
    sids = [a for a in argv if not a.startswith("--")]

    os.environ["DATA_LAYER_LIVE"] = "1"
    temporary = None
    if not keep_cache:
        # Nothing here touches the real cache, so a rehearsal cannot leave bundles or
        # weather files behind - which is what made a test asserting one file's
        # absence fail. It also means every timing below is a cold worst case.
        temporary = tempfile.mkdtemp(prefix="demo-check-cache-")
        os.environ["DATA_LAYER_CACHE_DIR"] = temporary

    if not sids:
        sids = golden_sids()

    print(f"demo-day checks on {len(sids)} propert{'y' if len(sids) == 1 else 'ies'}: "
          f"{', '.join(sids)}")
    print(f"cache: {temporary or 'the real one (--keep-cache)'}"
          f"{'' if run_analysis else '   [analysis skipped; pass --analysis]'}\n")

    worst: Status = "ok"
    for sid in sids:
        print(f"--- {sid}")
        for check in check_property(sid, run_analysis=run_analysis):
            print(f"  {_SYMBOL[check.status]}  {check.name:17} {check.detail}")
            if check.status == "fail":
                worst = "fail"
            elif check.status == "warn" and worst == "ok":
                worst = "warn"
        print()

    print({"ok": "All checks passed.",
           "warn": "Passed with warnings - read them before the demo.",
           "fail": "FAILURES above. These will show on stage."}[worst])
    return 1 if worst == "fail" else 0


if __name__ == "__main__":        # pragma: no cover - entry point
    raise SystemExit(main())
