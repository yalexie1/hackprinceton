import { evidenceText, inputName, readableText, warningText } from "../lib/homeowner-language";
import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import type { Assumption, MeasureResult } from "../lib/types";
import { hasPlaceholderEvidence } from "../lib/real-audit";

/**
 * Where a number on the page came from.
 *
 * Vignesha asked for a source behind every estimate, clickable, with the main pages kept clean -
 * so this is a drawer, not more prose. Everything it shows is already in the result: the physics
 * entries the backend used (`formula_ids`), the cost's own stated source (`finance.cost_source`),
 * each incentive's status, and the assumptions behind it with where each came from.
 *
 * It never computes or rephrases a figure. If the backend did not record a provenance, the
 * drawer says so rather than filling the gap with something plausible.
 */

/** Which spec a physics id lives in, from the prefix the backend uses. */
const SPEC_OF: { prefix: string[]; spec: string }[] = [
  {
    prefix: ["PV", "SOL", "IRR", "LAY", "ROOF", "SHD"],
    spec: "specs/physics/01-solar-pv.md",
  },
  {
    prefix: [
      "ZON",
      "ENV",
      "INF",
      "HVAC",
      "LGT",
      "DHW",
      "DEF",
      "WIN",
      "BEN",
      "PLUG",
    ],
    spec: "specs/physics/02-thermal-systems.md",
  },
  {
    prefix: ["DAY", "GLR", "CMF", "LCT"],
    spec: "specs/physics/03-daylight-comfort.md",
  },
  {
    prefix: ["COST", "ECO", "EMI", "TAR", "INC", "VAL", "MV", "UNC", "PACE"],
    spec: "specs/physics/04-economics-emissions-mv.md",
  },
];

export function specFor(id: string): string | null {
  const prefix = id.split("-")[0]?.toUpperCase();
  if (!prefix) return null;
  return SPEC_OF.find((s) => s.prefix.includes(prefix))?.spec ?? null;
}

/** The physics ids grouped by the spec they live in, so a reader gets one line per document. */
export function groupFormulas(ids: string[]) {
  const groups = new Map<string, string[]>();
  for (const id of ids) {
    const spec = specFor(id) ?? "unattributed";
    groups.set(spec, [...(groups.get(spec) ?? []), id]);
  }
  return [...groups.entries()].map(([spec, members]) => ({
    spec,
    ids: members,
  }));
}

const SOURCE_WORDS: Record<string, string> = {
  user: "provided during the audit",
  measured: "measured in the scan",
  costar: "the CoStar record",
  vexcel: "the aerial survey",
  vision: "read from the panoramas",
  published_default: "a published default",
  vintage_default: "a default for the building's vintage",
};

export function SourceDrawer({
  measure,
  assumptions,
  onClose,
}: {
  measure: MeasureResult;
  assumptions: Assumption[];
  onClose: () => void;
}) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const groups = groupFormulas(measure.formula_ids ?? []);
  const cost = measure.finance?.cost_source;
  const incentives = measure.finance?.incentives ?? [];
  const used = assumptions.filter(
    (a) => a.evidence?.length && !hasPlaceholderEvidence(a),
  );

  return (
    <div className="source-drawer-backdrop" onClick={onClose}>
      <div
        className="source-drawer"
        role="dialog"
        aria-label={`How ${measure.title} was calculated`}
        tabIndex={-1}
        ref={panel}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="source-drawer-head">
          <div>
            <span className="eyebrow">HOW THIS WAS CALCULATED</span>
            <h3>{measure.title}</h3>
          </div>
          <button aria-label="Close" className="icon-button" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <section>
          <h4>The cost</h4>
          {cost ? (
            <p>{readableText(cost)}</p>
          ) : (
            <p className="fineprint">
              No cost source was recorded for this measure.
            </p>
          )}
        </section>

        {incentives.length > 0 && (
          <section>
            <h4>Incentives</h4>
            <ul>
              {incentives.map((i, n) => (
                <li key={n}>
                  {i.name}
                  <small>
                    {" "}
                    — {readableText(i.status)}
                    {i.eligibility
                      ? `, eligibility ${readableText(i.eligibility)}`
                      : ""}
                  </small>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <h4>How the estimate was made</h4>
          {groups.length === 0 ? (
            <p className="fineprint">
              No calculation methods were recorded for this upgrade.
            </p>
          ) : (
            <ul>
              {groups.map((g) => (
                <li key={g.spec}>
                  {g.spec.includes("01-solar") ? "Sunlight, roof space and solar panel output" : g.spec.includes("02-thermal") ? "Heat flow, heating, cooling and everyday electricity use" : g.spec.includes("03-daylight") ? "Daylight and indoor conditions" : g.spec.includes("04-economics") ? "Installation costs, energy prices and savings over time" : "A calculation method whose description was not recorded"}
                </li>
              ))}
            </ul>
          )}
          <p className="fineprint">
            These methods combine the recorded building details with weather, equipment assumptions and energy prices. They produce estimates, not guaranteed savings.
          </p>
        </section>

        {used.length > 0 && (
          <section>
            <h4>Building details recorded in this audit</h4>
            <p className="fineprint">This is a selection of the audit’s sourced inputs, not a list of exact dependencies for this upgrade. The Assumptions page contains all recorded inputs.</p>
            <ul>
              {used.slice(0, 8).map((a) => (
                <li key={a.key}>
                  {inputName(a.key, a.label)}
                  <small>
                    {" "}
                    — {SOURCE_WORDS[a.source] ?? a.source}
                    {a.evidence?.[0] ? ` · ${evidenceText(a.evidence[0])}` : ""}
                  </small>
                </li>
              ))}
            </ul>
          </section>
        )}

        {measure.warnings?.length > 0 && (
          <section>
            <h4>Caveats the analysis recorded</h4>
            <ul>
              {measure.warnings.map((w, n) => (
                <li key={n}>{warningText(w)}</li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
