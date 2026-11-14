import { BookOpen, Database, FunctionSquare, Workflow } from "lucide-react";

/**
 * How it works: the pipeline, every source, and where each equation is written down.
 *
 * Two rules this page keeps, both deliberate. **It names sources and equations; it does not
 * restate their numbers.** A constant copied onto a marketing page is a constant that will one
 * day disagree with the code, and the specs are the record. **It distinguishes what is measured
 * from what is assumed**, because that distinction is the product.
 *
 * Sources are read out of `specs/data-integration.md` section 9 and `specs/physics/01`-`04`.
 */

const STAGES: { id: string; title: string; body: string }[] = [
  {
    id: "S1-S2",
    title: "Find the building, then gather what is known about it",
    body:
      "Three independent sources are joined on one property: the interior scan, the aerial " +
      "survey of the roof and parcel, and the commercial property record. Anything that cannot " +
      "be fetched is recorded as a fallback with the reason, and appears in the run log rather " +
      "than being quietly substituted.",
  },
  {
    id: "S3-S4",
    title: "Build a model of the building",
    body:
      "Room geometry and the wall graph come from the scan. Where the scan carries no window " +
      "openings, window sizes are read from the panoramas instead, and the model says which " +
      "route was used. Everything that is not measured is a stated assumption with a source and " +
      "a confidence, and every one of them can be overridden.",
  },
  {
    id: "S5",
    title: "Simulate the building as it stands",
    body:
      "An hourly year of weather for the site drives a zone-by-zone energy model: heating, " +
      "cooling, hot water, lighting, plug loads. The result is checked against the energy use " +
      "of real surveyed buildings of the same type, size and climate, and says so when it lands " +
      "outside the normal range. Given twelve monthly bills it is calibrated to them.",
  },
  {
    id: "S6-S7",
    title: "Evaluate each upgrade, then build a plan that fits",
    body:
      "Every upgrade is modelled against the building as the plan has already changed it, " +
      "priced from published cost data, and checked against incentives. Operations come first, " +
      "then loads, then equipment, and solar is sized last to the energy still needed. An " +
      "upgrade only enters the plan if it saves more over its life than it costs.",
  },
  {
    id: "S8-S9",
    title: "Write it up, and draft the paperwork",
    body:
      "The summary quotes only figures from the run. Legal documents are filled from a template " +
      "for the state and building type; anything the analysis cannot supply is left as a visible " +
      "blank, statutory text is never invented, and each document carries the statutory checks " +
      "it passed and failed.",
  },
];

const SPONSOR_SOURCES: { what: string; source: string; gives: string }[] = [
  {
    what: "Interior scan",
    source: "Matterport Model API",
    gives: "rooms, wall graph, window and door openings, panoramas, the georeference",
  },
  {
    what: "Roof and parcel",
    source: "Vexcel property extract",
    gives: "parcel polygon, building footprints, roof attributes, per-capture history",
  },
  {
    what: "Aerial image",
    source: "Vexcel ortho extract",
    gives: "the photograph under the roof view",
  },
  {
    what: "Roof objects",
    source: "Vexcel precomputed attributes",
    gives:
      "vents, units and obstruction counts. Taken from the survey's own attributes, not from " +
      "image segmentation, which missed real objects and invented others",
  },
  {
    what: "Property record",
    source: "CoStar data kit",
    gives: "use type, year built, storeys, building area, tenancy, comparable sales",
  },
];

const PUBLIC_SOURCES: { what: string; source: string; gives: string }[] = [
  {
    what: "Weather",
    source: "TMYx typical year (climate.onebuilding.org), from NOAA station observations",
    gives:
      "the hourly year for the nearest qualifying station. Open-Meteo's archive is the fallback, " +
      "and the run says when it was used",
  },
  {
    what: "Solar yield check",
    source: "PVGIS (European Commission JRC)",
    gives: "an independent annual yield for the site, used to cross-check the modelled design",
  },
  {
    what: "Energy prices",
    source: "US EIA retail sales and natural gas series",
    gives:
      "state average prices by sector. A state average is not a utility tariff, and every price " +
      "says which it is",
  },
  {
    what: "Who serves the meter",
    source: "US Census geocoder (incorporated places, counties)",
    gives:
      "the serving utility's place and the state, used instead of the record's mailing city",
  },
  {
    what: "Benchmarks",
    source: "EIA RECS 2020 and CBECS 2018 public microdata; ENERGY STAR national medians",
    gives:
      "the energy-use distribution of real surveyed homes and offices, by type, size and climate",
  },
  {
    what: "Climate zone",
    source: "ASHRAE 169-2021, computed from the site's own weather",
    gives:
      "the thermal zone from heating and cooling degree-days. The moisture letter needs rainfall " +
      "data this project does not fetch and is taken from the state, which the record states",
  },
  {
    what: "Statutes",
    source: "California and Texas codes, as cited in each document",
    gives: "the clauses a retrofit contract or C-PACE package must carry",
  },
];

