import { useEffect, useRef, useState } from "react";
import "leaflet/dist/leaflet.css";
import "./roi-map.css";
import { request } from "../lib/api";
import { paybackBreaks, paybackColor, ROI_COLORS, type RoiMapData, type RoiRow } from "../lib/roi-map";
import RoiTable, { usd } from "./RoiTable";

const CITIES = [
  { id: "la", label: "Los Angeles" },
  { id: "houston", label: "Houston" },
] as const;

function popup(r: RoiRow): string {
  const rate = r.rate_source === "zip_utility" ? r.utility : "state average rate (no utility listed for this zip)";
  return (
    `<strong>${r.zip}</strong><br/>Estimated payback: ${r.payback_years ?? "none"} years<br/>` +
    `Saves about ${usd(r.annual_savings_usd)} a year<br/>Cost after incentives: ${usd(r.net_upfront_usd)}<br/>` +
    `Rate used: $${r.rate_usd_per_kwh.toFixed(2)} per kWh (${rate})<br/><em>Estimate for a typical home, not an audit.</em>`
  );
}

export default function RoiMap() {
  const [city, setCity] = useState<"la" | "houston">("la");
  const [data, setData] = useState<RoiMapData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mapEl = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    request<RoiMapData>(`/roi-map?city=${city}`)
      .then((d) => live && setData(d))
      .catch(() => live && setError("The savings map could not be loaded. The backend may not be running."));
    return () => {
      live = false;
    };
  }, [city]);

  useEffect(() => {
    if (!data || !mapEl.current) return;
    let cancelled = false;
    let remove: (() => void) | undefined;
    const el = mapEl.current;
    import("leaflet").then(({ default: L }) => {
      if (cancelled) return;
      const map = L.map(el);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 15,
        attribution: "© OpenStreetMap contributors",
      }).addTo(map);
      const breaks = paybackBreaks(data.rows);
      const points = data.rows.map((r) => {
        L.circleMarker([r.lat, r.lon], {
          radius: 9,
          weight: 1,
          color: "#23372d",
          fillColor: paybackColor(r.payback_years, breaks),
          fillOpacity: 0.85,
        })
          .bindPopup(popup(r))
          .addTo(map);
        return [r.lat, r.lon] as [number, number];
      });
      if (points.length) map.fitBounds(points, { padding: [20, 20] });
      remove = () => map.remove();
    });
    return () => {
      cancelled = true;
      remove?.();
    };
  }, [data]);

  const breaks = data ? paybackBreaks(data.rows) : [];
  return (
    <section className="roi-map" aria-labelledby="roi-title">
      <h2 id="roi-title">Where does rooftop solar pay back fastest?</h2>
      <p className="roi-label">
        {data?.label ?? "Estimated payback of rooftop solar on a typical home. Not an audit of any building."}
      </p>
      <div className="roi-tabs" role="group" aria-label="City">
        {CITIES.map((c) => (
          <button key={c.id} type="button" aria-pressed={city === c.id} onClick={() => setCity(c.id)}>
            {c.label}
          </button>
        ))}
      </div>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p>Loading the map…</p>}
      {data && (
        <>
          <div
            ref={mapEl}
            className="roi-canvas"
            role="img"
            aria-label={`Map of estimated solar payback by zip code, ${data.name}`}
          />
          <ul className="roi-legend" aria-label="Colour key">
            {ROI_COLORS.map((c, i) => (
              <li key={c}>
                <span style={{ background: c }} aria-hidden="true" />
                {i === 0
                  ? `under ${breaks[0]} years`
                  : i === ROI_COLORS.length - 1
                    ? `${breaks[i - 1]} years or more`
                    : `${breaks[i - 1]} to ${breaks[i]} years`}
              </li>
            ))}
          </ul>
          <RoiTable rows={data.rows} />
          <h3>How this estimate is made</h3>
          <ul>
            {data.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
