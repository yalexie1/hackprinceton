import {
  ArrowRight,
  Building2,
  Home,
  Layers3,
  MapPin,
  Search,
  SlidersHorizontal,
  ShieldCheck,
} from "lucide-react";
import type { PropertySummary } from "../lib/types";
import PropertyPreview from "./PropertyPreview";
import HouseViewer from "./HouseViewer";
import { fixtureSource, demoShowcaseRun } from "../lib/fixtures";
import { useMemo } from "react";
import { propertyReadiness, sortByReadiness } from "../lib/property-readiness";
export default function Find({
  properties,
  query,
  setQuery,
  segment,
  setSegment,
  loading,
  demo,
  onSelect,
}: {
  properties: PropertySummary[];
  query: string;
  setQuery: (q: string) => void;
  segment: string;
  setSegment: (v: string) => void;
  loading: boolean;
  demo: boolean;
  onSelect: (p: PropertySummary) => void;
}) {
  const showcase = useMemo(() => demoShowcaseRun(), []);
  const orderedProperties = useMemo(
    () => sortByReadiness(properties),
    [properties],
  );
  return (
    <>
      <section className="find-hero">
        <div className="perspective-heading">
          <div className="hero-copy">
            <span className="eyebrow">
              <span className="status-dot" />A CLEARER VIEW. A LIGHTER
              FOOTPRINT.
            </span>
            <h1>
              A new perspective
              <br />
              <em>on your building.</em>
            </h1>
          </div>
          <div className="hero-intro">
            <p>
              See where your building uses energy, compare improvements and
              understand what they could cost and save.
            </p>
            <a className="hero-property-link" href="#your-properties">
              Find your property <ArrowRight size={16} />
            </a>
          </div>
        </div>
        <HouseViewer run={showcase} />
        <div className="perspective-strip">
          <span>
            <span className="strip-number">01 /</span> Understand your space
          </span>
          <span>
            <span className="strip-number">02 /</span> Discover what’s possible
          </span>
          <span>
            <span className="strip-number">03 /</span> Make a plan that fits
          </span>
        </div>
      </section>
      <div className="section-heading find-heading" id="your-properties">
        <div>
          <span className="eyebrow">START WITH A PROPERTY</span>
          <h2>Choose a home or office.</h2>
        </div>
        <span className="coverage">
          <span className="status-dot" />
          Los Angeles &amp; Houston
        </span>
      </div>
      <div className="search-toolbar">
        <label className="search-box">
          <Search size={19} />
          <input
            aria-label="Search properties"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by property name, address, or city…"
          />
          {loading && <span className="loading-dot" />}
        </label>
        <label className="filter-select">
          <SlidersHorizontal size={16} />
          <select
            aria-label="Property type"
            value={segment}
            onChange={(e) => setSegment(e.target.value)}
          >
            <option value="">All properties</option>
            <option value="residential">Residential</option>
            <option value="commercial">Commercial</option>
          </select>
        </label>
      </div>
      <div className="property-order-note">
        <ShieldCheck size={23} />
        <div>
          <strong>Most measured evidence first</strong>
          <p>
            Properties with more measured inputs come first. This is a guide to
            audit readiness, not a guarantee of savings or accuracy.
          </p>
          <details>
            <summary>How this order is determined</summary>
            <p>
              The reviewed order is the house, Culver, then Houston. The house
              has measured walls, window openings and room outlines. Both
              offices rely on an aerial footprint and image-based window
              estimates; Culver has more scan views available. Unassessed
              properties follow the reviewed ones. Review the actual audit’s
              assumptions, weather source and utility-bill calibration before
              relying on an estimate.
            </p>
          </details>
        </div>
      </div>
      <div className="property-grid">
        {orderedProperties.map((p, i) => (
          <button
            className="property-card"
            key={p.sid}
            aria-label={`Explore ${p.name}${p.city ? ` in ${p.city}` : ""}`}
            onClick={() => onSelect(p)}
          >
            <div className="property-image" aria-hidden="true">
              <PropertyPreview property={p} allowListedLocation={!demo} />
              <span className="property-type">
                {p.segment === "commercial" ? (
                  <Building2 size={13} />
                ) : (
                  <Home size={13} />
                )}{" "}
                {p.use_type.replaceAll("_", " ")}
              </span>
              <span className="property-index">
                {String(i + 1).padStart(2, "0")}
              </span>
            </div>
            <div className="property-copy">
              <div>
                <h3>{p.name}</h3>
                <ArrowRight size={20} />
              </div>
              <p>
                <MapPin size={14} />
                {[p.city, p.state].filter(Boolean).join(", ") ||
                  p.address ||
                  "Address unavailable"}
              </p>
              <div className="property-meta">
                <span>
                  {p.room_count > 0
                    ? `${p.room_count} rooms`
                    : "Room count not provided"}
                </span>
                <span>
                  {p.pano_count
                    ? `${p.pano_count} panoramic views`
                    : "No panoramic views listed"}
                </span>
                {p.pano_count > 0 && (
                  <span>
                    {p.has_splat ? "3D scan available" : "Interior scan"}
                  </span>
                )}
              </div>
              <div className="property-readiness">
                <strong>
                  {propertyReadiness(p.sid)?.label ||
                    "Evidence not assessed yet"}
                </strong>
                <p>
                  {propertyReadiness(p.sid)?.evidence ||
                    "This property has not had the same data-coverage review as the three demonstration properties."}
                </p>
                <span>
                  {propertyReadiness(p.sid)?.limitation ||
                    "An audit must establish which inputs are measured and which are estimated."}
                </span>
              </div>
              {demo && (
                <small className="fixture-source">{fixtureSource(p.sid)}</small>
              )}
              <span className="property-action">
                Explore this property <ArrowRight size={14} />
              </span>
            </div>
          </button>
        ))}
      </div>
      {properties.length > 0 && (
        <p className="property-imagery-note">
          Aerial images show geospatial context around a scan, street-address or
          reported listing location, not a surveyed property boundary. Imagery
          may predate current conditions.{" "}
          <a
            href="https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer"
            target="_blank"
            rel="noreferrer"
          >
            Imagery source &amp; attribution
          </a>
          {" · "}
          <a
            href="https://github.com/yalexie1/hackprinceton/blob/main/specs/data-integration.md#32-geocoordinates--this-answers-the-specs-top-risk"
            target="_blank"
            rel="noreferrer"
          >
            Scan-location sources
          </a>
          {" · "}
          <a
            href="https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address=3000%20S%20Robertson%20Blvd%2C%20Los%20Angeles%2C%20CA&amp;benchmark=Public_AR_Current&amp;format=json"
            target="_blank"
            rel="noreferrer"
          >
            Culver address location
          </a>
        </p>
      )}
      {!loading && properties.length === 0 && (
        <div className="empty-state">
          <Search />
          <h3>No matching properties</h3>
          <p>Try a different name or city, or clear the property filter.</p>
          <button
            className="secondary-button"
            onClick={() => {
              setQuery("");
              setSegment("");
            }}
          >
            Clear filters
          </button>
        </div>
      )}
      <div className="source-footer">
        <div>
          <Layers3 size={18} />
          <span>Three perspectives. One clearer picture.</span>
        </div>
        <p>
          Matterport <span>·</span> Vexcel <span>·</span> CoStar
        </p>
        <small>
          {demo
            ? "Demo properties and results are illustrative. Connect to live mode for sponsor data."
            : "Data availability varies by property. Provenance is shown in the audit."}
        </small>
      </div>
    </>
  );
}
