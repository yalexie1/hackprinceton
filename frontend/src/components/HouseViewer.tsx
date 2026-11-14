import { useEffect, useRef, useState } from "react";
import {
  ArrowDownLeft,
  Box,
  ChevronRight,
  Layers3,
  Minus,
  MousePointer2,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Sun,
} from "lucide-react";
import type { HouseController, HouseMode, HouseRoom } from "../lib/house-scene";
import type { EnergyPart, EnergyPoint } from "../lib/energy-explorer";
import type { RunResult } from "../lib/types";
import EnergyOverlay from "./EnergyOverlay";

const homeRooms: {
  id: HouseRoom;
  name: string;
  title: string;
  detail: string;
  icon: string;
}[] = [
  {
    id: "living",
    name: "Living room",
    title: "A more comfortable everyday.",
    detail:
      "Look through the living space. Windows, lighting, and insulation all shape how a home feels — and how much energy it uses.",
    icon: "01",
  },
  {
    id: "bedroom",
    name: "Bedroom",
    title: "Small details. Better rest.",
    detail:
      "Explore the upper floor. A well-insulated envelope keeps bedrooms comfortable through warm afternoons and cooler nights.",
    icon: "02",
  },
  {
    id: "roof",
    name: "Solar roof",
    title: "Potential, right above you.",
    detail:
      "Take a closer look at the solar array. In a real audit, roof geometry and local sunlight help determine what is possible.",
    icon: "03",
  },
];
const officeRooms = [
  {
    id: "living" as const,
    name: "Work area",
    title: "A more comfortable workday.",
    detail:
      "Explore the concept work area. Lighting, windows and operating schedules affect energy use and comfort.",
    icon: "01",
  },
  {
    id: "bedroom" as const,
    name: "Upper floor",
    title: "Look inside the building envelope.",
    detail:
      "Inspect the upper floor of this concept office. The actual scan and audit determine which spaces and upgrades are available.",
    icon: "02",
  },
  {
    id: "roof" as const,
    name: "Roof & solar",
    title: "Explore the roof’s potential.",
    detail:
      "This is a concept roof. Open Solar & roof for the property’s analyzed roof geometry, imagery and solar findings.",
    icon: "03",
  },
];

