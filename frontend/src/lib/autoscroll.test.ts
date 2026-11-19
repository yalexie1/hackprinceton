import { describe, expect, it, vi } from "vitest";
import { autoscrollEnabled, startAutoscroll } from "./autoscroll";

function fakeWindow(scrollHeight = 2000, innerHeight = 800) {
  const listeners: Record<string, ((e: any) => void)[]> = {};
  const frames: ((t: number) => void)[] = [];
  const win: any = {
    location: { href: "http://localhost:5173/" },
    innerHeight,
    scrollY: 0,
    document: { scrollingElement: { scrollHeight } },
    matchMedia: () => ({ matches: false }),
    scrollTo: vi.fn((_x: number, y: number) => (win.scrollY = y)),
    requestAnimationFrame: (f: (t: number) => void) => frames.push(f),
    cancelAnimationFrame: vi.fn(),
    setTimeout: (f: () => void) => (f(), 1),
    clearTimeout: vi.fn(),
    addEventListener: (t: string, f: (e: any) => void) => (listeners[t] ??= []).push(f),
    removeEventListener: (t: string, f: (e: any) => void) => (listeners[t] = (listeners[t] ?? []).filter((g) => g !== f)),
  };
  const fire = (t: string, e: any = {}) => (listeners[t] ?? []).forEach((f) => f(e));
  let clock = 0;
  const run = (ms: number, dt = 16) => {
    for (const end = clock + ms; clock <= end; clock += dt) frames.splice(0).forEach((f) => f(clock));
  };
  return { win, fire, run };
}

describe("demo autoscroll", () => {
  it("scrolls to the bottom, rests, then comes back up", () => {
    const { win, run } = fakeWindow();
    startAutoscroll(win, { speed: 1000, pauseMs: 100 });
    run(1500);
    const ys = win.scrollTo.mock.calls.map((c: number[]) => c[1]);
    expect(Math.max(...ys)).toBe(1200);
    expect(ys.at(-1)).toBeLessThan(1200);
  });

  it("stops for good on a key, click, wheel or touch", () => {
    for (const ev of ["keydown", "mousedown", "wheel", "touchstart", "pointerdown"]) {
      const { win, fire, run } = fakeWindow();
      startAutoscroll(win, { speed: 1000 });
      run(200);
      const at = win.scrollY;
      fire(ev);
      run(1000);
      expect(win.scrollY).toBe(at);
    }
  });

  it("keeps going when the mouse just moves", () => {
    const { win, fire, run } = fakeWindow();
    startAutoscroll(win, { speed: 1000 });
    run(100);
    const before = win.scrollY;
    fire("mousemove", { clientX: 140, clientY: 100 });
    run(200);
    expect(win.scrollY).toBeGreaterThan(before);
  });

  it("is off with ?autoscroll=0 or reduced motion", () => {
    const { win } = fakeWindow();
    expect(autoscrollEnabled(win)).toBe(true);
    win.location.href = "http://localhost:5173/?autoscroll=0";
    expect(autoscrollEnabled(win)).toBe(false);
    win.location.href = "http://localhost:5173/";
    win.matchMedia = () => ({ matches: true });
    expect(autoscrollEnabled(win)).toBe(false);
  });
});
