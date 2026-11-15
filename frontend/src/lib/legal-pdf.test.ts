import { describe, expect, it } from "vitest";
import { readFileSync, writeFileSync } from "node:fs";
import type { DocumentDraft } from "./types";
import { createLegalPdf, legalText } from "./legal-pdf";

const draft: DocumentDraft = {
  doc_id: "review-draft",
  doc_type: "retrofit_contract_residential",
  state: "CA",
  disclaimer: "Draft for attorney review. Complete all missing terms before signing.",
  unfilled_placeholders: ["owner_mailing_address", "subcontractor_yes_box", "stat_cancellation_notice"],
  statutory_checks: [{ requirement: "Cancellation notice", citation: "Applicable state law", satisfied: false }],
  markdown: `# Residential Home Improvement Contract

This agreement is between Jane Homeowner and ABC Contractor. The owner's address is [[BLANK: owner_mailing_address, value required]].

<!-- fmt: 12pt bold -->
The owner must receive the required notice before signing this contract.

### Subcontractors

Will the contractor use subcontractors? {{subcontractor_yes_box}} Yes {{subcontractor_no_box}} No

| Item | Owner | Contractor |
|---|---|---|
| Name | Jane Homeowner | ABC Contractor |
| Signature | | |
| Date | [[BLANK: buyer_signature_date, value required]] | [[BLANK: contractor_signature_date, value required]] |

### Notice of Cancellation

[[BLANK: stat_cancellation_notice, insert verbatim statutory text]]

---

${"The owner and contractor should review the completed scope, schedule, price, and any notices before signing. ".repeat(26)}
`,
};

describe("legal PDF draft", () => {
  it("renders a complete multi-page PDF with readable blanks and vector checkbox squares", () => {
    expect(legalText("{{subcontractor_yes_box}} Yes [[BLANK: owner_mailing_address, value required]]"))
      .toBe("[] Yes ____________________ (Owner's mailing address)");
    expect(legalText("[[BLANK: stat_ca_right_to_cancel_notice, insert verbatim statutory text]]"))
      .toContain("California right-to-cancel notice; exact legal wording required");
    const pdf = createLegalPdf(draft);
    expect(pdf.getNumberOfPages()).toBeGreaterThan(1);
    const bytes = pdf.output("arraybuffer");
    expect(String.fromCharCode(...new Uint8Array(bytes.slice(0, 5)))).toBe("%PDF-");
    if (process.env.LEGAL_PDF_QA_OUTPUT) writeFileSync(process.env.LEGAL_PDF_QA_OUTPUT, Buffer.from(bytes));
  });
  it("renders the shared residential draft fixture without dropping its legal review section", () => {
    const fixture = JSON.parse(readFileSync(new URL("../../../specs/examples/house/document_draft.json", import.meta.url), "utf8")) as DocumentDraft;
    const pdf = createLegalPdf(fixture);
    expect(pdf.getNumberOfPages()).toBeGreaterThan(0);
    if (process.env.LEGAL_PDF_FIXTURE_OUTPUT) writeFileSync(process.env.LEGAL_PDF_FIXTURE_OUTPUT, Buffer.from(pdf.output("arraybuffer")));
  });
});