export default function HouseViewer({
  compact = false,
  office = false,
  embedded = false,
  run,
}: {
  compact?: boolean;
  office?: boolean;
  embedded?: boolean;
  run?: RunResult | null;
}) {
  const host = useRef<HTMLDivElement>(null);
  const controller = useRef<HouseController | null>(null);
  const energyHover = useRef<((part: EnergyPart | null) => void) | null>(null);
  const energyProject = useRef<((points: EnergyPoint[]) => void) | null>(null);
  const [mode, setMode] = useState<HouseMode>("exploded");
  const [rotating, setRotating] = useState(false);
  const [room, setRoom] = useState<HouseRoom | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable">(
    "loading",
  );
  const rooms = office ? officeRooms : homeRooms;
  const selected = rooms.find((r) => r.id === room);
  const current = useRef({ mode, rotating });
  current.current = { mode, rotating };

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let cancelled = false;
    let started = false;
    const start = async () => {
      if (started) return;
      started = true;
      try {
        const { createHouseScene } = await import("../lib/house-scene");
        if (cancelled) return;
        const scene = createHouseScene(element, {
          compact,
          office,
          onUnavailable: () => setStatus("unavailable"),
          onHover: (part) => energyHover.current?.(part),
          onProject: (points) => energyProject.current?.(points),
        });
        controller.current = scene;
        scene.setMode(compact ? "exterior" : current.current.mode, true);
        scene.setRotating(current.current.rotating);
        setStatus("ready");
      } catch {
        if (!cancelled) setStatus("unavailable");
      }
    };
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          void start();
          observer.disconnect();
        }
      },
      { rootMargin: "120px" },
    );
    observer.observe(element);
    return () => {
      cancelled = true;
      observer.disconnect();
      controller.current?.dispose();
      controller.current = null;
    };
  }, [compact, office]);

  function changeMode(next: HouseMode) {
    setMode(next);
    setRoom(null);
    controller.current?.setMode(next);
    controller.current?.reset();
  }
  function focusRoom(next: HouseRoom) {
    setRoom(next);
    setRotating(false);
    controller.current?.setRotating(false);
    const nextMode =
      next === "bedroom" || next === "roof" ? "exploded" : "cutaway";
    if (mode !== nextMode) {
      setMode(nextMode);
      controller.current?.setMode(nextMode);
    }
    controller.current?.focus(next);
  }
  const ready = status === "ready";
  return (
    <div
      className={`house-viewer ${compact ? "house-thumbnail building-art" : "house-explorer"} ${embedded ? "house-embedded" : ""} ${run?.plan && !compact ? "has-energy-plan" : ""}`}
    >
      {!compact && (
        <div className="explorer-topbar">
          <div className="explorer-caption">
            <span className="status-dot" />
            <span>
              {run?.plan
                ? "YOUR BUILDING, REIMAGINED"
                : office
                  ? "THE EVERGREEN OFFICE"
                  : "THE EVERGREEN HOUSE"}
              <small>
                {run?.plan
                  ? "EXPLORE THE ENERGY UPGRADES"
                  : "AN INTERACTIVE PERSPECTIVE"}
              </small>
            </span>
          </div>
          <div className="view-switch" role="group" aria-label="Building view">
            {(
              [
                ["exterior", "Exterior", Box],
                ["cutaway", "Cutaway", ArrowDownLeft],
                ["exploded", "Exploded", Layers3],
              ] as const
            ).map(([id, label, Icon]) => (
              <button
                key={id}
                aria-pressed={mode === id}
                onClick={() => changeMode(id)}
                disabled={!ready}
              >
                <Icon size={14} />
                <span>{label}</span>
              </button>
            ))}
          </div>
        </div>
      )}
      <div
        ref={host}
        className="house-canvas"
        role="img"
        aria-label={
          compact
            ? `Architectural preview of an illustrative ${office ? "office" : "house"}`
            : `Interactive concept ${office ? "office" : "house"} in ${mode} view. Use the view, room, rotate and zoom buttons to explore.`
        }
      />
      {status === "loading" && (
        <div className="house-loading">
          <span className="loading-orbit" />
          <span>Setting the scene…</span>
        </div>
      )}
      {status === "unavailable" && (
        <div className="house-fallback">
          <Box size={40} />
          <strong>3D view unavailable</strong>
          <p>
            The 3D view is unavailable in this browser. You can still explore
            every property and energy plan below.
          </p>
        </div>
      )}
      {!compact && (
        <>
          {run?.plan && ready && (
            <EnergyOverlay
              run={run}
              controller={controller.current}
              mode={mode}
              hoverRef={energyHover}
              projectRef={energyProject}
            />
          )}
          <div className="scene-compass" aria-hidden="true">
            <span>N</span>
            <div>↗</div>
          </div>
          <div className="scene-tools" role="group" aria-label="Model controls">
            <button
              title={rotating ? "Pause rotation" : "Auto rotate"}
              aria-label={rotating ? "Pause rotation" : "Auto rotate"}
              aria-pressed={rotating}
              disabled={!ready}
              onClick={() => {
                setRotating(!rotating);
                controller.current?.setRotating(!rotating);
              }}
            >
              {rotating ? <Pause size={17} /> : <Play size={17} />}
            </button>
            <span />
            <button
              title="Zoom in"
              aria-label="Zoom in"
              disabled={!ready}
              onClick={() => controller.current?.zoom(0.8)}
            >
              <Plus size={18} />
            </button>
            <button
              title="Zoom out"
              aria-label="Zoom out"
              disabled={!ready}
              onClick={() => controller.current?.zoom(1.25)}
            >
              <Minus size={18} />
            </button>
            <span />
            <button
              title="Reset view"
              aria-label="Reset view"
              disabled={!ready}
              onClick={() => {
                setRoom(null);
                setRotating(false);
                controller.current?.setRotating(false);
                controller.current?.reset();
              }}
            >
              <RotateCcw size={16} />
            </button>
          </div>
          <div className="scene-room-panel">
            <span className="scene-label">TAKE A CLOSER LOOK</span>
            <div
              className="scene-room-buttons"
              role="group"
              aria-label="Explore rooms"
            >
              {rooms.map((item) => (
                <button
                  key={item.id}
                  disabled={!ready}
                  aria-pressed={room === item.id}
                  onClick={() => focusRoom(item.id)}
                >
                  <span>{item.icon}</span>
                  {item.name}
                  <ChevronRight size={13} />
                </button>
              ))}
            </div>
          </div>
          <div
            className={`scene-insight ${selected ? "is-selected" : ""}`}
            aria-live="polite"
          >
            <span className="insight-icon">
              {selected ? <Layers3 size={19} /> : <Sun size={20} />}
            </span>
            <span>
              <small>
                {selected
                  ? "INSIDE THE POSSIBILITIES"
                  : "A LITTLE EXPLORATION GOES A LONG WAY"}
              </small>
              <strong>{selected?.title || "See the whole picture."}</strong>
              <p>
                {selected?.detail ||
                  "Lift the roof. Look inside. Discover how every part of a building connects."}
              </p>
            </span>
          </div>
          <div className="scene-bottomline">
            <span>
              <MousePointer2 size={12} /> Drag to orbit <i /> Scroll or pinch to
              zoom
            </span>
            <small>Illustrative model · not a property scan</small>
          </div>
        </>
      )}
    </div>
  );
}
