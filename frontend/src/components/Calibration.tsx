import type { RunResult } from "../lib/types";
import { number } from "../lib/format";
import Warnings from "./Warnings";

export default function Calibration({ run }: { run: RunResult }) {
  const summary = run.baseline?.calibration || run.building_model?.calibration;
  if (!summary)
    return (
      <p className="inline-note">
        Uncalibrated estimate: these results have not been matched to your
        utility bills.
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
                <td>{fit.passed ? "Within tolerance" : "Outside tolerance"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="fineprint">
        Monthly criteria: bias within ±5%, CV(RMSE) at most 15%. A fitted
        baseline does not guarantee future savings.
      </p>
      {summary.moved.length > 0 && (
        <details>
          <summary>Inputs adjusted within their stated ranges</summary>
          <ul>
            {summary.moved.map((key) => (
              <li key={key}>
                {run.building_model?.assumptions.find((a) => a.key === key)
                  ?.label || key}
              </li>
            ))}
          </ul>
        </details>
      )}
      <Warnings warnings={summary.warnings} />
    </section>
  );
}
