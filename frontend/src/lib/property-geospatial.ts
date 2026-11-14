import type { PropertySummary } from "./types";

export interface PropertyLocation {
  lat: number;
  lon: number;
  source: "scan" | "address" | "listing";
  citation: string;
}

// Verified scalars, never the invented office coordinates in the example bundles.
const locations: Record<string, PropertyLocation> = {
  zvKHR9DHNjJ: {
    lat: 34.093491667,
    lon: -118.3171,
    source: "scan",
    citation:
      "https://github.com/yalexie1/hackprinceton/blob/main/specs/data-integration.md#32-geocoordinates--this-answers-the-specs-top-risk",
  },
  ZSPaQbkGcJJ: {
    lat: 34.032445385978065,
    lon: -118.38941475137618,
    source: "scan",
    citation:
      "https://github.com/yalexie1/hackprinceton/issues/1#issuecomment-6883308835",
  },
  L3266YcPPvd: {
    lat: 29.746027599,
    lon: -95.457545726,
    source: "scan",
    citation:
      "https://github.com/yalexie1/hackprinceton/blob/main/specs/data-integration.md",
  },
};

export function propertyLocation(sid: string) {
  return locations[sid] || null;
}

export function listedPropertyLocation(
  property: PropertySummary,
): PropertyLocation | null {
  if (
    typeof property.lat !== "number" ||
    typeof property.lon !== "number" ||
    !Number.isFinite(property.lat) ||
    !Number.isFinite(property.lon) ||
    Math.abs(property.lat) > 85.05112878 ||
    Math.abs(property.lon) > 180
  )
    return null;
  return {
    lat: property.lat,
    lon: property.lon,
    source: "listing",
    citation: `/api/properties/${encodeURIComponent(property.sid)}`,
  };
}

export const aerialAttribution =
  "Esri, Vantor, Earthstar Geographics, GIS User Community";
export const aerialService =
  "https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer";

export function aerialImageUrl(
  location: PropertyLocation,
  commercial: boolean,
) {
  if (
    !Number.isFinite(location.lat) ||
    !Number.isFinite(location.lon) ||
    Math.abs(location.lat) > 85.05112878 ||
    Math.abs(location.lon) > 180
  )
    return null;
  const radius = 6378137;
  const x = (radius * location.lon * Math.PI) / 180;
  const y =
    radius * Math.log(Math.tan(Math.PI / 4 + (location.lat * Math.PI) / 360));
  const width = commercial ? 300 : 120;
  const height = (width * 400) / 640;
  const query = new URLSearchParams({
    bbox: [x - width / 2, y - height / 2, x + width / 2, y + height / 2].join(
      ",",
    ),
    bboxSR: "3857",
    imageSR: "3857",
    size: "640,400",
    format: "jpg",
    f: "image",
  });
  return `${aerialService}/export?${query}`;
}
