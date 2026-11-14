"""Prepare real side-angle discovery photos, privately, without running an audit.

Run from the repository root; see frontend/README.md. No sponsor bytes or keys
belong in this script or version control.
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sid")
    parser.add_argument("latitude", type=float)
    parser.add_argument("longitude", type=float)
    parser.add_argument("--prefer", choices=("north", "south", "east", "west"), default="north")
    parser.add_argument("--context-m", type=float, default=0, help="Optional wider geographic crop, in metres; never a property boundary")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.sid):
        parser.error("sid must be a single model identifier")
    if not (-85 < args.latitude < 85 and -180 <= args.longitude <= 180):
        parser.error("latitude/longitude outside the supported range")
    if args.context_m and not 20 <= args.context_m <= 200:
        parser.error("context crop must be 20–200 metres")

    from dotenv import load_dotenv
    from backend.data_layer import cache, imagery, vexcel
    load_dotenv(ROOT / ".env")
    if cache.cache_root().resolve() != ROOT / "data/cache":
        parser.error("unset DATA_LAYER_CACHE_DIR: this helper prepares the repository's private photo cache")
    data, _ = vexcel.get_vexcel_data_with_notes(
        vexcel.point_wkt(args.latitude, args.longitude),
        at=(args.latitude, args.longitude), locator="matterport")
    if not data or not data.parcel_wkt:
        raise SystemExit("No actual Vexcel parcel found; no photo manifest written.")
    region = data.parcel_wkt
    if args.context_m:
        # A display crop around the actual scan point, not inferred building
        # geometry. This avoids clipping the house in its long narrow parcel.
        dy = args.context_m / 2 / 111320
        dx = dy / math.cos(math.radians(args.latitude))
        w, e = args.longitude - dx, args.longitude + dx
        s, n = args.latitude - dy, args.latitude + dy
        region = f"POLYGON (({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))"
    paths = {}
    for direction in vexcel.oblique_directions(data.parcel_wkt):
        try:
            path, _ = imagery.fetch_oblique(region, direction, sid=args.sid)
            if path and (ROOT / path).is_file():
                paths[direction] = path
        except Exception as exc:
            print(f"{direction}: unavailable ({type(exc).__name__})", file=sys.stderr)
    if not paths:
        raise SystemExit("No real side-angle photos were returned; existing manifest unchanged.")
    manifest = {"sid": args.sid, "provider": "Vexcel", "preferred_direction": args.prefer, "oblique_paths": paths}
    path = ROOT / "data/cache/frontend-property-imagery" / f"{args.sid}.json"
    cache.atomic_write_path(path, json.dumps(manifest).encode())
    print(f"{args.sid}: cached {len(paths)} actual side-angle photos; prefers {args.prefer}.")


if __name__ == "__main__":
    main()
