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
const house = demoRun(sharedHouse.property.sid, sharedHouse.request.budget_usd);
const office = demoRun(
  sharedOffice.property.sid,
  sharedOffice.request.budget_usd,
);
describe("shared contract screen compatibility", () => {
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
    ).toContain("Uncalibrated estimate");
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
    expect(home).toContain("upper estimate may exceed your cash budget");
  });
  it("handles measured ranges, categorical assumptions, and yes/no assumptions from both examples", () => {
    for (const run of [house, office]) {
      const html = renderToStaticMarkup(
        <Assumptions run={run} demo busy={false} onSave={() => {}} />,
      );
      for (const assumption of run.building_model!.assumptions)
        expect(html).toContain(assumption.label.replaceAll("&", "&amp;"));
      expect(html).toContain("Confidence");
    }
  });
  it("draws the shared roof geometry and office candidates, and leaves missing house layout empty", () => {
    const roof = renderToStaticMarkup(<Geometry run={house} demo />);
    expect(roof).toContain("<polygon");
    expect(roof).toContain("Proposed modules");
    const layout = renderToStaticMarkup(<Geometry run={office} layout demo />);
    expect((layout.match(/role="button"/g) || []).length).toBe(
      office.measures
        .find((m) => m.layout)!
        .layout!.candidates.filter((point) => point.recommended).length,
    );
    expect(layout).toContain("Recommended");
    expect(
      renderToStaticMarkup(<Geometry run={house} layout demo />),
    ).toContain("No workspace candidates yet");
  });
  it("distinguishes shared examples from sandbox scenarios on the Find screen", () => {
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
    expect(html).toContain("Shared contract example");
    expect(html).toContain("UI sandbox");
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
