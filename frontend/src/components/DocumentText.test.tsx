import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import DocumentText from "./DocumentText";

describe("real legal document presentation", () => {
  it("renders legal tables and headings, hides internal comments and preserves visible missing terms", () => {
    const html = renderToStaticMarkup(
      <DocumentText
        text={
          "<!-- internal template marker -->\n\n# Contract\n\n### Parties\n\n| Party | Value |\n| --- | --- |\n| Owner | **Example Owner** |\n| Licence | [[BLANK: licence, value required]] |\n\nLegacy term: {{start_date}}\n\n- Confirm scope"
        }
      />,
    );
    expect(html).toContain("<h3>Contract</h3>");
    expect(html).toContain("<h4>Parties</h4>");
    expect(html).toContain("<table>");
    expect(html).toContain("<strong>Example Owner</strong>");
    expect(html).toContain("<mark>licence — needs confirmation</mark>");
    expect(html).toContain("<mark>start date — needs confirmation</mark>");
    expect(html).not.toContain("[[BLANK:");
    expect(html).not.toContain("{{start_date}}");
    expect(html).toContain("<li>Confirm scope</li>");
    expect(html).not.toContain("internal template marker");
  });
  it("does not execute HTML, load external images or allow script links", () => {
    const html = renderToStaticMarkup(
      <DocumentText
        text={
          '<script>alert(1)</script>\n\n<img src="https://example.com/tracker.png" onerror="alert(1)">\n\n![external](https://example.com/another.png)\n\n[unsafe](javascript:alert(1))\n\nLegal text remains.'
        }
      />,
    );
    expect(html).not.toContain("<script");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("javascript:");
    expect(html).not.toContain("onerror");
    expect(html).toContain("Legal text remains.");
  });
  it("shows an actual checkbox symbol instead of a checkbox field name", () => {
    const html = renderToStaticMarkup(
      <DocumentText text="Subcontractors: {{subcontractor_yes_box}} Yes {{subcontractor_no_box}} No" />,
    );
    expect(html).toContain("<span>☐</span> Yes");
    expect(html).toContain("<span>☐</span> No");
    expect(html).not.toContain("subcontractor yes box");
  });
});
