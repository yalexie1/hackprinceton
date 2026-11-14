import { useState } from "react";
import { Compass, Info, Sun } from "lucide-react";
import type { RunResult } from "../lib/types";
import { number, polygon, ranged } from "../lib/format";
export default function Geometry({
  run,
  layout = false,
  demo,
}: {
  run: RunResult;
  layout?: boolean;
  demo: boolean;
}) {
  const solar = run.measures.find((m) => m.solar)?.solar;
  const desks = run.measures.find((m) => m.layout)?.layout;
  const roofs = run.building_model?.roof_planes || [];
  const [selected, setSelected] = useState(0);
  const candidates = desks?.candidates || [];
  const roofPolys = roofs.map((r) => polygon(r.polygon_wkt));
  const panelPolys = solar?.panels.map((p) => polygon(p.polygon_wkt)) || [];
  const points = layout
    ? candidates.map((p) => [p.x, p.y])
    : [...roofPolys, ...panelPolys].flat();
  if (!points.length)
    return (
      <div className="empty-state">
        <Sun />
        <h3>
          {layout ? "No workspace candidates yet" : "No roof geometry yet"}
        </h3>
        <p>
          The analysis will provide{" "}
          {layout
            ? "scored desk positions"
            : "roof planes and panel placements"}{" "}
          when available for this property.
        </p>
      </div>
    );
  const minX = Math.min(...points.map((p) => p[0]));
  const maxX = Math.max(...points.map((p) => p[0]));
  const minY = Math.min(...points.map((p) => p[1]));
  const maxY = Math.max(...points.map((p) => p[1]));
  const scale = Math.min(510 / (maxX - minX || 1), 290 / (maxY - minY || 1));
  const xy = (p: number[]) => [
    85 + (p[0] - minX) * scale,
    365 - (p[1] - minY) * scale,
  ];
  const pts = (poly: number[][]) => poly.map((p) => xy(p).join(",")).join(" ");
  const current = candidates[selected];
  const unsupported =
    !layout &&
    (roofPolys.some((p) => !p.length) || panelPolys.some((p) => !p.length));
  return (
    <section className="geometry-panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">
            {layout ? "WORK WITH YOUR SPACE" : "ENERGY FROM ABOVE"}
          </span>
          <h2>
            {layout ? "A brighter place to work." : "Your roof has potential."}
          </h2>
        </div>
        <Compass size={26} />
      </div>
      <p className="section-description">
        {layout
          ? "Compare daylight, glare, and comfort at each candidate position. Select a point to inspect its score."
          : "Explore the roof planes and proposed solar modules returned by the analysis."}
      </p>
      <div className="geometry-canvas">
        <svg
          viewBox="0 0 680 430"
          role={layout ? "group" : "img"}
          aria-label={
            layout
              ? "Desk candidate map"
              : "Roof planes and proposed panel layout"
          }
        >
          <defs>
            <pattern
              id="geo-grid"
              width="25"
              height="25"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M25 0H0V25"
                fill="none"
                stroke="#c7d2be"
                strokeWidth=".7"
              />
            </pattern>
          </defs>
          <rect width="680" height="430" fill="#e8eddf" />
          <rect width="680" height="430" fill="url(#geo-grid)" />
          {layout ? (
            candidates.map((point, i) => {
              const [x, y] = xy([point.x, point.y]);
              return (
                <g
                  key={i}
                  role="button"
                  tabIndex={0}
                  aria-label={`Position ${i + 1}, score ${point.score}`}
                  onClick={() => setSelected(i)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelected(i);
                    }
                  }}
                >
                  <circle
                    cx={x}
                    cy={y}
                    r="28"
                    fill={point.recommended ? "#82a778" : "#b6c8a8"}
                    opacity={0.35 + point.score * 0.4}
                  />
                  <rect
                    x={x - 12}
                    y={y - 8}
                    width="24"
                    height="16"
                    rx="3"
                    fill={selected === i ? "#234d3d" : "#799973"}
                  />
                  <text
                    x={x}
                    y={y + 4}
                    textAnchor="middle"
                    fill="white"
                    fontSize="10"
                  >
                    {i + 1}
                  </text>
                </g>
              );
            })
          ) : (
            <>
              {roofPolys.map((p, i) => (
                <polygon
                  key={i}
                  points={pts(p)}
                  fill="#c6cebb"
                  stroke="#7b8b6d"
                  strokeWidth="2"
                />
              ))}
              {panelPolys.map((p, i) => (
                <polygon
                  key={i}
                  points={pts(p)}
                  fill="#315768"
                  stroke="#91acb2"
                  strokeWidth="1.5"
                >
                  <title>
                    Panel {i + 1}: {number(solar!.panels[i].annual_kwh)} kWh /
                    year, shading loss{" "}
                    {number(solar!.panels[i].shading_loss_fraction * 100, 1)}%
                  </title>
                </polygon>
              ))}
            </>
          )}
          <path
            d="M626 84V46m-6 8 6-8 6 8"
            stroke="#64735d"
            fill="none"
            strokeWidth="2"
          />
          <text x="626" y="37" textAnchor="middle" fontSize="11" fill="#64735d">
            {layout ? "+y" : "N"}
          </text>
          <text x="28" y="405" fill="#64735d" fontSize="11">
            {demo
              ? "Illustrative geometry · not to scale"
              : layout
                ? "Model coordinates · candidate map, not a floor plan"
                : "Map-coordinate polygons · geographic projection may distort scale"}
          </text>
        </svg>
      </div>
      {unsupported && (
        <p className="inline-note">
          <Info size={14} />
          Some geometry uses an unsupported WKT type and could not be drawn. The
          analysis data is available in the report.
        </p>
      )}
      {layout && current ? (
        <div className="detail-grid">
          <div>
            <span>Position {selected + 1}</span>
            <strong>
              {current.recommended ? "Recommended" : "Alternative"}
            </strong>
          </div>
          <div>
            <span>Daylight score</span>
            <strong>{number(current.daylight, 2)}</strong>
          </div>
          <div>
            <span>Glare risk</span>
            <strong>{number(current.glare_risk, 2)}</strong>
          </div>
          <div>
            <span>Comfort PPD</span>
            <strong>{number(current.comfort_ppd, 1)}%</strong>
          </div>
          <div>
            <span>Overall score</span>
            <strong>{number(current.score, 2)}</strong>
          </div>
          <div>
            <span>Desks requested</span>
            <strong>{desks?.desks_requested}</strong>
          </div>
        </div>
      ) : (
        solar && (
          <>
            <div className="detail-grid">
              <div>
                <span>System capacity</span>
                <strong>{number(solar.system_kw_dc, 1)} kW DC</strong>
              </div>
              <div>
                <span>Proposed modules</span>
                <strong>{solar.panel_count} panels</strong>
              </div>
              <div>
                <span>Annual production</span>
                <strong>{number(solar.annual_kwh.expected)} kWh</strong>
                <small>{ranged(solar.annual_kwh)} kWh</small>
              </div>
              <div>
                <span>Self-consumption</span>
                <strong>
                  {solar.self_consumption_fraction == null
                    ? "Unknown"
                    : `${number(solar.self_consumption_fraction * 100)}%`}
                </strong>
              </div>
            </div>
            {roofs.map((roof) => (
              <p className="fineprint" key={roof.id}>
                {roof.id} · {number(roof.area_m2)} m² ·{" "}
                {number(roof.usable_area_m2)} m² usable · tilt{" "}
                {ranged(roof.tilt_deg)}° ·{" "}
                {roof.geometry_source.replaceAll("_", " ")}
              </p>
            ))}
            {[solar.electrical, solar.structural].map((flag) => (
              <p className="inline-note" key={flag.key}>
                <Info size={14} />
                <span>
                  <strong>
                    {flag.key.replaceAll(".", " ")} ·{" "}
                    {flag.status.replaceAll("_", " ")}
                  </strong>
                  <br />
                  {flag.message}
                </span>
              </p>
            ))}
          </>
        )
      )}
    </section>
  );
}
