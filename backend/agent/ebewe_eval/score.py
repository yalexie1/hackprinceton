"""Score predicted vs EBEWE site EUI. python -m backend.agent.ebewe_eval.score <arm> [--summary out.json]
All metrics are on EUI (kBtu/ft2): our model usually covers one suite or unit, EBEWE is whole-building, so totals
are never compared. Reports a naive constant predictor beside every model number (everyone gets the cohort median)."""
import json
import math
import random
import statistics as st
import sys

from backend.agent.ebewe_eval.common import KWH_PER_M2_TO_KBTU_PER_FT2 as K
from backend.agent.ebewe_eval.common import WORK


def spearman(x, y):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for k, i in enumerate(order):
            r[i] = k
        return r
    a, b, n = rank(x), rank(y), len(x)
    ma, mb = sum(a) / n, sum(b) / n
    c = sum((i - ma) * (j - mb) for i, j in zip(a, b))
    d = math.sqrt(sum((i - ma) ** 2 for i in a) * sum((j - mb) ** 2 for j in b))
    return c / d if d else float("nan")


def two_sided_factor2(ratio: float) -> bool:
    """A miss by a factor of 2 in EITHER direction (ratio at least 2 or at most 0.5)."""
    return ratio >= 2 or ratio <= 0.5


def rows_for(arm: str):
    sel = {s["sid"]: s for s in json.loads((WORK / "selected.json").read_text())}
    done: dict = {}
    for line in (WORK / f"results_{arm}.jsonl").read_text().splitlines():
        r = json.loads(line)
        done[r["sid"]] = r                                    # a later record for a sid replaces an earlier one
    rows, failed = [], []
    for sid, r in done.items():
        if r["status"] != "done" or not r.get("area_m2"):
            failed.append(r)
            continue
        s = sel[sid]
        f = K / r["area_m2"]
        rows.append({"use": s["use_type"], "truth": s["truth_eui_kbtu_ft2"], "area": r["area_m2"],
                     "pred": (r["elec"] + r["gas"]) * f,
                     "lo": ((r["elec_lo"] or r["elec"]) + (r["gas_lo"] or r["gas"])) * f,
                     "hi": ((r["elec_hi"] or r["elec"]) + (r["gas_hi"] or r["gas"])) * f})
    return rows, failed


def metrics(rows):
    if not rows:
        return {"n": 0}
    err = [r["pred"] / r["truth"] - 1 for r in rows]
    random.seed(1)
    boots = sorted(st.median(abs(random.choice(err)) for _ in err) for _ in range(2000))
    med = st.median(r["truth"] for r in rows)
    cov = [r["lo"] <= r["truth"] <= r["hi"] for r in rows]
    return {"n": len(rows), "median_abs_error": st.median(abs(e) for e in err), "ci90": [boots[100], boots[1900]],
            "median_signed_error": st.median(err), "within_25": sum(abs(e) <= .25 for e in err) / len(err),
            "off_by_2x_either_way": sum(two_sided_factor2(1 + e) for e in err) / len(err),
            "range_contained_truth": sum(cov) / len(cov), "truth_above_range": sum(r["truth"] > r["hi"] for r in rows),
            "truth_below_range": sum(r["truth"] < r["lo"] for r in rows),
            "rank_correlation": spearman([r["pred"] for r in rows], [r["truth"] for r in rows]) if len(rows) > 3 else None,
            "constant_predictor_median_abs_error": st.median(abs(med / r["truth"] - 1) for r in rows),
            "cohort_median_truth_eui": med}


def main(argv: list[str]) -> None:
    arm = argv[0]
    rows, failed = rows_for(arm)
    out = {"arm": arm, "scored": len(rows), "failed": len(failed), "all": metrics(rows)}
    for use in sorted({r["use"] for r in rows}):
        out[use] = metrics([r for r in rows if r["use"] == use])
    for k, v in out.items():
        if isinstance(v, dict) and v.get("n"):
            print(f"{k:18} n={v['n']:3d} medAPE {v['median_abs_error']*100:5.1f}% signed {v['median_signed_error']*100:+6.1f}% "
                  f"within25 {v['within_25']*100:3.0f}% off2x {v['off_by_2x_either_way']*100:3.0f}% "
                  f"coverage {v['range_contained_truth']*100:3.0f}% constant-predictor {v['constant_predictor_median_abs_error']*100:5.1f}%")
    print(f"{len(failed)} failed or refused of {len(rows) + len(failed)}")
    if "--summary" in argv:
        path = argv[argv.index("--summary") + 1]
        open(path, "w").write(json.dumps(out, indent=1))        # aggregates only: no sids, addresses or per-building values


if __name__ == "__main__":
    main(sys.argv[1:])
