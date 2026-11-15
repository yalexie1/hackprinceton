import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import Evals, { columnLabel, type EvalsData } from "./Evals";

const data: EvalsData = {
  metered_study: {
    status: "ok",
    title: "Metered buildings",
    question: "How close is our predicted annual electricity to a real meter?",
    headline: [
      {
        label: "Interval coverage",
        value: 17.6,
        unit: "%",
        nominal: 80,
        ci90: [13.7, 22.2],
        n: 494,
        note: "How often the metered annual fell inside our stated 10-90 band.",
      },
      {
        label: "Median absolute error",
        value: 55.5,
        unit: "%",
        nominal: null,
        ci90: null,
        n: 494,
        note: "Half of buildings are predicted closer than this.",
      },
    ],
    bins: {
      below_low: 38.1,
      low_to_expected: 11.7,
      expected_to_high: 5.9,
      above_high: 44.3,
    },
    bins_note: "Truth falls below and above in near-equal measure.",
    weather_decomposition: {
      electricity_median_pct: -1,
      heating_need_median_pct: 24.8,
      n_electricity: 494,
      n_heating: 451,
      note: "Swapping measured station temperatures for the reanalysis path.",
    },
    caveats: ["caveat one", "caveat two", "caveat three", "caveat four", "caveat five"],
    provenance: {
      dataset: "Building Data Genome Project 2",
      year: 2017,
      n_scored: 494,
      n_sites: 5,
      refused: 0,
      arm: "bdg2temp",
    },
  },
  pv_crosscheck: { status: "not_run", title: "PV yield vs PVGIS", question: "Does it agree?" },
};

describe("evals page", () => {
  it("shows a measured figure against the value it was supposed to hit", () => {
    const html = renderToStaticMarkup(<Evals data={data} />);
    expect(html).toContain("17.6");
    expect(html).toContain("Interval coverage");
    // The nominal is the whole point: 17.6% means nothing without the 80% it missed.
    expect(html).toContain("80");
    expect(html).toContain("nominal");
  });

  it("shows the sample size and the confidence interval next to the figure", () => {
    const html = renderToStaticMarkup(<Evals data={data} />);
    expect(html).toContain("494");
    expect(html).toContain("13.7");
    expect(html).toContain("22.2");
  });

  it("renders every caveat on the page rather than hiding them behind a disclosure", () => {
    const html = renderToStaticMarkup(<Evals data={data} />);
    for (const caveat of data.metered_study.caveats ?? []) {
      expect(html).toContain(caveat);
    }
    expect(html).not.toContain("<details");
  });

  it("marks an eval that has not run as not run, never as a zero", () => {
    const html = renderToStaticMarkup(<Evals data={data} />);
    expect(html).toContain("PV yield vs PVGIS");
    expect(html).toContain("Not run yet");
    expect(html).not.toContain(">0%<");
  });

  it("explains the weather split instead of printing two bare numbers", () => {
    const html = renderToStaticMarkup(<Evals data={data} />);
    expect(html).toContain("24.8");
    expect(html).toContain("Heating need");
    expect(html).toContain("Electricity");
  });

  it("says plainly that the band is too narrow rather than leaving the bins to speak", () => {
    const html = renderToStaticMarkup(<Evals data={data} />);
    expect(html).toContain("38.1");
    expect(html).toContain("44.3");
    expect(html).toContain(data.metered_study.bins_note as string);
  });
});

describe("evals table with ragged rows", () => {
  const ragged: EvalsData = {
    pv_crosscheck: {
      status: "ok",
      title: "PV yield vs PVGIS",
      question: "Does it agree?",
      rows: [
        { sid: "a", pct_diff: -2.7, reason: "" },
        { sid: "b", pct_diff: null, note_only_on_this_row: "late key" },
      ],
    },
  };

  it("never prints the literal string undefined when rows have different keys", () => {
    const html = renderToStaticMarkup(<Evals data={ragged} />);
    expect(html).not.toContain("undefined");
    // The key that appears only on the second row must still get a column,
    // humanised rather than printed as the raw key.
    expect(html).toContain("Note only on this row");
    expect(html).not.toContain("note_only_on_this_row");
    expect(html).toContain("late key");
  });
});

