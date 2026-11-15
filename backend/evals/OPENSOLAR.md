# OpenSolar spot check — manual procedure

Owner: @vigjay (issue #394). The lead's note says the CoStar judge trusts OpenSolar,
so this is a credibility check against a tool the industry already believes, on 2–3
properties — not a statistical result.

**This cannot be automated and must not be faked.** OpenSolar is an external tool
driven by a human in a browser. No agent should enter credentials into it. Every number
in `out/opensolar_spotcheck.json` is read off the screen by the operator named in the
file. A field that was not read stays `null` — never estimated, never interpolated.

Until the JSON exists, `publish.py` renders this check as `not_run` on the site, which
is the correct and honest state.

## Properties

Use the golden set, so our own figures come from a run anyone can reproduce:

| sid | What it is |
|---|---|
| `ZSPaQbkGcJJ` | Culver Connect, Los Angeles — commercial office |
| (house) | the residential golden property |
| (third, optional) | `office_houston`, for a second climate and tariff |

## Steps

1. Get our figures first, so you are not tempted to tune toward OpenSolar:

   ```bash
   python -m backend.evals.run_pv
   ```

   Record `system_kw_dc`, `annual_kwh` and `kwh_per_kw` per property from
   `out/pv_crosscheck.json`.

2. In OpenSolar, create a project at the **same address**. Let it pull its own imagery
   and roof geometry — do not hand-place panels to match ours. The point is an
   independent design.

3. Read and record, per property:
   - system size (kW DC) and **module count**
   - annual production (kWh, year 1)
   - **tilt and azimuth** of each array it created
   - which roof faces it used
   - the production model and weather source it names, if shown

4. Fill `out/opensolar_spotcheck.json`:

   ```json
   [{"sid": "ZSPaQbkGcJJ", "address": "...",
     "our_system_kw": 0.0, "our_annual_kwh": 0.0, "our_modules": 0,
     "our_tilt_deg": 0.0, "our_azimuth_deg": 0.0,
     "opensolar_system_kw": 0.0, "opensolar_annual_kwh": 0.0, "opensolar_modules": 0,
     "opensolar_tilt_deg": 0.0, "opensolar_azimuth_deg": 0.0,
     "pct_diff_kw": 0.0, "pct_diff_kwh": 0.0, "pct_diff_kwh_per_kw": 0.0,
     "operator": "", "date": "", "notes": ""}]
   ```

5. Re-run `python -m backend.evals.publish` to pick it up.

## Reading the result

**Record tilt, azimuth and module count or the comparison is uninterpretable.** A 20%
gap in annual kWh means two completely different things depending on where it comes from:

- **Different system size or module count** → a *layout* difference. Our usable-area
  rules (`ROOF-04`), setbacks (`ROOF-06`) or packing (`LAY-01`) disagree with theirs.
  This is the likelier cause and the more fixable one.
- **Same size, different kWh** → a *yield* difference, i.e. the production chain
  (`IRR`/`PV`) or the weather year. Compare `kwh_per_kw`, not total kWh, to see this.

So `pct_diff_kwh_per_kw` is the number that isolates the physics; `pct_diff_kw` isolates
the layout. Report both, and say which dominates.

A difference is **not** automatically our error. OpenSolar has its own weather year, its
own losses and its own module assumptions. Treat a gap under about 10% on `kwh_per_kw`
as agreement, and anything larger as a question to investigate rather than a verdict —
and write the investigation in `notes`.
