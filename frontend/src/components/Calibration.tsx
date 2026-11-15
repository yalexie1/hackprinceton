import { inputName } from "../lib/homeowner-language";
import type { RunResult } from "../lib/types";
import { number } from "../lib/format";
import Warnings from "./Warnings";

export default function Calibration({ run }: { run: RunResult }) {
  const summary = run.baseline?.calibration || run.building_model?.calibration;
  if (!summary)
    return (
      <p className="inline-note">
        Not checked against your utility bills yet. Adding twelve months of
        bills helps check whether the energy estimate matches your home.
      </p>
    );
  return (
    <section
      className="calibration-panel"
      aria-label="Utility bill calibration"
    >
      <h3>
        {summary.calibrated
          ? "Calibrated to your bills"
          : "Bill fit needs review"}
      </h3>
      <details className="financial-guide">
        <summary>How closely does the estimate match your bills?</summary>
        <p>
          We compare twelve months of bills with the energy model. Bias shows
          whether the model estimates more or less use than the bills. Fit error
          measures the overall difference; lower is better.
        </p>
        <div className="calibration-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fuel</th>
                <th>Bias before → after</th>
                <th>Fit error before → after</th>
                <th>Monthly fit</th>
              </tr>
            </thead>
            <tbody>
              {summary.fits.map((fit) => (
                <tr key={fit.fuel}>
                  <th>{fit.fuel === "gas" ? "Gas" : "Electricity"}</th>
                  <td>
                    {number(fit.nmbe_before * 100, 1)}% →{" "}
                    {number(fit.nmbe_after * 100, 1)}%
                  </td>
                  <td>
                    {number(fit.cv_rmse_before * 100, 1)}% →{" "}
                    {number(fit.cv_rmse_after * 100, 1)}%
                  </td>
                  <td>
                    {fit.passed ? "Within tolerance" : "Outside tolerance"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="fineprint">
          Monthly checks allow an average over- or under-estimate of up to 5% and an overall monthly fit error of up to 15%. Matching past bills does not guarantee future savings.
        </p>
      </details>
      {summary.moved.length > 0 && (
        <details>
          <summary>Inputs adjusted within their stated ranges</summary>
          <ul>
            {summary.moved.map((key) => (
              <li key={key}>
                {inputName(key, run.building_model?.assumptions.find((a) => a.key === key)?.label)}
              </li>
            ))}
          </ul>
        </details>
      )}
      <Warnings warnings={summary.warnings} />
    </section>
  );
}
