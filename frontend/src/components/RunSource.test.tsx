import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import RunSource from "./RunSource";
import type { RunResult } from "../lib/types";
import house from "../../../specs/examples/house/run_result.json";

describe("run provenance", () => {
  it("does not describe a reopened result as a new calculation or new audit", () => {
    const html = renderToStaticMarkup(<RunSource run={{ ...house, data_source: "live", served_by: "analysis" } as RunResult} restored />);
    expect(html).toContain("Reopened audit");
    expect(html).not.toContain("New calculation");
    expect(html).not.toContain("New audit");
  });
  it("distinguishes computed analysis from both agent runs and recorded playback", () => {
    const html = render("live", "analysis");
    expect(html).toContain("New calculation");
    expect(html).toContain("your budget and your role");
    expect(html).not.toContain("Saved property audit");
    expect(html).not.toContain("New audit");
  });
  function render(
    data_source: RunResult["data_source"],
    served_by: RunResult["served_by"],
  ) {
    return renderToStaticMarkup(
      <RunSource run={{ ...house, data_source, served_by } as RunResult} />,
    );
  }
  it("does not mistake a recording of live data for a fresh live run", () => {
    const html = render("live", "replay");
    expect(html).toContain("Based on this property’s records");
    expect(html).toContain("Saved property audit");
    expect(html).toContain("does not run a fresh analysis");
    expect(html).not.toContain("New audit");
  });
  it("does not mistake a live agent using example inputs for live property data", () => {
    const html = render("example", "live");
    expect(html).toContain("Example inputs — not a real property audit");
    expect(html).toContain("New audit");
    expect(html).not.toContain("Based on this property’s records");
  });
  it("treats missing and null source fields as unknown", () => {
    for (const missing of [undefined, null]) {
      const html = render(missing, missing);
      expect(html).toContain("Building records not verified");
      expect(html).toContain("Audit type not reported");
      expect(html).not.toContain("Based on this property’s records");
    }
  });
});
