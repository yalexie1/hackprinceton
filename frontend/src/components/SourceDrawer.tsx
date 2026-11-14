import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import type { Assumption, MeasureResult } from "../lib/types";

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
  { prefix: ["PV", "SOL", "IRR", "LAY", "ROOF", "SHD"], spec: "specs/physics/01-solar-pv.md" },
  { prefix: ["ZON", "ENV", "INF", "HVAC", "LGT", "DHW", "DEF", "WIN", "BEN", "PLUG"], spec: "specs/physics/02-thermal-systems.md" },
  { prefix: ["DAY", "GLR", "CMF", "LCT"], spec: "specs/physics/03-daylight-comfort.md" },
  { prefix: ["COST", "ECO", "EMI", "TAR", "INC", "VAL", "MV", "UNC", "PACE"], spec: "specs/physics/04-economics-emissions-mv.md" },
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
  return [...groups.entries()].map(([spec, members]) => ({ spec, ids: members }));
}

const SOURCE_WORDS: Record<string, string> = {
  user: "you told us",
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
  const used = assumptions.filter((a) => a.evidence?.length);

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
          {cost ? <p>{cost}</p> : <p className="fineprint">No cost source was recorded for this measure.</p>}
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
                    — {i.status}
                    {i.eligibility ? `, eligibility ${i.eligibility.replaceAll("_", " ")}` : ""}
                  </small>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <h4>The physics</h4>
          {groups.length === 0 ? (
            <p className="fineprint">No formula entries were recorded for this measure.</p>
          ) : (
            <ul>
              {groups.map((g) => (
                <li key={g.spec}>
                  <code>{g.ids.join(", ")}</code>
                  <small> — {g.spec}</small>
                </li>
              ))}
            </ul>
          )}
          <p className="fineprint">
            Each entry is a derivation in the spec, with its sources and the values it uses.
          </p>
        </section>

        {used.length > 0 && (
          <section>
            <h4>What it assumed</h4>
            <ul>
              {used.slice(0, 8).map((a) => (
                <li key={a.key}>
                  {a.label || a.key}
                  <small>
                    {" "}
                    — {SOURCE_WORDS[a.source] ?? a.source}
                    {a.evidence?.[0]?.ref ? ` (${a.evidence[0].ref})` : ""}
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
                <li key={n}>{w}</li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
