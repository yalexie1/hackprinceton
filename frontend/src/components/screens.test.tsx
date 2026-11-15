import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { demoProperties, demoRun } from "../lib/fixtures";
import PlanView, { MeasureCard } from "./Plan";
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
const house = demoRun(sharedHouse.property.sid, sharedHouse.request.budget_usd);
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
        expect(html).toContain(assumption.label.replaceAll("&", "&amp;"));
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
          measure.layout.candidates.filter((point) => point.recommended).length,
        );
        expect(layout).toContain("Recommended");
      } else if (measure?.not_applicable_reason) {
        expect(layout).toContain(measure.not_applicable_reason);
      } else expect(layout).toContain("No workspace candidates yet");
    }
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
    expect(html).toContain('class="property-image" aria-hidden="true"');
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
});
