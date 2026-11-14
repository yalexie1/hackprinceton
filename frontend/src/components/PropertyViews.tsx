import { useEffect, useRef, useState } from "react";
import { Box, MapPin, Mountain, Satellite } from "lucide-react";
import type { PropertySummary } from "../lib/types";
import type { PropertyImagery, PropertyOblique } from "../lib/property-imagery";
import {
  aerialAttribution,
  aerialImageUrl,
  propertyLocation,
  listedPropertyLocation,
} from "../lib/property-geospatial";

/**
 * Aerial / oblique / model, as a segmented control on a property card.
 *
 * **The control offers only the views that exist.** Measured through `/preview` on main: the
 * three demonstration properties have four obliques each, two of the three have a Vexcel ortho,
 * and the other seventeen have neither. A fixed three-tab strip would open an empty frame for
 * most of the list, which reads as a broken app rather than as missing data - so the tabs are
 * built from what came back, and a property with one view gets no strip at all.
 *
 * **"Aerial" is two different things and they are labelled as such.** The Vexcel orthophoto is
 * our own survey imagery; the Esri basemap tile is geospatial context around a computed point.
 * Showing both under one word would let a viewer read a basemap as evidence about the building,
 * so they are separate views with their own captions and their own attribution.
 *
 * **The model is loaded only while it is the selected view.** This renders inside a grid of
 * twenty cards; twenty Matterport iframes would autoplay twenty scenes and put the viewer key in
 * twenty frames. The iframe mounts on selection and unmounts when the viewer leaves the tab.
 */

export type ViewKind = "ortho" | "oblique" | "context" | "model";

export interface PropertyView {
  kind: ViewKind;
  label: string;
  caption: string;
  credit: string;
  url?: string;
  direction?: string;
}

const ICONS: Record<ViewKind, typeof MapPin> = {
  ortho: Satellite,
  oblique: Mountain,
  context: MapPin,
  model: Box,
};

/**
 * The views a property can actually show.
 *
 * **The map comes first, so it is the default.** It is the one view every locatable property has,
 * it is the same picture for all of them, and it loads from a tile service in one request - so the
 * grid settles immediately instead of twenty cards each waiting on their own survey crop. The
 * evidence views sit one click away: the side angle (the only one that shows a facade), then our
 * own overhead survey, then the model.
 */
export function propertyViews(
  property: PropertySummary,
  imagery: PropertyImagery,
  { allowListedLocation = false, hasModelKey = false } = {},
): PropertyView[] {
  const views: PropertyView[] = [];

  const scanLocation = propertyLocation(property.sid);
  const location =
    scanLocation ||
    (allowListedLocation ? listedPropertyLocation(property) : null);
  const context =
    location && aerialImageUrl(location, property.segment === "commercial");
  if (context)
    views.push({
      kind: "context",
      label: "Map",
      caption: `Overhead view · ${
        location!.source === "scan"
          ? "scan location"
          : location!.source === "listing"
            ? "listing location"
            : "address location"
      }`,
      credit: aerialAttribution,
      url: context,
    });

  for (const oblique of imagery.obliques)
    views.push({
      kind: "oblique",
      label: "Side angle",
      caption: `Side-angle aerial · ${oblique.direction} view`,
      credit: "Vexcel aerial imagery",
      url: oblique.url,
      direction: oblique.direction,
    });

  if (imagery.ortho)
    views.push({
      kind: "ortho",
      label: "Aerial",
      caption: "Overhead survey · Vexcel orthophoto",
      credit: "Vexcel aerial imagery",
      url: imagery.ortho,
    });

  // The model goes last, and is never the default view. Two reasons, both learned the hard way:
  // a card whose first view is an iframe loads a Matterport scene for every card in the grid,
  // which is what mounting-on-selection was supposed to avoid; and a property we cannot place
  // must not be handed a tour at all. `sid` is the Matterport model id, so an unverified sid
  // would embed `m=<unknown>` and put the viewer key in the markup for a building we have no
  // scan for. A scan-computed location is the evidence that this sid is a scan we hold.
  const scanned = Boolean(property.room_count || property.pano_count);
  if (scanned && hasModelKey && scanLocation?.source === "scan")
    views.push({
      kind: "model",
      label: "3D model",
      caption: "Interior scan · walk the space",
      credit: "Matterport scan",
    });

  return views;
}

