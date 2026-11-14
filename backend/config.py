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
