import { useEffect, useRef, useState } from "react";
import { Box, Expand, Info, LocateFixed } from "lucide-react";
import HouseViewer from "./HouseViewer";
import type { Anchor, MeasureResult, Plan, RunResult } from "../lib/types";
interface Sdk {
  Mattertag: {
    add: (tags: unknown[]) => Promise<string[]>;
    remove: (...ids: string[]) => Promise<void>;
    navigateToTag: (id: string, transition: string) => Promise<unknown>;
  };
  Sweep: {
    data: {
      subscribe: (observer: {
        onCollectionUpdated: (
          sweeps: Record<string, { sid: string; uuid?: string }>,
        ) => void;
      }) => { cancel: () => void };
    };
    moveTo: (id: string, options: { transition: string }) => Promise<unknown>;
  };
}
// No assumption that Model API pano IDs equal Showcase sweep IDs.
export function resolveSweep(
  anchor: Anchor,
  sweeps: Record<string, { sid: string; uuid?: string }>,
) {
  return Object.values(sweeps).find(
    (s) =>
      anchor.pano_id && (s.sid === anchor.pano_id || s.uuid === anchor.pano_id),
  )?.sid;
}
export default function Tour({
  sid,
  office,
  demo,
  measures,
  plan,
  focus,
  run,
}: {
  sid: string;
  office: boolean;
  demo: boolean;
  measures: MeasureResult[];
  plan?: Plan | null;
  focus?: string;
  run?: RunResult | null;
}) {
  const iframe = useRef<HTMLIFrameElement>(null);
  const sdk = useRef<Sdk | null>(null);
  const sweeps = useRef<Record<string, { sid: string; uuid?: string }>>({});
  const tags = useRef<Record<string, string>>({});
  const [ready, setReady] = useState(false);
  const [notice, setNotice] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [tagVersion, setTagVersion] = useState(0);
  const key = __MATTERPORT_SDK_KEY__;
  useEffect(() => {
    if (demo || !loaded || !key || !iframe.current) return;
    let cancelled = false;
    let subscription: { cancel: () => void } | undefined;
    const connect = async () => {
      try {
        const url = `https://api.matterport.com/sdk/bootstrap/3.1.0-0-g1cd7e0997a/sdk.es6.js?applicationKey=${encodeURIComponent(key)}`;
        const module = await import(/* @vite-ignore */ url);
        const connected = (await module.connect(iframe.current)) as Sdk;
        if (cancelled) return;
        sdk.current = connected;
        subscription = connected.Sweep.data.subscribe({
          onCollectionUpdated: (data) => {
            sweeps.current = data;
          },
        });
        setReady(true);
      } catch {
        if (!cancelled)
          setNotice(
            "You can explore the tour, but evidence markers could not connect. The upgrade details remain available.",
          );
      }
    };
    void connect();
    return () => {
      cancelled = true;
      subscription?.cancel();
      sdk.current = null;
      setReady(false);
    };
  }, [demo, key, loaded, sid]);
  useEffect(() => {
    const connected = sdk.current;
    if (!ready || !connected) return;
    let cancelled = false;
    let created: string[] = [];
    const pinned = (plan?.selected.map((item) => item.measure) || []).flatMap(
      (measure) =>
        measure.anchors
          .filter((anchor) =>
            [anchor.x, anchor.y, anchor.z].every(
              (v) => typeof v === "number" && Number.isFinite(v),
            ),
          )
          .map((anchor) => ({ measure, anchor })),
    );
    if (!pinned.length) return;
    void connected.Mattertag.add(
      pinned.map(({ measure, anchor }) => ({
        label: measure.title,
        description: measure.description,
        anchorPosition: { x: anchor.x, y: anchor.z, z: -anchor.y! },
        stemVector: { x: 0, y: 0.3, z: 0 },
        color: { r: 0.4, g: 0.7, b: 0.4 },
      })),
    )
      .then((ids) => {
        created = ids;
        if (cancelled) {
          void connected.Mattertag.remove(...ids).catch(() => undefined);
          return;
        }
        tags.current = Object.fromEntries(
          ids.map((id, i) => [pinned[i].measure.measure_id, id]),
        );
        setTagVersion((version) => version + 1);
      })
      .catch(() => {
        if (!cancelled)
          setNotice(
            "Some evidence pins could not be placed. The measure details remain available.",
          );
      });
    return () => {
      cancelled = true;
      tags.current = {};
      if (created.length)
        void connected.Mattertag.remove(...created).catch(() => undefined);
    };
  }, [ready, plan]);
  useEffect(() => {
    const connected = sdk.current;
    const measure = measures.find((m) => m.measure_id === focus);
    if (!connected || !ready || !measure) return;
    const anchor = measure.anchors[0];
    const sweep = anchor && resolveSweep(anchor, sweeps.current);
    const tag = tags.current[measure.measure_id];
    const navigation = sweep
      ? connected.Sweep.moveTo(sweep, { transition: "transition.fade" })
      : tag
        ? connected.Mattertag.navigateToTag(tag, "transition.fly")
        : null;
    if (!navigation)
      setNotice("No verified tour location is available for this measure.");
    else {
      setNotice("");
      void navigation.catch(() =>
        setNotice("This evidence location is unavailable in the tour."),
      );
    }
  }, [focus, measures, ready, tagVersion]);
  return (
    <section className="tour-card" aria-label="Building explorer">
      <div className="card-heading">
        <div>
          <Box size={16} />
          <span>{demo ? "Building overview" : "Inside your building"}</span>
        </div>
        <button
          className="icon-button"
          aria-label="Expand building view"
          onClick={() =>
            void (demo ? document.querySelector(".tour-card") : iframe.current)
              ?.requestFullscreen?.()
              .catch(() =>
                setNotice("Fullscreen is unavailable in this browser."),
              )
          }
        >
          <Expand size={16} />
        </button>
      </div>
      <div className="tour-canvas">
        {demo ? (
          <HouseViewer office={office} embedded run={run} />
        ) : (
          <iframe
            ref={iframe}
            title="Matterport property tour"
            src={`https://my.matterport.com/show?${new URLSearchParams({ m: sid, play: "1", ...(key ? { applicationKey: key } : {}) })}`}
            allow="fullscreen; xr-spatial-tracking"
            allowFullScreen
            onLoad={() => setLoaded(true)}
          />
        )}
      </div>
      <div className="tour-caption">
        <LocateFixed size={14} />
        <span>
          {demo
            ? "Interactive concept model · no measured geometry"
            : ready
              ? "Select a measure to explore its evidence"
              : "Explore the tour. Evidence markers are not connected."}
        </span>
      </div>
      {notice && (
        <p className="inline-note">
          <Info size={14} />
          {notice}
        </p>
      )}
    </section>
  );
}
