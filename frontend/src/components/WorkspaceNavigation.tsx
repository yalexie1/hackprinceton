import type { ReactNode } from "react";
import { BookOpen, CheckCircle2, ClipboardList, FileText, Home, Layers3, LoaderCircle, MapPin, Settings2, Sun } from "lucide-react";
import "./workspace-navigation.css";

export type View = "find" | "setup" | "audit" | "plan" | "roof" | "layout" | "assumptions" | "documents" | "how" | "evals" | "solar-map";
export const publicViews: ReadonlySet<View> = new Set(["find", "how", "evals", "solar-map"]);
export const views: { id: View; label: string; icon: typeof Home }[] = [
  { id: "find", label: "Properties", icon: Home },
  { id: "plan", label: "Energy plan", icon: ClipboardList },
  { id: "roof", label: "Solar & roof", icon: Sun },
  { id: "layout", label: "Workspace", icon: Layers3 },
  { id: "assumptions", label: "Assumptions", icon: Settings2 },
  { id: "documents", label: "Documents", icon: FileText },
  { id: "solar-map", label: "Solar map", icon: MapPin },
  { id: "evals", label: "Accuracy & evidence", icon: CheckCircle2 },
  { id: "how", label: "How it works", icon: BookOpen },
];

export default function WorkspaceNavigation({
  view, complete, hasRun, busy, needsInput, propertyName, onNavigate, children,
}: {
  view: View;
  complete: boolean;
  hasRun: boolean;
  busy: boolean;
  needsInput: boolean;
  propertyName?: string;
  onNavigate: (view: View) => void;
  children?: ReactNode;
}) {
  function link(item: typeof views[number]) {
    return (
      <button
        key={item.id}
        className="workspace-link"
        aria-current={view === item.id ? "page" : undefined}
        onClick={() => onNavigate(item.id)}
      >
        <item.icon size={18} aria-hidden="true" />
        {item.label}
      </button>
    );
  }
  return (
    <header className="workspace-header">
      <div className="workspace-topbar">
        <a className="workspace-brand" href="#" onClick={(event) => {
          event.preventDefault();
          onNavigate("find");
        }}>
          <img src="/leto-logo.png" alt="Leto — properties" />
        </a>
        <nav className="workspace-public-links" aria-label="Main navigation">
          {views.filter((item) => publicViews.has(item.id)).map(link)}
        </nav>
        <div className="workspace-connection">{children}</div>
      </div>
      {complete ? (
        <div className="property-navigation">
          <div className="property-navigation-context">
            <span>Your audit</span>
            <strong>{propertyName}</strong>
          </div>
          <nav className="property-navigation-links" aria-label="Property analysis">
            {link({ id: "audit", label: "Audit trail", icon: CheckCircle2 })}
            {views.filter((item) => !publicViews.has(item.id)).map(link)}
          </nav>
        </div>
      ) : hasRun ? (
        <div className="workspace-audit-status">
          <span>{propertyName}</span>
          <button className="workspace-link" aria-current={view === "audit" ? "page" : undefined} onClick={() => onNavigate("audit")}>
            {busy ? <LoaderCircle className="spin" size={18} aria-hidden="true" /> : <ClipboardList size={18} aria-hidden="true" />}
            {needsInput ? "Your input is needed" : busy ? "Return to your audit" : "Reconnect to your audit"}
          </button>
        </div>
      ) : null}
    </header>
  );
}
