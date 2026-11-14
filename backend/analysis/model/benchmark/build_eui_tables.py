"""Rebuild ``eui_tables.csv`` from the EIA public-use microdata (physics 02 BEN-01).

Offline tool, not imported at run time. The microdata are public but large, so they are not in
the repository; download them and pass the folder:

    curl -o DIR/cbecs2018.csv https://www.eia.gov/consumption/commercial/data/2018/xls/cbecs2018_final_public.csv
    curl -o DIR/recs2020.csv  https://www.eia.gov/consumption/residential/data/2020/csv/recs2020_public_v7.csv
    python -m backend.analysis.model.benchmark.build_eui_tables DIR

Every row is one cut (survey, building type, climate, fuel group, size class) with the
weighted percentiles of site energy use intensity in kBtu per square foot, as the surveys
publish it. Only cuts with at least ``N_MIN_STORED`` sampled buildings are written.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / "eui_tables.csv"
QUANTILES = (5, 10, 25, 50, 75, 90, 95)
N_MIN_STORED = 30

# CBECS 2018 PUBCLIM: groups of ASHRAE 169-2021 zones (EIA, "Definitions of CBECS climate zones")
CBECS_CLIMATE = {1: "cold_or_very_cold", 2: "cool", 3: "mixed_mild", 4: "warm", 5: "hot_or_very_hot"}
# Size classes. Homes: total energy-consuming area (RECS TOTSQFT_EN). Offices: gross building area
# (CBECS SQFT), grouped from the published SQFTC classes so that each group keeps a usable sample.
HOME_SIZE = [(0, 1000, "lt1000"), (1000, 1500, "1000_1499"), (1500, 2000, "1500_1999"),
             (2000, 2500, "2000_2499"), (2500, 3000, "2500_2999"), (3000, 1e12, "ge3000")]
OFFICE_SIZE = [(0, 10000, "le10k"), (10000, 50000, "10k_50k"), (50000, 200000, "50k_200k"),
               (200000, 1e12, "gt200k")]


def weighted_quantiles(x, w, qs):
    """Inverse of the weighted empirical distribution, plotting position (cum_w - w/2) / sum_w."""
    x, w = np.asarray(x, float), np.asarray(w, float)
    order = np.argsort(x)
    x, w = x[order], w[order]
    pos = (np.cumsum(w) - 0.5 * w) / w.sum()
    return np.interp(np.asarray(qs, float) / 100.0, pos, x)


def size_label(sqft, classes):
    for lo, hi, label in classes:
        if lo <= sqft < hi:
            return label
    return "*"


def rows_for(df, survey, btype, weight):
    """All cuts of ``df`` over the key columns, '*' meaning every value."""
    out = []
    climates = [("climate", c) for c in sorted(df.climate.unique())] + [("climate", "*")]
    extra = []
    if "climate_digit" in df:
        extra = [("climate_digit", d) for d in sorted(df.climate_digit.unique())]
    for ckey, cval in climates + extra:
        d0 = df if cval == "*" else df[df[ckey] == cval]
        climate = cval if ckey == "climate" else f"digit:{cval}"
        for fuel in ("*", "electric", "gas"):
            d1 = d0 if fuel == "*" else d0[d0.fuel == fuel]
            for size in ["*"] + sorted(d1["size"].unique()):
                d = d1 if size == "*" else d1[d1["size"] == size]
                if len(d) < N_MIN_STORED:
                    continue
                w = d[weight]
                row = dict(survey=survey, building_type=btype, climate=climate, fuel=fuel, size=size,
                           n=len(d), weighted_count=round(float(w.sum()), 1),
                           agg_total=round(float((w * d.total).sum() / (w * d.sqft).sum()), 3))
                for name in ("total", "electricity", "gas"):
                    if name == "gas" and fuel != "gas":
                        continue
                    vals = weighted_quantiles(d[name] / d.sqft, w, QUANTILES)
                    for q, v in zip(QUANTILES, vals):
                        row[f"{name}_p{q}"] = round(float(v), 3)
                out.append(row)
    return out


def recs(path: Path):
    r = pd.read_csv(path, low_memory=False)
    df = pd.DataFrame({
        "type": r.TYPEHUQ, "climate": r.IECC_climate_code.astype(str),
        "sqft": r.TOTSQFT_EN.astype(float), "w": r.NWEIGHT,
        "total": r.TOTALBTU, "electricity": r.BTUEL, "gas": r.BTUNG,
        "fuel": np.where(r.USENG == 1, "gas",
                         np.where((r.USELP == 0) & (r.USEFO == 0), "electric", "other")),
    })
    df["climate_digit"] = df.climate.str[0]
    df["size"] = [size_label(s, HOME_SIZE) for s in df.sqft]
    rows = []
    for btype, codes in (("single_family", (2, 3)), ("multifamily", (4, 5))):
        rows += rows_for(df[df.type.isin(codes)], "RECS2020", btype, "w")
    return rows


def cbecs(path: Path):
    c = pd.read_csv(path, low_memory=False)
    o = c[(c.PBA == 2) & c.MFBTU.notna() & c.PUBCLIM.isin(CBECS_CLIMATE)]
    only_el = (o.ELUSED == 1) & (o.NGUSED == 2) & (o.FKUSED == 2) & (o.PRUSED == 2) & (o.DHUSED == 2)
    df = pd.DataFrame({
        "climate": o.PUBCLIM.map(CBECS_CLIMATE), "sqft": o.SQFT.astype(float), "w": o.FINALWT,
        "total": o.MFBTU, "electricity": o.ELBTU.fillna(0.0), "gas": o.NGBTU.fillna(0.0),
        "fuel": np.where(o.NGUSED == 1, "gas", np.where(only_el, "electric", "other")),
    })
    df["size"] = [size_label(s, OFFICE_SIZE) for s in df.sqft]
    return rows_for(df, "CBECS2018", "office", "w")


def main(folder: str) -> None:
    folder = Path(folder)
    rows = recs(folder / "recs2020.csv") + cbecs(folder / "cbecs2018.csv")
    cols = ["survey", "building_type", "climate", "fuel", "size", "n", "weighted_count", "agg_total"]
    cols += [f"{name}_p{q}" for name in ("total", "electricity", "gas") for q in QUANTILES]
    pd.DataFrame(rows).reindex(columns=cols).to_csv(OUT, index=False)
    print(f"{len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
