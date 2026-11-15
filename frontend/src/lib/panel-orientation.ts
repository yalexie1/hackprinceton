import type { RunResult } from "./types";

export interface PanelFacing {
  azimuthDeg: number;
  label: string;
}

const COMPASS = [
  "north",
  "northeast",
  "east",
  "southeast",
  "south",
  "southwest",
  "west",
  "northwest",
];

export function compassName(azimuthDeg: number): string {
  const a = ((azimuthDeg % 360) + 360) % 360;
  return COMPASS[Math.floor((a + 22.5) / 45) % 8];
}

// The direction the recommended solar array faces: the azimuth (0 = north,
// clockwise) of the roof plane that carries the most panels. Null when the
// run has no panels or no roof planes to read an azimuth from.
export function panelFacing(run?: RunResult | null): PanelFacing | null {
  if (!run) return null;
  const solar =
    run.plan?.selected.find((item) => item.measure.solar)?.measure.solar ||
    run.plan?.financeable.find((m) => m.solar)?.solar ||
    run.measures.find((m) => m.solar)?.solar;
  const planes = run.building_model?.roof_planes || [];
  if (!solar?.panels?.length || !planes.length) return null;
  const counts = new Map<string, number>();
  for (const p of solar.panels)
    counts.set(p.plane_id, (counts.get(p.plane_id) || 0) + 1);
  let best: { id: string; n: number } | null = null;
  for (const [id, n] of counts) if (!best || n > best.n) best = { id, n };
  const plane = planes.find((p) => p.id === best?.id);
  if (!plane || !Number.isFinite(plane.azimuth_deg)) return null;
  const azimuthDeg = ((plane.azimuth_deg % 360) + 360) % 360;
  return { azimuthDeg, label: compassName(azimuthDeg) };
}
