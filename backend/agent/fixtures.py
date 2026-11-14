"""Example folders under specs/examples/, discovered by scanning (no sid is hard-coded, so
`office/` can be repointed and `office_houston/` picked up without a code change)."""
from __future__ import annotations

import json
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[2] / "specs" / "examples"


def flavors() -> list[str]:
    """Every example folder that carries a run_result.json, sorted for determinism."""
    return sorted(p.name for p in EXAMPLES.iterdir() if (p / "run_result.json").is_file())


def load(flavor: str, name: str):
    return json.loads((EXAMPLES / flavor / name).read_text())


def flavor_for_sid(sid: str, default: str = "house") -> str:
    for flavor in flavors():
        if load(flavor, "run_result.json")["property"]["sid"] == sid:
            return flavor
    return default
