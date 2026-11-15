import "../evals.css";
import "../eval-highlights.css";
import React from "react";

/**
 * How well the projections hold up, measured against real data.
 *
 * This component renders; it never computes. Every number comes from
 * backend/evals/out/*.json via backend/evals/publish.py, so the page cannot
 * disagree with the scorecard. If a figure is not in the JSON it does not
 * belong here.
 *
 * The highlights section at the top reads public/eval-highlights.json: four
 * results copied from the scored runs (BDG2 calibrated, LA EBEWE, PVGIS), each
 * with its limits beside it. If that file fails to load, the section is left out.
 */

export type Headline = {
  label: string;
  value: number;
  unit: string;
  nominal: number | null;
  ci90: [number, number] | number[] | null;
  n: number;
  note: string;
};

export type EvalSection = {
  status: "ok" | "not_run" | string;
  title: string;
  question: string;
  headline?: Headline[];
  bins?: Record<string, number>;
  bins_note?: string;
  weather_decomposition?: {
    electricity_median_pct: number;
    heating_need_median_pct: number;
    n_electricity: number;
    n_heating: number;
    note: string;
  };
  caveats?: string[];
  provenance?: Record<string, unknown>;
  rows?: Array<Record<string, unknown>>;
  note?: string;
  supported_zones?: {
    title: string; headline: Headline[]; bins: Record<string, number>;
    n: number; n_sites: number; zones: string[]; sites: string[]; note: string; ci_note: string;
  };
};

export type EvalsData = Record<string, EvalSection>;

/* ---------------------------------------------------------------------------
 * Making the raw scorecard readable.
 *
 * The JSON is written for machines: snake_case keys, booleans, enum tokens,
 * opaque Matterport ids and full float precision. A judge reading the page
 * should never see any of that. Everything below is presentation only; no
 * number is recomputed, only rounded and labelled.
 * ------------------------------------------------------------------------ */

const BIN_LABEL: Record<string, string> = {
  below_low: "Below our low estimate",
  low_to_expected: "Between low and expected",
  expected_to_high: "Between expected and high",
  above_high: "Above our high estimate",
};

/** Plain-English column headings for the keys that actually occur. */
const COLUMN_LABEL: Record<string, string> = {
  sid: "Building",
  state: "State",
  segment: "Market segment",
  status: "Status",
  reason: "Reason",
  verdict: "Verdict",
  year: "Benchmark year",
  mountingplace: "Mounting",
  system_kw_dc: "System size",
  annual_kwh: "Annual output",
  kwh_per_kw: "Our yield",
  pvgis_kwh_per_kw: "PVGIS yield",
  pct_diff: "Difference from PVGIS",
  pv10_deviation_pct: "Deviation",
  pv10_tolerance_pct: "Tolerance",
  pv10_within: "Within tolerance",
  our_usd_per_w: "Our cost per watt",
  p25_usd_per_w: "Market lower quartile",
  median_usd_per_w: "Market median",
  p75_usd_per_w: "Market upper quartile",
  pct_vs_median: "Against the market median",
  // "With a year of utility bills" (#437): plain headings, not "Without bills pct".
  measure: "Measure",
  without_bills_pct: "Without bills",
  with_bills_pct: "With a year of bills",
  n_systems: "Systems compared",
  indicative: "Thin benchmark",
};

/** Enum-ish string values that would otherwise print as raw tokens. */
const VALUE_LABEL: Record<string, string> = {
  inside_iqr: "Inside the market range",
  above_iqr: "Above the market range",
  below_iqr: "Below the market range",
  not_checked: "Not checked",
  checked: "Checked",
};

/**
 * The three Matterport scans in the demo set. Anything else keeps its raw id:
 * inventing a name for a building we cannot identify would be a lie on a page
 * whose whole point is not lying.
 */
const SID_NAME: Record<string, string> = {
  ZSPaQbkGcJJ: "Culver Connect (LA office)",
  zvKHR9DHNjJ: "Los Angeles house",
  L3266YcPPvd: "Houston office",
};

