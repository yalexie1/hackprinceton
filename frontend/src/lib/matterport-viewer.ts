// Official Embed SDK bootstrap. Only the browser-scoped SDK key belongs here.
// https://developers.matterport.com/embed-sdk/quickstart/
const BOOTSTRAP = "https://api.matterport.com/sdk/bootstrap/3.1.0-0-g1cd7e0997a/sdk.es6.js";

export interface ViewerSession {
  Model: { getData(): Promise<{ sid: string }> };
  disconnect(): void;
}
export interface ViewerBootstrap {
  connect(frame: HTMLIFrameElement): Promise<ViewerSession>;
}

const bootstraps = new Map<string, Promise<ViewerBootstrap>>();
export function loadViewerBootstrap(key: string): Promise<ViewerBootstrap> {
  let pending = bootstraps.get(key);
  if (!pending) {
    const url = `${BOOTSTRAP}?${new URLSearchParams({ applicationKey: key })}`;
    pending = import(/* @vite-ignore */ url) as Promise<ViewerBootstrap>;
    bootstraps.set(key, pending);
    void pending.catch(() => bootstraps.delete(key));
  }
  return pending;
}

/** Connect only the current frame, verify its model, and close late/stale sessions.
 * A document load is not proof that Showcase authorized or loaded the model.
 */
export function startViewerSession(
  frame: HTMLIFrameElement,
  key: string,
  sid: string,
  callbacks: { ready(): void; failed(): void },
  load: (key: string) => Promise<ViewerBootstrap> = loadViewerBootstrap,
  timeoutMs = 45_000,
): () => void {
  let cancelled = false;
  let session: ViewerSession | undefined;
  const disconnect = () => {
    const held = session;
    session = undefined;
    try { held?.disconnect(); } catch { /* already closed by Showcase */ }
  };
  const fail = () => {
    if (cancelled) return;
    cancelled = true;
    clearTimeout(timer);
    disconnect();
    callbacks.failed();
  };
  const timer = setTimeout(fail, timeoutMs);
  void (async () => {
    try {
      const bootstrap = await load(key);
      if (cancelled) return;
      session = await bootstrap.connect(frame);
      if (cancelled) { disconnect(); return; }
      const model = await session.Model.getData();
      if (cancelled) return;
      if (model.sid !== sid) throw new Error("Unexpected model");
      clearTimeout(timer);
      callbacks.ready();
    } catch { fail(); }
  })();
  return () => {
    cancelled = true;
    clearTimeout(timer);
    disconnect();
  };
}
