import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { demoProperties, demoRun } from "../lib/fixtures";
import PlanView, { MeasureCard } from "./Plan";
import Assumptions from "./Assumptions";
import Geometry from "./Geometry";
import Find from "./Find";
import Documents from "./Documents";
const house = demoRun("zvKHR9DHNjJ", 14000);
const office = demoRun("HjEyXryhRLk", 3500);
describe("shared contract screen compatibility", () => {
  it("renders the real shared house and office plans, keeping optional property value separate", () => {
    const home = renderToStaticMarkup(
      <PlanView run={house} onFocus={() => {}} onDocuments={() => {}} />,
    );
    const work = renderToStaticMarkup(
      <PlanView run={office} onFocus={() => {}} onDocuments={() => {}} />,
    );
    expect(home).toContain("Rooftop solar, 2.8 kW");
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
      office.measures.find((m) => m.layout)!.layout!.candidates.length,
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
    expect(html).toContain("5836 La Mirada Ave");
    expect(html).toContain("Suite A - 2,000SF");
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
