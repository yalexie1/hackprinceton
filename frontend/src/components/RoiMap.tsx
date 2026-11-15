import { readableText } from "../lib/homeowner-language";
import { useEffect, useRef, useState } from "react";
import "leaflet/dist/leaflet.css";
import "./roi-map.css";
import { request } from "../lib/api";
import { paybackBreaks, paybackColor, ROI_COLORS, type RoiMapData, type RoiRow } from "../lib/roi-map";
import RoiTable, { usd } from "./RoiTable";

function assumptionText(value: string) {
  if (value.startsWith("6 kW DC")) return "A 6-kilowatt rooftop panel system, tilted 20 degrees and facing south, with 14% system losses. Sunlight estimates come from the European Commission’s PVGIS solar model and ERA5 weather data.";
  if (value.startsWith("cost from the finance module")) return "Installation cost uses the same residential rooftop-solar cost estimate as the energy plan. No incentives are applied in this 2026 comparison. Financing, panel ageing and future energy-price increases are not included.";
  const text = readableText(value).replace(/retail rate/gi,"electricity purchase price").replace(/zip-level/gi,"ZIP-code").replace(/\bzip\b(?!-code)/gi,"ZIP code").replace(/simple payback/g,"time to recover the installation cost").replace(/exports/g,"surplus electricity sent to the grid").replace(/surplus electricity sent to the grid earn/g,"surplus electricity sent to the grid earns");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const CITIES = [
  { id: "la", label: "Los Angeles" },
  { id: "houston", label: "Houston" },
] as const;

function popup(r: RoiRow): string {
  const rate = r.rate_source === "zip_utility" ? r.utility : "State average rate (no utility listed for this ZIP code)";
  return (
    `<strong>${r.zip}</strong><br/>${r.payback_years === null ? "No payback" : `Estimated payback: ${r.payback_years} years`}<br/>` +
    `Saves about ${usd(r.annual_savings_usd)} a year<br/>Cost: ${usd(r.net_upfront_usd)} (no incentives applied)<br/>` +
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
      .catch(() => live && setError("The savings map could not be loaded. Please check the connection and try again."));
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
      <span className="eyebrow">SOLAR COMPARISON</span>
      <h2 id="roi-title">Where does rooftop solar pay back fastest?</h2>
      <p className="roi-label">
        {readableText(data?.label ?? "Estimated payback of rooftop solar on a typical home. Not an audit of any building.")}
      </p>
      <p className="section-description">Payback is the estimated time for electricity savings to cover the installation cost. Compare locations below; each estimate is for a typical home, not an audit of your property.</p>
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
          <h3>Reading the map</h3>
          <ul className="roi-legend" aria-label="Colour key">
            {ROI_COLORS.map((c, i) => (
              <li key={c}>
                <span style={{ background: c }} aria-hidden="true" />
                {i === 0
                  ? `Under ${breaks[0]} years`
                  : i === ROI_COLORS.length - 1
                    ? `${breaks[i - 1]} years or more`
                    : `${breaks[i - 1]} to ${breaks[i]} years`}
              </li>
            ))}
          </ul>
          <h3>Compare ZIP codes</h3>
          <div className="roi-table-scroll"><RoiTable rows={data.rows} /></div>
          <h3>How this estimate is made</h3>
          <ul>
            {data.assumptions.map((a) => (
              <li key={a}>{assumptionText(a)}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
