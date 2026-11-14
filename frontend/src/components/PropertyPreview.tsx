import { MapPin } from "lucide-react";
import { useState } from "react";
import type { PropertySummary } from "../lib/types";
import {
  aerialAttribution,
  aerialImageUrl,
  propertyLocation,
  listedPropertyLocation,
} from "../lib/property-geospatial";
import "./property-discovery.css";

export default function PropertyPreview({
  property,
  allowListedLocation = false,
}: {
  property: PropertySummary;
  allowListedLocation?: boolean;
}) {
  const location =
    propertyLocation(property.sid) ||
    (allowListedLocation ? listedPropertyLocation(property) : null);
  const url =
    location && aerialImageUrl(location, property.segment === "commercial");
  const [failed, setFailed] = useState(false);
  return (
    <div className="property-geospatial">
      {url && !failed ? (
        <>
          <img
            src={url}
            alt={`Aerial context for ${property.name}, centred on its ${location!.source === "scan" ? "verified scan" : location!.source === "listing" ? "reported listing" : "street-address"} location`}
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            onError={() => setFailed(true)}
          />
          <span className="property-location-pin">
            <MapPin size={22} />
          </span>
          <span className="property-map-north">N ↑</span>
          <div className="property-map-footer">
            <span className="property-map-caption">
              Aerial view ·{" "}
              {location!.source === "scan"
                ? "scan location"
                : location!.source === "listing"
                  ? "listing location"
                  : "address location"}
            </span>
            <span className="property-map-credit">{aerialAttribution}</span>
          </div>
        </>
      ) : (
        <div className="property-map-unavailable">
          <MapPin size={27} />
          <strong>
            {failed ? "Aerial image unavailable" : "Location not verified yet"}
          </strong>
          <span>
            {[property.address, property.city, property.state]
              .filter(Boolean)
              .join(", ") || property.name}
          </span>
        </div>
      )}
    </div>
  );
}
