import { jsPDF } from "jspdf";
import type { DocumentDraft } from "./types";

const margin = 19;
const pageWidth = 215.9;
const contentWidth = pageWidth - 2 * margin;
const bottom = 254;
const ink: [number, number, number] = [29, 42, 39];
const muted: [number, number, number] = [83, 98, 92];

const blankLabels: Record<string, string> = {
  owner_mailing_address: "Owner's mailing address",
  buyer_signature_date: "Date the owner signs",
  contractor_business_address: "Contractor's business address",
  contractor_cancellation_email: "Contractor's cancellation email address",
  contractor_phone: "Contractor's telephone number",
  contractor_license_number: "Contractor's California license number",
  contract_price_usd: "Total contract price in dollars and cents",
  progress_payment_table: "Progress payment schedule",
  payment_due_days: "Number of days allowed for payment",
  start_date: "Approximate start date",
  completion_date: "Approximate completion date",
  workmanship_warranty_years: "Length of the workmanship warranty in years",
  incentive_paperwork_choice: "Party responsible for incentive paperwork",
  work_hours: "Permitted work hours",
  contractor_signatory_name: "Name of the person signing for the contractor",
  contractor_signatory_title: "Title of the person signing for the contractor",
  contractor_signature_date: "Date the contractor signs",
  cancel_title: "Title of the applicable cancellation notice",
  schedule_a_rows: "Description of each improvement, its materials, and its completion test",
  schedule_c_table: "Estimated costs and savings for each improvement",
  stat_ca_entitled_to_copy: "California notice about receiving a completed copy of the contract",
  stat_ca_downpayment_cap: "California down-payment notice",
  stat_ca_progress_payment_notice: "California progress-payment notice",
  stat_ca_change_order_note: "California change-order notice",
  stat_ca_cgl_statement: "California commercial general liability insurance statement",
  stat_ca_workers_comp_statement: "California workers' compensation insurance statement",
  stat_ca_mechanics_lien_warning: "California mechanics lien warning",
  stat_ca_cslb_notice: "California Contractors State License Board notice",
  stat_ca_right_to_cancel_notice: "California right-to-cancel notice",
  stat_ca_notice_of_cancellation_form: "California Notice of Cancellation form",
};

function blankLabel(key: string): string {
  const clean = key.trim();
  if (blankLabels[clean]) return blankLabels[clean];
  const words = clean.replace(/^stat_ca_/, "California ").replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function blankText(key: string): string {
  const label = blankLabel(key);
  return `____________________ (${label}${key.trim().startsWith("stat_ca_") ? "; exact legal wording required" : ""})`;
}

function plain(value: string): string {
  return value.normalize("NFKD")
    .replace(/[\u2010-\u2015\u2212]/g, "-")
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201c\u201d]/g, '"')
    .replace(/\u2264/g, "no more than")
    .replace(/\u2265/g, "at least")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1 ($2)")
    .replace(/\*\*/g, "")
    .replace(/`/g, "")
    .replace(/<[^>]+>/g, "")
    .replace(/[^\x20-\x7E\xA7\n]/g, "");
}

export function legalText(value: string): string {
  return plain(value
    .replace(/\[\[BLANK:\s*([^\]]+)\]\]/g, (_match, detail: string) =>
      detail.split(",")[0].trim().endsWith("_box") ? "[]" : blankText(detail.split(",")[0]),
    )
    .replace(/\{\{([^}]+)\}\}/g, (_match, key: string) =>
      key.trim().endsWith("_box") ? "[]" : blankText(key),
    )
    .replace(/\[(?: |x|X)\]/g, "[]"));
}

function finishedText(value: string): string {
  return value
    .replace(/\*\[Unverified: which energy-code verifications apply to each measure, see section 8\.\]\*/gi, "")
    .replace(/\*\*First-page block\*\* \(B&P §7159\(c\)\(3\)\(B\); Civ\. Code §1689\.7\(b\); type no smaller than the body\)/gi, "**Contract information**")
    .replace(/One row per measure\. Columns: improvement, location in the home, work to be done, significant materials and equipment, completion test\./gi, "Each improvement is described below by location, work, significant materials and equipment, and the test for completion.")
    .replace(/Same table as 4\.6\./gi, "The progress payment stages appear in Section 4.6.")
    .replace(/Generated from `Plan`\./gi, "This schedule summarizes the energy analysis prepared for the Property.")
    .replace(/\*\*Notice of Cancellation\*\* \(attached in duplicate, easily detachable; B&P §7159\(e\)\(6\)\. Civ\. Code §1689\.7\(c\) does not apply: it excludes §7151\.2 contracts\)/gi, "**Notice of Cancellation** (two detachable copies must be attached before signing)")
    .replace(/licence classification\(s\)\s*,/gi, "licence classification(s) ____________________ (Contractor's license classification),");
}

function reviewText(value: string): string {
  return value
    .replace(/`/g, "")
    .replace(/Every stat_ placeholder filled from the verbatim statute file/gi, "Each required California notice contains the exact statutory wording")
    .replace(/a statutory text is still a blank/gi, "Required statutory wording remains to be inserted")
    .replace(/software cannot verify/gi, "Verification is required before signing")
    .replace(/software cannot confirm/gi, "This duty must be confirmed at signing")
    .replace(/first-page block missing or has blanks/gi, "First-page information remains incomplete")
    .replace(/type size enforced only in export/gi, "The required type size is applied in this PDF")
    .replace(/applies only when financing_contingent = yes; the draft does not record it/gi, "Confirm whether the agreement depends on financing before signing")
    .replace(/\bCA-(?:R|HIC|FIN|PAY|LIC|ARB|CXL)-\d+[a-z]?\s*:\s*/gi, "")
    .replace(/\b[a-z]+(?:_[a-z0-9]+)+\b/g, (key) => blankLabel(key));
}

