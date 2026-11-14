import {
  ArrowRight,
  Building2,
  Home,
  Layers3,
  MapPin,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import type { PropertySummary } from "../lib/types";
import BuildingArt from "./BuildingArt";
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
  return (
    <>
      <section className="find-hero">
        <div className="hero-copy">
          <span className="eyebrow">
            <span className="status-dot" />
            BUILDING INTELLIGENCE, BETTER POSSIBILITIES
          </span>
          <h1>
            Less energy.
            <br />
            <em>More possibility.</em>
          </h1>
          <p>
            See what your building could become. A practical energy plan,
            grounded in your space and shaped around your budget.
          </p>
          <div className="hero-footnote">
            <Layers3 size={17} />
            Inside, outside, and everything in between.
          </div>
        </div>
        <div className="hero-art">
          <BuildingArt />
          <span className="floating-card">
            <span className="mini-sun">☀</span>
            <span>
              A brighter outlook
              <small>Understand the potential in your property.</small>
            </span>
          </span>
        </div>
      </section>
      <div className="section-heading find-heading">
        <div>
          <span className="eyebrow">START WITH YOUR SPACE</span>
          <h2>Find your next opportunity.</h2>
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
      <div className="property-grid">
        {properties.map((p, i) => (
          <button
            className="property-card"
            key={p.sid}
            onClick={() => onSelect(p)}
          >
            <div className="property-image">
              <BuildingArt compact office={p.segment === "commercial"} />
              <span className="property-type">
                {p.segment === "commercial" ? (
                  <Building2 size={13} />
                ) : (
                  <Home size={13} />
                )}{" "}
                {p.use_type.replaceAll("_", " ")}
              </span>
              <span className="property-index">0{i + 1}</span>
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
                <span>{p.room_count} rooms</span>
                <span>{p.pano_count} panoramas</span>
                <span>{p.has_splat ? "Aerial splat" : "Interior scan"}</span>
              </div>
              <span className="property-action">
                Explore this property <ArrowRight size={14} />
              </span>
            </div>
          </button>
        ))}
      </div>
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
