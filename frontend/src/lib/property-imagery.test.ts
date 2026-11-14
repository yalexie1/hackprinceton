import { describe, expect, it } from "vitest";
import { propertyObliques } from "./property-imagery";

describe("cached side-angle aerial images", () => {
  it("accepts data-layer and preview direction names in a stable order", () => {
    expect(
      propertyObliques({
        south: "data/cache/south.jpg",
        "oblique-north": "data/cache/north.jpg",
      }),
    ).toEqual([
      { direction: "north", url: "/api/assets/data/cache/north.jpg" },
      { direction: "south", url: "/api/assets/data/cache/south.jpg" },
    ]);
  });
  it("keeps upstream signed URLs and paths outside the app out of image sources", () => {
    for (const path of [
      "https://provider.example/a.jpg?key=secret",
      "../a.jpg",
      "/etc/a.jpg",
      "data/cache/../a.jpg",
      "data/cache/a.jpg?key=secret",
      "data\\cache\\a.jpg",
    ])
      expect(propertyObliques({ north: path })).toEqual([]);
    expect(propertyObliques({})).toEqual([]);
  });
});
