"""Run real-analysis (no agent) for the selected buildings and append one JSON line each to WORK/results_<arm>.jsonl.
  python -m backend.agent.ebewe_eval.run <start> <end> <none|vision> <concurrency> [selected_file]
arm none  = TRUE vintage defaults: observe_interior returns nothing (not even the hand-written examples).
arm vision = real vision (about 1 USD per property of Anthropic calls; panoramas go only to the Anthropic API).
Needs the API keys in the shell (set -a; . ./.env; set +a). Never prints a key."""
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from backend.agent.ebewe_eval.common import ROOT, WORK


def main(argv: list[str]) -> None:
    start, end, arm, conc = int(argv[0]), int(argv[1]), argv[2], int(argv[3])
    selected = argv[4] if len(argv) > 4 else "selected.json"
    from backend.agent import analysis_run, live, vision_client
    from backend.agent.vision_client import Usage
    from backend.analysis import api as analysis
    from backend.schema import RunRequest
    live._load_env()
    sel = json.loads((WORK / selected).read_text())[start:end]
    usage = Usage()
    if arm == "none":
        os.environ["AGENT_VISION"] = "0"
        analysis.observe_interior = lambda bundle: ([], [])
    else:
        orig = vision_client.enable_vision
        vision_client.enable_vision = lambda an, d, usage_=None: orig(an, d, usage=usage)
    lock, out = threading.Lock(), WORK / f"results_{arm}.jsonl"

    def val(x):
        return x["expected"] if isinstance(x, dict) and "expected" in x else x

    def one(s):
        t, rec = time.time(), {"sid": s["sid"], "arm": arm}
        try:
            rid = analysis_run.start_run(RunRequest(sid=s["sid"], budget_usd=1.0, role="landlord", mode="analysis"))
            run = live._RUNS[rid]
            while time.time() - t < 900:
                time.sleep(3)
                try:
                    if run.store.load(rid).status in ("done", "error"):
                        break
                except Exception:
                    pass
            d = ROOT / "data" / "runs" / rid
            errs = [str(getattr(e, "message", ""))[:160] for e in run.events if getattr(e, "type", "") == "error"]
            if errs:
                rec["run_errors"] = errs[:2]
            res = json.loads((d / "result.json").read_text())
            model = json.loads((d / "model.json").read_text())
            an = res["baseline"]["annual"]
            rec.update(status=res["status"], run=rid, data_source=res.get("data_source"),
                       area_m2=val(sum((z.get("floor_area_m2") or z.get("area_m2") or 0) for z in model["zones"])),
                       elec=val(an["electricity_kwh"]), gas=val(an["gas_kwh"]),
                       elec_lo=an["electricity_kwh"].get("low") if isinstance(an["electricity_kwh"], dict) else None,
                       elec_hi=an["electricity_kwh"].get("high") if isinstance(an["electricity_kwh"], dict) else None,
                       gas_lo=an["gas_kwh"].get("low") if isinstance(an["gas_kwh"], dict) else None,
                       gas_hi=an["gas_kwh"].get("high") if isinstance(an["gas_kwh"], dict) else None,
                       vision=sum(1 for x in model["assumptions"] if x["source"] == "vision"))
        except Exception as e:
            rec.update(status="error", error=f"{type(e).__name__}: {str(e)[:150]}")
        rec["secs"] = round(time.time() - t)
        with lock, out.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
        return rec

    t0 = time.time()
    with ThreadPoolExecutor(conc) as ex:
        recs = list(ex.map(one, sel))
    ok = [r for r in recs if r["status"] == "done"]
    print(f"{arm}: {len(ok)}/{len(recs)} done in {time.time() - t0:.0f}s")
    if arm == "vision":
        print(f"vision usage: calls {usage.calls}, in {usage.input_tokens}, out {usage.output_tokens}, est ${usage.cost_usd:.2f}")


if __name__ == "__main__":
    main(sys.argv[1:])
