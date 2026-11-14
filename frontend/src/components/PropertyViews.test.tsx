import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { demoProperties } from "../lib/fixtures";
import PropertyViews, { propertyViews } from "./PropertyViews";
import { propertyObliques } from "../lib/property-imagery";

const obliques = propertyObliques({
  "oblique-north": "data/cache/vexcel-image/house/north.jpg",
  "oblique-west": "data/cache/vexcel-image/house/west.jpg",
});
const ortho = "/api/assets/data/cache/vexcel-image/house/ortho.jpg";

describe("the property view toggle", () => {
  it("offers only the views a property actually has", () => {
    // The seventeen unreviewed properties have no ortho and no obliques. A fixed three-tab strip
    // would open an empty frame for them, so the kinds must come from the data.
    const bare = propertyViews(
      demoProperties[0],
      { obliques: [], ortho: null },
      { hasModelKey: true },
    );
    expect(bare.map((view) => view.kind)).not.toContain("oblique");
    expect(bare.map((view) => view.kind)).not.toContain("ortho");

    const full = propertyViews(
      demoProperties[0],
      { obliques, ortho },
      { hasModelKey: true },
    );
    expect(new Set(full.map((view) => view.kind))).toEqual(
      new Set(["oblique", "ortho", "model", "context"]),
    );
  });

  it("keeps the Vexcel orthophoto and the Esri basemap as separate views with their own credit", () => {
    // Collapsing them under one word would let a viewer read a basemap as evidence about the
    // building.
    const views = propertyViews(demoProperties[0], { obliques: [], ortho });
    const aerial = views.find((view) => view.kind === "ortho")!;
    const map = views.find((view) => view.kind === "context")!;
    expect(aerial.credit).toContain("Vexcel");
    expect(aerial.caption).toContain("orthophoto");
    expect(map.credit).toContain("Esri");
    expect(map.credit).not.toContain("Vexcel");
    expect(aerial.label).not.toBe(map.label);
  });

  it("does not offer a 3D model for a property with no scan, or with no viewer key", () => {
    const unscanned = {
      ...demoProperties[0],
      room_count: 0,
      pano_count: 0,
    };
    expect(
      propertyViews(unscanned, { obliques, ortho }, { hasModelKey: true }).map(
        (view) => view.kind,
      ),
    ).not.toContain("model");
    expect(
      propertyViews(
        demoProperties[0],
        { obliques, ortho },
        { hasModelKey: false },
      ).map((view) => view.kind),
    ).not.toContain("model");
  });

  it("never makes the 3D model the default view", () => {
    // Regression: the model was ordered before the map, so a card with no imagery loaded yet
    // defaulted to an iframe - a Matterport scene per card in the grid, which is exactly what
    // mounting-on-selection exists to avoid.
    for (const imagery of [
      { obliques: [], ortho: null },
      { obliques: [], ortho },
      { obliques, ortho },
    ]) {
      const views = propertyViews(demoProperties[0], imagery, {
        hasModelKey: true,
      });
      expect(views[0]?.kind).not.toBe("model");
    }
  });

  it("does not offer a tour for a property whose sid is not a scan we hold", () => {
    // Regression: `sid` is the Matterport model id, so an unverified sid embedded `m=<unknown>`
    // and put the viewer key in the markup for a building we have no scan for.
    const html = renderToStaticMarkup(
      <PropertyViews
        property={{ ...demoProperties[0], sid: "unknown" }}
        imagery={{ obliques: [], ortho: null }}
        modelKey="test-key"
      />,
    );
    expect(html).not.toContain("matterport.com");
    expect(html).not.toContain("test-key");
    expect(html).toContain("Location not verified yet");
  });

  it("defaults to the map, because every locatable property has one and it settles in one request", () => {
    const html = renderToStaticMarkup(
      <PropertyViews
        property={demoProperties[0]}
        imagery={{ obliques, ortho }}
      />,
    );
    expect(html).toContain("MapServer/export?");
    expect(html).toContain("Esri, Vantor");
    expect(html).toContain("property-location-pin");
    expect(
      propertyViews(demoProperties[0], { obliques, ortho })[0]?.kind,
    ).toBe("context");
  });

  it("labels each side angle by direction, and never pins the basemap marker on a photograph", () => {
    const side = propertyViews(demoProperties[0], { obliques, ortho }).find(
      (view) => view.kind === "oblique",
    );
    expect(side?.url).toBe(
      "/api/assets/data/cache/vexcel-image/house/north.jpg",
    );
    expect(side?.caption).toBe("Side-angle aerial · north view");
    expect(side?.credit).toBe("Vexcel aerial imagery");
    // A survey photograph's centre is not the property's location, so the pin must not follow it.
    const photoOnly = renderToStaticMarkup(
      <PropertyViews
        property={{ ...demoProperties[0], sid: "unknown" }}
        imagery={{ obliques, ortho: null }}
      />,
    );
    expect(photoOnly).toContain("Side-angle aerial");
    expect(photoOnly).not.toContain("property-location-pin");
  });

  it("renders one tab per kind, not one per oblique direction", () => {
    const html = renderToStaticMarkup(
      <PropertyViews
        property={demoProperties[0]}
        imagery={{ obliques, ortho }}
        modelKey="test-key"
      />,
    );
    expect((html.match(/role="tab"/g) || []).length).toBe(4);
    expect((html.match(/Side angle/g) || []).length).toBe(1);
  });

  it("hides the strip when there is nothing to switch between", () => {
    const html = renderToStaticMarkup(
      <PropertyViews
        property={{ ...demoProperties[0], sid: "unknown" }}
        imagery={{ obliques: [], ortho: null }}
      />,
    );
    expect(html).not.toContain('role="tablist"');
  });

  it("never puts a sponsor URL or a credential in an image source", () => {
    const hostile = propertyObliques({
      "oblique-north": "https://api.vexcelgroup.com/signed?token=secret",
      "oblique-south": "../../.env",
      "oblique-east": "data/cache/ok.jpg",
    });
    // Rendered with no basemap location, so the surviving photo is what gets drawn.
    const html = renderToStaticMarkup(
      <PropertyViews
        property={{ ...demoProperties[0], sid: "unknown" }}
        imagery={{ obliques: hostile, ortho: null }}
      />,
    );
    expect(html).not.toContain("vexcelgroup.com");
    expect(html).not.toContain("token=secret");
    expect(html).not.toContain(".env");
    expect(html).toContain("/api/assets/data/cache/ok.jpg");
    // And the hostile paths are gone from the view list too, not merely unrendered.
    const urls = propertyViews(demoProperties[0], {
      obliques: hostile,
      ortho: null,
    })
      .map((view) => view.url || "")
      .join(" ");
    expect(urls).not.toContain("vexcelgroup.com");
    expect(urls).not.toContain(".env");
  });

  it("falls back to a location frame rather than an empty box when a property has no imagery at all", () => {
    const html = renderToStaticMarkup(
      <PropertyViews
        property={{ ...demoProperties[0], sid: "unknown" }}
        imagery={{ obliques: [], ortho: null }}
      />,
    );
    expect(html).toContain("Location not verified yet");
    expect(html).not.toContain("<img");
  });
});
