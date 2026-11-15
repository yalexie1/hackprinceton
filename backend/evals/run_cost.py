"""Installed PV cost (COST-01) against the LBNL Tracking the Sun market distribution.

Tracking the Sun is ~1.3M real installed systems with reported up-front prices. This
compares our modelled $/W_dc for the golden properties against the interquartile range
of real systems in the same state, customer segment and most recent year.

A price inside the IQR means our cost assumption is ordinary for that market. It does
NOT mean a specific project would cost that: Tracking the Sun is reported price before
incentives, spread over installers, system sizes and hardware we do not match on.

Writes backend/evals/out/cost_check.json
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TTS = ROOT / "data/cache/evals/tts"
OUT = ROOT / "backend/evals/out"
EXAMPLES = ROOT / "specs/examples"
PROPERTIES = ("office", "house", "office_houston")

# Below this many systems a percentile is a handful of projects, not a market.
MIN_BAND_ROWS = 30

# Tracking the Sun's customer_segment vocabulary. "-1" means not reported and is
# dropped rather than guessed. Everything non-residential is pooled: on their own,
# COM/GOV/SCHOOL/NON-PROFIT are too thin per state-year to give a stable band.
SEGMENT_CODES = {
    "residential": {"RES"},
    "commercial": {"NON-RES", "COM", "GOV", "SCHOOL", "NON-PROFIT"},
}


def market_stats(rows: list[tuple[float, float]], min_year_rows: int = 1) -> dict | None:
    """rows = [(system_kw_dc, total_installed_price_usd)] -> p25/median/p75 of $/W_dc.

    A non-positive size or price is a reporting artefact, not a free system; dropped.
    """
    per_w = [price / (kw * 1000.0) for kw, price in rows if kw > 0 and price > 0]
    if len(per_w) < min_year_rows or not per_w:
        return None
    q = st.quantiles(per_w, n=4) if len(per_w) >= 4 else [min(per_w), st.median(per_w), max(per_w)]
    return {"p25": round(q[0], 3), "median": round(st.median(per_w), 3),
            "p75": round(q[2], 3), "n": len(per_w)}


def cost_row(sid: str, state: str, segment: str, our_usd_per_w: float | None,
             stats: dict | None) -> dict:
    """Our modelled $/W against the market band. Copies the band, computes no physics."""
    row: dict = {
        "sid": sid, "state": state, "segment": segment,
        "our_usd_per_w": None if our_usd_per_w is None else round(our_usd_per_w, 3),
        "p25_usd_per_w": None, "median_usd_per_w": None, "p75_usd_per_w": None,
        "n_systems": None, "year": None, "indicative": False, "verdict": "not_checked",
    }
    if our_usd_per_w is None or not stats:
        row["reason"] = ("no modelled PV cost for this property" if our_usd_per_w is None
                         else f"no Tracking the Sun systems for {state}/{segment}")
        return row

    row.update({"p25_usd_per_w": stats["p25"], "median_usd_per_w": stats["median"],
                "p75_usd_per_w": stats["p75"], "n_systems": stats["n"],
                "year": stats.get("year"),
                "indicative": stats["n"] < MIN_BAND_ROWS})
    row["pct_vs_median"] = round(100 * (our_usd_per_w / stats["median"] - 1), 1)
    if our_usd_per_w < stats["p25"]:
        row["verdict"] = "below_iqr"
    elif our_usd_per_w > stats["p75"]:
        row["verdict"] = "above_iqr"
    else:
        row["verdict"] = "inside_iqr"
    return row


def _band(state: str, segment: str) -> dict | None:
    """Most recent installation year with enough systems, for one state and segment."""
    import pyarrow.parquet as pq

    path = TTS / f"{state}.parquet"
    if not path.is_file():
        return None
    table = pq.read_table(path, columns=["installation_date", "pv_system_size_dc",
                                         "total_installed_price", "customer_segment"])
    by_year: dict[int, list[tuple[float, float]]] = {}
    dates = table.column("installation_date").to_pylist()
    sizes = table.column("pv_system_size_dc").to_pylist()
    prices = table.column("total_installed_price").to_pylist()
    segs = table.column("customer_segment").to_pylist()
    for d, kw, price, seg in zip(dates, sizes, prices, segs):
        if not d or kw is None or price is None or not seg:
            continue
        if str(seg).strip().upper() not in SEGMENT_CODES[segment]:
            continue
        try:
            year = int(str(d)[:4])
        except ValueError:
            continue
        by_year.setdefault(year, []).append((float(kw), float(price)))

    for year in sorted(by_year, reverse=True):
        stats = market_stats(by_year[year], min_year_rows=5)
        if stats:
            stats["year"] = year
            return stats
    return None


def main() -> int:
    from backend.schema import PropertyBundle
    from backend.analysis import api

    rows = []
    for name in PROPERTIES:
        path = EXAMPLES / name / "property_bundle.json"
        if not path.is_file():
            continue
        bundle = PropertyBundle(**json.load(open(path)))
        sid, state = bundle.summary.sid, (bundle.summary.state or "CA")
        segment = "residential" if bundle.summary.segment == "residential" else "commercial"
        our = None
        try:
            model = api.build_building_model(bundle)
            baseline = api.run_baseline(bundle, model)
            design = api.design_pv(bundle, model, baseline)
            measure = api.price_measure(bundle, api.evaluate_measure(bundle, model, "PV_ROOF", "owner_occupier"))
            # Gross installed cost, not net_upfront_usd: Tracking the Sun reports
            # price BEFORE incentives, so comparing net would understate us.
            cost = measure.finance.installed_cost_usd.expected if measure.finance else None
            if cost and design and design.system_kw_dc > 0:
                our = cost / (design.system_kw_dc * 1000.0)
        except Exception as exc:
            rows.append({**cost_row(sid, state, segment, None, None),
                         "reason": f"{type(exc).__name__}: {exc}"})
            print(f"{name}: error {type(exc).__name__}", flush=True)
            continue
        rows.append(cost_row(sid, state, segment, our, _band(state, segment)))
        r = rows[-1]
        print(f"{name}: {r['verdict']} ours={r['our_usd_per_w']} "
              f"market p25/med/p75={r['p25_usd_per_w']}/{r['median_usd_per_w']}/"
              f"{r['p75_usd_per_w']} n={r['n_systems']} year={r['year']}", flush=True)

    checked = [r for r in rows if r["verdict"] != "not_checked"]
    payload = {
        "status": "ok" if checked else "not_run",
        "title": "Installed cost vs Tracking the Sun",
        "question": "Is our modelled installed PV cost ordinary for this market, "
                    "or are we quoting a price nobody actually pays?",
        "entry": "COST-01",
        "source": "LBNL Tracking the Sun 2024, OEDI, partitioned by state",
        "n_checked": len(checked),
        "rows": rows,
        "caveats": [
            "Tracking the Sun reports up-front price before incentives, across installers, "
            "hardware and system sizes we do not match on. Inside the IQR means our "
            "assumption is ordinary, not that a given project would cost that.",
            "Only CA and TX are downloaded, because PropertySummary.state admits only "
            "those two.",
            "A band built from fewer than 30 systems is flagged indicative and should not "
            "be read as a verdict.",
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cost_check.json").write_text(json.dumps(payload, indent=1))
    print(f"\nwrote {OUT / 'cost_check.json'}  checked={len(checked)}/{len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
