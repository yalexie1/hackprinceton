import { assetUrl } from "./api";

export interface PropertyOblique {
  url: string;
  direction: string;
}

const directions = ["north", "south", "east", "west"] as const;

// Only accept cache paths served by the app. Sponsor credentials and upstream
// signed URLs must never be sent to a browser as image sources.
export function propertyObliques(
  paths: Record<string, string>,
): PropertyOblique[] {
  return directions.flatMap((direction) => {
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
