"""Join the CoStar/Matterport kit scans in Los Angeles to EBEWE by normalised street address, then apply the
pre-registered quality filter. Writes WORK/selected.json. Run: python -m backend.agent.ebewe_eval.match

Truth per building = median weather-normalised site EUI (kBtu/ft2) over the usable years; band = min..max.
Filter: at least 3 usable years, GFA at least 20,000 ft2, EUI between 10 and 300. One scan per address."""
import json
import re
import statistics
import urllib.request

from backend.agent.ebewe_eval.common import EBEWE_URL, USABLE_YEARS, WORK

_ABBREV = (("STREET", "ST"), ("AVENUE", "AVE"), ("BOULEVARD", "BLVD"), ("DRIVE", "DR"), ("ROAD", "RD"),
           ("PLACE", "PL"), ("NORTH", "N"), ("SOUTH", "S"), ("EAST", "E"), ("WEST", "W"))


def norm(address: str) -> str:
    a = re.sub(r"[.,#]", " ", (address or "").upper())
    for k, v in _ABBREV:
        a = re.sub(rf"\b{k}\b", v, a)
    return re.sub(r"\s+", " ", a).strip()


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def truth_for(rows: list[dict]):
    """(eui_median, eui_min, eui_max, gfa_ft2, years) from EBEWE rows of one building, or None if it fails the filter."""
    use = []
    for r in rows:
        if r.get("program_year") not in USABLE_YEARS:
            continue
        e = _f(r.get("weather_normalized_3")) or _f(r.get("site_eui"))
        g = _f(r.get("property_gfa_1"))
        if e and g and 10 <= e <= 300 and g >= 20000:
            use.append((r["program_year"], e, g))
    if len({y for y, _, _ in use}) < 3:
        return None
    eui = [e for _, e, _ in use]
    return statistics.median(eui), min(eui), max(eui), statistics.median(g for _, _, g in use), sorted({y for y, _, _ in use})


def main() -> None:
    from backend.data_layer import index
    WORK.mkdir(parents=True, exist_ok=True)
    raw = WORK / "ebewe.json"
    if not raw.is_file():
        with urllib.request.urlopen(EBEWE_URL, timeout=300) as r:
            raw.write_bytes(r.read())
    by: dict[str, list[dict]] = {}
    for r in json.loads(raw.read_text()):
        by.setdefault(norm(r.get("building_address", "")), []).append(r)
    seen, out = set(), []
    for s in sorted(index.summaries(), key=lambda s: s.sid):
        if s.state != "CA" or not s.address:
            continue
        key = norm(s.address)
        if key in seen:
            continue
        rows = by.get(key) or by.get(re.sub(r"\b(STE|SUITE|APT|UNIT|FL)\b.*$", "", key).strip())
        t = truth_for(rows) if rows else None
        if not t:
            continue
        seen.add(key)
        out.append({"sid": s.sid, "address": s.address, "use_type": s.use_type, "truth_eui_kbtu_ft2": t[0],
                    "truth_min": t[1], "truth_max": t[2], "gfa_ft2": t[3], "years": t[4]})
    order = {"office": 0, "retail": 1, "other": 2, "multifamily_unit": 3}
    out.sort(key=lambda r: (order.get(r["use_type"], 9), r["sid"]))
    (WORK / "selected.json").write_text(json.dumps(out, indent=0))
    print(f"{len(out)} buildings selected into {WORK / 'selected.json'}")


if __name__ == "__main__":
    main()
