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

export interface PropertyImagery {
  obliques: PropertyOblique[];
  /** The Vexcel orthophoto, when the preview holds one and its file is served. */
  ortho: string | null;
}

/**
 * The same guard `propertyObliques` applies, as a reusable predicate: only a relative cache path
 * this app serves. An absolute URL, a scheme, a traversal segment or a query is rejected, because
 * a sponsor's signed URL or a credential must never reach a browser as an image source.
 */
export function servableCachePath(path: unknown): path is string {
  return (
    typeof path === "string" &&
    Boolean(path) &&
    !path.startsWith("/") &&
    !path.includes(":") &&
    !path.split("/").some((part) => part === ".." || part === ".") &&
    !/[?#\\]/.test(path)
  );
}

/**
 * Obliques and the orthophoto in one cached read.
 *
 * `loadPropertyObliques` is left exactly as it is: it is called from the card today and its
 * contract is a list of obliques. This wraps it, so a caller that also wants the aerial view does
 * not have to decide which of two near-identical loaders to use.
 *
 * `image_available` is honoured. The preview reports whether the file is actually held, and a
 * path whose bytes are missing would put an empty frame behind a tab that promised a photo.
 */
export async function loadPropertyImagery(
  sid: string,
  signal: AbortSignal,
): Promise<PropertyImagery> {
  if (signal.aborted) return { obliques: [], ortho: null };
  const obliques = await loadPropertyObliques(sid, signal);
  let ortho: string | null = null;
  try {
    const preview = await api.preview(sid, signal);
    const path = preview.ortho?.path;
    if (
      preview.sid === sid &&
      preview.available &&
      preview.ortho?.image_available !== false &&
      servableCachePath(path)
    )
      ortho = assetUrl(path);
  } catch {
    // A preview that does not answer leaves the aerial tab unoffered, which is the honest
    // outcome. The obliques above are unaffected.
  }
  return { obliques, ortho };
}
