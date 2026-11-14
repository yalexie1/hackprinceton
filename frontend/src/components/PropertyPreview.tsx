import { useEffect, useState } from "react";
import type { PropertySummary } from "../lib/types";
import {
  loadPropertyImagery,
  type PropertyImagery,
  type PropertyOblique,
} from "../lib/property-imagery";
import PropertyViews from "./PropertyViews";
import "./property-discovery.css";

/**
 * The imagery on a property card, with the view the reader chooses.
 *
 * The rendering lives in `PropertyViews`; this fetches what is available and hands it over. The
 * read is cached-only: browsing cards must not start an audit or expose a sponsor API key to the
 * client, and `/preview` never fetches upstream imagery.
 */
export default function PropertyPreview({
  property,
  allowListedLocation = false,
}: {
  property: PropertySummary;
  allowListedLocation?: boolean;
}) {
  const [imagery, setImagery] = useState<PropertyImagery>({
    obliques: [],
    ortho: null,
  });
  useEffect(() => {
    const controller = new AbortController();
    setImagery({ obliques: [], ortho: null });
    void loadPropertyImagery(
      property.sid,
      AbortSignal.any([controller.signal, AbortSignal.timeout(6000)]),
    )
      .then((next) => {
        if (!controller.signal.aborted) setImagery(next);
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [property.sid]);
  return (
    <PropertyPreviewImage
      key={`${property.sid}:${imagery.obliques.map((image) => image.url).join(",")}:${imagery.ortho ?? ""}`}
      property={property}
      allowListedLocation={allowListedLocation}
      obliques={imagery.obliques}
      ortho={imagery.ortho}
    />
  );
}

/**
 * The same card with imagery supplied directly, for tests and for any caller that has already
 * loaded it. Kept on its original props so existing callers do not have to change.
 */
export function PropertyPreviewImage({
  property,
  allowListedLocation = false,
  obliques = [],
  ortho = null,
}: {
  property: PropertySummary;
  allowListedLocation?: boolean;
  obliques?: PropertyOblique[];
  ortho?: string | null;
}) {
  return (
    <PropertyViews
      property={property}
      imagery={{ obliques, ortho }}
      allowListedLocation={allowListedLocation}
      modelKey={
        typeof __MATTERPORT_SDK_KEY__ === "string"
          ? __MATTERPORT_SDK_KEY__
          : undefined
      }
    />
  );
}
