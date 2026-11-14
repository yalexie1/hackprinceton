import { describe, expect, it } from "vitest";
import { api, assetUrl, streamRun } from "./api";
import { SCHEMA_VERSION } from "./types";
import type { DocumentRequest, RunEvent, RunResult } from "./types";

const examples = Object.values(
  import.meta.glob("../../../specs/examples/*/run_result.json", {
    eager: true,
    import: "default",
  }),
) as RunResult[];
const documents = Object.values(
  import.meta.glob("../../../specs/examples/*/document_request.json", {
    eager: true,
    import: "default",
  }),
) as DocumentRequest[];

describe.skipIf(process.env.RUN_API_INTEGRATION !== "1")(
  "frontend client against real replay FastAPI server",
  () => {
    it("accepts the current backend contract", async () => {
      expect(await api.health()).toMatchObject({
        status: "ok",
        schema_version: SCHEMA_VERSION,
      });
    });

    for (const example of examples) {
      it(`searches, audits, adjusts and drafts ${example.property.sid}`, async () => {
        const found = await api.search(
          example.property.name,
          example.property.segment,
        );
        expect(
          found.some((property) => property.sid === example.property.sid),
        ).toBe(true);
        const { run_id } = await api.start(example.request);
        const recorded = process.env.REPLAY_SOURCE === "recorded";
        expect(run_id.startsWith("run_demo_")).toBe(recorded);
        const result = await api.result(run_id);
        expect(result).toMatchObject({
          schema_version: SCHEMA_VERSION,
          status: "done",
          property: { sid: example.property.sid },
        });
        expect(result.plan).toBeTruthy();
        const roof = await api.roof(run_id);
        expect(roof.srid).toBe(4326);
        expect(roof.panels_selected).toBe(
          result.plan!.selected.some(
            (item) => item.measure.measure_id === "PV_ROOF",
          ),
        );
        expect(Array.isArray(roof.planes)).toBe(true);
        if (roof.ortho) {
          expect(roof.ortho.bounds.north).toBeGreaterThan(
            roof.ortho.bounds.south,
          );
          expect(["detection_fit", "parcel_bbox"]).toContain(
            roof.ortho.bounds_source,
          );
          expect(typeof roof.ortho.image_available).toBe("boolean");
        }
        const types = await api.templates(
          example.property.state || "CA",
          example.property.segment,
        );
        expect(types.length).toBeGreaterThan(0);
        if (example.property.segment === "residential")
          expect(types).not.toContain("cpace_package");

        const history: RunEvent[] = [];
        await streamRun(
          run_id,
          (event) => history.push(event),
          AbortSignal.timeout(10000),
          { followToEnd: true },
        );
        expect(history.at(-1)?.type).toBe("done");

        const nextBudget = result.request.budget_usd + 1000;
        await api.update(run_id, { budget_usd: nextBudget });
        const revised: RunEvent[] = [];
        await streamRun(
          run_id,
          (event) => revised.push(event),
          AbortSignal.timeout(10000),
          { afterEvents: history.length, followToEnd: true },
        );
        expect(revised[0]?.message).toBe("Applying your change");
        expect(revised.at(-1)?.message).toBe("Re-run complete");
        expect(
          revised.some(
            (event) =>
              event.type === "tool_call" && event.payload.name === "set_budget",
          ),
        ).toBe(true);
        expect((await api.result(run_id)).plan?.budget_usd).toBe(nextBudget);

        const assumption = result.building_model?.assumptions.find(
          (item) => item.user_editable,
        );
        if (assumption) {
          const value =
            typeof assumption.value === "object"
              ? assumption.value.expected
              : assumption.value;
          await api.update(run_id, { overrides: { [assumption.key]: value } });
          expect(
            (await api.result(run_id)).request.overrides?.[assumption.key],
          ).toBe(value);
        }
        await expect(
          api.update(run_id, { overrides: { nonexistent_input: 1 } }),
        ).rejects.toThrow("not an assumption");
        await expect(
          api.answer(run_id, "completed-question", null),
        ).rejects.toThrow("not waiting");
        const template = documents.find(
          (item) => item.run_id === example.run_id,
        );
        expect(template).toBeTruthy();
        const draft = await api.draft({ ...template!, run_id });
        expect(draft.doc_id).toBeTruthy();
        expect(draft.markdown).toBeTruthy();
        expect(Array.isArray(draft.statutory_checks)).toBe(true);
        if (recorded) {
          expect(draft.statutory_checks.length).toBeGreaterThan(0);
          expect(draft.unfilled_placeholders.length).toBeGreaterThan(0);
          expect(draft.disclaimer).toBeTruthy();
          await expect(
            api.draft({ ...template!, run_id, doc_type: "bid_package_rfp" }),
          ).rejects.toMatchObject({
            status: 404,
            code: "template_not_available",
          });
        }
      }, 20000);
    }

    it("preserves backend error envelopes and confines asset access", async () => {
      await expect(api.result("missing-run")).rejects.toThrow("unknown run_id");
      const response = await fetch(assetUrl("nonexistent/mask.png"));
      expect(response.status).toBe(404);
      expect((await response.json()).error.code).toBe("asset_not_found");
    });
  },
);
