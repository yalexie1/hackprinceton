import { api, assetUrl, request } from "./api";

export interface PropertyOblique {
  url: string;
  direction: string;
}

const directions = ["north", "south", "east", "west"] as const;

// Only accept cache paths served by the app. Sponsor credentials and upstream
// signed URLs must never be sent to a browser as image sources.
export function propertyObliques(
  paths: Record<string, string>,
  preferredDirection?: string,
): PropertyOblique[] {
  const ordered = [...directions].sort(
    (a, b) =>
      Number(b === preferredDirection) - Number(a === preferredDirection),
  );
  return ordered.flatMap((direction) => {
    const path = paths[`oblique-${direction}`] || paths[direction];
    if (
      typeof path !== "string" ||
      !path ||
      path.startsWith("/") ||
      path.includes(":") ||
      path.split("/").some((part) => part === ".." || part === ".") ||
      /[?#\\]/.test(path)
    )
      return [];
    return [{ url: assetUrl(path), direction }];
  });
}

// Read the canonical preview first. An optional prepared crop can improve the
// default photo while retaining canonical images as fallbacks. Both are cache
// reads; neither starts an audit or an upstream image fetch.
export async function loadPropertyObliques(sid: string, signal: AbortSignal) {
  if (signal.aborted) return [];
  let canonical: PropertyOblique[] = [];
  try {
    const preview = await api.preview(sid, signal);
    if (preview.sid === sid && preview.available)
      canonical = propertyObliques(preview.oblique_paths || {});
  } catch {
    if (signal.aborted) return [];
  }
  try {
    const manifest = await request<{
      sid: string;
      provider: string;
      preferred_direction?: string;
      oblique_paths: Record<string, string>;
    }>(
      `/assets/data/cache/frontend-property-imagery/${encodeURIComponent(sid)}.json`,
      { signal },
    );
    if (manifest.sid === sid && manifest.provider === "Vexcel") {
      const images = propertyObliques(
        manifest.oblique_paths || {},
        manifest.preferred_direction,
      );
      if (images.length)
        return [
          ...images,
          ...canonical.filter(
            (image) => !images.some((curated) => curated.url === image.url),
          ),
        ];
    }
  } catch {
    if (signal.aborted) return [];
  }
  return canonical;
}
