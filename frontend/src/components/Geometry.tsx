import { useEffect, useState } from "react";
import { Compass, Info, Sun } from "lucide-react";
import type { RoofView, RunResult } from "../lib/types";
import { api, assetUrl } from "../lib/api";
import Warnings from "./Warnings";
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
  const solar =
    run.plan?.selected.find((item) => item.measure.solar)?.measure.solar ||
    run.plan?.financeable.find((m) => m.solar)?.solar ||
    run.measures.find((m) => m.solar)?.solar;
  const desks = run.measures.find((m) => m.layout)?.layout;
  const [roofView, setRoofView] = useState<RoofView | null>(null);
  const [roofError, setRoofError] = useState("");
  const [imageFailed, setImageFailed] = useState(false);
  const [showDetections, setShowDetections] = useState(false);
  const [showPanels, setShowPanels] = useState(true);
  const [allPositions, setAllPositions] = useState(false);
  useEffect(() => {
    setRoofView(null);
    setRoofError("");
    setImageFailed(false);
    if (demo || layout) return;
    const abort = new AbortController();
    void api
      .roof(run.run_id, abort.signal)
      .then((data) => {
        if (data.srid !== 4326)
          throw new Error("Unsupported roof coordinate system.");
        if (!abort.signal.aborted) setRoofView(data);
      })
      .catch((error) => {
        if (!abort.signal.aborted)
          setRoofError(
            error instanceof Error
              ? error.message
              : "Roof data is unavailable.",
          );
      });
    return () => abort.abort();
  }, [run, demo, layout]);
  const roofs = run.building_model?.roof_planes || [];
  const candidates = desks?.candidates || [];
  const [selected, setSelected] = useState(() =>
    Math.max(
      0,
      candidates.findIndex((candidate) => candidate.recommended),
    ),
  );
  const roofPolys = (roofView?.planes || roofs).map((r) =>
    polygon(r.polygon_wkt),
  );
  const panels = roofView?.panels || solar?.panels || [];
  const panelPolys = panels.map((p) => polygon(p.polygon_wkt));
  const detections = roofView?.detections || [];
  const ortho = roofView?.ortho;
  const bounds = ortho?.bounds;
  const validBounds =
    bounds &&
    [bounds.west, bounds.south, bounds.east, bounds.north].every(
      Number.isFinite,
    ) &&
    bounds.east > bounds.west &&
    bounds.north > bounds.south;
  const points = layout
    ? candidates.map((p) => [p.x, p.y])
    : [
        ...roofPolys,
        ...panelPolys,
        ...detections.map((d) => polygon(d.bbox_wkt)),
        ...(validBounds
          ? [
              [
                [bounds.west, bounds.south],
                [bounds.east, bounds.north],
              ],
            ]
          : []),
      ].flat();
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
  const longitudeScale =
    !layout && roofView ? Math.cos((((minY + maxY) / 2) * Math.PI) / 180) : 1;
  const scale = Math.min(
    510 / ((maxX - minX) * longitudeScale || 1),
    290 / (maxY - minY || 1),
  );
  const xy = (p: number[]) => [
    85 + (p[0] - minX) * longitudeScale * scale,
    365 - (p[1] - minY) * scale,
  ];
  const pts = (poly: number[][]) => poly.map((p) => xy(p).join(",")).join(" ");
  const current = candidates[selected];
  const hasRecommended = candidates.some((point) => point.recommended);
  const positions = candidates
    .map((point, i) => ({ point, i }))
    .filter(
      ({ point }) => allPositions || !hasRecommended || point.recommended,
    );
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
      {!layout && (
        <div className="roof-layer-controls">
          <label>
            <input
              type="checkbox"
              checked={showPanels}
              onChange={(event) => setShowPanels(event.target.checked)}
            />
            Solar proposal
          </label>
          {detections.length > 0 && (
            <label>
              <input
                type="checkbox"
                checked={showDetections}
                onChange={(event) => setShowDetections(event.target.checked)}
              />
              Detection boxes
            </label>
          )}
          {roofView && (
            <span>
              {roofView.panels_selected
                ? "Solar is included in your plan"
                : panels.length
                  ? "Solar is an evaluated option, outside the selected plan"
                  : "No panel proposal"}
            </span>
          )}
        </div>
      )}
      {layout && (
        <div className="roof-layer-controls">
          <label>
            Workspace positions
            <select
              value={allPositions ? "all" : "recommended"}
              onChange={(event) => {
                const next = event.target.value === "all";
                setAllPositions(next);
                if (
                  !next &&
                  hasRecommended &&
                  !candidates[selected]?.recommended
                )
                  setSelected(
                    candidates.findIndex((point) => point.recommended),
                  );
              }}
            >
              <option value="recommended">
                {hasRecommended
                  ? "Recommended positions"
                  : "Available positions"}
              </option>
              <option value="all">All analysed positions</option>
            </select>
          </label>
          <span>
            {positions.length} shown of {candidates.length} analysed
          </span>
          <label>
            Inspect position
            <select
              value={selected}
              onChange={(event) => setSelected(Number(event.target.value))}
            >
              {positions.map(({ point, i }) => (
                <option key={i} value={i}>
                  Position {i + 1} · {point.room_id.replaceAll("_", " ")} ·
                  score {number(point.score, 2)}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      {roofError && (
        <p className="inline-note">
          Aerial view unavailable: {roofError} Showing the run’s supplied
          geometry.
        </p>
      )}
      {ortho && (
        <p className="inline-note">
          {ortho.bounds_source === "parcel_bbox"
            ? "Approximate aerial alignment using the parcel boundary."
            : "Aerial alignment recovered from the detection boxes."}{" "}
          {(!ortho.image_available || imageFailed) &&
            "The aerial image is not cached or could not be loaded; only the supplied geometry is shown."}
        </p>
      )}
      {!layout && !demo && !roofError && roofView && !ortho && (
        <p className="inline-note">
          No aerial image was supplied for this run. Only the supplied roof
          geometry is shown.
        </p>
      )}
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
          {!layout && validBounds && ortho?.image_available && !imageFailed && (
            <image
              href={assetUrl(ortho.path)}
              x={xy([bounds.west, bounds.north])[0]}
              y={xy([bounds.west, bounds.north])[1]}
              width={(bounds.east - bounds.west) * longitudeScale * scale}
              height={(bounds.north - bounds.south) * scale}
              preserveAspectRatio="none"
              onError={() => setImageFailed(true)}
            >
              <title>Aerial image, north at the top</title>
            </image>
          )}
          {layout ? (
            positions.map(({ point, i }) => {
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
                  <title>{`Position ${i + 1}, ${point.room_id}: score ${number(point.score, 2)}, ${point.recommended ? "recommended" : "alternative"}`}</title>
                  <circle
                    cx={x}
                    cy={y}
                    r={point.recommended || selected === i ? 28 : 6}
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
                  {(point.recommended || selected === i) && (
                    <text
                      x={x}
                      y={y + 4}
                      textAnchor="middle"
                      fill="white"
                      fontSize="16"
                    >
                      {i + 1}
                    </text>
                  )}
                </g>
              );
            })
          ) : (
            <>
              {roofPolys.map(
                (p, i) =>
                  p.length > 0 && (
                    <polygon
                      key={i}
                      points={pts(p)}
                      fill={
                        ortho?.image_available && !imageFailed
                          ? "#c6cebb66"
                          : "#c6cebb"
                      }
                      stroke="#7b8b6d"
                      strokeWidth="2"
                    />
                  ),
              )}
              {showPanels &&
                panelPolys.map(
                  (p, i) =>
                    p.length > 0 && (
                      <polygon
                        key={i}
                        points={pts(p)}
                        fill="#315768"
                        stroke="#91acb2"
                        strokeWidth="1.5"
                      >
                        <title>{`Panel ${i + 1}: ${number(panels[i].annual_kwh)} kWh / year, shading loss ${number(panels[i].shading_loss_fraction * 100, 1)}%`}</title>
                      </polygon>
                    ),
                )}
              {showDetections &&
                detections.map((detection, i) => {
                  const outline = polygon(
                    detection.mask_wkt || detection.bbox_wkt,
                  );
                  return outline.length ? (
                    <polygon
                      key={`detection-${i}`}
                      points={pts(outline)}
                      fill="none"
                      stroke="#b35b20"
                      strokeWidth="2"
                      strokeDasharray="6 4"
                    >
                      <title>{`${detection.label}: ${number(detection.confidence * 100)}% confidence. ${detection.mask_area_m2 == null ? "Mask area unavailable." : `Mask area ${number(detection.mask_area_m2, 1)} m².`} Box outlines are not mask footprints.`}</title>
                    </polygon>
                  ) : null;
                })}
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
      {!layout && detections.length > 0 && (
        <details className="roof-detections">
          <summary>Inspect {detections.length} roof detections</summary>
          <p>
            Boxes locate findings; their area is not the detected roof area.
            Each mask area below comes directly from the data source;
            overlapping masks are not added together.
          </p>
          <ul>
            {detections.map((detection, i) => (
              <li key={i}>
                {detection.label} · {number(detection.confidence * 100)}%
                confidence ·{" "}
                {detection.mask_area_m2 == null
                  ? "mask area unavailable"
                  : `${number(detection.mask_area_m2, 1)} m² mask area`}
              </li>
            ))}
          </ul>
        </details>
      )}
      {unsupported && (
        <p className="inline-note">
          <Info size={14} />
          Some positions are unavailable or use an unsupported geometry type.
          Only supplied polygons are drawn; panel counts and energy estimates
          remain available below.
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
            <span>Daylight autonomy at 300 lux</span>
            <strong>
              {number(current.daylight * 100, 1)}% of occupied hours
            </strong>
          </div>
          <div>
            <span>Glare risk</span>
            <strong>
              {number(current.glare_risk * 100, 1)}% of occupied hours
            </strong>
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
      {layout && (
        <Warnings
          warnings={[...(desks?.warnings || []), ...(current?.warnings || [])]}
        />
      )}
    </section>
  );
}