/** "note_only_on_this_row" -> "Note only on this row". Never a raw key. */
function humanise(token: string): string {
  const words = token.replace(/_/g, " ").trim();
  if (!words) return token;
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function columnLabel(key: string): string {
  return COLUMN_LABEL[key] ?? humanise(key);
}

function round(value: number, digits: number): string {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/**
 * The unit is inferred from the key's suffix, so a new column in the JSON gets
 * formatted without a code change here. Order matters: `_kwh_per_kw` must be
 * tested before `_kwh`.
 */
export function formatNumber(key: string, value: number): string {
  if (!Number.isFinite(value)) return "—";
  const k = key.toLowerCase();
  if (k === "year" || k.endsWith("_year")) return String(value);
  if (k.endsWith("_per_kw")) return `${round(value, 0)} kWh/kW`;
  if (k.endsWith("_usd_per_w")) return `$${round(value, 2)}/W`;
  if (k.endsWith("_usd") || k.startsWith("usd_")) return `$${round(value, 0)}`;
  if (k.endsWith("_kwh")) return `${round(value, 0)} kWh`;
  if (k.endsWith("_pct") || k.startsWith("pct_") || k.includes("_pct_"))
    return `${round(value, 1)}%`;
  if (k.endsWith("_kw_dc") || k.endsWith("_kw")) return `${round(value, 1)} kW`;
  if (k.startsWith("n_") || Number.isInteger(value)) return round(value, 0);
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

/** Looks like a machine token (snake_case or a single lowercase word). */
function isToken(s: string): boolean {
  return /^[a-z0-9]+(_[a-z0-9]+)*$/.test(s);
}

export function formatCell(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return formatNumber(key, value);
  if (typeof value === "string") {
    if (key === "sid") return SID_NAME[value] ?? value;
    const mapped = VALUE_LABEL[value];
    if (mapped) return mapped;
    // Free text (anything with a space, or already capitalised) is left alone;
    // only machine tokens get humanised.
    return isToken(value) ? humanise(value) : value;
  }
  if (Array.isArray(value)) {
    const parts = value.map((v) => formatCell(key, v)).filter((s) => s !== "—");
    return parts.length > 0 ? parts.join(", ") : "—";
  }
  return String(value);
}

function evidenceProse(text: string) {
  return text.replace(/PV-10/g, "The solar comparison")
    .replace(/pct_diff/g, "the displayed difference")
    .replace(/mountingplace/g, "mounting method")
    .replace(/free vs building/g, "free-standing versus roof-mounted panels")
    .replace(/PropertySummary.state admits only those two/g, "this prototype supports those two states")
    .replace(/Inside the IQR/g, "Inside the middle half of market prices")
    .replace(/cross-sectional error distribution/g, "comparison across different buildings")
    .replace(/Guideline 14 time-series fit/g, "check against monthly bills under Guideline 14")
    .replace(/effective N/g, "number of independent observations")
    .replace(/CIs/g, "Confidence intervals")
    .replace(/CI is/g, "confidence interval is")
    .replace(/DEF default tables/g, "published building assumptions")
    .replace(/Irradiance/g, "Sunlight data")
    .replace(/irradiance/g, "sunlight")
    .replace(/BOTH arms/g, "both comparisons")
    .replace(/arm difference/g, "difference between comparisons")
    .replace(/single zone at a single storey/g, "one shared heating-and-cooling space on one floor")
    .replace(/surface-to-volume ratio/g, "amount of exterior wall and roof relative to indoor space")
    .replace(/office or residential defaults/g, "typical office or home assumptions")
    .replace(/site-clustered/g, "site-based")
    .replace(/bootstrap over one cluster/g, "statistical resampling of a single site");
}

function Figure({ item }: { item: Headline }) {
  return (
    <li className="eval-figure">
      <p className="eval-figure-label">{item.label}</p>
      <p className="eval-figure-value">
        {item.value}
        <span className="eval-figure-unit">{item.unit}</span>
      </p>
      {item.nominal !== null && (
        <p className="eval-figure-nominal">
          against a nominal target of {item.nominal}
          {item.unit}
        </p>
      )}
      <p className="eval-figure-meta">
        {item.ci90 ? `90% confidence ${item.ci90[0]}–${item.ci90[1]}${item.unit}, ` : ""}
        {item.n} buildings
      </p>
      <p className="eval-figure-note">{item.note ? evidenceProse(item.note) : ""}</p>
    </li>
  );
}

function NotRun({ section }: { section: EvalSection }) {
  return (
    <section className="eval-section eval-section-pending">
      <h3>{section.title}</h3>
      <p className="eval-question">{section.question}</p>
      <p className="eval-pending">
        <strong>Not run yet.</strong> We would rather show nothing than a number we
        have not measured.
      </p>
    </section>
  );
}

/**
 * Studies left off the page by the team lead's call (15 Nov). The data stays in
 * evals.json and backend/evals/out; only the rendering is skipped.
 */
const HIDDEN_SECTIONS = new Set(["metered_buildings"]);

/** The headline results, shown first. Same figure cards as the studies below. */
function Highlights({ section }: { section: EvalSection }) {
  const sources = section.provenance?.sources;
  return (
    <section className="eval-section eval-highlights" aria-label={section.title}>
      <h3>{section.title}</h3>
      <p className="eval-question">{section.question}</p>
      <ul className="eval-figures">
        {(section.headline ?? []).map((item) => (
          <Figure key={item.label} item={item} />
        ))}
      </ul>
      {(section.caveats ?? []).length > 0 && (
        <div className="eval-caveats">
          <h4>What these do not tell you</h4>
          <ul>
            {(section.caveats ?? []).map((caveat) => (
              <li key={caveat}>{caveat}</li>
            ))}
          </ul>
        </div>
      )}
      {sources ? <p className="eval-provenance">{String(sources)}.</p> : null}
    </section>
  );
}

function Metered({ section }: { section: EvalSection }) {
  const bins = section.bins ?? {};
  const w = section.weather_decomposition;
  const p = section.provenance ?? {};
  return (
    <section className="eval-section">
      <h3>{section.title}</h3>
      <p className="eval-question">{section.question}</p>

      <ul className="eval-figures">
        {(section.headline ?? []).map((item) => (
          <Figure key={item.label} item={item} />
        ))}
      </ul>

      {Object.keys(bins).length > 0 && (
        <div className="eval-bins">
          <h4>Where the real meter reading actually fell</h4>
          <table>
            <tbody>
              {Object.entries(bins).map(([key, value]) => (
                <tr key={key}>
                  <th scope="row">{BIN_LABEL[key] ?? key}</th>
                  <td>{value}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="eval-note">{section.bins_note}</p>
        </div>
      )}

      {w && (
        <div className="eval-weather">
          <h4>How much of this is the weather data?</h4>
          <table>
            <tbody>
              <tr>
                <th scope="row">Electricity</th>
                <td>
                  {w.electricity_median_pct}% ({w.n_electricity} buildings)
                </td>
              </tr>
              <tr>
                <th scope="row">Heating need</th>
                <td>
                  {w.heating_need_median_pct}% ({w.n_heating} buildings)
                </td>
              </tr>
            </tbody>
          </table>
          <p className="eval-note">{w.note}</p>
        </div>
      )}

      {(section.caveats ?? []).length > 0 && (
        <div className="eval-caveats">
          <h4>What this does not tell you</h4>
          <ul>
            {(section.caveats ?? []).map((caveat) => (
              <li key={caveat}>{evidenceProse(caveat)}</li>
            ))}
          </ul>
        </div>
      )}

      {section.supported_zones && <section className="eval-supported">
        <h4>{section.supported_zones.title}</h4>
        <p>{evidenceProse(section.supported_zones.note)}</p>
        <p><strong>{section.supported_zones.n} buildings from {section.supported_zones.n_sites} site</strong> · Climate zones {section.supported_zones.zones.join(" and ")}</p>
        <ul className="eval-figures">{section.supported_zones.headline.map(item => <Figure key={item.label} item={item}/>)}</ul>
        <table><tbody>{Object.entries(section.supported_zones.bins).map(([label,value]) => <tr key={label}><th scope="row">{BIN_LABEL[label] || humanise(label)}</th><td>{value}%</td></tr>)}</tbody></table>
        <p className="eval-note">{evidenceProse(section.supported_zones.ci_note)}</p>
      </section>}
      <p className="eval-provenance">
        {String(p.dataset ?? "")}
        {p.year ? `, ${String(p.year)}` : ""}. {String(p.n_scored ?? "")} buildings
        across {String(p.n_sites ?? "")} sites, {String(p.refused ?? 0)} refused by the
        model.
      </p>
    </section>
  );
}

function Rows({ section }: { section: EvalSection }) {
  const rows = section.rows ?? [];
  // Union of keys across every row, not just the first: rows are ragged (a
  // not_checked row carries `reason`, a checked one carries `pct_diff`), and
  // taking the first row's keys would print the literal "undefined" for the rest.
  const keys = [...new Set(rows.flatMap((r) => Object.keys(r)))].filter(
    (k) => k !== "warnings",
  );
  return (
    <section className="eval-section">
      <h3>{section.title}</h3>
      <p className="eval-question">{section.question}</p>
      {rows.length > 0 && (
        <div className="eval-table-scroll">
          <table>
            <thead>
              <tr>
                {keys.map((k) => (
                  <th key={k} scope="col">
                    {columnLabel(k)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  {keys.map((k) => (
                    <td key={k} className={k === "sid" ? "eval-cell-name" : undefined}>
                      {formatCell(k, row[k])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {(section.caveats ?? []).length > 0 && (
        <div className="eval-caveats">
          <h4>What this does not tell you</h4>
          <ul>
            {(section.caveats ?? []).map((caveat) => (
              <li key={caveat}>{evidenceProse(caveat)}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export default function Evals({ data, highlights }: { data?: EvalsData; highlights?: EvalSection }) {
  const [loaded, setLoaded] = React.useState<EvalsData | null>(data ?? null);
  const [failed, setFailed] = React.useState(false);
  const [top, setTop] = React.useState<EvalSection | null>(highlights ?? null);

  React.useEffect(() => {
    if (highlights) return;
    let live = true;
    fetch("/eval-highlights.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: EvalSection) => live && setTop(d))
      .catch(() => undefined); // optional: the full studies still render without it
    return () => {
      live = false;
    };
  }, [highlights]);

  React.useEffect(() => {
    if (data) return;
    let live = true;
    fetch("/evals.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: EvalsData) => live && setLoaded(d))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [data]);

  if (failed) {
    return (
      <section className="evals">
        <h2>How accurate is this?</h2>
        <p>The results could not be loaded. Nothing is shown rather than a guess.</p>
      </section>
    );
  }
  if (!loaded) {
    return (
      <section className="evals">
        <h2>How accurate is this?</h2>
        <p>Loading the measured results…</p>
      </section>
    );
  }

  return (
    <section className="evals">
      <h2>How accurate is this?</h2>
      <p className="eval-intro">
        These studies compare our estimates with recorded energy use or another model. Read the limits beside each result: a model comparison does not prove savings, and these studies do not establish accuracy for your individual home.
      </p>
      {top && top.status === "ok" && <Highlights section={top} />}
      {Object.entries(loaded).filter(([key]) => !HIDDEN_SECTIONS.has(key)).map(([key, section]) =>
        section.status !== "ok" ? (
          <NotRun key={key} section={section} />
        ) : section.headline ? (
          <Metered key={key} section={section} />
        ) : (
          <Rows key={key} section={section} />
        ),
      )}
    </section>
  );
}
