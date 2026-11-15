"""Acquire the first-stage public inputs, enforcing the delivered sizes and hashes.

Raw data stays outside Git. Example:
python -m backend.evals.high_level.acquire_bdg2 \
    --cache-dir /private/tmp/leto-validation-inputs-400/bdg2 \
    --report /private/tmp/leto-validation-inputs-400/acquisition.json

Definitions are pinned to #403 revision 081a433's bdg2.yaml. Mutable upstream
URLs are accepted ONLY when bytes still match that delivered version.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from urllib.request import urlopen

BASE = "https://media.githubusercontent.com/media/buds-lab/building-data-genome-project-2/master/data/"
SOURCE_REVISION = "081a433fc63301fbb73b732ad01155042b34b85c"
DATASET = "Building Data Genome Project 2; Miller et al., Scientific Data 7, 368 (2020), doi:10.1038/s41597-020-00712-x"
LICENSE_URL = "https://github.com/buds-lab/building-data-genome-project-2/blob/master/LICENSE"


@dataclass(frozen=True)
class Input:
    name: str
    relative_url: str
    size: int
    sha256: str


INPUTS = (
    Input("metadata.csv", "metadata/metadata.csv", 272024, "992d0b29f24f96ad4332bc4dbb534b7bdd7dd2689aad093f94e93068ecddca02"),
    Input("weather.csv", "weather/weather.csv", 19457782, "a8189f1c6acdf3b9933a9e6354b8e7c1278cd56a7075929623a17565d44f04bd"),
    Input("electricity_cleaned.csv", "meters/cleaned/electricity_cleaned.csv", 174977911, "b6ffc9b4dfcefe5c753594730a08ae822b0d50fec6815abb8f185591e6c630a3"),
    Input("gas_cleaned.csv", "meters/cleaned/gas_cleaned.csv", 22002654, "b3b059d32e8a16a92fb274e2e90483fac9b7797e42a9e07840ab9df130266405"),
)


def verify(path: Path, spec: Input) -> dict:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    if size != spec.size or digest.hexdigest() != spec.sha256:
        raise ValueError(f"{spec.name}: byte count or SHA256 does not match delivered manifest")
    return {"name": spec.name, "bytes": size, "sha256": digest.hexdigest(), "status": "verified"}


def acquire(spec: Input, folder: Path, opener=urlopen) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / spec.name
    if target.exists():
        return {**verify(target, spec), "acquisition": "existing_verified"}
    part = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".bdg2-", delete=False) as sink:
            part = Path(sink.name)
            size = 0
            with opener(BASE + spec.relative_url, timeout=30) as response:
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > spec.size:
                        raise ValueError(f"{spec.name}: response exceeds delivered manifest size")
                    sink.write(chunk)
        record = verify(part, spec)
        part.replace(target)
        return {**record, "acquisition": "downloaded_verified"}
    finally:
        if part is not None and part.exists():
            part.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--files", nargs="+", choices=[s.name for s in INPUTS])
    args = parser.parse_args()
    records = []
    report = {"dataset": DATASET, "license_url": LICENSE_URL, "source_revision": SOURCE_REVISION,
              "retrieved_utc": datetime.now(timezone.utc).isoformat(), "files": records}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    for spec in INPUTS:
        if args.files and spec.name not in args.files:
            continue
        print(f"Verifying {spec.name} ({spec.size} bytes)", flush=True)
        try:
            records.append({**acquire(spec, args.cache_dir), "url": BASE + spec.relative_url})
        except Exception as exc:
            records.append({"name": spec.name, "status": "failed", "error": str(exc)})
            args.report.write_text(json.dumps(report, indent=2) + "\n")
            raise
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Verified {len(records)} inputs; wrote {args.report}", flush=True)


if __name__ == "__main__":
    main()