describe("evals table reads as plain English", () => {
  const judged: EvalsData = {
    pv_crosscheck: {
      status: "ok",
      title: "PV yield vs PVGIS",
      question: "Does it agree?",
      rows: [
        {
          sid: "ZSPaQbkGcJJ",
          annual_kwh: 357079.40762399795,
          kwh_per_kw: 1631.47,
          pv10_tolerance_pct: 6.66,
          pv10_within: true,
          system_kw_dc: 218.87,
          status: "checked",
        },
        { sid: "unknown-scan-id", pv10_within: false, status: "not_checked" },
      ],
    },
    cost_check: {
      status: "ok",
      title: "Cost vs the market",
      question: "Is the price plausible?",
      rows: [
        {
          sid: "zvKHR9DHNjJ",
          our_usd_per_w: 2.2,
          n_systems: 2830,
          year: 2023,
          indicative: false,
          verdict: "inside_iqr",
          pct_vs_median: -25.3,
        },
      ],
    },
  };

  const html = renderToStaticMarkup(<Evals data={judged} />);

  it("never shows a raw snake_case key as a column heading", () => {
    for (const key of ["pv10_within", "our_usd_per_w", "n_systems", "annual_kwh"]) {
      expect(html).not.toContain(key);
    }
    expect(html).toContain("Within tolerance");
    expect(html).toContain("Our cost per watt");
    expect(html).toContain("Systems compared");
  });

  it("rounds and localises numbers instead of printing float noise", () => {
    expect(html).not.toContain("357079.40762399795");
    expect(html).toContain("357,079 kWh");
    expect(html).toContain("1,631 kWh/kW");
    expect(html).toContain("218.9 kW");
    expect(html).toContain("$2.20/W");
    expect(html).toContain("6.7%");
    expect(html).toContain("-25.3%");
    expect(html).toContain("2,830");
    // A year is a label, not a quantity: never "2,023".
    expect(html).toContain("2023");
    expect(html).not.toContain("2,023");
  });

  it("writes booleans as Yes and No", () => {
    expect(html).toContain(">Yes<");
    expect(html).toContain(">No<");
    expect(html).not.toContain(">true<");
    expect(html).not.toContain(">false<");
  });

  it("spells out enum tokens", () => {
    expect(html).toContain("Inside the market range");
    expect(html).toContain("Not checked");
    expect(html).toContain("Checked");
    expect(html).not.toContain("inside_iqr");
    expect(html).not.toContain("not_checked");
  });

  it("names the buildings it knows and keeps the raw id for the ones it does not", () => {
    expect(html).toContain("Culver Connect (LA office)");
    expect(html).toContain("Los Angeles house");
    expect(html).not.toContain("ZSPaQbkGcJJ");
    // No invented name for an unrecognised scan.
    expect(html).toContain("unknown-scan-id");
  });
});

describe("published climate subset", () => {
  it("renders the supplied subset beside the full headline without hiding its limitation", () => {
    const withSubset = structuredClone(data);
    withSubset.metered_study.supported_zones = {
      title:"Supported climate zones only", n:96, n_sites:1, sites:["Panther"], zones:["2A","3B"],
      headline:[{label:"Median absolute error",value:56.7,unit:"%",nominal:null,ci90:null,n:96,note:""}],
      bins:{above_high:76}, note:"Restricted to supported climates.", ci_note:"Only one site; no confidence interval is reported.",
    };
    const html = renderToStaticMarkup(<Evals data={withSubset}/>);
    for (const text of ["494","96","56.7","76","Only one site"]) expect(html).toContain(text);
    expect(html).not.toContain("<details");
  });
});

describe("with-bills table headings", () => {
  it("labels the comparison columns in plain words", () => {
    expect(columnLabel("without_bills_pct")).toBe("Without bills");
    expect(columnLabel("with_bills_pct")).toBe("With a year of bills");
    expect(columnLabel("measure")).toBe("Measure");
  });
});

describe("evals highlights", () => {
  it("shows the headline results first, with their limits beside them", () => {
    const highlights = {
      status: "ok",
      title: "The results we stand behind",
      question: "Four measured results.",
      headline: [
        { label: "Median error with a year of utility bills", value: 4.1, unit: "%", nominal: null, ci90: null, n: 44, note: "Scored on a year the model never saw." },
      ],
      caveats: ["Calibration succeeds for 44 of 283 buildings today."],
      provenance: { sources: "Building Data Genome Project 2" },
    };
    const html = renderToStaticMarkup(<Evals data={data} highlights={highlights} />);
    expect(html.indexOf("The results we stand behind")).toBeLessThan(html.indexOf("Metered buildings"));
    expect(html).toContain("4.1");
    expect(html).toContain("44 of 283");
    expect(html).toContain("What these do not tell you");
  });

  it("is left out when there is nothing to show", () => {
    const html = renderToStaticMarkup(<Evals data={data} highlights={{ status: "not_run", title: "x", question: "y" }} />);
    expect(html).not.toContain("The results we stand behind");
  });
});

describe("hidden studies", () => {
  it("leaves the metered-buildings study off the page", () => {
    const html = renderToStaticMarkup(<Evals data={{ metered_buildings: data.metered_study }} />);
    expect(html).not.toContain("Metered buildings");
    expect(html).not.toContain("Interval coverage");
  });
});

describe("evidence kind", () => {
  it("labels what kind of evidence each highlight is", () => {
    const highlights = {
      status: "ok", title: "T", question: "Q",
      headline: [{ label: "Solar", value: 100, unit: "%", nominal: null, ci90: null, n: 76, note: "", kind: "Agreement with another model" }],
    };
    const html = renderToStaticMarkup(<Evals data={{}} highlights={highlights} />);
    expect(html).toContain("Agreement with another model");
  });
});
