"""Audit an immutable first-stage source snapshot without changing that snapshot.

python -m backend.evals.high_level.audit_initial --source-root /path/to/snapshot \
    --output /tmp/initial-audit.json [--runs /path/to/runs.json]

The synthetic counterexample verifies arithmetic only. Without per-building runs,
the actual 494-building headline metrics are explicitly NOT reproduced.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

from .metrics import score


def audit(source_root: Path, runs_path: Path | None = None) -> dict:
    source = source_root / "backend/evals/score_eval.py"
    spec = importlib.util.spec_from_file_location("delivered_score_eval", source)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load the delivered scorer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ratios = [0.2, 0.5, 1.0, 2.0]
    rows = [{"truth_elec_kwh": 100, "arms": {"test": {"elec": {
        "low": r * 100, "expected": r * 100, "high": r * 100,
    }}}} for r in ratios]
    independent = score(rows, "test")
    delivered = module.describe([100 * (r - 1) for r in ratios])
    result = {
        "audit_scope": "initial source/metric audit; no model tuning",
        "source_revision": subprocess.check_output(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True).strip(),
        "scorer_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "arithmetic_probe": {
            "evidence_type": "synthetic arithmetic counterexample, not building evidence",
            "prediction_truth_ratios": ratios,
            "correct_factor_two_or_more_pct": independent["factor_two_or_more_pct"],
            "delivered_factor_2_plus_pct": delivered.get("factor_2_plus"),
            "finding": "Delivered factor_2_plus is not a symmetric factor-of-two metric"
                if delivered.get("factor_2_plus") != independent["factor_two_or_more_pct"]
                else "No discrepancy in this counterexample",
        },
        "building_metrics": {"status": "blocked", "reason": "Per-building output not provided; aggregate headlines not independently reproduced"},
    }
    if runs_path:
        content = runs_path.read_bytes()
        data = json.loads(content)
        rows = data["runs"]
        arms = data.get("arms", ["bdg2temp", "openmeteo"])
        paired = [r for r in rows if all("elec" in r.get("arms", {}).get(a, {}) for a in arms)]
        result["building_metrics"] = {
            "status": "scored_owner_outputs_not_model_reproduction",
            "runs_sha256": hashlib.sha256(content).hexdigest(),
            "n_output_rows": len(rows), "n_common_success": len(paired),
            "per_arm_all_available": {a: score(rows, a) for a in arms},
            "paired": {a: score(paired, a) for a in arms},
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--runs", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.source_root.resolve(), args.runs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"Wrote {args.output}; building metrics: {result['building_metrics']['status']}")


if __name__ == "__main__":
    main()
