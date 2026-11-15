import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import Evals, { type EvalsData } from "./Evals";

const data: EvalsData = {
  metered_buildings: {
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
    for (const caveat of data.metered_buildings.caveats ?? []) {
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
    expect(html).toContain(data.metered_buildings.bins_note as string);
  });
});
