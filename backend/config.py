"""Non-secret settings (SPEC 12). Each number cites the entry it comes from. No secret and
no API key belongs here: those live in the git-ignored .env."""
from pathlib import Path

# ---- model ids: SPEC 8 build notes ----
ORCHESTRATOR_MODEL = "claude-opus-5-5"     # SPEC 8: the auditor
SUBAGENT_MODEL = "claude-sonnet-5-5"       # SPEC 8: scout, surveyor, physicist, financier, counsel
VISION_MODEL = "claude-haiku-5-5"          # SPEC 8: bulk image reading

# ---- the ask rule: SPEC 5.3 ----
ASK_WIDTH = 0.40    # SPEC 5.3 step 3: ask when (high - low) / expected of the plan's total savings exceeds this
ASK_MAX = 3         # SPEC 5.3 step 4: stop after this many questions

# ---- economic defaults: specs/physics/04-economics-emissions-mv.md ECO-05 ----
DISCOUNT_RATE_REAL = 0.030        # ECO-05: real discount rate d, DOE/FEMP 2025, AS135-2025 page 1
DISCOUNT_RATE_NOMINAL = 0.045     # ECO-05: nominal rate D, used only for nominal debt (ECO-12)
INFLATION = 0.0146                # ECO-05: 1.045 / 1.03 - 1
ANALYSIS_PERIOD_CAP_YEARS = 40    # ECO-05: N = min(useful life, 40), 10 CFR 436.14(d)(1)
SENSITIVITY_DISCOUNT_RATE = 0.07  # ECO-05: OMB A-94 / M-25-23; reported beside the default, never ranks
OM_REAL_ESCALATION = 0.0          # ECO-05: HB135 3.2.2.2, O&M and replacement costs
# Real energy escalation (e_elec, e_gas) is a table by city, sector and period, not one
# number: ECO-06. The finance package (A25) reads that table; it is not duplicated here.

# ---- C-PACE: PLACEHOLDERS ----
# No source has been opened for a default rate or term (specs/physics/04 ECO-12 gives the
# payment formula only). None means "not set"; the C-PACE package (A28) must not run on a
# guess, and must take both from a cited source or from the user.
CPACE_RATE = None          # PLACEHOLDER: annual rate, no source yet
CPACE_TERM_YEARS = None    # PLACEHOLDER: term in years, no source yet; never above the useful life

# ---- cache directory: the Data lane's cache (workplan 2.3) ----
CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"

# ---- real energy price escalation: ECO-06 expected values ----
# Equivalent constant real rate (percent per year) for the AS135-2025 reference projection,
# base year 2026, d = 0.03, keyed (city, sector, fuel) -> {analysis period N: percent}.
# California is census division Pacific (Los Angeles), Texas West South Central (Houston).
# These five columns are all that was recorded; the full index tables were not copied into the
# repo, so other N are interpolated (see finance/economics) and flagged.
ESCALATION_REAL_PCT = {
    ("los_angeles", "residential", "electricity"): {10: -1.08, 15: -0.62, 20: -0.36, 25: -0.18, 30: -0.05},
    ("los_angeles", "residential", "gas"): {10: -1.74, 15: -1.08, 20: -0.70, 25: -0.47, 30: -0.33},
    ("los_angeles", "commercial", "electricity"): {10: -1.59, 15: -1.16, 20: -0.92, 25: -0.75, 30: -0.62},
    ("los_angeles", "commercial", "gas"): {10: -1.24, 15: -0.76, 20: -0.48, 25: -0.32, 30: -0.23},
    ("houston", "residential", "electricity"): {10: 0.31, 15: 0.10, 20: 0.08, 25: 0.13, 30: 0.14},
    ("houston", "residential", "gas"): {10: 0.34, 15: 0.50, 20: 0.55, 25: 0.56, 30: 0.55},
    ("houston", "commercial", "electricity"): {10: 0.55, 15: 0.22, 20: 0.17, 25: 0.21, 30: 0.22},
    ("houston", "commercial", "gas"): {10: 1.33, 15: 1.26, 20: 1.18, 25: 1.09, 30: 0.99},
}
ESCALATION_BAND = 0.010   # ECO-06 rule 2 [J]: low = expected - 1.0 percentage point, high = expected + 1.0
