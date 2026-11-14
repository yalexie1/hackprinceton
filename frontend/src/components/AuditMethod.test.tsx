import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import AuditMethodChoice from "./AuditMethod";

describe("audit method choice", () => {
  it("labels computed live-data analysis explicitly and explains its requirements", () => {
    const html = renderToStaticMarkup(
      <AuditMethodChoice value="analysis" onChange={() => {}} />,
    );
    expect(html).toContain('value="analysis" selected=""');
    expect(html).toContain("Calculate a new plan");
    expect(html).toContain("property’s records must be available");
    expect(html).not.toContain("10 s");
    expect(html).toContain('aria-describedby="audit-method-detail"');
  });
  it("keeps server-default delivery honest when it can be either replay or an agent", () => {
    const html = renderToStaticMarkup(
      <AuditMethodChoice value="server" onChange={() => {}} />,
    );
    expect(html).toContain('value="server" selected=""');
    expect(html).toContain("Use the saved property audit");
    expect(html).toContain("Example results are never used");
  });
});
