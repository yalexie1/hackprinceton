import { MapPin } from "lucide-react";
import { useEffect, useState } from "react";
import type { PropertySummary } from "../lib/types";
import { api } from "../lib/api";
import {
  propertyObliques,
  type PropertyOblique,
} from "../lib/property-imagery";
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
  const [obliques, setObliques] = useState<PropertyOblique[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    setObliques([]);
    // This endpoint only reads cached imagery; browsing cards must not start an
    // audit or expose a sponsor API key to the client.
    void api
      .preview(
        property.sid,
        AbortSignal.any([controller.signal, AbortSignal.timeout(6000)]),
      )
      .then((preview) => {
        if (
          !controller.signal.aborted &&
          preview.available &&
          preview.sid === property.sid
        )
          setObliques(propertyObliques(preview.oblique_paths || {}));
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [property.sid]);
  return (
    <PropertyPreviewImage
      key={`${property.sid}:${obliques.map((image) => image.url).join(",")}`}
      property={property}
      allowListedLocation={allowListedLocation}
      obliques={obliques}
    />
  );
}

export function PropertyPreviewImage({
  property,
  allowListedLocation = false,
  obliques = [],
}: {
  property: PropertySummary;
  allowListedLocation?: boolean;
  obliques?: PropertyOblique[];
}) {
  const location =
    propertyLocation(property.sid) ||
    (allowListedLocation ? listedPropertyLocation(property) : null);
  const overhead =
    location && aerialImageUrl(location, property.segment === "commercial");
  const candidates = [
    ...obliques,
    ...(overhead ? [{ url: overhead, direction: null }] : []),
  ];
  const [imageIndex, setImageIndex] = useState(0);
  const image = candidates[imageIndex];
  const isOblique = Boolean(image?.direction);
  const failed = imageIndex > 0;
  return (
    <div className={`property-geospatial${isOblique ? " has-oblique" : ""}`}>
      {image ? (
        <>
          <img
            key={image.url}
            src={image.url}
            alt={
              isOblique
                ? `Side-angle aerial photo of ${property.name}, ${image.direction} view`
                : `Overhead aerial context for ${property.name}, centred on its ${location!.source === "scan" ? "scan-computed" : location!.source === "listing" ? "reported listing" : "street-address"} location`
            }
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            onError={() => setImageIndex((index) => index + 1)}
          />
          {!isOblique && (
            <>
              <span className="property-location-pin">
                <MapPin size={22} />
              </span>
              <span className="property-map-north">N ↑</span>
            </>
          )}
          <div className="property-map-footer">
            <span className="property-map-caption">
              {isOblique ? (
                `Side-angle aerial · ${image.direction} view`
              ) : (
                <>
                  Overhead view ·{" "}
                  {location!.source === "scan"
                    ? "scan location"
                    : location!.source === "listing"
                      ? "listing location"
                      : "address location"}
                </>
              )}
            </span>
            <span className="property-map-credit">
              {isOblique ? "Vexcel aerial imagery" : aerialAttribution}
            </span>
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
