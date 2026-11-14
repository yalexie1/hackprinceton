import { afterEach, describe, expect, it, vi } from "vitest";
import { loadPropertyObliques, propertyObliques } from "./property-imagery";

afterEach(() => vi.unstubAllGlobals());

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
  it("shows a prepared facade direction first without starting an audit or upstream fetch", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          sid: "house",
          provider: "Vexcel",
          preferred_direction: "west",
          oblique_paths: {
            "oblique-north": "data/cache/n.jpg",
            "oblique-west": "data/cache/w.jpg",
          },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetch);
    const images = await loadPropertyObliques(
      "house",
      new AbortController().signal,
    );
    expect(images[0]).toEqual({
      direction: "west",
      url: "/api/assets/data/cache/w.jpg",
    });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe(
      "/api/assets/data/cache/frontend-property-imagery/house.json",
    );
  });
  it("uses the canonical preview if no prepared cache exists", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response("{}", { status: 404 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            sid: "office",
            available: true,
            oblique_paths: { north: "data/cache/office.jpg" },
          }),
        ),
      );
    vi.stubGlobal("fetch", fetch);
    expect(
      await loadPropertyObliques("office", new AbortController().signal),
    ).toEqual([
      { direction: "north", url: "/api/assets/data/cache/office.jpg" },
    ]);
    expect(fetch.mock.calls[1][0]).toBe("/api/properties/office/preview");
  });
  it("rejects another property's photos and tolerates older backends without preview support", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            sid: "other",
            provider: "Vexcel",
            oblique_paths: { north: "data/cache/other.jpg" },
          }),
        ),
      )
      .mockResolvedValueOnce(new Response("{}", { status: 404 }));
    vi.stubGlobal("fetch", fetch);
    expect(
      await loadPropertyObliques("house", new AbortController().signal),
    ).toEqual([]);
  });
  it("does not continue reading images after the property request is cancelled", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const controller = new AbortController();
    controller.abort();
    expect(await loadPropertyObliques("house", controller.signal)).toEqual([]);
    expect(fetch).not.toHaveBeenCalled();
  });
});
