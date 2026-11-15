import { afterEach, describe, expect, it, vi } from "vitest";
import { auditIdFromUrl, auditUrl, restoreAudit } from "./audit-link";
import type { RunResult } from "./types";
import house from "../../../specs/examples/house/run_result.json";

afterEach(() => vi.unstubAllGlobals());

function result() {
  const run = structuredClone(house) as RunResult;
  run.run_id = "run_saved_house";
  run.data_source = "live";
  run.served_by = "analysis";
  for (const measure of [...run.measures, ...run.plan!.selected.map((m) => m.measure), ...run.plan!.financeable])
    if (measure.finance) measure.finance.cost_source = "Published cost reference";
  return run;
}

describe("existing audit links", () => {
  it("preserves unrelated query parameters and anchors when adding or clearing a run", () => {
    const href = "http://localhost:5173/?filter=office#your-properties";
    expect(auditUrl(href, "run_saved_house")).toBe("/?filter=office&audit=run_saved_house#your-properties");
    expect(auditUrl("http://localhost:5173/?filter=office&audit=run_saved_house#your-properties", null))
      .toBe("/?filter=office#your-properties");
    expect(auditIdFromUrl("http://localhost:5173/?audit=run_saved_house")).toBe("run_saved_house");
    expect(auditIdFromUrl("http://localhost:5173/?audit=../secrets")).toBeNull();
    expect(auditIdFromUrl(href)).toBeNull();
  });

  it("reopens only the exact existing real result with a cancellable GET", async () => {
    const run = result();
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(run)));
    vi.stubGlobal("fetch", fetch);
    const signal = new AbortController().signal;
    expect(await restoreAudit(run.run_id, signal)).toEqual(run);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toContain(`/api/runs/${run.run_id}`);
    expect(fetch.mock.calls[0][1].signal).toBe(signal);
    expect(fetch.mock.calls[0][1].method).toBeUndefined();
  });

  it.each(["example", "wrong-id", "wrong-schema", "wrong-property"])("refuses %s results without starting a replacement", async (problem) => {
    const run = result();
    if (problem === "example") run.data_source = "example";
    if (problem === "wrong-id") run.run_id = "run_other";
    if (problem === "wrong-schema") run.schema_version = "future";
    if (problem === "wrong-property") run.request.sid = "other";
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(run)));
    vi.stubGlobal("fetch", fetch);
    await expect(restoreAudit("run_saved_house")).rejects.toThrow();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("leaves a missing run missing, instead of replacing it with an example or a new audit", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { message: "Unknown run" } }), { status: 404 }));
    vi.stubGlobal("fetch", fetch);
    await expect(restoreAudit("run_missing")).rejects.toThrow("Unknown run");
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][1].method).toBeUndefined();
  });
});
