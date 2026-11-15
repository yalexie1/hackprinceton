import { afterEach, describe, expect, it, vi } from "vitest";
import { startViewerSession, type ViewerSession, type ViewerBootstrap } from "./matterport-viewer";

function session(sid = "house"): ViewerSession {
  return { Model: { getData: vi.fn().mockResolvedValue({ sid }) }, disconnect: vi.fn() };
}
const frame = {} as HTMLIFrameElement;
const callbacks = () => ({ ready: vi.fn(), failed: vi.fn() });
const settle = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };
afterEach(() => vi.useRealTimers());

describe("Matterport connection lifecycle", () => {
  it("does not report readiness for the wrong property's model", async () => {
    const sdk = session("different-house"), cb = callbacks();
    const stop = startViewerSession(frame, "browser-key", "house", cb,
      async () => ({ connect: async () => sdk }));
    await settle();
    expect(cb.ready).not.toHaveBeenCalled();
    expect(cb.failed).toHaveBeenCalledOnce();
    expect(sdk.disconnect).toHaveBeenCalledOnce();
    stop();
  });

  it("disconnects a successful session when its view is removed", async () => {
    const sdk = session(), cb = callbacks();
    const stop = startViewerSession(frame, "browser-key", "house", cb,
      async () => ({ connect: async () => sdk }));
    await settle();
    expect(cb.ready).toHaveBeenCalledOnce();
    expect(sdk.disconnect).not.toHaveBeenCalled();
    stop(); stop();
    expect(sdk.disconnect).toHaveBeenCalledOnce();
  });

  it("closes a late connection after navigation without updating the old view", async () => {
    let resolve!: (sdk: ViewerSession) => void;
    const pending = new Promise<ViewerSession>((r) => { resolve = r; });
    const sdk = session(), cb = callbacks();
    const stop = startViewerSession(frame, "browser-key", "house", cb,
      async () => ({ connect: () => pending }));
    await settle(); stop(); resolve(sdk); await settle();
    expect(sdk.disconnect).toHaveBeenCalledOnce();
    expect(cb.ready).not.toHaveBeenCalled();
    expect(cb.failed).not.toHaveBeenCalled();
  });

  it("bounds an indefinitely pending connection and closes it if it later arrives", async () => {
    vi.useFakeTimers();
    let resolve!: (sdk: ViewerSession) => void;
    const pending = new Promise<ViewerSession>((r) => { resolve = r; });
    const sdk = session(), cb = callbacks();
    const stop = startViewerSession(frame, "browser-key", "house", cb,
      async () => ({ connect: () => pending }), 100);
    await settle(); await vi.advanceTimersByTimeAsync(100);
    expect(cb.failed).toHaveBeenCalledOnce();
    resolve(sdk); await settle();
    expect(sdk.disconnect).toHaveBeenCalledOnce();
    expect(cb.ready).not.toHaveBeenCalled(); stop();
  });

  it("does not start a new handshake if navigation cancels a slow bootstrap", async () => {
    let resolve!: (value: ViewerBootstrap) => void;
    const pending = new Promise<ViewerBootstrap>((r) => { resolve = r; });
    const connect = vi.fn<ViewerBootstrap["connect"]>(), cb = callbacks();
    const stop = startViewerSession(frame, "browser-key", "house", cb, () => pending);
    stop(); resolve({ connect }); await settle();
    expect(connect).not.toHaveBeenCalled();
  });
});
