// Demo autoscroll: on page load, glide slowly to the bottom and back up, looping, until someone
// clicks or taps the page (a key press or the scroll wheel also stops it, so it never fights a
// visitor). Moving the mouse does not stop it. Off when the system asks for reduced motion or the
// URL has ?autoscroll=0.

export interface AutoscrollOptions {
  speed?: number; // pixels per second
  startDelayMs?: number;
  pauseMs?: number; // rest at the top and bottom
}

const STOP_EVENTS = ["wheel", "touchstart", "keydown", "mousedown", "pointerdown"] as const;

export function autoscrollEnabled(win: Window): boolean {
  if (new URL(win.location.href).searchParams.get("autoscroll") === "0") return false;
  return !win.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

export function startAutoscroll(win: Window = window, opts: AutoscrollOptions = {}): () => void {
  const speed = opts.speed ?? 120;
  const pauseMs = opts.pauseMs ?? 1500;
  const doc = win.document;
  let stopped = false;
  let dir = 1;
  let restUntil = 0;
  let last: number | null = null;
  let pos: number | null = null; // fractional position; scrollTo rounds
  let raf = 0;

  const stop = () => {
    if (stopped) return;
    stopped = true;
    win.cancelAnimationFrame(raf);
    win.clearTimeout(timer);
    for (const e of STOP_EVENTS) win.removeEventListener(e, stop, true);
  };

  const step = (now: number) => {
    if (stopped) return;
    const el = doc.scrollingElement ?? doc.documentElement;
    const max = el.scrollHeight - win.innerHeight;
    const dt = last === null ? 0 : Math.min(now - last, 100) / 1000;
    last = now;
    if (max > 4 && now >= restUntil) {
      if (pos === null || Math.abs(pos - win.scrollY) > 2) pos = win.scrollY;
      pos = Math.max(0, Math.min(max, pos + dir * speed * dt));
      win.scrollTo(0, pos);
      if ((dir > 0 && pos >= max) || (dir < 0 && pos <= 0)) {
        dir = -dir;
        restUntil = now + pauseMs;
      }
    }
    raf = win.requestAnimationFrame(step);
  };

  for (const e of STOP_EVENTS) win.addEventListener(e, stop, { capture: true, passive: true });
  const timer = win.setTimeout(() => {
    if (!stopped) raf = win.requestAnimationFrame(step);
  }, opts.startDelayMs ?? 2000);
  return stop;
}
