import { describe, expect, it } from "vitest";
import { aerialImageUrl, propertyLocation } from "./property-geospatial";

describe("actual property geospatial context", () => {
  it("uses verified scan points and the matched Census street address, never illustrative office coordinates", () => {
    expect(propertyLocation("zvKHR9DHNjJ")).toMatchObject({
      lat: 34.093491667,
      lon: -118.3171,
      source: "scan",
    });
    expect(propertyLocation("ZSPaQbkGcJJ")).toMatchObject({
      lat: 34.032827502845,
      lon: -118.38990083201,
      source: "address",
    });
    expect(propertyLocation("L3266YcPPvd")).toMatchObject({
      lat: 29.746027599,
      lon: -95.457545726,
      source: "scan",
    });
    expect(propertyLocation("unverified-property")).toBeNull();
  });
  it("requests a north-up Web Mercator crop centred on the supplied point", () => {
    const url = new URL(
      aerialImageUrl(
        { lat: 0, lon: 0, source: "scan", citation: "test" },
        false,
      )!,
    );
    expect(url.host).toBe("services.arcgisonline.com");
    expect(url.searchParams.get("bboxSR")).toBe("3857");
    const [west, south, east, north] = url.searchParams
      .get("bbox")!
      .split(",")
      .map(Number);
    expect((west + east) / 2).toBeCloseTo(0, 7);
    expect((south + north) / 2).toBeCloseTo(0, 7);
    expect(east - west).toBe(120);
    expect(north - south).toBe(75);
  });
  it("refuses invalid locations instead of displaying the wrong place", () => {
    for (const [lat, lon] of [
      [NaN, 0],
      [90, 0],
      [0, 181],
    ])
      expect(
        aerialImageUrl({ lat, lon, source: "scan", citation: "test" }, false),
      ).toBeNull();
  });
});
