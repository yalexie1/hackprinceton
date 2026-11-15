"""PV yield cross-check: our modelled design against PVGIS (physics 01 PV-10).

Reuses backend.analysis.model.benchmark.pv.cross_check_pv, which already implements
PV-10 including the transposition ratio between our plane orientations and PVGIS's,
the loss ratio, and the PV-09 tolerance. This module runs the golden properties through
it and records the result; it implements no physics of its own.

On PVWatts. Issue #394 asks for "PV vs PVWatts/PVGIS". specs/physics.md section 5
records that developer.nrel.gov and nsrdb.nrel.gov do not resolve from this environment,
so PVWatts is not available as a reference. main() retries once and records the outcome
in `pvwatts` rather than leaving a reader to assume it was checked.

Writes backend/evals/out/pv_crosscheck.json
"""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "backend/evals/out"
EXAMPLES = ROOT / "specs/examples"
PROPERTIES = ("office", "house", "office_houston")

# PVGIS mountingplace used for the cached reference. free vs building moves E_y by
# 4-5% (1754 vs 1677 kWh/kWp at Los Angeles), so a row without it is not reproducible.
MOUNTINGPLACE = "free"


def pv_row(sid: str, annual_kwh: float | None, system_kw_dc: float | None,
           pvgis_kwh_per_kw: float | None, mountingplace: str | None,
           tolerance: float | None = None, within: bool | None = None,
           deviation: float | None = None, warnings: list[str] | None = None) -> dict:
    """One property's comparison. Copies PV-10's verdict; computes only the raw ratio."""
    if not mountingplace:
        raise ValueError("mountingplace is required: PVGIS free vs building moves the "
                         "reference yield by 4-5%, so a row without it is not reproducible")

    row: dict = {"sid": sid, "mountingplace": mountingplace,
                 "system_kw_dc": system_kw_dc, "annual_kwh": annual_kwh,
                 "pvgis_kwh_per_kw": pvgis_kwh_per_kw,
                 "kwh_per_kw": None, "pct_diff": None,
                 "pv10_deviation_pct": None if deviation is None else round(100 * deviation, 2),
                 "pv10_tolerance_pct": None if tolerance is None else round(100 * tolerance, 2),
                 "pv10_within": within,
                 "warnings": warnings or []}

    if not annual_kwh or not system_kw_dc or system_kw_dc <= 0 or not pvgis_kwh_per_kw:
        row["status"] = "not_checked"
        row["reason"] = ("no PV design for this property" if not annual_kwh or not system_kw_dc
                         else "no PVGIS reference yield for the site")
        return row

    row["kwh_per_kw"] = round(annual_kwh / system_kw_dc, 2)
    row["pct_diff"] = round(100 * (row["kwh_per_kw"] / pvgis_kwh_per_kw - 1), 2)
    row["status"] = "checked"
    return row


def _pvwatts_reachable() -> dict:
    try:
        socket.getaddrinfo("developer.nrel.gov", 443)
        return {"status": "resolves", "note": "retry the PVWatts comparison; it was "
                                              "unavailable when specs/physics.md was written"}
    except socket.gaierror as exc:
        return {"status": "unavailable",
                "note": f"developer.nrel.gov does not resolve from this environment ({exc}); "
                        f"PVGIS is the only reference used. Matches specs/physics.md section 5."}


def main() -> int:
    from backend.schema import PropertyBundle
    from backend.analysis import api
    from backend.analysis.model.benchmark.checks import check_pv

    rows = []
    for name in PROPERTIES:
        path = EXAMPLES / name / "property_bundle.json"
        if not path.is_file():
            continue
        bundle = PropertyBundle(**json.load(open(path)))
        sid = bundle.summary.sid
        try:
            model = api.build_building_model(bundle)
            baseline = api.run_baseline(bundle, model)
            design = api.design_pv(bundle, model, baseline)
            warnings, check = check_pv(design, model.roof_planes, bundle.climate,
                                       weather_csv=api._weather_csv(bundle))
            rows.append(pv_row(sid=sid,
                               annual_kwh=design.annual_kwh.expected if design else None,
                               system_kw_dc=design.system_kw_dc if design else None,
                               pvgis_kwh_per_kw=bundle.climate.pvgis_annual_kwh_per_kw,
                               mountingplace=MOUNTINGPLACE,
                               tolerance=check.tolerance, within=check.within,
                               deviation=check.deviation, warnings=warnings))
        except Exception as exc:
            rows.append(pv_row(sid=sid, annual_kwh=None, system_kw_dc=None,
                               pvgis_kwh_per_kw=bundle.climate.pvgis_annual_kwh_per_kw,
                               mountingplace=MOUNTINGPLACE,
                               warnings=[f"{type(exc).__name__}: {exc}"]))
        print(f"{name}: {rows[-1]['status']} "
              f"{rows[-1].get('kwh_per_kw')} vs PVGIS {rows[-1]['pvgis_kwh_per_kw']} "
              f"({rows[-1].get('pct_diff')}%)", flush=True)

    checked = [r for r in rows if r["status"] == "checked"]
    payload = {
        "status": "ok" if checked else "not_run",
        "title": "PV yield vs PVGIS",
        "question": "Does our modelled PV yield agree with PVGIS, an independent "
                    "estimate of the same system at the same site?",
        "entry": "PV-10",
        "mountingplace": MOUNTINGPLACE,
        "pvwatts": _pvwatts_reachable(),
        "n_checked": len(checked),
        "rows": rows,
        "caveats": [
            "PVGIS is a model, not a meter: agreement means two models agree, not that "
            "either is right. An empirical PV check needs metered output (e.g. the NIST "
            "campus arrays) and is not done here.",
            "PVGIS mountingplace is recorded because free vs building moves the reference "
            "yield by 4-5%.",
            "PV-10 compares after moving PVGIS to our plane orientation and losses; "
            "pct_diff is the raw ratio before that adjustment and will differ.",
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pv_crosscheck.json").write_text(json.dumps(payload, indent=1))
    print(f"\nwrote {OUT / 'pv_crosscheck.json'}  checked={len(checked)}/{len(rows)}")
    print(f"pvwatts: {payload['pvwatts']['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
