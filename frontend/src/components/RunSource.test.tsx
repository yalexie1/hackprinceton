import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import RunSource from "./RunSource";
import type { RunResult } from "../lib/types";
import house from "../../../specs/examples/house/run_result.json";

describe("run provenance", () => {
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
    expect(html).toContain("Live property data");
    expect(html).toContain("Saved replay");
    expect(html).toContain("does not run a fresh analysis");
    expect(html).not.toContain("Live run");
  });
  it("does not mistake a live agent using example inputs for live property data", () => {
    const html = render("example", "live");
    expect(html).toContain("Example property data");
    expect(html).toContain("Live run");
    expect(html).not.toContain("Live property data");
  });
  it("treats missing and null source fields as unknown", () => {
    for (const missing of [undefined, null]) {
      const html = render(missing, missing);
      expect(html).toContain("Property data source unknown");
      expect(html).toContain("Delivery mode unknown");
      expect(html).not.toContain("Live property data");
    }
  });
});
