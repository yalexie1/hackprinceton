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
import PropertyPreview from "./PropertyPreview";
import HouseViewer from "./HouseViewer";
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
        <HouseViewer />
        <p className="hero-data-note">
          Choose a property below to see its estimated costs and savings.
        </p>
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
      {/* The "Most measured evidence first" card was removed on request. The ordering it
          described is unchanged - `orderedProperties` still puts the reviewed properties first -
          and each card still carries its own readiness line, which is where a reader meets the
          measured-versus-estimated distinction now. */}
      <div className="property-grid">
        {orderedProperties.map((p, i) => (
          // The card is an article, not a button: its preview holds its own Map / Aerial /
          // 3D model buttons, and a button inside a button is invalid HTML. The whole card
          // stays clickable with a mouse; keyboard and screen-reader users get the real
          // button on the property name.
          <article
            className="property-card"
            key={p.sid}
            onClick={() => onSelect(p)}
          >
            <div className="property-image">
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
                <h3>
                  <button
                    type="button"
                    className="property-open"
                    aria-label={`Explore ${p.name}${p.city ? ` in ${p.city}` : ""}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      onSelect(p);
                    }}
                  >
                    {p.name}
                  </button>
                </h3>
                <ArrowRight size={20} aria-hidden="true" />
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
              <span className="property-action">
                Explore this property <ArrowRight size={14} aria-hidden="true" />
              </span>
            </div>
          </article>
        ))}
      </div>
      {properties.length > 0 && (
        /* The explanatory prose was removed on request. The attribution links stay: the overhead
           tiles are licensed imagery whose credit is a condition of use, and the per-card credit
           line carries the same attribution beside every map. */
        <p className="property-imagery-note">
          <a
            href="https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer"
            target="_blank"
            rel="noreferrer"
          >
            Overhead imagery &amp; attribution
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
            href="https://github.com/yalexie1/hackprinceton/issues/1#issuecomment-6883308835"
            target="_blank"
            rel="noreferrer"
          >
            Live scan-location verification
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
          Matterport <span>·</span> Vexcel <span>·</span> CoStar <span>·</span>{" "}
          LangChain
        </p>
        <small>
          Your plan uses the available building records. Each estimate explains
          what was measured and what still needs checking.
        </small>
      </div>
    </>
  );
}
