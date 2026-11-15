import { useEffect, useRef, useState } from "react";
import { Box } from "lucide-react";
import { startViewerSession } from "../lib/matterport-viewer";

export default function MatterportViewer({ sid, name, sdkKey }: {
  sid: string; name: string; sdkKey: string;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  useEffect(() => {
    if (!loaded || !frame.current) return;
    return startViewerSession(frame.current, sdkKey, sid, {
      ready: () => setState("ready"), failed: () => setState("error"),
    });
  }, [sid, sdkKey, loaded, attempt]);
  useEffect(() => {
    if (state !== "loading" || loaded) return;
    // Also bound a frame navigation that never fires its load event.
    const timer = setTimeout(() => setState("error"), 45_000);
    return () => clearTimeout(timer);
  }, [state, loaded, attempt]);
  return (
    <>
      {state !== "ready" && (
        <div className="property-model-loading" role={state === "error" ? "alert" : "status"}>
          <Box size={22} aria-hidden="true" />
          {state === "error" ? (
            <>
              <strong>We couldn’t open this 3D scan.</strong>
              <span>Try again, or choose another property view.</span>
              <button className="secondary-button" onClick={() => {
                setLoaded(false); setState("loading"); setAttempt((n) => n + 1);
              }}>Try the 3D scan again</button>
            </>
          ) : <span>Opening the property’s interior scan…</span>}
        </div>
      )}
      <iframe
        key={`${sid}:${attempt}`}
        ref={frame}
        className="property-model-frame"
        title={`Interior scan of ${name}`}
        allow="fullscreen; xr-spatial-tracking"
        referrerPolicy="strict-origin-when-cross-origin"
        onLoad={() => { if (state !== "error") setLoaded(true); }}
        src={`https://my.matterport.com/show?${new URLSearchParams({
          m: sid, play: "1", title: "0", applicationKey: sdkKey,
        })}`}
      />
    </>
  );
}