type Block = { kind: "heading" | "paragraph" | "list" | "quote" | "rule" | "table"; text: string; level?: number; rows?: string[][]; format?: string };

function blocks(markdown: string): Block[] {
  const result: Block[] = [];
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  let paragraph: string[] = [];
  let format = "";
  function flush() {
    if (paragraph.length) {
      result.push({ kind: "paragraph", text: paragraph.join(" "), format });
      paragraph = [];
      format = "";
    }
  }
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) { flush(); continue; }
    if (/^[-*+]$/.test(line)) { flush(); continue; }
    if (/^<!--/.test(line)) {
      flush();
      const match = line.match(/fmt:\s*(.*?)\s*-->/i);
      if (match) format = match[1];
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flush();
      result.push({ kind: "heading", level: heading[1].length, text: heading[2], format });
      format = "";
      continue;
    }
    if (/^[-*_]{3,}$/.test(line)) { flush(); result.push({ kind: "rule", text: "" }); continue; }
    if (line.startsWith("|")) {
      flush();
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        const cells = lines[i].trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
        if (!cells.every((cell) => /^:?-{3,}:?$/.test(cell))) rows.push(cells);
        i++;
      }
      i--;
      result.push({ kind: "table", text: "", rows, format });
      format = "";
      continue;
    }
    if (/^(?:[-*+]\s+|\d+\.\s+)/.test(line)) {
      flush();
      result.push({ kind: "list", text: line.replace(/^[-*+]\s+/, "- "), format });
      format = "";
      continue;
    }
    if (line.startsWith(">")) {
      flush(); result.push({ kind: "quote", text: line.replace(/^>\s?/, ""), format }); format = "";
      continue;
    }
    paragraph.push(line);
  }
  flush();
  return result;
}

