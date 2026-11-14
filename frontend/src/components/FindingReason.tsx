/**
 * Why an upgrade was left out, in words a building owner can act on.
 *
 * The backend's one-line `detail` is accurate and terse - "SIR 0.36 is below the break-even of
 * 1" - which is right for a record and wrong for a reader who has never met the term. The short
 * line stays as the summary; opening the item explains the test itself, says what would change
 * the answer, and never restates a number the backend did not give.
 */

export const REASON_LABELS: Record<string, string> = {
  not_cost_effective: "Costs more than it saves",
  over_budget: "Does not fit this budget",
  not_applicable: "Does not apply to this building",
  no_savings: "Saves no energy here",
  no_cost_data: "No priced quote yet",
  already_done: "Already installed",
  role: "Not yours to change",
  feasibility: "Needs a check first",
  dependency: "Needs another upgrade first",
};

/** What the reason means, and what would change it. Plain language, no jargon introduced. */
export const REASON_DETAIL: Record<string, { what: string; change: string }> = {
  not_cost_effective: {
    what:
      "Over the equipment's working life this upgrade is expected to save less money than it " +
      "costs to install. The test is the savings-to-investment ratio: total savings over the " +
      "life, in today's money, divided by what you pay up front. Below 1 means it loses money; " +
      "the plan only recommends 1 or above.",
    change:
      "A firm quote below the published cost, a rebate that has not been counted, or higher " +
      "energy prices than today's would each raise the ratio. It is also worth doing anyway if " +
      "the equipment is failing and must be replaced regardless.",
  },
  over_budget: {
    what:
      "This upgrade would save money over its life, but the cash needed up front is more than " +
      "the budget left after the upgrades above it. It is ranked, not rejected.",
    change:
      "Raise the budget and it may enter the plan. It is also listed as financeable, which " +
      "means it could be paid for over time rather than up front - subject to its own " +
      "eligibility checks.",
  },
  no_savings: {
    what:
      "Modelled against this building as it stands, the upgrade does not reduce energy use. " +
      "Usually that is because the thing it improves is already doing its job - a control that " +
      "is already set back, or a system already sized correctly.",
    change:
      "Nothing, unless the building changes. If you believe the model has the current state " +
      "wrong, correct the relevant assumption and the answer will follow.",
  },
  no_cost_data: {
    what:
      "The energy saving was modelled, but no cost source this project trusts covers this " +
      "upgrade for a building of this type and size. A price has not been invented to fill the gap.",
    change: "A contractor's quote. With a real price it can be ranked with everything else.",
  },
  already_done: {
    what:
      "The building already has this, so there is nothing to install. The evidence is in the " +
      "line above - usually something seen in the scan or stated in the property record.",
    change: "Nothing. If the evidence is wrong, correct the assumption behind it.",
  },
  not_applicable: {
    what: "This upgrade does not fit the building that was surveyed.",
    change: "Nothing, unless the survey described the wrong building or space.",
  },
  role: {
    what:
      "This changes part of the building that your role does not control - a tenant cannot " +
      "replace a landlord's roof or rooftop plant.",
    change: "The owner's consent, or a different role on the audit.",
  },
  feasibility: {
    what:
      "Something must be confirmed on site before this can be costed or recommended. The line " +
      "above says what.",
    change: "The check it names - usually a surveyor, an engineer, or the building's own records.",
  },
  dependency: {
    what: "This only pays off once another upgrade is in place, so it is held until that one is.",
    change: "Doing the upgrade it depends on first.",
  },
};

/** A readable name for a measure id the result did not carry a title for. */
export const MEASURE_NAMES: Record<string, string> = {
  ENV_ATTIC: "Attic or roof insulation",
  ENV_WALL: "Wall insulation",
  ENV_AIRSEAL: "Air sealing",
  WIN_REPLACE: "Window replacement",
  WIN_FILM: "Solar control window film",
  WIN_SHADE: "Exterior or interior shading",
  ROOF_COOL: "Cool roof coating or membrane",
  HVAC_HP: "Heat pump",
  HVAC_RTU: "High-efficiency rooftop units",
  HVAC_ECON: "Economizer and rooftop controls",
  HVAC_DUCT: "Duct sealing",
  DHW_HPWH: "Heat pump water heater",
  LGT_LED: "LED retrofit",
  LGT_CTRL: "Occupancy and daylight controls",
  PLUG_MGMT: "Plug load management",
  CTRL_TSTAT: "Smart thermostat and setback",
  PV_ROOF: "Rooftop solar",
  LAYOUT: "Desk placement for daylight",
};

/**
 * The name to show. The result's own title first; then a readable name for the id; and only if
 * both are missing, the id tidied up - so a reader never meets `WIN_FILM`.
 */
export function measureName(id: string, title?: string): string {
  if (title) return title;
  if (MEASURE_NAMES[id]) return MEASURE_NAMES[id];
  const words = id.toLowerCase().replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