const EQUATIONS: { group: string; spec: string; entries: string }[] = [
  {
    group: "Sun, irradiance and solar yield",
    spec: "specs/physics/01-solar-pv.md",
    entries:
      "Solar position and the plane-of-array irradiance on each roof plane (SOL, IRR); the panel " +
      "layout and row shading (LAY, SHD); the cell temperature, losses and inverter chain that " +
      "turn irradiance into AC energy (PV-01 to PV-09); and PV-10, which moves PVGIS to the " +
      "design's own orientation to cross-check the result.",
  },
  {
    group: "Heat, air and the systems",
    spec: "specs/physics/02-thermal-systems.md",
    entries:
      "The zone heat balance and hourly loads (ZON); envelope conduction and solar gain (ENV); " +
      "infiltration and ventilation (INF); heating, cooling and hot water equipment (HVAC, DHW); " +
      "lighting and plug loads (LGT); the vintage defaults by climate zone and age (DEF); and " +
      "BEN-01 to BEN-03, the benchmark against surveyed buildings.",
  },
  {
    group: "Daylight and comfort",
    spec: "specs/physics/03-daylight-comfort.md",
    entries:
      "Daylight at a point, glare risk, thermal comfort and the lighting controls that convert " +
      "daylight into saved electricity (DAY, GLR, CMF, LCT).",
  },
  {
    group: "Money, carbon and measurement",
    spec: "specs/physics/04-economics-emissions-mv.md",
    entries:
      "Installed costs and their sources (COST); net present value, payback, the " +
      "savings-to-investment ratio and the rate of return (ECO); tariffs, net metering and export " +
      "(TAR); emissions by grid subregion (EMI); incentives (INC); the property value uplift " +
      "(VAL); and bill calibration (MV).",
  },
];

export default function HowItWorks() {
  return (
    <section className="how-it-works">
      <div className="section-heading">
        <div>
          <span className="eyebrow">HOW IT WORKS</span>
          <h2>Every number has a source.</h2>
        </div>
        <BookOpen size={26} />
      </div>
      <p className="section-description">
        This is an engineering estimate, not a guess and not an appraisal. Below is what the
        analysis does, every source it uses, and where each equation is written down. Figures are
        named here, never restated: the specifications are the record, and a number copied onto a
        page is a number that will one day disagree with the code.
      </p>

      <h3>
        <Workflow size={19} /> What happens to your building
      </h3>
      <ol className="hiw-stages">
        {STAGES.map((s) => (
          <li key={s.id}>
            <strong>{s.title}</strong>
            <p>{s.body}</p>
          </li>
        ))}
      </ol>

      <h3>
        <Database size={19} /> Where the facts come from
      </h3>
      <h4>About your building</h4>
      <table className="hiw-table">
        <thead>
          <tr>
            <th>What</th>
            <th>Source</th>
            <th>What it gives</th>
          </tr>
        </thead>
        <tbody>
          {SPONSOR_SOURCES.map((r) => (
            <tr key={r.what}>
              <td>{r.what}</td>
              <td>{r.source}</td>
              <td>{r.gives}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h4>Public data</h4>
      <table className="hiw-table">
        <thead>
          <tr>
            <th>What</th>
            <th>Source</th>
            <th>What it gives</th>
          </tr>
        </thead>
        <tbody>
          {PUBLIC_SOURCES.map((r) => (
            <tr key={r.what}>
              <td>{r.what}</td>
              <td>{r.source}</td>
              <td>{r.gives}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="fineprint">
        The exact endpoints, parameters and the date each was last verified are in
        <code> specs/data-integration.md</code> section 9.
      </p>

      <h3>
        <FunctionSquare size={19} /> The equations
      </h3>
      <p className="section-description">
        Each entry below is a derivation with its own sources, its assumptions and the values it
        uses. Any estimate in the app lists the entries behind it under “How this was calculated”.
      </p>
      <dl className="hiw-equations">
        {EQUATIONS.map((e) => (
          <div key={e.group}>
            <dt>{e.group}</dt>
            <dd>
              {e.entries}
              <br />
              <code>{e.spec}</code>
            </dd>
          </div>
        ))}
      </dl>

      <h3>What this does not do</h3>
      <ul className="hiw-limits">
        <li>
          It is not an appraisal. The property value figure is shown separately and is never added
          to energy savings or used in the ranking.
        </li>
        <li>
          It is not legal advice. Documents are drafts for an attorney, with blanks left visible
          and statutory text never invented.
        </li>
        <li>
          It does not replace a site visit. Anything that needs eyes on the building — electrical
          capacity, roof structure, equipment age — is flagged for a check rather than assumed
          away.
        </li>
        <li>
          Savings are estimates with a stated range. Confirm costs with a contractor before
          starting work.
        </li>
      </ul>
    </section>
  );
}
