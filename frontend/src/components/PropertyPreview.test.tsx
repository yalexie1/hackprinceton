import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { demoProperties } from "../lib/fixtures";
import PropertyPreview, { PropertyPreviewImage } from "./PropertyPreview";
import { propertyObliques } from "../lib/property-imagery";
import { propertyViews } from "./PropertyViews";

describe("property-specific imagery", () => {
  it("can use a connected listing’s reported coordinates without marking them as a verified scan", () => {
    const html = renderToStaticMarkup(
      <PropertyPreview
        property={{ ...demoProperties[0], sid: "connected-listing" }}
        allowListedLocation
      />,
    );
    expect(html).toContain("listing location");
    expect(html).not.toContain("verified scan");
    expect(html).toContain("MapServer/export?");
  });
  it("gives each reviewed property a distinct real geospatial image and attribution", () => {
    const images = demoProperties.map((property) =>
      renderToStaticMarkup(<PropertyPreview property={property} />),
    );
    expect(
      new Set(images.map((html) => html.match(/src="([^"]+)"/)?.[1])).size,
    ).toBe(3);
    for (const html of images) {
      expect(html).toContain("MapServer/export?");
      expect(html).toContain("Esri, Vantor");
      expect(html).not.toContain("house-canvas");
    }
    expect(images.join("")).toContain("scan location");
  });
  it("offers an actual side-angle photo, and carries no north-up pin on it", () => {
    // This test used to assert the card *preferred* the side angle. The map is now the default
    // view by product decision - it is the one view every locatable property has and it settles
    // the grid in a single request - so the side angle is a click away rather than first. What
    // has not changed, and is what this test defends: the photo is offered, it is credited to
    // Vexcel, and the north-up pin belongs to the basemap only and must never be drawn over a
    // survey photograph, whose centre is not the property's location.
    const obliques = propertyObliques({
      "oblique-south": "data/cache/vexcel-image/house/south.jpg",
    });
    const side = propertyViews(demoProperties[0], {
      obliques,
      ortho: null,
    }).find((view) => view.kind === "oblique");
    expect(side?.url).toBe("/api/assets/data/cache/vexcel-image/house/south.jpg");
    expect(side?.caption).toBe("Side-angle aerial · south view");
    expect(side?.credit).toBe("Vexcel aerial imagery");

    // With no basemap location there is nothing to default to, so the photo renders - and then
    // it must come with no pin.
    const photoOnly = renderToStaticMarkup(
      <PropertyPreviewImage
        property={{ ...demoProperties[0], sid: "unknown" }}
        obliques={obliques}
      />,
    );
    expect(photoOnly).toContain(
      "/api/assets/data/cache/vexcel-image/house/south.jpg",
    );
    expect(photoOnly).not.toContain("property-location-pin");
    expect(photoOnly).not.toContain("MapServer/export?");
  });
  it("does not substitute a generic model or invented location when a property is unverified", () => {
    const html = renderToStaticMarkup(
      <PropertyPreview property={{ ...demoProperties[0], sid: "unknown" }} />,
    );
    expect(html).toContain("Location not verified yet");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("house-canvas");
  });
});
