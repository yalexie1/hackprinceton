import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import WorkspaceNavigation, { views } from "./WorkspaceNavigation";

const base = {
  view: "find" as const,
  complete: false,
  hasRun: false,
  busy: false,
  needsInput: false,
  onNavigate: () => {},
};

describe("workspace navigation availability", () => {
  it("offers only usable public destinations before analysis", () => {
    const html = renderToStaticMarkup(<WorkspaceNavigation {...base} />);
    expect(html).toContain('aria-label="Main navigation"');
    for (const label of ["Properties", "Solar map", "Accuracy &amp; evidence", "How it works"])
      expect(html).toContain(label);
    expect(html).not.toContain('aria-label="Property analysis"');
    expect(html).not.toContain("Energy plan");
    expect(html).not.toContain("disabled");
    expect(html).not.toContain("sidebar");
  });

  it("keeps a running or disconnected audit reachable without exposing results", () => {
    for (const busy of [true, false]) {
      const html = renderToStaticMarkup(<WorkspaceNavigation {...base} hasRun busy={busy} />);
      expect(html).toContain(busy ? "Return to your audit" : "Reconnect to your audit");
      expect(html).not.toContain('aria-label="Property analysis"');
    }
    expect(renderToStaticMarkup(<WorkspaceNavigation {...base} hasRun needsInput />))
      .toContain("Your input is needed");
  });

  it("reveals all result destinations after completion and identifies the current one", () => {
    const html = renderToStaticMarkup(
      <WorkspaceNavigation {...base} complete hasRun view="roof" propertyName="A finished property" />,
    );
    expect(html).toContain('aria-label="Property analysis"');
    for (const label of ["Energy plan", "Solar &amp; roof", "Assumptions", "Documents", "Audit trail", "A finished property"])
      expect(html).toContain(label);
    expect(html).not.toContain(">Workspace</button>");
    expect(html.indexOf("Audit trail")).toBeLessThan(html.indexOf("Energy plan"));
    expect((html.match(/aria-current="page"/g) || []).length).toBe(1);
    expect(html).not.toContain("disabled");
  });
});

describe("retired desk layout", () => {
  it("has no Workspace destination", () => {
    expect(views.map((v) => v.label)).not.toContain("Workspace");
  });
});
