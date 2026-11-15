import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { demoProperties, demoRun } from "../lib/fixtures";
import PlanView, { MeasureCard } from "./Plan";
import { inputName, warningText } from "../lib/homeowner-language";
import Assumptions from "./Assumptions";
import Geometry from "./Geometry";
import Find from "./Find";
import Documents, { documentScope } from "./Documents";
import Warnings, { AuditNarrative } from "./Warnings";
import Calibration from "./Calibration";
import sharedHouse from "../../../specs/examples/house/run_result.json";
import sharedOffice from "../../../specs/examples/office/run_result.json";
import HouseViewer from "./HouseViewer";
import AuditTasks from "./AuditTasks";
import { UNCAPPED_BUDGET_USD } from "../lib/budget-phase";
const house = demoRun(sharedHouse.property.sid, sharedHouse.request.budget_usd);
function uncapped(run: ReturnType<typeof demoRun>) {
  const clone = structuredClone(run);
  clone.request.budget_usd = UNCAPPED_BUDGET_USD;
  clone.plan!.budget_usd = UNCAPPED_BUDGET_USD;
  return clone;
}
const office = demoRun(
  sharedOffice.property.sid,
  sharedOffice.request.budget_usd,
);
describe("shared contract screen compatibility", () => {
  it("uses office language in the office concept model", () => {
    const html = renderToStaticMarkup(<HouseViewer office />);
    expect(html).toContain("Work area");
    expect(html).toContain("Upper floor");
    expect(html).not.toContain("Bedroom");
    expect(html).not.toContain("Living room");
  });
  it("does not show kickoff task statuses as current after the audit finishes", () => {
    const event = {
      type: "todo" as const,
      message: "Audit plan",
      payload: { todos: [{ content: "Fetch data", status: "in_progress" }] },
    };
    expect(
      renderToStaticMarkup(<AuditTasks event={event} finished={false} />),
    ).toContain("in progress");
    const completed = renderToStaticMarkup(
      <AuditTasks event={event} finished />,
    );
    expect(completed).toContain("initial audit checklist");
    expect(completed).not.toContain("in progress");
    expect(completed).not.toContain("pending");
    const earlier = renderToStaticMarkup(
      <AuditTasks event={event} finished={false} archived />,
    );
    expect(earlier).toContain("earlier");
    expect(earlier).not.toContain("in progress");
  });
  it("explains why desk placement is unavailable when the scan has no room outlines", () => {
    const run = structuredClone(office);
    const layout = run.measures.find(
      (measure) => measure.measure_id === "LAYOUT",
    )!;
    layout.applicable = false;
    layout.layout = null;
    layout.not_applicable_reason = "The scan has no room outlines.";
    const html = renderToStaticMarkup(<Geometry run={run} layout demo />);
    expect(html).toContain("Desk placement cannot be assessed");
    expect(html).toContain("The scan has no room outlines.");
    expect(html).not.toContain("The analysis will provide");
  });
  it("separates additional-budget options from other exclusions without changing analysis data", () => {
    const run = structuredClone(house);
    run.measures.forEach((measure) => {
      measure.applicable = true;
    });
    const option = run.measures[0];
    run.plan!.financeable = [option];
    run.plan!.skipped = [
      {
        measure_id: option.measure_id,
        reason: "over_budget",
        detail: "More cash needed",
      },
      {
        measure_id: run.measures[1].measure_id,
        reason: "not_cost_effective",
        detail: "Fails cost test",
      },
    ];
    const html = renderToStaticMarkup(
      <PlanView run={run} onFocus={() => {}} onDocuments={() => {}} />,
    );
    expect(html).toContain('class="plan-tab financeable"');
    expect(html).toContain('class="plan-tab skipped"');
    expect(html).toContain("Needs more budget<span>1</span>");
    expect(html).toContain("Other findings<span>1</span>");
    expect(run.plan!.skipped).toHaveLength(2);
    expect(html).toContain("aria-controls=");
  });
  it("keeps selected marginal sizing in a C-PACE document scope", () => {
    const run = structuredClone(office);
    const selected = run.plan!.selected[0].measure;
    const standalone = structuredClone(selected);
    selected.title = "Selected plan sizing";
    standalone.title = "Larger standalone sizing";
    run.plan!.financeable = [standalone];
    expect(
      documentScope(run, "cpace_package").find(
        (m) => m.measure_id === selected.measure_id,
      )?.title,
    ).toBe("Selected plan sizing");
  });
  it("shows bill-fit results and warnings without claiming a failed fit is calibrated", () => {
    const run = structuredClone(house);
    run.baseline!.calibration = {
      calibrated: false,
      fits: [
        {
          fuel: "gas",
          nmbe_before: 0.3,
          cv_rmse_before: 0.4,
          nmbe_after: 0.07,
          cv_rmse_after: 0.18,
          passed: false,
        },
      ],
      moved: ["wall.u_value"],
      warnings: ["Possible unmodelled gas load"],
    };
    const html = renderToStaticMarkup(<Calibration run={run} />);
    expect(html).toContain("Bill fit needs review");
    expect(html).toContain("Outside tolerance");
    expect(html).toContain("Possible unmodelled gas load");
    expect(html).toContain("30% → 7%");
    expect(
      renderToStaticMarkup(
        <Calibration
          run={{ ...house, baseline: null, building_model: null }}
        />,
      ),
    ).toContain("Not checked against your utility bills yet");
  });
  it("does not claim an unchanged replay plan fits a lower requested budget", () => {
    const run = structuredClone(house);
    run.plan!.budget_usd = 0;
    const html = renderToStaticMarkup(
      <PlanView run={run} onFocus={() => {}} onDocuments={() => {}} />,
    );
    expect(html).toContain("exceeds your cash budget at expected costs");
    expect(html).not.toContain("The plan fits at expected costs");
  });
  it("keeps long provenance details expandable and de-duplicates repeated fallback warnings", () => {
    const warning = `vexcel/property/extract:extent: ${"Both outlines and the decision remain visible. ".repeat(12)}END OF DETAIL`;
    const html = renderToStaticMarkup(
      <Warnings warnings={[warning, warning]} />,
    );
    expect(html).toContain("<details");
    expect(html).toContain("Read full note");
    expect(html.split("END OF DETAIL")).toHaveLength(2);
  });
  it("groups related warnings without losing distinct source notes", () => {
    const electricity = "EIA electricity uses a state average, not your contract.";
    const gas = "EIA gas uses last year's annual average.";
    const html = renderToStaticMarkup(
      <Warnings warnings={[electricity, gas, electricity, "TMY weather is not this year's weather."]} />,
    );
    expect(html.split("Check the energy prices used")).toHaveLength(2);
    expect(html).toContain("Read 2 notes");
    for (const note of [electricity, gas])
      expect(html.split(warningText(note).replaceAll("'", "&#x27;"))).toHaveLength(2);
    expect(html).toContain("Review the weather data used");
  });
  it("marks an earlier narrative as outdated after a backend re-run warning", () => {
    const html = renderToStaticMarkup(
      <AuditNarrative
        text="Earlier savings: $1000"
        warnings={["re-run: summary not regenerated"]}
      />,
    );
    expect(html).toContain("outdated numbers");
    expect(html).toContain("<details");
    expect(html).toContain("Earlier savings: $1000");
  });
  it("offers no edit control for a locked assumption", () => {
    const run = structuredClone(house);
    const assumption = run.building_model!.assumptions[0];
    assumption.label = "Locked input";
    assumption.user_editable = false;
    const html = renderToStaticMarkup(
      <Assumptions run={run} demo={false} busy={false} onSave={() => {}} />,
    );
    expect(html).toContain("Locked input");
    expect(html).not.toContain('aria-label="Edit Locked input"');
  });
  it("renders the real shared house and office plans, keeping optional property value separate", () => {
    const home = renderToStaticMarkup(
      <PlanView run={house} onFocus={() => {}} onDocuments={() => {}} />,
    );
    const work = renderToStaticMarkup(
      <PlanView run={office} onFocus={() => {}} onDocuments={() => {}} />,
    );
    for (const item of house.plan!.selected)
      expect(home).toContain(item.measure.title);
    expect(home).not.toContain("Estimated value uplift");
    expect(work).toContain("Estimated value uplift");
    expect(work).toContain("Shown separately from energy savings.");
    const tight = structuredClone(house);
    tight.request.budget_usd = tight.plan!.total_upfront_usd.expected;
    tight.plan!.budget_usd = tight.request.budget_usd;
    expect(
      renderToStaticMarkup(
        <PlanView run={tight} onFocus={() => {}} onDocuments={() => {}} />,
      ),
    ).toContain("upper estimate may exceed your cash budget");
  });
  it("handles measured ranges, categorical assumptions, and yes/no assumptions from both examples", () => {
    for (const run of [house, office]) {
      const html = renderToStaticMarkup(
        <Assumptions run={run} demo busy={false} onSave={() => {}} />,
      );
      for (const assumption of run.building_model!.assumptions)
        expect(html).toContain(inputName(assumption.key, assumption.label).replaceAll("&", "&amp;"));
      expect(html).toContain("Where this detail came from");
    }
  });
  it("draws shared roof geometry and reports unavailable layouts using the analysis reason", () => {
    const roof = renderToStaticMarkup(<Geometry run={house} demo />);
    expect(roof).toContain("<polygon");
    expect(roof).toContain("Proposed modules");
    for (const run of [house, office]) {
      const measure = run.measures.find((item) => item.measure_id === "LAYOUT");
      const layout = renderToStaticMarkup(<Geometry run={run} layout demo />);
      if (measure?.layout) {
        expect((layout.match(/role="button"/g) || []).length).toBe(
          measure.layout.candidates.length,
        );
        expect(layout).toContain("exploratory");
        expect(layout).not.toContain("Recommended");
      } else if (measure?.not_applicable_reason) {
        expect(layout).toContain(measure.not_applicable_reason);
      } else expect(layout).toContain("No workspace candidates yet");
    }
  });
  it("does not let unvalidated comfort scores rank, label, or style workspace candidates", () => {
    const run = structuredClone(office);
    const measure = run.measures.find((item) => item.measure_id === "LAYOUT")!;
    measure.layout = {
      desks_requested: 1,
      candidates: [0, 1].map((i) => ({
        room_id: `room_${i + 1}`, x: i * 3, y: i * 2,
        daylight: 0.45, daylight_factor: 2.1, view_azimuth_deg: 90, direct_sun_hours: 120,
        score: i, recommended: i === 1, comfort_ppd: 15, glare_risk: 0.3, max_dt_pr_k: 4,
      })),
    };
    const before = renderToStaticMarkup(<Geometry run={run} layout demo />);
    for (const point of measure.layout.candidates) {
      point.score = 1 - point.score;
      point.recommended = !point.recommended;
      point.comfort_ppd = 99;
      point.glare_risk = 1;
      point.max_dt_pr_k = 99;
    }
    expect(renderToStaticMarkup(<Geometry run={run} layout demo />)).toBe(before);
    expect((before.match(/role="button"/g) || []).length).toBe(2);
    expect(before).toContain("45% of occupied hours");
    expect(before).toContain("not measured");
    expect(before).toContain("120 occupied hours per year");
    expect(before).not.toMatch(/Overall score|Glare risk|Recommended|PPD/);
  });
  it("offers shared analysis properties without invented sandbox properties", () => {
    const html = renderToStaticMarkup(
      <Find
        properties={demoProperties}
        query=""
        setQuery={() => {}}
        segment=""
        setSegment={() => {}}
        loading={false}
        demo
        onSelect={() => {}}
      />,
    );
    expect(html).toContain(sharedHouse.property.name);
    expect(html).toContain(sharedOffice.property.name);
    expect(html).not.toContain("Shared contract example");
    expect(html).not.toContain("EXAMPLE ENERGY PLAN");
    expect(html).not.toContain("$619");
    expect(html).not.toContain("UI sandbox");
    expect(html).toContain(
      'aria-label="Explore Culver Connect in Los Angeles"',
    );
    // the card holds the preview's own buttons, so it must not itself be a button
    expect(html).not.toMatch(/<button[^>]*class="property-card"/);
    expect(html).toMatch(/<article class="property-card"/);
    expect(html).toMatch(/<button type="button" class="property-open"/);
  });
  it("requires approval before drafting and restricts residential/commercial document choices", () => {
    const home = renderToStaticMarkup(<Documents run={house} demo />);
    const work = renderToStaticMarkup(<Documents run={office} demo />);
    expect(home).toContain('disabled=""');
    expect(home).toContain("approve creating this draft");
    expect(home).not.toContain("Commercial C-PACE package");
    expect(work).toContain("Commercial C-PACE package");
  });
  it("renders every selected measure even when optional finance details are absent", () => {
    const measure = structuredClone(house.measures[0]);
    measure.finance = null;
    expect(
      renderToStaticMarkup(
        <MeasureCard measure={measure} onFocus={() => {}} />,
      ),
    ).toContain("Cost unavailable");
  });
  it("shows what applies to the building with no budget language before a budget is given", () => {
    const html = renderToStaticMarkup(
      <PlanView run={uncapped(house)} onFocus={() => {}} onDocuments={() => {}} />,
    );
    expect(html).not.toContain("100,000,000");
    expect(html).not.toMatch(/budget/i);
    expect(html).not.toContain("Needs more budget");
    expect(html).toContain("Other findings");
    expect(html).toContain("apply to your building");
  });
  it("restores the three budget tabs once a budget exists", () => {
    const html = renderToStaticMarkup(
      <PlanView run={house} onFocus={() => {}} onDocuments={() => {}} />,
    );
    expect(html).toContain("Needs more budget");
    expect(html).toContain("cash budget");
  });
  it("blames a too-small budget rather than the building when nothing is selected", () => {
    const run = structuredClone(house);
    run.request.budget_usd = 0;
    run.plan!.budget_usd = 0;
    run.plan!.selected = [];
    const html = renderToStaticMarkup(<PlanView run={run} onFocus={() => {}} onDocuments={() => {}} />);
    expect(html).toMatch(/budget/i);
    expect(html).not.toContain("apply to your building");
  });
  it("gives an empty state with no budget language when nothing applies to the building", () => {
    const run = uncapped(house);
    run.plan!.selected = [];
    run.plan!.financeable = [];
    const html = renderToStaticMarkup(<PlanView run={run} onFocus={() => {}} onDocuments={() => {}} />);
    expect(html).not.toMatch(/budget/i);
  });
  it("says so if the uncapped run could have been truncated by the sentinel", () => {
    const run = uncapped(house);
    run.plan!.total_upfront_usd.high = UNCAPPED_BUDGET_USD;
    const html = renderToStaticMarkup(<PlanView run={run} onFocus={() => {}} onDocuments={() => {}} />);
    expect(html).toContain("may not be complete");
  });
  it("sends a person to the budget before offering contractor documents", () => {
    const html = renderToStaticMarkup(
      <PlanView run={uncapped(house)} onFocus={() => {}} onDocuments={() => {}} />,
    );
    expect(html).toContain("disabled");
    expect(html).not.toContain("Prepare documents");
  });
  it("keeps per-measure cost labels but no budget framing on an expanded card before a budget is given", () => {
    const measure = house.plan!.selected[0].measure;
    const html = renderToStaticMarkup(
      <MeasureCard measure={measure} onFocus={() => {}} defaultOpen />,
    );
    expect(html).toContain("Installed cost");
    expect(html).toContain("Cash needed upfront");
    expect(html).not.toMatch(/budget/i);
  });
  it("filters an over-budget skipped item out of Other findings before a budget is given", () => {
    const skipped = [
      {
        measure_id: "ENV_WALL",
        reason: "over_budget",
        detail: "Net upfront cost is above the whole budget.",
      },
    ];
    const pre = uncapped(house);
    pre.plan!.skipped = skipped;
    const preHtml = renderToStaticMarkup(
      <PlanView
        run={pre}
        onFocus={() => {}}
        onDocuments={() => {}}
        initialTab="skipped"
      />,
    );
    expect(preHtml).not.toContain("Does not fit this budget");
    const budgetedRun = structuredClone(house);
    budgetedRun.plan!.skipped = skipped;
    const budgetedHtml = renderToStaticMarkup(
      <PlanView
        run={budgetedRun}
        onFocus={() => {}}
        onDocuments={() => {}}
        initialTab="skipped"
      />,
    );
    expect(budgetedHtml).toContain("Does not fit this budget");
  });
});