/** One strip per card. Hidden when there is nothing to switch between. */
function ViewStrip({
  views,
  active,
  onPick,
  name,
}: {
  views: PropertyView[];
  active: number;
  onPick: (index: number) => void;
  name: string;
}) {
  if (views.length < 2) return null;
  // One button per view, deduplicated by label: four obliques are one "Side angle" tab that
  // steps through directions, not four tabs that say the same word.
  const seen = new Set<string>();
  const tabs = views.flatMap((view, index) =>
    seen.has(view.label) ? [] : (seen.add(view.label), [{ view, index }]),
  );
  if (tabs.length < 2) return null;
  return (
    <div
      className="property-view-strip"
      role="tablist"
      aria-label={`Views of ${name}`}
    >
      {tabs.map(({ view, index }) => {
        const Icon = ICONS[view.kind];
        const selected = views[active]?.label === view.label;
        return (
          <button
            key={view.label}
            type="button"
            role="tab"
            aria-selected={selected}
            className={selected ? "selected" : ""}
            onClick={(event) => {
              // The whole card is a button that opens the property; switching a view must not
              // also navigate.
              event.stopPropagation();
              event.preventDefault();
              onPick(index);
            }}
          >
            <Icon size={14} aria-hidden="true" />
            <span>{view.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export default function PropertyViews({
  property,
  imagery,
  allowListedLocation = false,
  modelKey,
}: {
  property: PropertySummary;
  imagery: PropertyImagery;
  allowListedLocation?: boolean;
  modelKey?: string;
}) {
  const views = propertyViews(property, imagery, {
    allowListedLocation,
    hasModelKey: Boolean(modelKey),
  });
  const [index, setIndex] = useState(0);
  // The imagery arrives after the first render, so the list grows under us; clamp rather than
  // leave a stale index pointing past the end.
  useEffect(() => {
    setIndex((current) => (current < views.length ? current : 0));
  }, [views.length]);

  const view = views[index];
  const obliques = views.filter((v) => v.kind === "oblique");
  const failed = useRef(new Set<string>());
  // Reset when the viewer leaves the tab: the frame unmounts, so the next visit boots again.
  const [modelReady, setModelReady] = useState(false);
  useEffect(() => {
    if (view?.kind !== "model") setModelReady(false);
  }, [view?.kind]);

  if (!view)
    return (
      <div className="property-geospatial">
        <div className="property-map-unavailable">
          <MapPin size={27} />
          <strong>Location not verified yet</strong>
          <span>
            {[property.address, property.city, property.state]
              .filter(Boolean)
              .join(", ") || property.name}
          </span>
        </div>
      </div>
    );

  return (
    <div
      className={`property-geospatial${view.kind === "oblique" ? " has-oblique" : ""}`}
    >
      {view.kind === "model" ? (
        <>
          {/* Showcase boots its own bundle, model metadata and first panorama after the document
              loads, which is seconds on a cold profile - and because the frame only exists once
              the tab is chosen, the viewer pays all of it at click time. An empty dark frame for
              several seconds reads as broken, so say what is happening until it paints.
              `loading="lazy"` was previously on this iframe and was actively harmful: the
              element is created only when selected, so there is nothing to defer, and the
              attribute just delayed the request behind the browser's lazy-load bookkeeping. */}
          {!modelReady && (
            <div className="property-model-loading">
              <Box size={22} aria-hidden="true" />
              <span>Loading the interior scan…</span>
            </div>
          )}
          <iframe
            className="property-model-frame"
            title={`Interior scan of ${property.name}`}
            allow="fullscreen; xr-spatial-tracking"
            referrerPolicy="no-referrer"
            onLoad={() => setModelReady(true)}
            src={`https://my.matterport.com/show?${new URLSearchParams({
              m: property.sid,
              play: "0",
              title: "0",
              ...(modelKey ? { applicationKey: modelKey } : {}),
            })}`}
          />
        </>
      ) : (
        <img
          key={view.url}
          src={view.url}
          alt={
            view.kind === "oblique"
              ? `Side-angle aerial photo of ${property.name}, ${view.direction} view`
              : view.kind === "ortho"
                ? `Overhead orthophoto of ${property.name}`
                : `Overhead aerial context for ${property.name}`
          }
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => {
            // Step to the next view of the same kind before leaving the kind entirely, so one
            // missing crop does not drop the viewer from a facade to a basemap.
            if (view.url) failed.current.add(view.url);
            const next =
              views.findIndex(
                (candidate, at) =>
                  at > index &&
                  candidate.kind === view.kind &&
                  candidate.url &&
                  !failed.current.has(candidate.url),
              ) ??
              -1;
            setIndex(
              next >= 0
                ? next
                : Math.min(index + 1, Math.max(views.length - 1, 0)),
            );
          }}
        />
      )}

      {view.kind === "context" && (
        <>
          <span className="property-location-pin">
            <MapPin size={22} />
          </span>
          <span className="property-map-north">N ↑</span>
        </>
      )}
      {view.kind === "ortho" && <span className="property-map-north">N ↑</span>}

      <ViewStrip
        views={views}
        active={index}
        onPick={setIndex}
        name={property.name}
      />

      <div className="property-map-footer">
        <span className="property-map-caption">
          {view.caption}
          {view.kind === "oblique" && obliques.length > 1 && (
            <button
              type="button"
              className="property-view-next"
              onClick={(event) => {
                event.stopPropagation();
                event.preventDefault();
                const at = obliques.indexOf(view);
                const next = obliques[(at + 1) % obliques.length];
                setIndex(views.indexOf(next));
              }}
            >
              Next direction
            </button>
          )}
        </span>
        <span className="property-map-credit">{view.credit}</span>
      </div>
    </div>
  );
}
