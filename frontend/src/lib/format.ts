import type { Ranged } from "./types";
export const money = (n: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
export const number = (n: number, digits = 0) =>
  new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(n);
export const ranged = (r: Ranged, currency = false) =>
  `${currency ? money(r.low) : number(r.low, 2)}–${currency ? money(r.high) : number(r.high, 2)}`;
export function download(name: string, text: string, type = "text/markdown") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
// Single-ring WKT polygons from the public contract. Unsupported geometry stays visible as a warning.
export function polygon(wkt?: string | null): [number, number][] {
  if (typeof wkt !== "string") return [];
  const match = /^POLYGON\s*\(\(\s*([^()]+)\s*\)\)$/i.exec(wkt.trim());
  if (!match) return [];
  const points = match[1]
    .split(",")
    .map((pair) => pair.trim().split(/\s+/).map(Number));
  return points.length >= 4 &&
    points.every((p) => p.length === 2 && p.every(Number.isFinite))
    ? (points as [number, number][])
    : [];
}
