import { readableText, warningText } from "../lib/homeowner-language";
import { useEffect, useState } from "react";
import { Compass, Info, Sun } from "lucide-react";
import type { RoofView, RunResult } from "../lib/types";
import { api, assetUrl } from "../lib/api";
import Warnings from "./Warnings";
import { number, polygon, ranged } from "../lib/format";
import { panelFacing } from "../lib/panel-orientation";
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
  const layoutMeasure = run.measures.find(
    (m) => m.measure_id === "LAYOUT" || m.layout,
  );
  const desks = layoutMeasure?.layout;
  const facing = layout ? null : panelFacing(run);
  const [roofView, setRoofView] = useState<RoofView | null>(null);
  const [roofError, setRoofError] = useState("");
  const [imageFailed, setImageFailed] = useState(false);
  const [showPanels, setShowPanels] = useState(true);
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
  const [selected, setSelected] = useState(0);
  useEffect(() => setSelected(0), [run.run_id]);
  const roofPolys = (roofView?.planes || roofs).map((r) =>
    polygon(r.polygon_wkt),
  );
  const panels = roofView?.panels || solar?.panels || [];
  const panelPolys = panels.map((p) => polygon(p.polygon_wkt));
  const ortho = roofView?.ortho;
  const bounds = ortho?.bounds;
  const validBounds =
    bounds &&
    [bounds.west, bounds.south, bounds.east, bounds.north].every(
      Number.isFinite,
    ) &&
    bounds.east > bounds.west &&
    bounds.north > bounds.south;
  const roofPoints = [...roofPolys, ...panelPolys].flat();
  // Use the real photo's width and centre the crop on the roof. A tall parcel
  // photograph otherwise collapses into a narrow strip inside a landscape map.
  const roofCentreY = roofPoints.length ? (Math.min(...roofPoints.map(p => p[1])) + Math.max(...roofPoints.map(p => p[1]))) / 2 : validBounds ? (bounds.south+bounds.north)/2 : 0;
  const imageHalfHeight = validBounds ? (bounds.east-bounds.west) * Math.cos(roofCentreY*Math.PI/180) * 1000/680/2 : 0;
  const imageCorners = validBounds ? [[bounds.west, roofCentreY-imageHalfHeight], [bounds.east, roofCentreY+imageHalfHeight]] : [];
  const canvasHeight = !layout && validBounds ? 1000 : 430;
  const points = !layout && validBounds ? imageCorners : layout
    ? candidates.map((p) => [p.x, p.y])
    : [
        ...roofPolys,
        ...panelPolys,
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
          {layout
            ? layoutMeasure && !layoutMeasure.applicable
              ? "Desk placement cannot be assessed"
              : "No workspace candidates yet"
            : "No roof geometry yet"}
        </h3>
        <p>
          {layout && layoutMeasure?.not_applicable_reason ? (
            layoutMeasure.not_applicable_reason
          ) : (
            <>
              The analysis will provide{" "}
              {layout
                ? "candidate workspace positions"
                : "roof planes and panel placements"}{" "}
              when available for this property.
            </>
          )}
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
    (layout ? 510 : 680) / ((maxX - minX) * longitudeScale || 1),
    (layout ? 290 : canvasHeight) / (maxY - minY || 1),
  );
  const xy = (p: number[]) => [
    340 + (p[0] - (minX + maxX) / 2) * longitudeScale * scale,
    canvasHeight / 2 - (p[1] - (minY + maxY) / 2) * scale,
  ];
  const pts = (poly: number[][]) => poly.map((p) => xy(p).join(",")).join(" ");
  const current = candidates[selected];
  const positions = candidates.map((point, i) => ({ point, i }));
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
            {layout ? "Explore your workspace." : "Your roof, clearly explained."}
          </h2>
        </div>
        <Compass size={26} />
      </div>
      <p className="section-description">
        {layout
          ? "Select a position to explore daylight calculated from room geometry and a sky model. These comparisons are exploratory and have not been validated against measurements. They do not establish comfort or a best desk position."
          : "Explore your aerial photograph and the estimated panel layout. Switch the overlays on or off to see the roof underneath. This is an initial proposal, not an installation drawing."}
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
          <span>
            {positions.length} positions · no ranking
          </span>
          <label>
            Inspect position
            <select
              value={selected}
              onChange={(event) => setSelected(Number(event.target.value))}
            >
              {positions.map(({ point, i }) => (
                <option key={i} value={i}>
                  Position {i + 1} · {point.room_id.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      {roofError && (
        <p className="inline-note">
          The aerial view could not be loaded. Showing the roof outlines saved with this audit instead.
        </p>
      )}
      {ortho && (
        <p className="inline-note">
          {ortho.bounds_source === "parcel_bbox"
            ? "Approximate aerial alignment using the parcel boundary."
            : "Aerial alignment estimated from the image outlines."}{" "}
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
      <div className={`geometry-canvas ${layout ? "" : "roof-photo-canvas"}`}>
        <svg
          viewBox={`0 0 680 ${canvasHeight}`}
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
          <rect width="680" height={canvasHeight} fill="#e8eddf" />
          <rect width="680" height={canvasHeight} fill="url(#geo-grid)" />
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
                  aria-label={`Position ${i + 1}, ${point.room_id.replaceAll("_", " ")}`}
                  aria-pressed={selected === i}
                  onClick={() => setSelected(i)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelected(i);
                    }
                  }}
                >
                  <title>{`Position ${i + 1}, ${point.room_id.replaceAll("_", " ")}`}</title>
                  <circle
                    cx={x}
                    cy={y}
                    r={selected === i ? 28 : 20}
                    fill="#b6c8a8"
                    opacity={0.7}
                  />
                  <rect
                    x={x - 12}
                    y={y - 8}
                    width="24"
                    height="16"
                    rx="3"
                    fill={selected === i ? "#174b35" : "#486653"}
                  />
                  {selected === i && <text
                      x={x}
                      y={y + 4}
                      textAnchor="middle"
                      fill="white"
                      fontSize="16"
                    >
                      {i + 1}
                  </text>}
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
            </>
          )}
          <path
            d="M626 84V46m-6 8 6-8 6 8"
            stroke="#64735d"
            fill="none"
            strokeWidth="2"
          />
          <text x="626" y="37" textAnchor="middle" fontSize="30" fill="#344c3d">
            {layout ? "+y" : "N"}
          </text>

        </svg>
      </div>
      <p className="fineprint">{layout ? "Exploratory positions in the model, not a measured floor plan." : "Aerial survey with estimated outlines. Image alignment is approximate; verify dimensions before installation."}</p>
      {facing && showPanels && (
        <p className="section-description roof-facing">
          The proposed panels face {facing.label} (
          {Math.round(facing.azimuthDeg)}° from north; north is at the top of
          the map). An installer should confirm the panel position and expected
          sunlight before installation.
        </p>
      )}
      {!layout && roofs.some(r => r.geometry_source === "vexcel_parametric") && (
        <p className="fineprint">Roof slope and sections are estimated from the aerial outline and roof shape. An installer should confirm the boundary, slope, clearances and obstructions before installation.</p>
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
        <div className="detail-grid workspace-details">
          <div>
            <span>Position {selected + 1}</span>
            <strong>
              {current.room_id.replaceAll("_", " ")}
            </strong>
          </div>
          <div>
            <span>Modelled daylight at 300 lux</span>
            <strong>
              {number(current.daylight * 100, 1)}% of occupied hours
            </strong>
            <small>Calculated from room geometry and a sky model; not measured.</small>
          </div>
          {current.daylight_factor != null && Number.isFinite(current.daylight_factor) && (
            <div>
              <span>Modelled indoor daylight relative to outdoors</span>
              <strong>{number(current.daylight_factor, 1)}%</strong>
              <small>Under the model’s overcast sky; not a measurement.</small>
            </div>
          )}
          {current.direct_sun_hours != null && Number.isFinite(current.direct_sun_hours) && (
            <div>
              <span>Modelled time with direct sun in view</span>
              <strong>{number(current.direct_sun_hours)} occupied hours per year</strong>
            </div>
          )}
          {current.view_azimuth_deg != null && Number.isFinite(current.view_azimuth_deg) && (
            <div>
              <span>Direction used for this comparison</span>
              <strong>{number(current.view_azimuth_deg)}° clockwise from north</strong>
            </div>
          )}
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
                <span>Solar energy used in the building</span>
                <strong>
                  {solar.self_consumption_fraction == null
                    ? "Unknown"
                    : `${number(solar.self_consumption_fraction * 100)}%`}
                </strong>
              </div>
            </div>
            {roofs.map((roof, i) => (
              <p className="fineprint" key={roof.id}>
                Roof section {i + 1} · {number(roof.area_m2)} m² ·{" "}
                {number(roof.usable_area_m2)} m² usable · tilt{" "}
                {ranged(roof.tilt_deg)}° ·{" "}
                {readableText(roof.geometry_source)}
              </p>
            ))}
            {[solar.electrical, solar.structural].map((flag) => (
              <p className="inline-note" key={flag.key}>
                <Info size={14} />
                <span>
                  <strong>
                    {flag === solar.electrical ? "Electrical review" : "Structural review"} ·{" "}
                    {readableText(flag.status)}
                  </strong>
                  <br />
                  {warningText(flag.message)}
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
