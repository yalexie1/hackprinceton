import "../evals.css";
import React from "react";

/**
 * How well the projections hold up, measured against real data.
 *
 * This component renders; it never computes. Every number comes from
 * backend/evals/out/*.json via backend/evals/publish.py, so the page cannot
 * disagree with the scorecard. If a figure is not in the JSON it does not
 * belong here.
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
};

export type EvalsData = Record<string, EvalSection>;

const BIN_LABEL: Record<string, string> = {
  below_low: "Below our low estimate",
  low_to_expected: "Between low and expected",
  expected_to_high: "Between expected and high",
  above_high: "Above our high estimate",
};

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
          against a nominal {item.nominal}
          {item.unit}
        </p>
      )}
      <p className="eval-figure-meta">
        {item.ci90 ? `90% confidence ${item.ci90[0]}–${item.ci90[1]}${item.unit}, ` : ""}
        {item.n} buildings
      </p>
      <p className="eval-figure-note">{item.note}</p>
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
              <li key={caveat}>{caveat}</li>
            ))}
          </ul>
        </div>
      )}

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
                    {k.replace(/_/g, " ")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  {keys.map((k) => (
                    <td key={k}>
                      {row[k] === null || row[k] === undefined || row[k] === ""
                        ? "—"
                        : String(row[k])}
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
              <li key={caveat}>{caveat}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export default function Evals({ data }: { data?: EvalsData }) {
  const [loaded, setLoaded] = React.useState<EvalsData | null>(data ?? null);
  const [failed, setFailed] = React.useState(false);

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
      <main className="evals">
        <h2>How accurate is this?</h2>
        <p>The results could not be loaded. Nothing is shown rather than a guess.</p>
      </main>
    );
  }
  if (!loaded) {
    return (
      <main className="evals">
        <h2>How accurate is this?</h2>
        <p>Loading the measured results…</p>
      </main>
    );
  }

  return (
    <main className="evals">
      <h2>How accurate is this?</h2>
      <p className="eval-intro">
        Every number below is measured against data we did not choose after the fact.
        Where we do badly, it says so.
      </p>
      {Object.entries(loaded).map(([key, section]) =>
        section.status !== "ok" ? (
          <NotRun key={key} section={section} />
        ) : section.headline ? (
          <Metered key={key} section={section} />
        ) : (
          <Rows key={key} section={section} />
        ),
      )}
    </main>
  );
}