export function createLegalPdf(draft: DocumentDraft): jsPDF {
  const pdf = new jsPDF({ unit: "mm", format: "letter", compress: true });
  let y = 25;
  function page() {
    pdf.addPage();
    y = 25;
  }
  function ensure(height: number) { if (y + height > bottom) page(); }
  function style(size: number, bold = false, color = ink) {
    pdf.setFont("times", bold ? "bold" : "normal");
    pdf.setFontSize(size);
    pdf.setTextColor(...color);
  }
  function drawLine(line: string, x: number, baseline: number, size: number) {
    let cursor = x;
    for (const [index, part] of line.split("[]").entries()) {
      if (index) {
        pdf.setDrawColor(...ink);
        pdf.setLineWidth(0.3);
        pdf.rect(cursor + 0.35, baseline - 2.9, 3.2, 3.2);
        cursor += 4.5;
      }
      if (part) { pdf.text(part, cursor, baseline); cursor += pdf.getTextWidth(part); }
    }
    return cursor;
  }
  function write(value: string, options: { size?: number; bold?: boolean; indent?: number; after?: number; color?: [number, number, number]; keep?: number; } = {}) {
    const size = options.size ?? 10.5;
    const indent = options.indent ?? 0;
    const lineHeight = size * 0.45;
    style(size, options.bold, options.color);
    const lines = pdf.splitTextToSize(legalText(value), contentWidth - indent) as string[];
    ensure(Math.max(options.keep ?? 0, Math.min(lines.length, 2) * lineHeight + (options.after ?? 2.8)));
    for (const line of lines) {
      ensure(lineHeight);
      drawLine(line, margin + indent, y, size);
      y += lineHeight;
    }
    y += options.after ?? 2.8;
  }

  // The legal team's disclaimer is part of the draft, not a footnote.
  const disclaimerText = plain(draft.disclaimer);
  style(10.5, true, [85, 48, 29]);
  const disclaimerLines = pdf.splitTextToSize(disclaimerText, contentWidth - 8) as string[];
  const disclaimerHeight = Math.max(17, disclaimerLines.length * 5 + 8);
  pdf.setFillColor(252, 244, 230);
  pdf.setDrawColor(180, 140, 93);
  pdf.rect(margin, y - 5, contentWidth, disclaimerHeight, "FD");
  disclaimerLines.forEach((line, index) => pdf.text(line, margin + 4, y + index * 5));
  y += disclaimerHeight + 5;

  // Remove only drafting annotations from the export; substantive clauses remain authored by legal.
  for (const block of blocks(draft.markdown)) {
    const text = finishedText(block.text);
    if (block.kind === "quote" && legalText(text) === disclaimerText) continue;
    if (block.kind === "rule") {
      ensure(8); pdf.setDrawColor(184, 193, 188); pdf.line(margin, y + 2, pageWidth - margin, y + 2); y += 8;
    } else if (block.kind === "heading") {
      const level = block.level ?? 3;
      const size = level === 1 ? 15 : level === 2 ? 12.5 : 11.5;
      y += level <= 2 ? 4 : 2;
      write(text, { size, bold: true, after: 3.5, keep: 38 });
      if (level <= 2) { pdf.setDrawColor(177, 193, 183); pdf.line(margin, y - 1, pageWidth - margin, y - 1); y += 2; }
    } else if (block.kind === "paragraph" || block.kind === "quote") {
      const isNotice = /bold|boxed/i.test(block.format ?? "");
      const size = /12pt/i.test(block.format ?? "") ? 12 : 10.5;
      const start = y;
      const boldLead = text.match(/^\*\*([^*]+)\*\*(?:\s+|$)(.*)$/s);
      if (boldLead && !isNotice) {
        if (boldLead[2]) ensure(29);
        write(boldLead[1], { size, bold: true, indent: block.kind === "quote" ? 5 : 0, after: boldLead[2] ? 1.2 : 3.2, keep: 12 });
        if (boldLead[2]) write(boldLead[2], { size, indent: block.kind === "quote" ? 5 : 0, after: 3.2 });
      } else {
        write(text, { size, bold: isNotice, indent: block.kind === "quote" ? 5 : 0, after: 3.2 });
      }
      if (/boxed/i.test(block.format ?? "") && start >= 25 && y < bottom) {
        pdf.setDrawColor(83, 98, 92); pdf.rect(margin - 2, start - 4, contentWidth + 4, y - start + 5);
      }
    } else if (block.kind === "list") {
      write(text, { indent: 5, after: 1.8 });
    } else if (block.kind === "table" && block.rows?.length) {
      const rows = block.rows;
      const columns = Math.max(...rows.map((row) => row.length));
      const firstWidth = columns === 2 ? contentWidth * 0.36 : contentWidth / columns;
      const widths = Array.from({ length: columns }, (_, index) => columns === 2 ? (index === 0 ? firstWidth : contentWidth - firstWidth) : contentWidth / columns);
      for (let rowIndex = 0; rowIndex < rows.length; rowIndex++) {
        style(9.5, rowIndex === 0);
        const wrapped = widths.map((width, column) => pdf.splitTextToSize(legalText(rows[rowIndex][column] ?? ""), width - 5) as string[]);
        const height = Math.max(9, Math.max(...wrapped.map((cell) => cell.length)) * 4.3 + 4);
        ensure(height);
        let x = margin;
        for (let column = 0; column < columns; column++) {
          if (rowIndex === 0) pdf.setFillColor(234, 239, 235);
          else pdf.setFillColor(255, 255, 255);
          pdf.setDrawColor(183, 194, 186);
          pdf.rect(x, y, widths[column], height, "FD");
          style(9.5, rowIndex === 0);
          wrapped[column].forEach((line, lineIndex) => drawLine(line, x + 2.5, y + 5 + lineIndex * 4.3, 9.5));
          if (/^signature$/i.test(rows[rowIndex][0] ?? "") && column > 0) {
            pdf.setDrawColor(...ink); pdf.line(x + 3, y + height - 2.5, x + widths[column] - 3, y + height - 2.5);
          }
          x += widths[column];
        }
        y += height;
      }
      y += 5;
    }
  }

  page();
  write("ATTORNEY REVIEW SCHEDULE", { size: 14, bold: true, after: 3, keep: 26 });
  write("This schedule is for review and completion before the agreement is signed. It does not form part of the agreement.", { size: 10.5, after: 6 });
  if (draft.unfilled_placeholders.length) {
    write("Terms and notices to complete", { size: 12.5, bold: true, keep: 20 });
    for (const key of [...new Set(draft.unfilled_placeholders)].filter((key) => !key.endsWith("_box"))) {
      write(`${blankLabel(key)}: ____________________${key.startsWith("stat_ca_") ? " (exact legal wording must be inserted)" : ""}`, { size: 10, after: 1.5 });
    }
  }
  y += 4;
  write("Legal requirements for counsel to review", { size: 12.5, bold: true, keep: 20 });
  if (!draft.statutory_checks.length) {
    write("Statutory requirements have not been checked for this draft.", { size: 10.5 });
  }
  const reviewItems = new Map<string, { satisfied: boolean; title: string; citations: Set<string>; notes: Set<string> }>();
  for (const check of draft.statutory_checks) {
    const title = reviewText(check.requirement);
    const key = `${check.satisfied}:${title}`;
    const item = reviewItems.get(key) ?? { satisfied: check.satisfied, title, citations: new Set<string>(), notes: new Set<string>() };
    const citation = reviewText(check.citation);
    if (citation && !/^this file\b/i.test(citation)) item.citations.add(citation);
    if (check.note) item.notes.add(reviewText(check.note));
    reviewItems.set(key, item);
  }
  for (const item of reviewItems.values()) {
    const title = `${item.satisfied ? "Present in draft" : "To be completed"} - ${item.title}`;
    const explanation = [...item.citations, ...item.notes].join("; ");
    style(10.5, true);
    const titleHeight = (pdf.splitTextToSize(legalText(title), contentWidth) as string[]).length * 10.5 * 0.45;
    style(10);
    const explanationHeight = (pdf.splitTextToSize(legalText(explanation), contentWidth - 5) as string[]).length * 10 * 0.45;
    ensure(titleHeight + explanationHeight + 3);
    write(title, { size: 10.5, bold: true, color: item.satisfied ? [35, 89, 58] : [124, 69, 29], after: 0.8 });
    if (explanation) write(explanation, { size: 10, color: muted, indent: 5, after: 2 });
  }

  const pages = pdf.getNumberOfPages();
  for (let number = 1; number <= pages; number++) {
    pdf.setPage(number);
    pdf.setDrawColor(177, 193, 183);
    pdf.line(margin, 18, pageWidth - margin, 18);
    pdf.line(margin, 263, pageWidth - margin, 263);
    style(8.5, true, muted); pdf.text("LETO  |  LEGAL DOCUMENT DRAFT", margin, 14);
    style(8.5, false, muted); pdf.text("Review and complete before signing", margin, 269);
    pdf.text(`${number} / ${pages}`, pageWidth - margin, 269, { align: "right" });
  }
  return pdf;
}

export function exportLegalPdf(draft: DocumentDraft): void {
  const name = `${draft.doc_type}-${draft.state}`.toLowerCase().replace(/[^a-z0-9-]+/g, "-");
  createLegalPdf(draft).save(`${name}-draft.pdf`);
}
