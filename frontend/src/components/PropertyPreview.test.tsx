import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { demoProperties } from "../lib/fixtures";
import PropertyPreview from "./PropertyPreview";

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
    expect(images.join("")).toContain("address location");
    expect(images.join("")).toContain("scan location");
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
